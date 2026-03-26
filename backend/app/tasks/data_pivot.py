# src/tasks/data_pivot.py
import json
import shutil
import zipfile
import rioxarray
import matplotlib
import numpy as np
import pandas as pd
import xarray as xr
import geopandas as gpd
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List
from datetime import datetime
from matplotlib.ticker import FuncFormatter
from ..db import crud
from ..db.database import SessionLocal
from ..core.config import settings
from ..core.data_mapping import ELEMENT_TO_DB_MAPPING, ELEMENT_TO_NC_MAPPING, get_name_to_id_mapping
from ..core.data_pivot import bulid_feature_for_pivot
from ..utils.file_io import load_model, find_nc_file_for_timestamp, find_corrected_nc_file_for_timestamp
from ..utils.metrics import cal_metrics, cal_comprehensive_score

matplotlib.use('Agg')  # 使用 'Agg' 后端, 适用于非GUI环境的后台任务
plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号

# 要素到单位的映射，用于在色标上显示单位
ELEMENT_UNIT_MAPPING = {
    '温度': '℃',
    '相对湿度': '%',
    '过去1小时降水量': 'mm',
    '2分钟平均风速': 'm/s'
}

# 要素到色标bar的映射, 降水bar的几个关键刻度设置:0.1, 2, 5, 10, 20, 50, 70, 100, 200, 300
ELEMENT_BAR_MAPPING = {
    '温度': 'RdBu_r',
    '相对湿度': {
        'boundaries': [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        'ticks': [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        'colors': [
            '#FFFFFF',  # 0-10 白色
            '#E6F9E6',  # 10-20 极浅绿
            '#CFF3CF',  # 20-30 很浅绿
            '#B7EDB7',  # 30-40 浅绿
            '#9FE79F',  # 40-50 绿
            '#87D787',  # 50-60 稍深绿
            '#6FC76F',  # 60-70 中绿
            '#57B757',  # 70-80 深绿
            '#3FA73F',  # 80-90 更深绿
            '#289728'   # 90-100 最深绿
        ]
    },
    '2分钟平均风速': 'RdYlBu_r',
    '过去1小时降水量': {
        'boundaries': [0, 0.1, 2, 5, 10, 20, 50, 70, 100, 200, 300],
        'ticks': [0, 0.1, 2, 5, 10, 20, 50, 70, 100, 200, 300],
        'colors': [
            '#FFFFFF',   # 0-0.1 白色
            '#B7F7B7',   # 0.1-2 浅绿色
            '#008000',   # 2-5 深绿色
            "#34C3C3",   # 5-10 浅蓝色
            '#00008B',   # 10-20 深蓝色
            '#FF00FF',   # 20-50 品红色
            "#6A4B2D",   # 50-70 深褐色
            '#FFA500',   # 70-100 棕黄色
            "#FF6F00",   # 100-200 橘黄色
            '#FF0000',   # 200-300 红色
            "#B8662C"    # >300 褐色
        ]
    }
}

# 定义使用残差模式的要素列表
RESIDUAL_ELEMENTS = ["温度", "相对湿度", "过去1小时降水量"] 

def evaluate_model(task_id: str, element: str, station_name: str, start_time: datetime, end_time: datetime, model_paths: List[str]):
    """模型评估分析[后台任务]"""
    db = SessionLocal()
    
    try:
        # 任务初始化
        crud.update_task_status(db, task_id, "PROCESSING", 0.0, "任务初始化, 准备获取数据...")
        # 获取并准备用于预测的数据和特征
        station_mapping = get_name_to_id_mapping(settings.STATION_INFO_PATH)
        df_base = crud.get_proc_feature_for_pivot(db, station_mapping, element, station_name, start_time, end_time)

        if df_base.empty:
            crud.update_task_status(db, task_id, "FAILED", 0.0, "在指定条件下没有找到可供分析的数据")
            raise ValueError("在指定条件下没有找到可供分析的数据")
        
        crud.update_task_status(db, task_id, "PROCESSING", 20.0, "数据获取完成, 开始构建特征...")
        element_db_column = ELEMENT_TO_DB_MAPPING[element]
        df_X, df_y = bulid_feature_for_pivot(df_base.copy(), element)
        crud.update_task_status(db, task_id, "PROCESSING", 40.0, "特征构建完成, 开始模型预测...")

        # 计算原始数据的指标
        grid_values = df_X[f"{element_db_column}_grid"].tolist()
        original_metric = cal_metrics(df_y, grid_values)
        
        # 循环处理模型并实时更新进度
        total_models = len(model_paths)
        all_metrics = [{"station_name": station_name, "model_name": "原始数据(清洗后)", "metrics": original_metric}]
        all_predictions = []
        for i, model_path in enumerate(model_paths):
            model_path = Path(model_path)
            model_name = model_path.stem
            # 更新进度
            progress = 40 + (((i + 1) / total_models) * 60)
            progress_text = f"正在处理第 {i + 1} 个模型: {model_name}"
            crud.update_task_status(db, task_id, "PROCESSING", progress, progress_text)
            print(f"正在处理第 {i + 1} 个模型: {model_name}")
            # 加载模型
            model = load_model(model_path)
            # 预测
            pred_raw = model.predict(df_X)
            # 判断是否需要还原残差
            if element in RESIDUAL_ELEMENTS:
                pred_y = pred_raw + np.array(grid_values)
            else:
                pred_y = pred_raw
            # 添加到结果列表
            all_predictions.append({"station_name": station_name, "model_name": model_name, "pred_values": pred_y.tolist()})
            all_metrics.append({"station_name": station_name, "model_name": model_name, "metrics": cal_metrics(df_y, pred_y)})
            print(f"第 {i + 1} 个模型: {model_name} 预测完成")
        
        # 计算综合评分
        try:
            all_metrics_with_S = cal_comprehensive_score(all_metrics)
        except Exception as e:
            print(f"计算综合评分时出错: {e}")
            all_metrics_with_S = all_metrics    # 如果失败, 使用原指标

        # 组装并保存最终结果
        timestamps = pd.to_datetime(df_base["timestamp"])  # 转换为datetime对象
        final_results = {
            "timestamps": [ts.isoformat() for ts in timestamps],
            "station_values": df_y.tolist(),
            "grid_values": df_X[f"{element_db_column}_grid"].tolist(),
            "pred_values": all_predictions,
            "metrics": all_metrics_with_S,
        }
        # 保存结果到本地, 以便api在任务完成后读取数据
        output_dir = Path(f"output/pivot_model_results/{element}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{element}_{station_name}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_results, f, ensure_ascii=False, indent=4)

        # 更新任务状态
        task = crud.get_task_by_id(db, task_id)
        if task:
            params = task.get_params()
            params["result_path"] = str(output_path)
            task.set_params(params)
            db.add(task)
            crud.update_task_status(db, task_id, "COMPLETED", 100.0, "分析完成, 结果已保存")
        else:
            raise ValueError("找不到任务记录以保存结果路径")

    except Exception as e:
        error_msg = f"任务执行失败: {e}"
        print(error_msg)
        crud.update_task_status(db, task_id, "FAILED", 0.0, error_msg)
    finally:
        db.close()

def create_export_zip_task(task_id: str, element: str, start_time: datetime, end_time: datetime):
    """查找指定范围内的所有订正后.nc文件, 并将它们压缩成一个zip包[后台任务]"""
    db = SessionLocal()
    try:
        # 1. 定义输出路径
        output_dir = Path("output/temp_data/export")
        output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = output_dir / f"{task_id}.zip"

        # 2. 获取所有时间戳
        timestamps = pd.date_range(start=start_time, end=end_time, freq='h')
        total_files = len(timestamps)
        files_found = 0
        
        crud.update_task_status(db, task_id, "PROCESSING", 0, f"准备压缩 {total_files} 个文件...")

        # 3. 循环查找并压缩文件
        # 使用 'w' 模式创建新的zip文件, ZIP_DEFLATED 提供较好的压缩率
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, ts in enumerate(timestamps):
                try:
                    # 查找对应的订正文件
                    file_path = find_corrected_nc_file_for_timestamp(element, ts)
                    
                    # 写入zip包, arcname=file_path.name 确保zip包内是扁平结构, 不含服务器绝对路径
                    zf.write(file_path, arcname=file_path.name)
                    files_found += 1
                except FileNotFoundError:
                    # 如果某个时次的文件不存在, 打印警告并跳过
                    print(f"警告: 未找到 {ts} 的订正文件, 已跳过")
                    pass
                
                # 4. 周期性更新进度 (例如每50个文件或最后1个文件)
                if (i + 1) % 10 == 0 or (i + 1) == total_files:
                    progress = ((i + 1) / total_files) * 100
                    crud.update_task_status(db, task_id, "PROCESSING", progress, f"正在压缩文件... ({i+1}/{total_files})")

        # 5. 任务完成, 更新数据库
        final_message = f"打包完成, 共找到 {files_found} / {total_files} 个文件"
        task = crud.get_task_by_id(db, task_id)
        if task:
            params = task.get_params()
            params["result_path"] = str(zip_path)
            params["files_found"] = files_found
            params["total_requested"] = total_files
            task.set_params(params)
            db.add(task)
            db.commit() # 确保参数写入
        
        crud.update_task_status(db, task_id, "COMPLETED", 100, final_message)

    except Exception as e:
        print(f"导出任务 {task_id} 失败: {e}")
        crud.update_task_status(db, task_id, "FAILED", 0, f"任务失败: {e}")
    finally:
        db.close()

def create_export_images_task(
    task_id: str, 
    element: str, 
    start_time: datetime, 
    end_time: datetime
):
    """
    查找订正后的.nc文件, 绘制成.png图像, 并压缩为.zip包。
    """
    db = SessionLocal()
    try:    
        # 1. 定义临时图片目录和最终zip输出路径
        temp_image_dir = Path("output/temp_data/export_images") / task_id
        temp_image_dir.mkdir(parents=True, exist_ok=True)
        
        zip_output_dir = Path("output/temp_data/export")
        zip_output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = zip_output_dir / f"{task_id}_images.zip"

        # 2. 获取NC变量名和时间戳
        nc_var = ELEMENT_TO_NC_MAPPING.get(element)
        if not nc_var:
            raise ValueError(f"无效的要素名称: {element}")
            
        timestamps = pd.date_range(start=start_time, end=end_time, freq='h')
        total_files = len(timestamps)
        files_found = 0
        
        crud.update_task_status(db, task_id, "PROCESSING", 0, f"准备生成 {total_files} 张图像...")

        # 读取湖北省行政区划边界，并准备一个用于掩膜的合并后边界
        province_gdf = None # 用于绘制市界
        hubei_mask_geometry = None # 用于裁剪
        province_geo_path = Path(settings.HUBEI_MAP_PATH)
        
        if province_geo_path.exists():
            try:
                province_gdf = gpd.read_file(province_geo_path)
                
                # 准备用于掩膜的省级边界
                # 确保 CRS (WGS84)
                if province_gdf.crs is None:
                    province_gdf_crs = province_gdf.set_crs("EPSG:4326")
                else:
                    province_gdf_crs = province_gdf.to_crs("EPSG:4326")
                
                # 创建一个合并的省级边界 (保留 province_gdf 不变, 用于绘制市级边界)
                hubei_boundary_dissolved = province_gdf_crs.dissolve()
                hubei_mask_geometry = hubei_boundary_dissolved.geometry
                
                # 打印 GeoJSON 范围
                print(f"信息: 成功加载 GeoJSON 掩膜. 边界范围 (lon/lat bounds): {hubei_mask_geometry.bounds}")
                
            except Exception as geo_e:
                print(f"读取行政区划失败: {geo_e}")
                province_gdf = None
                hubei_mask_geometry = None
        else:
             print(f"警告: 找不到 GeoJSON 文件: {province_geo_path}")
        
        # 3. 循环查找、绘图、保存
        for i, ts in enumerate(timestamps):
            try:
                # 查找对应的订正文件
                nc_file_path = find_nc_file_for_timestamp(element, ts)
                correct_nc_file_path = find_corrected_nc_file_for_timestamp(element, ts)
                
                # 使用 xarray 和 matplotlib 绘图：一行三列（原始 / 订正 / 误差）
                with xr.open_dataset(nc_file_path) as ds_orig, xr.open_dataset(correct_nc_file_path) as ds_corr:
                    
                    # 步骤 1: 立即为整个数据集设置空间维度
                    try:
                        # 检查 .rio 访问器是否存在
                        if rioxarray is None or not hasattr(ds_orig, "rio"):
                            raise AttributeError("'Dataset' object has no attribute 'rio'. rioxarray 导入或注册失败。")
                        
                        ds_orig_spatial = ds_orig.rio.set_spatial_dims(x_dim='lon', y_dim='lat').rio.write_crs("EPSG:4326")
                        ds_corr_spatial = ds_corr.rio.set_spatial_dims(x_dim='lon', y_dim='lat').rio.write_crs("EPSG:4326")
                    
                    except AttributeError as e:
                        print(f"致命错误: {e}")
                        print("请确保 'rioxarray' 已正确安装 (pip install rioxarray)。将使用未裁剪的数据。")
                        ds_orig_spatial = ds_orig
                        ds_corr_spatial = ds_corr
                            
                    except Exception as rio_e:
                        print(f"警告: 设置空间维度失败: {rio_e}。将使用未裁剪的数据。")
                        ds_orig_spatial = ds_orig
                        ds_corr_spatial = ds_corr

                    # 步骤 2: 现在才选择变量和时间
                    data_array_orig = ds_orig_spatial[nc_var].isel(time=0)
                    data_array_corr = ds_corr_spatial[nc_var].isel(time=0)
                    # 相对湿度最大值为100, 如果预测出大于100的值置为100
                    if element == "相对湿度":
                        data_array_orig = data_array_orig.clip(max=100)
                        data_array_corr = data_array_corr.clip(max=100)

                    # 步骤 3: 在裁剪前, 重命名维度为 'x' 和 'y'
                    # rioxarray.clip() 严格要求维度名为 'x' 和 'y'
                    try:
                        data_array_orig = data_array_orig.rename({'lon': 'x', 'lat': 'y'})
                        data_array_corr = data_array_corr.rename({'lon': 'x', 'lat': 'y'})
                    except Exception as rename_e:
                        print(f"警告: 重命名 'lon'/'lat' 失败: {rename_e}。裁剪可能会失败。")

                    # 步骤 4: 应用掩膜 (如果 hubei_mask_geometry 存在)
                    if hubei_mask_geometry is not None:
                        try:
                            # 检查 DataArray 范围 (仅调试一次)
                            if i == 0: 
                                # 使用 'x' 和 'y'
                                print(f"信息 (ts={ts}): 准备裁剪. DataArray 范围 (x): {float(data_array_orig['x'].min())} to {float(data_array_orig['x'].max())}")
                                print(f"信息 (ts={ts}): 准备裁剪. DataArray 范围 (y): {float(data_array_orig['y'].min())} to {float(data_array_orig['y'].max())}")

                            # 裁剪 (边界外为 NaN)
                            data_array_orig = data_array_orig.rio.clip(hubei_mask_geometry, all_touched=True, drop=False)
                            data_array_corr = data_array_corr.rio.clip(hubei_mask_geometry, all_touched=True, drop=False)
                            
                            # 检查裁剪结果 (仅调试一次)
                            if i == 0:
                                nan_count_orig = np.count_nonzero(np.isnan(data_array_orig.values))
                                if nan_count_orig == 0:
                                    print(f"警告: 裁剪 'orig' 未产生 NaN。请再次核对 GeoJSON 和 NC 经纬度范围。")
                                else:
                                    print(f"信息: 成功裁剪 'orig', 产生 {nan_count_orig} 个 NaN。")

                        except AttributeError as e:
                            # 如果 ds.rio 成功了，但 da.rio 失败了
                            print(f"警告: 裁剪 DataArray 失败: {e}。是否是切片导致rio访问器丢失？")
                        except Exception as clip_e:
                            print(f"警告: 裁剪步骤失败: {clip_e}")

                    # 计算最大最小值，用于统一色标范围
                    # 使用 np.nanmin/np.nanmax 忽略掩膜区域的NaN值
                    try:
                        orig_min = float(np.nanmin(data_array_orig.values))
                        corr_min = float(np.nanmin(data_array_corr.values))
                        orig_max = float(np.nanmax(data_array_orig.values))
                        corr_max = float(np.nanmax(data_array_corr.values))
                        
                        vmin = min(orig_min, corr_min)
                        vmax = max(orig_max, corr_max)
                        
                        # 处理 vmin 和 vmax 相等或无效的情况 (例如全为NaN)
                        if np.isnan(vmin) or np.isnan(vmax) or vmin == vmax:
                            vmin = 0.0
                            vmax = 1.0
                            
                    except Exception:
                        # 回退逻辑 (例如数据全为0或NaN)
                        vmin = float(data_array_orig.min())
                        vmax = float(data_array_orig.max())
                        if vmin == vmax:
                            vmin -= 0.5
                            vmax += 0.5


                    # 计算误差并确定对称色标范围
                    # diff 会自动继承掩膜 (边界外为 NaN)
                    diff = data_array_corr - data_array_orig
                    try:
                        diff_abs_max = float(np.nanmax(np.abs(diff.values)))
                        if np.isnan(diff_abs_max) or diff_abs_max == 0: # 避免 vmin=vmax=0
                            diff_abs_max = 1.0 
                    except Exception:
                        diff_abs_max = float(np.nanmax(np.abs(diff)))
                        if np.isnan(diff_abs_max) or diff_abs_max == 0:
                            diff_abs_max = 1.0

                    # 创建一行三列的子图
                    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(24, 8))

                    # 单位和色标标签
                    unit = ELEMENT_UNIT_MAPPING.get(element, '')
                    value_label = f"{element} ({unit})" if unit else element
                    diff_label = f"{element} (diff, {unit})" if unit else f"{element} (diff)"
                    bar_cfg = ELEMENT_BAR_MAPPING.get(element, 'RdBu_r')
                    # 兼容所有要素，统一cmap变量定义
                    if isinstance(bar_cfg, dict):
                        boundaries = bar_cfg['boundaries']
                        colors = bar_cfg['colors']
                        ticks = bar_cfg['ticks']
                        cmap = matplotlib.colors.ListedColormap(colors)
                        norm = matplotlib.colors.BoundaryNorm(boundaries, ncolors=len(colors), clip=True)
                    else:
                        cmap = bar_cfg
                        boundaries = None
                        norm = None
                        ticks = None

                    # 经纬度刻度格式化器
                    def _deg_fmt_lon(x, pos):
                        try:
                            s = f"{x:.2f}"
                            if '.' in s:
                                s = s.rstrip('0').rstrip('.')
                        except Exception:
                            s = str(x)
                        return s + '°E'

                    def _deg_fmt_lat(x, pos):
                        try:
                            s = f"{x:.2f}"
                            if '.' in s:
                                s = s.rstrip('0').rstrip('.')
                        except Exception:
                            s = str(x)
                        return s + '°N'

                    lon_formatter = FuncFormatter(_deg_fmt_lon)
                    lat_formatter = FuncFormatter(_deg_fmt_lat)

                    # 绘制订正前 (现在是掩膜后的数据, NaN区域将透明)
                    if boundaries is not None and norm is not None:
                        im1 = data_array_orig.plot.pcolormesh(
                            ax=ax1,
                            cmap=cmap,
                            norm=norm,
                            vmin=min(boundaries),
                            vmax=max(boundaries),
                            cbar_kwargs={'label': value_label, 'orientation': 'horizontal', 'pad': 0.15, 'ticks': ticks}
                        )
                    else:
                        im1 = data_array_orig.plot.pcolormesh(
                            ax=ax1,
                            cmap=cmap,
                            vmin=vmin,
                            vmax=vmax,
                            cbar_kwargs={'label': value_label, 'orientation': 'horizontal', 'pad': 0.15}
                        )
                    ax1.set_title(f"订正前 {element}\n{ts.strftime('%Y-%m-%d %H:%M')}", fontsize=14)
                    ax1.xaxis.set_major_formatter(lon_formatter)
                    ax1.yaxis.set_major_formatter(lat_formatter)
                    ax1.set_xlabel('Longitude') # 确保轴标签正确
                    ax1.set_ylabel('Latitude')  # 确保轴标签正确
                    # 叠加湖北省行政区划边界和地名 (使用原始的 province_gdf)
                    if province_gdf is not None:
                        province_gdf.boundary.plot(ax=ax1, color='gray', linewidth=1)
                        for idx, row in province_gdf.iterrows():
                            if row.geometry is not None and hasattr(row.geometry, 'centroid'):
                                centroid = row.geometry.centroid
                                name = row.get('name', row.get('NAME', None))
                                if name:
                                    ax1.text(centroid.x, centroid.y, name, fontsize=8, color='black', alpha=0.5, ha='center', va='center', zorder=10)

                    # 绘制订正后 (现在是掩膜后的数据, NaN区域将透明)
                    if boundaries is not None and norm is not None:
                        im2 = data_array_corr.plot.pcolormesh(
                            ax=ax2,
                            cmap=cmap,
                            norm=norm,
                            vmin=min(boundaries),
                            vmax=max(boundaries),
                            cbar_kwargs={'label': value_label, 'orientation': 'horizontal', 'pad': 0.15, 'ticks': ticks}
                        )
                    else:
                        im2 = data_array_corr.plot.pcolormesh(
                            ax=ax2,
                            cmap=cmap,
                            vmin=vmin,
                            vmax=vmax,
                            cbar_kwargs={'label': value_label, 'orientation': 'horizontal', 'pad': 0.15}
                        )
                    ax2.set_title(f"订正后 {element}\n{ts.strftime('%Y-%m-%d %H:%M')}", fontsize=14)
                    ax2.xaxis.set_major_formatter(lon_formatter)
                    ax2.yaxis.set_major_formatter(lat_formatter)
                    ax2.set_xlabel('Longitude') # 确保轴标签正确
                    ax2.set_ylabel('Latitude')  # 确保轴标签正确
                    if province_gdf is not None:
                        province_gdf.boundary.plot(ax=ax2, color='gray', linewidth=1)
                        for idx, row in province_gdf.iterrows():
                            if row.geometry is not None and hasattr(row.geometry, 'centroid'):
                                centroid = row.geometry.centroid
                                name = row.get('name', row.get('NAME', None))
                                if name:
                                    ax2.text(centroid.x, centroid.y, name, fontsize=8, color='black', alpha=0.5, ha='center', va='center', zorder=10)

                    # 绘制误差 (订正后 - 订正前, NaN区域将透明)
                    im3 = diff.plot.pcolormesh( # 【修改】imshow -> pcolormesh
                        ax=ax3,
                        cmap="coolwarm",
                        vmin=-diff_abs_max,
                        vmax=diff_abs_max,
                        cbar_kwargs={'label': diff_label, 'orientation': 'horizontal', 'pad': 0.15}
                    )
                    ax3.set_title(f"误差 (订正后 - 订正前)\n{ts.strftime('%Y-%m-%d %H:%M')}", fontsize=14)
                    ax3.xaxis.set_major_formatter(lon_formatter)
                    ax3.yaxis.set_major_formatter(lat_formatter)
                    ax3.set_xlabel('Longitude') # 确保轴标签正确
                    ax3.set_ylabel('Latitude')  # 确保轴标签正确
                    if province_gdf is not None:
                        province_gdf.boundary.plot(ax=ax3, color='gray', linewidth=1)
                        for idx, row in province_gdf.iterrows():
                            if row.geometry is not None and hasattr(row.geometry, 'centroid'):
                                centroid = row.geometry.centroid
                                name = row.get('name', row.get('NAME', None))
                                if name:
                                    ax3.text( centroid.x, centroid.y, name, fontsize=8, color='black', alpha=0.7, ha='center', va='center', zorder=10)

                    plt.tight_layout()  # 自动调整子图布局

                    # 定义图像输出路径
                    img_filename = f"compare_{nc_var}_{ts.strftime('%Y%m%d%H')}.png"
                    img_path = temp_image_dir / img_filename
                    
                    # 保存图像
                    fig.savefig(img_path, dpi=300, bbox_inches='tight')
                    
                    # 关闭图像以释放内存
                    plt.close(fig)
                    
                files_found += 1
                
            except Exception as plot_e:
                print(f"警告: 绘制 {ts} 时出错: {plot_e}, 已跳过")
                plt.close('all') # 确保关闭所有可能打开的图像
                pass
            
            # 4. 周期性更新进度
            if (i + 1) % 50 == 0 or (i + 1) == total_files:
                progress = ((i + 1) / total_files) * 90 # 压缩占10%
                # 确保进度不超过95
                progress = min(progress, 95)
                crud.update_task_status(db, task_id, "PROCESSING", progress, f"正在生成图像... ({i+1}/{total_files})")

        # 5. 压缩所有生成的图像
        crud.update_task_status(db, task_id, "PROCESSING", 95, f"图像生成完毕 ({files_found}张), 开始压缩...")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for img_file in temp_image_dir.glob("*.png"):
                zf.write(img_file, arcname=img_file.name)
        
        # 6. 任务完成, 更新数据库
        final_message = f"图像打包完成, 共生成 {files_found} / {total_files} 张图像"
        task = crud.get_task_by_id(db, task_id)
        if task:
            params = task.get_params()
            params["result_path"] = str(zip_path) # 存储zip包的路径
            params["files_found"] = files_found
            params["total_requested"] = total_files
            task.set_params(params)
            db.add(task)
            db.commit() # 确保参数写入
        
        crud.update_task_status(db, task_id, "COMPLETED", 100, final_message)

    except Exception as e:
        print(f"图像导出任务 {task_id} 失败: {e}")
        crud.update_task_status(db, task_id, "FAILED", 0, f"任务失败: {e}")
    finally:
        # 7. 清理临时图片目录
        try:
            if temp_image_dir.exists():
                shutil.rmtree(temp_image_dir)
                print(f"临时图片目录已删除: {temp_image_dir}")
        except OSError as e:
            print(f"删除临时图片目录 {temp_image_dir} 失败: {e}")

        db.close()

def evaluate_models_by_metrics(task_id: str, element: str, season: str, test_set_values: List[str]):
    """根据要素、季节和测试集值筛选模型并计算综合评分[后台任务]"""
    db = SessionLocal()
    try:
        # 任务初始化
        crud.update_task_status(db, task_id, "PROCESSING", 0.0, "任务初始化, 准备筛选模型...")

        # 获取所有模型记录
        all_records = crud.get_all_model_records(db)
        if not all_records:
            crud.update_task_status(db, task_id, "FAILED", 0.0, "数据库中没有任何模型记录")
            raise ValueError("数据库中没有任何模型记录")

        crud.update_task_status(db, task_id, "PROCESSING", 20.0, f"找到 {len(all_records)} 个模型记录, 开始筛选...")

        # 筛选符合条件的模型记录
        filtered_records = []
        for record in all_records:
            # 检查要素是否匹配
            if record.element != element:
                continue

            # 检查训练参数中的季节和测试集值
            train_params = record.get_train_params()
            record_season = train_params.get("season", "")
            record_test_set_values = train_params.get("test_set_values", [])

            # 季节匹配检查: 指定季节 -> 匹配该季节 + 全年模型
            if season != "全年":
                # 指定具体季节时, 匹配该季节和全年模型
                if record_season not in [season, "全年"]:
                    continue
            else:
                # 指定全年时, 只匹配全年模型
                if record_season != "全年":
                    continue

            # 测试集值匹配检查 (需要完全匹配)
            if set(record_test_set_values) != set(test_set_values):
                continue

            filtered_records.append(record)

        if not filtered_records:
            crud.update_task_status(db, task_id, "FAILED", 0.0, f"没有找到符合条件的模型记录: element={element}, season={season}, test_set_values={test_set_values}")
            raise ValueError(f"没有找到符合条件的模型记录: element={element}, season={season}, test_set_values={test_set_values}")

        crud.update_task_status(db, task_id, "PROCESSING", 40.0, f"筛选出 {len(filtered_records)} 个符合条件的模型, 开始读取指标...")

        # 读取每个模型的整体指标
        all_metrics = []
        for i, record in enumerate(filtered_records):
            progress = 40 + (((i + 1) / len(filtered_records)) * 40)
            progress_text = f"正在读取第 {i + 1} 个模型的指标: {record.model_name}"
            crud.update_task_status(db, task_id, "PROCESSING", progress, progress_text)

            # 构建指标文件路径
            train_params = record.get_train_params()
            model_name = train_params.get("model", "").lower()
            start_year = train_params.get("start_year", "")
            end_year = train_params.get("end_year", "")
            season = train_params.get("season", "")
            split_method = train_params.get("split_method", "")

            # 根据模型记录信息构建指标文件路径
            metrics_file_name = f"{model_name}_{element}_{start_year}_{end_year}_{season}_{split_method}_{record.task_id}.json"
            metrics_dir = Path(settings.METRIC_OUTPUT_DIR) / model_name / "overall"
            metrics_path = metrics_dir / metrics_file_name

            if not metrics_path.exists():
                print(f"警告: 找不到指标文件 {metrics_path}, 跳过该模型")
                continue

            # 读取指标文件
            try:
                with open(metrics_path, 'r', encoding='utf-8') as f:
                    metrics_data = json.load(f)

                # 使用测试集预测指标 (testset_pred)
                metrics = metrics_data.get("testset_pred", {})

                # 添加到结果列表
                all_metrics.append({
                    "model_name": record.model_name,
                    "model_id": record.model_id,
                    "task_id": record.task_id,
                    "season": record_season,
                    "metrics": metrics
                })

                print(f"成功读取模型 {record.model_name} 的指标")

            except Exception as e:
                print(f"读取模型 {record.model_name} 的指标文件失败: {e}")
                continue

        if not all_metrics:
            crud.update_task_status(db, task_id, "FAILED", 0.0, "所有模型的指标文件读取失败")
            raise ValueError("所有模型的指标文件读取失败")

        # 添加原始指标 (从第一个模型的testset_true获取)
        if all_metrics:
            try:
                # 获取第一个模型的指标文件路径
                first_record = filtered_records[0]
                train_params = first_record.get_train_params()
                model_name = train_params.get("model", "").lower()
                start_year = train_params.get("start_year", "")
                end_year = train_params.get("end_year", "")
                record_season = train_params.get("season", "")
                record_split_method = train_params.get("split_method", "")

                metrics_file_name = f"{model_name}_{element}_{start_year}_{end_year}_{record_season}_{record_split_method}_{first_record.task_id}.json"
                metrics_dir = Path(settings.METRIC_OUTPUT_DIR) / model_name / "overall"
                metrics_path = metrics_dir / metrics_file_name

                if metrics_path.exists():
                    with open(metrics_path, 'r', encoding='utf-8') as f:
                        metrics_data = json.load(f)

                    # 使用测试集真实指标 (testset_true)
                    original_metrics = metrics_data.get("testset_true", {})

                    # 添加原始指标到结果列表
                    all_metrics.insert(0, {
                        "model_name": "原始数据",
                        "model_id": "original_data",
                        "task_id": "original",
                        "season":  record_season,
                        "metrics": original_metrics
                    })

                    print("成功添加原始数据指标")

            except Exception as e:
                print(f"读取原始数据指标失败: {e}")

        crud.update_task_status(db, task_id, "PROCESSING", 85.0, f"成功读取 {len(all_metrics)} 个模型的指标, 开始计算综合评分...")

        # 计算综合评分
        try:
            all_metrics_with_S = cal_comprehensive_score(all_metrics)
        except Exception as e:
            print(f"计算综合评分时出错: {e}")
            all_metrics_with_S = all_metrics  # 如果失败, 使用原指标

        # 组装最终结果
        final_results = {
            "filter_conditions": {
                "element": element,
                "season": season,
                "test_set_values": test_set_values
            },
            "total_models_found": len(filtered_records),
            "total_metrics_loaded": len(all_metrics),
            "ranked_models": all_metrics_with_S
        }

        # 保存结果到本地
        output_dir = Path(f"output/pivot_model_ranking/{element}")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{element}_{season}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_results, f, ensure_ascii=False, indent=4)

        # 更新任务状态
        task = crud.get_task_by_id(db, task_id)
        if task:
            params = task.get_params()
            params["result_path"] = str(output_path)
            task.set_params(params)
            db.add(task)
            crud.update_task_status(db, task_id, "COMPLETED", 100.0, f"分析完成, 共对 {len(all_metrics_with_S)} 个模型进行排序")
        else:
            raise ValueError("找不到任务记录以保存结果路径")

    except Exception as e:
        error_msg = f"任务执行失败: {e}"
        print(error_msg)
        crud.update_task_status(db, task_id, "FAILED", 0.0, error_msg)
    finally:
        db.close()

