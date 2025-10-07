import os
import json
import shutil
import numpy as np
import pandas as pd
import xarray as xr
import multiprocessing as mp
from tqdm import tqdm
# from Tool.StatusManager import StatusManager
from utils import (
    load_config, get_station_files, get_grid_files, get_vars_mapping, get_id_to_name_mapping,
    cst_to_utc, merge_df, merge_all_s, merge_all_sg, import_csv_to_sqlite
)


class DataProcessor:
    """数据处理器"""
    def __init__(self, config):
        self.config = config
        self.status_manager = StatusManager(self.config['status_dir'])
        self.processing_cache = set()  # 简单的内存缓存，避免重复标记processing状态
        self.var_mapping = get_vars_mapping()
        self.id_to_name_mapping = get_id_to_name_mapping(self.config["station_info_file"])
    
    def _process_vars(self, vars_name):
        """处理多个要素"""
        for var_name in vars_name:
            self._process_single_var(var_name)

    def _process_single_var(self, var_name):
        """处理单个要素"""
        for year in range(self.config["start_year"], self.config["end_year"] + 1):
            self._process_single_var_single_year(var_name, year)
    
    def _process_single_var_single_year(self, var_name, year):
        """处理单个要素单个年份"""
        try:
            var_grid, var_station = self.var_mapping[var_name]
            # step1: 提取所有站点的年度数据
            station_temp_dir = os.path.join(self.config["station_temp_dir"], var_name, str(year))
            os.makedirs(station_temp_dir, exist_ok=True)
            station_files = get_station_files(self.config["station_input_dir"])
            station_coords = {}
            for station_file in tqdm(station_files, desc=f"({year}, {var_name}) 提取站点年度数据"):
                station_id, station_name, lat, lon = self._extract_station_data_year(station_file, var_name, year, station_temp_dir)
                if station_id is not None:
                    station_coords[station_id] = {"station_name": station_name, "lat": lat, "lon": lon}
            
            # step2: 根据82个站点的坐标提取格点值
            grid_files = get_grid_files(self.config["grid_input_dir"], var_grid, year)
            if not grid_files:
                print(f"({var_name}, {year}年) 没有格点数据")
                return
            print(f"({var_name}, {year}年) 格点数据文件数量: {len(grid_files)}, 正在合并所有数据并打开...")
            
            # 打开多个netCDF文件, 处理坐标非单调问题
            try:
                ds = xr.open_mfdataset(grid_files, combine="by_coords")
                print(f"({var_name}, {year}年) 使用by_coords方法成功打开格点数据")
            except ValueError as e:
                error_msg = str(e).lower()
                if ("non-monotonic" in error_msg or "not monotonic" in error_msg or 
                    "global indexes" in error_msg and "lat" in error_msg):
                    print(f"({var_name}, {year}年) 检测到纬度全局索引不单调问题: {e}")
                    print(f"({var_name}, {year}年) 使用备选合并方案(以第一个文件坐标为基准)...")
                    from Tool.Utils import safe_open_mfdataset
                    ds = safe_open_mfdataset(grid_files)
                    print(f"({var_name}, {year}年) 备选合并方案成功打开格点数据")
                else:
                    print(f"({var_name}, {year}年) 打开格点数据时发生其他错误: {e}")
                    raise
            
            grid_values_df = self._extract_grid_values(ds, var_grid, station_coords, year)
            ds.close()

            # step3: 合并站点数据和格点数据并按照要素/年份/站号.csv保存
            out_dir = os.path.join(self.config["output_dir"], var_name, str(year))
            os.makedirs(out_dir, exist_ok=True)
            for station_id, group_data in tqdm(grid_values_df.groupby("station_id"), desc=f"({year}, {var_name}) 合并|保存配对后的数据"):
                # 读取对应的站点数据
                station_file = os.path.join(station_temp_dir, f"{station_id}.csv")
                if os.path.exists(station_file):
                    station_df = pd.read_csv(station_file)
                    # 使用merge_df合并数据
                    try:
                        merged_df, station_range, grid_range = merge_df(station_df, group_data)
                    except Exception as e:
                        print(f"合并数据时出错: {e}")
                        self.status_manager.mark_failed(station_id, station_coords[station_id]["station_name"], type(e).__name__, str(e), year, var_name)
                    
                    merged_df.drop(columns=["station_id"], inplace=True)
                    out_path = os.path.join(out_dir, f"{station_id}.csv")
                    merged_df.to_csv(out_path, index=False)

                    # 标记成功状态
                    station_stats = station_df[var_station].describe().to_dict()
                    grid_stats = group_data[var_grid].describe().to_dict()
                    self.status_manager.mark_success(
                        station_id, station_name, out_path, station_stats, 
                        grid_stats, year, var_name, (station_range, grid_range)
                    )
                else:
                    print(f"警告: 站点 {station_id} 的数据文件不存在")
                    self.status_manager.mark_failed(station_id, station_name, "FileNotFoundError", "站点数据文件不存在", year, var_name)

            # 清理缓存
            try:
                shutil.rmtree(station_temp_dir)
            except Exception as e:
                print(f"清理缓存目录{station_temp_dir}时出错: {e}")

            print(f"({year}, {var_name}) 处理完成")
            
        except Exception as e:
            print(f"处理({year}, {var_name})时出错: {e}")
            # 标记所有站点的失败状态
            station_files = get_station_files(self.config["station_input_dir"])
            for station_file in station_files:
                station_id = os.path.basename(station_file).split(".")[0]
                station_name = self.id_to_name_mapping[station_id] if station_id in self.id_to_name_mapping else "未知"
                self.status_manager.mark_failed(station_id, station_name, type(e).__name__, str(e), year, var_name)

    def _extract_station_data_year(self, station_file, var_name, year, station_temp_dir):
        """提取站点年度数据+数据清洗"""
        _, var_station = self.var_mapping[var_name]
        station_id = os.path.basename(station_file).split(".")[0]
        
        # 开始处理状态
        station_name = self.id_to_name_mapping[station_id] if station_id in self.id_to_name_mapping else "未知"
        
        # 使用缓存避免重复标记processing状态
        cache_key = f"{station_id}_{year}_{var_name}"
        if cache_key not in self.processing_cache:
            self.status_manager.start_processing(station_id, station_name, year, var_name)
            self.processing_cache.add(cache_key)
        
        df = pd.read_csv(station_file)
        
        df["年"] = df["年"].astype(str)
        df_year = df[df["年"] == str(year)]
        
        if df_year.empty:
            print(f"({year}, {var_station}) 站点 {station_id} 没有数据")
            self.status_manager.mark_failed(station_id, station_name, "NoData", f"站点 {station_id} 在 {year} 年没有数据", year, var_name)
            return None, None, None, None
        
        # 数据清洗
        df_year_cleaned = self._clean_station_data(df_year, var_station)
        
        lat, lon = df_year_cleaned["纬度"].iloc[0], df_year_cleaned["经度"].iloc[0]
        station_name = df_year_cleaned["站名"].iloc[0] if "站名" in df_year_cleaned.columns else "未知"

        # 只保留基础列以及当前要素列
        base_cols = ["区站号(数字)", "站名", "纬度", "经度", "年", "月", "日", "时"]
        need_cols = [col for col in base_cols if col in df_year_cleaned.columns] + [var_station]
        df_year_filtered = df_year_cleaned[need_cols]

        # 将年月日时四列合并为时间列
        time_col = df_year_filtered["年"].astype(str).str.zfill(4) + \
                df_year_filtered["月"].astype(str).str.zfill(2) + \
                df_year_filtered["日"].astype(str).str.zfill(2) + \
                df_year_filtered["时"].astype(str).str.zfill(2)
        df_year_filtered = df_year_filtered.drop(columns=["年", "月", "日", "时"])
        df_year_filtered.insert(4, "时间", time_col)

        # 保存到临时目录
        out_path = os.path.join(station_temp_dir, f"{station_id}.csv")
        df_year_filtered.to_csv(out_path, index=False)

        return station_id, station_name, lat, lon

    def _extract_grid_values(self, ds, var_grid, station_coords, year):
        """提取所有站点的格点值"""
        print(f"|-->({year}, {var_grid}) 正在提取所有站点的格点值...")
        lats = [info["lat"] for info in station_coords.values()]
        lons = [info["lon"] for info in station_coords.values()]
        station_ids = list(station_coords.keys())

        sel_data = ds[var_grid].sel(
            lat=xr.DataArray(lats, dims="station"), 
            lon=xr.DataArray(lons, dims="station"), 
            method="nearest"
        )

        df = sel_data.to_dataframe().reset_index()
        # 添加站点ID映射
        df["station_id"] = df["station"].apply(lambda x: station_ids[x])
        df.drop(columns=["station", "lat", "lon"], inplace=True)

        # 北京时转换为世界时
        if self.config.get("cst_years") and year in self.config["cst_years"]:
            df["time"] = cst_to_utc(df["time"])

        return df

    def _clean_station_data(self, df, var_station):
        """清洗站点数据"""
        df_cleaned = df.copy()
        # 将异常值转换为NaN
        df_cleaned.loc[df_cleaned[var_station] > 9999, var_station] = np.nan
        # 处理缺失值: 三次样条插值/线性插值/直接删除
        if df_cleaned[var_station].isnull().sum() > 0:
            try:
                df_cleaned[var_station] = df_cleaned[var_station].interpolate(method="spline", order=3)
            except:
                try:
                    df_cleaned[var_station] = df_cleaned[var_station].interpolate(method="linear")
                except:
                    df_cleaned = df_cleaned.dropna(subset=[var_station])

        return df_cleaned

    def process(self, var=None):
        os.makedirs(self.config["status_dir"], exist_ok=True)
        if var:
            self._process_single_var(var)
        else:
            self._process_vars(self.config["vars"])
            # 合并原始数据并导入数据库
            db_output_dir = "Output/DB"
            all_s = merge_all_s(self.config["output_dir"], db_output_dir)
            import_csv_to_sqlite(f"{db_output_dir}/all_s.db", all_s, "Raw")
            # 合并处理完成后的数据并导入数据库
            all_sg = merge_all_sg(self.config["output_dir"], db_output_dir)
            import_csv_to_sqlite(f"{db_output_dir}/all_sg.db", all_sg, "Proc")


