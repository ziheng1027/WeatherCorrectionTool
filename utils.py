import os
import json
import glob
import time
import sqlite3
import pandas as pd
import xarray as xr
from tqdm import tqdm


"""----------------------------------------------DataProcessor Tool----------------------------------------------"""
def load_config(config_path):
    """加载JSON配置文件"""
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    return config

def get_station_files(dir):
    """获取站点文件列表"""
    if not os.path.isdir(dir):
        raise ValueError(f"{dir} 不是有效目录")
    station_files = [os.path.join(dir, f) for f in os.listdir(dir) if f.endswith('.csv')]
    return station_files

def get_grid_files(dir, var_grid, year):
    """获取格点文件列表"""
    if not os.path.isdir(dir):
        raise ValueError(f"{dir} 不是有效目录")
    dir = os.path.join(dir, f"{var_grid}.hourly", str(year))
    pattern = os.path.join(dir, "*.nc")
    grid_files = sorted(glob.glob(pattern))
    return grid_files

def get_vars_mapping():
    """获取变量名称的映射关系"""
    vars_map = {
        "温度": ("tmp", "温度/气温"),
        "相对湿度": ("rh", "相对湿度"),
        "降水量": ("pre", "过去1小时降水量"),
        "平均风速": ("wind_velocity", "2分钟平均风速"),
    }
    return vars_map

def get_name_to_id_mapping(station_info_file):
    """获取站点名称到ID的映射关系"""
    station_mapping = {}
    station_info = pd.read_csv(station_info_file, encoding='gbk')
    for _, row in station_info.iterrows():
        station_id = str(row['区站号(数字)'])  # 转换为字符串类型
        station_name = row['站名']
        station_mapping[station_name] = {
            "id": station_id,
            "lat": row['纬度'],
            "lon": row['经度']
        }
    return station_mapping

def get_id_to_name_mapping(station_info_file):
    """获取站点ID到名称的映射关系"""
    station_mapping = {}
    station_info = pd.read_csv(station_info_file, encoding='gbk')
    for _, row in station_info.iterrows():
        station_id = str(row['区站号(数字)'])  # 转换为字符串类型
        station_name = row['站名']
        station_mapping[station_id] = {
            "name": station_name,
            "lat": row['纬度'],
            "lon": row['经度']
        }
    return station_mapping

def cst_to_utc(cst_times):
    """北京时转世界时"""
    if isinstance(cst_times, pd.Series):
        # 处理DataFrame列
        cst_datetimes = pd.to_datetime(cst_times.astype(str), format='%Y%m%d%H')
        utc_datetimes = cst_datetimes - pd.Timedelta(hours=8)
        return utc_datetimes.dt.strftime('%Y%m%d%H').astype(int)
    else:
        # 处理列表或单个值
        cst_datetimes = pd.to_datetime(cst_times, format='%Y%m%d%H')
        utc_datetimes = cst_datetimes - pd.Timedelta(hours=8)
        return utc_datetimes.strftime('%Y%m%d%H').astype(int).tolist()

def utc_to_cst(utc_times):
    """世界时转北京时"""
    if isinstance(utc_times, pd.Series):
        # 处理DataFrame列
        utc_datetimes = pd.to_datetime(utc_times.astype(str), format='%Y%m%d%H')
        cst_datetimes = utc_datetimes + pd.Timedelta(hours=8)
        return cst_datetimes.dt.strftime('%Y%m%d%H').astype(int)
    else:
        # 处理列表或单个值
        utc_datetimes = pd.to_datetime(utc_times, format='%Y%m%d%H')
        cst_datetimes = utc_datetimes + pd.Timedelta(hours=8)
        return cst_datetimes.strftime('%Y%m%d%H').astype(int).tolist()

def merge_df(station_df, grid_df):
    """合并站点数据和格点数据"""
    # 站点时间为字符型, 格点时间为整数型
    station_df['时间'] = station_df['时间'].astype(int)
    station_times_range = (int(station_df['时间'].min()), int(station_df['时间'].max()))
    grid_times_range = (int(grid_df['time'].min()), int(grid_df['time'].max()))

    df_merged = pd.merge(station_df, grid_df, left_on='时间', right_on='time', how='inner')
    df_merged.drop(columns=['time'], inplace=True)
    return df_merged, station_times_range, grid_times_range

def safe_open_mfdataset(grid_files, **kwargs):
    """安全地打开多个netCDF文件, 处理坐标问题(基于手动合并方案优化)"""
    try:
        # 首先尝试标准方法
        ds = xr.open_mfdataset(grid_files, **kwargs)
        return ds
    except ValueError as e:
        error_msg = str(e).lower()
        
        # 检测全局纬度索引不单调错误
        if ("non-monotonic" in error_msg or "not monotonic" in error_msg or 
            "global indexes" in error_msg and "lat" in error_msg):
            print(f"检测到纬度全局索引不单调问题: {e}")
            print("使用替代合并方案...")
            
            try:
                # 获取第一个文件的坐标作为基准
                with xr.open_dataset(grid_files[0]) as ref_ds:
                    ref_lat = ref_ds.lat.values.copy()
                    ref_lon = ref_ds.lon.values.copy()
                
                print(f"所使用的坐标标准: lat: ({ref_lat.min():.2f}, {ref_lat.max():.2f}) | lon: ({ref_lon.min():.2f}, {ref_lon.max():.2f})")
                
                # 使用dask分块读取并统一坐标
                ds_list = []
                for i, file in enumerate(grid_files):
                    try:
                        # 使用分块读取减少内存占用
                        ds = xr.open_dataset(file, chunks={'time': 24})
                        # 统一使用第一个文件的坐标作为标准
                        ds = ds.assign_coords(lat=ref_lat, lon=ref_lon)
                        ds_list.append(ds)
                        print(f"文件 {i+1}/{len(grid_files)} 坐标统一完成")
                    except Exception as file_error:
                        print(f"处理文件 {file} 时出错: {file_error}")
                        # 如果分块处理失败，尝试不使用分块
                        try:
                            ds = xr.open_dataset(file)
                            ds = ds.assign_coords(lat=ref_lat, lon=ref_lon)
                            ds_list.append(ds)
                            print(f"文件 {i+1}/{len(grid_files)} 坐标统一完成(无分块)")
                        except:
                            raise
                
                if not ds_list:
                    raise ValueError("没有成功读取任何文件")
                
                # 合并所有数据集
                print(f"正在合并 {len(ds_list)} 个文件...")
                merged = xr.concat(ds_list, dim='time')
                
                # 获取变量名(假设所有文件有相同的变量)
                var_name = list(merged.data_vars.keys())[0] if merged.data_vars else None
                if var_name:
                    print(f"合并后的数据形状: {var_name}:{merged[var_name].shape}")
                
                print("所有文件坐标统一完成，成功合并数据")
                return merged
                
            except Exception as merge_error:
                print(f"手动合并方案失败: {merge_error}")
                # 最后尝试: 只使用第一个文件
                try:
                    print("尝试仅使用第一个文件...")
                    ds_first = xr.open_dataset(grid_files[0])
                    return ds_first
                except Exception as first_error:
                    print(f"无法打开第一个文件: {first_error}")
                    raise ValueError(f"无法处理坐标非单调问题: {e}")
        else:
            raise

def merge_all_s(input_dir, output_dir):
    """合并所有的原始站点数据, 用于存入数据库"""
    os.makedirs(output_dir, exist_ok=True)
    start_time = time.time()
    print("开始合并站点数据...")
    all_files = [file for file in os.listdir(input_dir) if file.endswith('.csv')]
    s_all = []
    for file in all_files:
        df = pd.read_csv(os.path.join(input_dir, file))
        # 将年月日时四列合并为时间列
        time_col = df["年"].astype(str).str.zfill(4) + \
                df["月"].astype(str).str.zfill(2) + \
                df["日"].astype(str).str.zfill(2) + \
                df["时"].astype(str).str.zfill(2)
        df = df.drop(columns=["年", "月", "日", "时"])
        df.insert(4, "时间", time_col)
        s_all.append(df)
    s_all = pd.concat(s_all, axis=0, ignore_index=True)
    # s_all.to_csv(os.path.join(output_dir, 'S_all.csv'), index=False)
    print(f"合并完成, 共 {len(s_all)} 行, 耗时 {time.time() - start_time:.2f} 秒")
    return s_all