class DataProcessor_MP(DataProcessor):
    """多进程数据处理器"""
    def __init__(self, config, num_workers=4):
        super().__init__(config)

        # windows系统下mp模块最多只能创建61个进程，因此需要限制num_workers
        self.num_workers = min(num_workers, 61) if num_workers < os.cpu_count() else os.cpu_count() - 1
        self.mp_context = mp.get_context("spawn")
    
    def _worker(self, task):
        var, year = task
        try:
            # 初始化状态管理器和缓存（每个进程需要独立的实例）
            self.status_manager = StatusManager(self.config['status_dir'])
            self.processing_cache = set()
            self._process_single_var_single_year(var, year)
            return {"status": "success", "var": var, "year": year}
        except Exception as e:
            return {"status": "failed", "var": var, "year": year, "error": str(e)}
    
    def _generate_tasks(self, var=None):
        tasks = []
        if var:
            for year in range(self.config["start_year"], self.config["end_year"] + 1):
                tasks.append((var, year))
            print(f"|-->生成{len(tasks)}个任务:")
            print(tasks)
        else:
            for var in self.config["vars"]:
                for year in range(self.config["start_year"], self.config["end_year"] + 1):
                    tasks.append((var, year))
            print(f"|-->生成{len(tasks)}个任务:")
            print(tasks)
        return tasks
    
    def process(self, var=None):
        print(f"|-->年份范围:({self.config['start_year']}, {self.config['end_year']}), 进程数量:{self.num_workers}")
        os.makedirs(self.config["status_dir"], exist_ok=True)
        tasks = self._generate_tasks(var)
        
        log_file = os.path.join(self.config["status_dir"], "DataProcessor_log.json")
        
        # 初始化进度日志（适配前端固定格式）
        progress_data = {
            "total": len(tasks) + 1, # 最后新增导入数据库步骤, 因此+1
            "succeed": 0,
            "failed": 0,
            "processing": len(tasks) + 1,
            "failed_details": []
        }
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=4)
        
        results = {"success": [], "failed": []}

        with self.mp_context.Pool(self.num_workers) as pool:
            for result in tqdm(pool.imap_unordered(self._worker, tasks), total=len(tasks), desc="任务进度"):
                if result["status"] == "success":
                    results["success"].append(result)
                else:
                    results["failed"].append(result)
                
                # 实时更新进度日志（适配前端固定格式）
                progress_data["succeed"] = len(results["success"])
                progress_data["failed"] = len(results["failed"])
                progress_data["processing"] = len(tasks) - len(results["success"]) - len(results["failed"])
                # 避免重复添加失败详情
                if result["status"] == "failed":
                    progress_data["failed_details"].append({
                        "task": f"{result['var']}, {result['year']}", 
                        "error": result.get("error", "Unknown error")
                    })
                
                with open(log_file, 'w', encoding='utf-8') as f:
                    json.dump(progress_data, f, ensure_ascii=False, indent=4)

        print(f"数据处理完成! 成功: {len(results['success'])}, 失败: {len(results['failed'])}")

        # 更新进度：多进程任务完成，开始数据库导入
        progress_data["processing"] = 1  # 只剩数据库导入任务在处理中
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=4)

        # 合并原始数据并导入数据库
        db_output_dir = "Output/DB"
        try:
            all_s = merge_all_s(self.config["station_input_dir"], db_output_dir)
            import_csv_to_sqlite(f"{db_output_dir}/raw_proc_data.db", all_s, "Raw")
            # 合并处理完成后的数据并导入数据库
            all_sg = merge_all_sg(self.config["output_dir"], db_output_dir)
            import_csv_to_sqlite(f"{db_output_dir}/raw_proc_data.db", all_sg, "Proc")
            
            # 数据库导入成功
            progress_data["succeed"] += 1
        except Exception as e:
            # 数据库导入失败
            progress_data["failed"] += 1
            progress_data["failed_details"].append({
                "task": "导入数据库", 
                "error": str(e)
            })
            print(f"导入数据库失败: {e}")

        # 更新最终状态
        progress_data["processing"] = 0  # 所有任务完成
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(progress_data, f, ensure_ascii=False, indent=4)
        
        print(f"进度日志已保存: {log_file}")
    

if __name__ == "__main__":
    config = load_config("Config/DataProcessor.json")
    processor = DataProcessor_MP(config, config.get("num_workers", 4))
    processor.process()