def merge_all_sg(input_dir, output_dir):
    """合并DataProcessor处理完成后的全部SG数据, 用于存入数据库"""
    os.makedirs(output_dir, exist_ok=True)
    base_cols = ["区站号(数字)", "站名", "纬度", "经度", "时间"]
    vars_mapping = get_vars_mapping()
    
    start_time = time.time()
    print("开始合并SG数据...")
    
    # 一次性获取所有CSV文件
    all_files = []
    for root, _, files in os.walk(input_dir):
        all_files.extend(os.path.join(root, f) for f in files if f.endswith('.csv'))
    
    if not all_files:
        print("没有找到CSV文件")
        return None
    
    print(f"找到 {len(all_files)} 个文件")
    
    # 按变量分组文件
    var_files = {}
    for file_path in all_files:
        parts = file_path.split(os.sep)
        if len(parts) >= 3 and (var_name := parts[-3]) in vars_mapping:
            var_files.setdefault(var_name, []).append(file_path)
    
    # 单进程处理每个变量
    vars_data = {}
    
    for var_name, files in var_files.items():
        print(f"处理变量 {var_name}: {len(files)} 个文件")
        
        var_dfs = []
        grid_col, station_col = vars_mapping[var_name]
        
        for file_path in files:
            try:
                df = pd.read_csv(file_path, dtype={'区站号(数字)': 'int32'})
                df = df.rename(columns={grid_col: f"格点{var_name}", station_col: f"站点{var_name}"})
                var_dfs.append(df[base_cols + [f"站点{var_name}", f"格点{var_name}"]])
            except Exception as e:
                print(f"读取 {file_path} 出错: {e}")
        
        if var_dfs:
            vars_data[var_name] = pd.concat(var_dfs, ignore_index=True)
            print(f"|-->{var_name}: {len(vars_data[var_name])} 行")
    
    if not vars_data:
        print("无有效数据")
        return None
    
    # 一次性合并所有变量
    print("合并所有变量...")
    
    # 创建基础DataFrame
    base_var = next(iter(vars_data.keys()))
    sg_all = vars_data[base_var]
    
    # 合并其他变量
    for var_name, df in vars_data.items():
        if var_name == base_var:
            continue
        var_cols = [f"站点{var_name}", f"格点{var_name}"]
        sg_all = sg_all.merge(df[base_cols + var_cols], on=base_cols, how='outer')
    
    # 排序并保存
    sg_all = sg_all.sort_values(['区站号(数字)', '时间']).reset_index(drop=True)
    # output_file = os.path.join(output_dir, "SG_all.csv")
    # sg_all.to_csv(output_file, index=False)
    
    print(f"完成! 耗时: {time.time() - start_time:.1f}s, 数据: {len(sg_all)} 行")
    return sg_all

"""----------------------------------------------DataBase Tool----------------------------------------------"""
def format_timestamp(timestamp_str):
    """将 2008010100 格式化为 2008-01-01 00:00"""
    timestamp_str = str(timestamp_str)
    if not timestamp_str or len(timestamp_str) != 10:
        return timestamp_str
    return f"{timestamp_str[:4]}-{timestamp_str[4:6]}-{timestamp_str[6:8]} {timestamp_str[8:10]}:00"

def import_csv_to_sqlite(db_file, data, table_name, batch_size=100000):
    """将CSV文件或DataFrame导入到SQLite数据库"""
    header_map = {
        "站名": "station_name",
        "站号": "station_id",
        "纬度": "lat",
        "经度": "lon",
        "时间": "timestamp",
        "格点温度": "grid_temperature",
        "站点温度": "station_temperature",
        "格点相对湿度": "grid_humidity",
        "站点相对湿度": "station_humidity",
        "格点降水量": "grid_precipitation",
        "站点降水量": "station_precipitation",
        "格点平均风速": "grid_windspeed",
        "站点平均风速": "station_windspeed",
        "区站号(数字)": "station_id",
        "测站高度": "height",
        "温度/气温": "temperature",
        "相对湿度": "humidity",
        "过去1小时降水量": "precipitation",
        "2分钟平均风速": "2min_windspeed",
        "10分钟平均风速": "10min_windspeed",
    }
    
    # 处理DataFrame输入
    if hasattr(data, 'to_csv'):  # 检查是否为DataFrame
        headers = data.columns.tolist()
        data_rows = data.values.tolist()
    else:  # 处理CSV字符串输入
        lines = data.strip().split("\n")
        headers = lines[0].split(",")
        data_rows = [line.split(",") for line in lines[1:]]

    # 映射为英文列名
    eng_headers = [header_map.get(h, h) for h in headers]

    # 连接数据库
    conn = sqlite3.connect(db_file)
    c = conn.cursor()

    # 优化设置
    c.execute('PRAGMA synchronous = OFF')
    c.execute('PRAGMA journal_mode = MEMORY')
    c.execute('PRAGMA temp_store = MEMORY')

    # 创建表
    columns_sql = ", ".join([f'"{col}" TEXT' for col in eng_headers])
    create_sql = f'CREATE TABLE IF NOT EXISTS "{table_name}" ({columns_sql})'
    c.execute(create_sql)

    # 清空表
    c.execute(f'DELETE FROM "{table_name}"')
    print(f"表 {table_name} 已清空旧数据")

    # 插入 SQL
    columns_str = ", ".join([f'"{col}"' for col in eng_headers])
    placeholders = ", ".join(["?"] * len(eng_headers))
    insert_sql = f'INSERT INTO "{table_name}" ({columns_str}) VALUES ({placeholders})'

    # 找到时间列索引
    timestamp_index = headers.index("时间") if "时间" in headers else None

    # 批量插入
    batch = []
    total_rows = 0
    for row in data_rows:
        if timestamp_index is not None and len(row) > timestamp_index:
            row[timestamp_index] = format_timestamp(row[timestamp_index])
        batch.append(row)
        if len(batch) >= batch_size:
            c.executemany(insert_sql, batch)
            total_rows += len(batch)
            batch = []

    if batch:
        c.executemany(insert_sql, batch)
        total_rows += len(batch)

    conn.commit()

    # 验证数据量
    c.execute(f'SELECT COUNT(*) FROM "{table_name}"')
    print(f"{table_name} 当前共有 {c.fetchone()[0]} 行数据，成功插入 {total_rows} 行。")

    # 显示时间样例
    if timestamp_index is not None:
        c.execute(f'SELECT DISTINCT timestamp FROM "{table_name}" LIMIT 5')
        samples = c.fetchall()
        print("时间格式化样例:")
        for s in samples:
            print(f"  {s[0]}")

    # 关闭数据库
    c.execute("PRAGMA synchronous = NORMAL")
    c.execute("PRAGMA journal_mode = DELETE")
    conn.close()
    
"""----------------------------------------------API Tool----------------------------------------------"""
def check_files_dp(station_dir, grid_dir):
    """获取指定目录下是否存在文件, 数据处理阶段的文件检查"""
    if not os.path.exists(station_dir):
        print(f"目录 {station_dir} 不存在")
        return False
    if not os.path.exists(grid_dir):
        print(f"目录 {grid_dir} 不存在")
        return False
    if not os.path.isdir(station_dir):
        print(f"{station_dir} 不是一个目录")
        return []
    if not os.path.isdir(grid_dir):
        print(f"{grid_dir} 不是一个目录")
        return []
    
    all_station_files = []
    all_grid_files = []

    for root, _, files in os.walk(station_dir):
        all_station_files.extend([os.path.join(root, file) for file in files if file.endswith('.csv')])
    for root, _, files in os.walk(grid_dir):
        all_grid_files.extend([os.path.join(root, file) for file in files if file.endswith('.nc')])

    # 只有当两个目录下文件数量都>0时才返回True
    return len(all_station_files) > 0 and len(all_grid_files) > 0

def check_files_db(sg_dir, dem_file):
    """获取指定目录下是否存在文件, 数据集构建阶段的文件检查"""
    if not os.path.exists(sg_dir):
        print(f"目录 {sg_dir} 不存在")
        return False
    if not os.path.isdir(sg_dir):
        print(f"{sg_dir} 不是一个目录")
        return []
    if not os.path.exists(dem_file):
        print(f"文件 {dem_file} 不存在")
        return False
    
    all_sg_files = []

    for root, _, files in os.walk(sg_dir):
        all_sg_files.extend([os.path.join(root, file) for file in files if file.endswith('.csv')])

    return len(all_sg_files) > 0

def get_db_var_mapping():
    db_var_mapping = {
        "temperature": {
            "grid": "Proc.grid_temperature AS grid_temperature",
            "station": "Proc.station_temperature AS station_temperature",
            "raw": "Raw.temperature AS raw_temperature"
        },
        "humidity": {
            "grid": "Proc.grid_humidity AS grid_humidity",
            "station": "Proc.station_humidity AS station_humidity",
            "raw": "Raw.humidity AS raw_humidity"
        },
        "precipitation": {
            "grid": "Proc.grid_precipitation AS grid_precipitation",
            "station": "Proc.station_precipitation AS station_precipitation",
            "raw": "Raw.precipitation AS raw_precipitation"
        },
        "windspeed": {
            "grid": "Proc.grid_windspeed AS grid_windspeed",
            "station": "Proc.station_windspeed AS station_windspeed",
            "raw": 'Raw."10min_windspeed" AS raw_windspeed'
        },
    }
    return db_var_mapping

"""----------------------------------------------------------------------------------------------------"""
def get_station_data(dir, name_to_id_mapping, station_name, var, start_time, end_time):
    """获取站点数据"""
    pass
