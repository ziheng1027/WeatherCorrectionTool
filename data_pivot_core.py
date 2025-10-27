# src/core/data_pivot.py
import numpy as np
import pandas as pd
import xarray as xr
from threading import Lock
from datetime import datetime
from .config import settings
from .data_mapping import ELEMENT_TO_DB_MAPPING, ELEMENT_TO_NC_MAPPING
from .model_train import get_terrain_feature
from ..core.data_preview import get_grid_data_at_time
from ..utils.file_io import find_nc_file_for_timestamp, find_corrected_nc_file_for_timestamp


def bulid_feature_for_pivot(df: pd.DataFrame, element: str):
    """为数据透视的模型评估构建用于模型预测的特征"""
    if df.empty:
        return df
    
    # 添加地形特征
    dem_ds = xr.open_dataset(settings.DEM_DATA_PATH)
    lat, lon = df.iloc[0]['lat'], df.iloc[0]['lon']
    elevation, slope, aspect = get_terrain_feature(dem_ds, lat, lon)
    df['elevation'] = elevation
    df['slope'] = slope
    df['aspect'] = aspect
    dem_ds.close()

    # 添加滞后特征
    element_db_column = ELEMENT_TO_DB_MAPPING[element]
    grid_col = f"{element_db_column}_grid"
    lags = settings.LAGS_CONFIG.get(element, [])
    for lag in lags:
        df[f"{grid_col}_lag_{lag}h"] = df[grid_col].shift(lag)
    # 删除因滞后项产生的NaN行
    df.dropna(inplace=True)

    # 重排特征列的顺序, 和训练模型时保持一致
    base_columns = ["lat", "lon", "year", "month", "day", "hour"]
    grid_columns = [grid_col]
    lag_columns = [f"{grid_col}_lag_{lag}h" for lag in lags]
    terrain_columns = ["elevation", "slope", "aspect"]
    feature_columns = base_columns + grid_columns + lag_columns + terrain_columns
    df_X = df[feature_columns]
    df_y = df[element_db_column]

    return df_X, df_y

def get_correct_grid_data_at_time(element: str, timestamp: datetime):
    """获取指定时刻, 订正后的完整格点数据"""
    file_path = find_corrected_nc_file_for_timestamp(element, timestamp)
    nc_var = ELEMENT_TO_NC_MAPPING[element]

    with xr.open_dataset(file_path) as ds:
        # 通过时间戳选择特定时刻的数据
        target_hour = timestamp.hour
        correct_data_at_time = ds[nc_var].sel(time=target_hour, method='nearest')

        # 降采样
        downsampled_correct_data = correct_data_at_time.coarsen(lat=5, lon=5, boundary='trim').mean()
        
        # 提取纬度、经度和数值
        lats = downsampled_correct_data.lat.values
        lons = downsampled_correct_data.lon.values
        values = downsampled_correct_data.values

    return lats, lons, values

def get_grid_data_for_heatmap(element: str, timestamp: datetime):
    """获取指定要素、时刻下订正前后的格点数据用于绘制对比热力图"""
    # 获取订正前的格点数据
    lats_before, lons_before, values_before = get_grid_data_at_time(element, timestamp)
    # 获取订正后的格点数据
    _, _, values_after = get_correct_grid_data_at_time(element, timestamp)
    
    return {
        "lats": lats_before.tolist(),
        "lons": lons_before.tolist(),
        "values_before": values_before.tolist(),
        "values_after": values_after.tolist(),
    }

def get_correct_grid_time_series_for_coord(
        task_id: str, progress_tasks: dict, progress_lock: Lock, element: str, 
        lat: float, lon: float, start_time: datetime, end_time: datetime
):
    """提取指定坐标点、时间范围内, 订正前后的格点时间序列数据[后台任务]"""
    try:
        nc_var = ELEMENT_TO_NC_MAPPING[element]
        if not nc_var:
            raise ValueError(f"无效的要素名称: {element}")
        
        hourly_timestamps = pd.date_range(start=start_time, end=end_time, freq='h')
        total_timestamps = len(hourly_timestamps)

        values_before, values_after = [], []
        timestamps_out = []

        # 循环遍历每个小时
        for i, ts in enumerate(hourly_timestamps):
            # 提取订正前的数据
            try:
                original_file = find_nc_file_for_timestamp(element, ts)
                with xr.open_dataset(original_file) as ds:
                    value = ds[nc_var].sel(lat=lat, lon=lon, method='nearest').item()
                    values_before.append(None if np.isnan(value) else float(value))
            except FileNotFoundError:
                values_before.append(None)
            
            # 提取订正后的数据
            try:
                correct_file = find_corrected_nc_file_for_timestamp(element, ts)
                with xr.open_dataset(correct_file) as ds:
                    value = ds[nc_var].sel(lat=lat, lon=lon, method='nearest').item()
                    values_after.append(None if np.isnan(value) else float(value))
            except FileNotFoundError:
                values_after.append(None)

            timestamps_out.append(ts.to_pydatetime())

            # 更新任务进度
            progress = ((i + 1) / total_timestamps) * 100
            progress_text = f"正在提取数据... ({i+1}/{total_timestamps})"
            with progress_lock:
                if task_id in progress_tasks:
                    progress_tasks[task_id]["progress"] = round(progress, 2)
                    progress_tasks[task_id]["status"] = "PROCESSING"
                    progress_tasks[task_id]["progress_text"] = progress_text

        # 组装并保存结果到临时文件
        final_results = {
            "lat": lat,
            "lon": lon,
            "timestamps": timestamps_out,
            "values_before": values_before,
            "values_after": values_after,
        }
        
        # 将最终结果存入内存字典
        with progress_lock:
            if task_id in progress_tasks:
                progress_tasks[task_id]["status"] = "COMPLETED"
                progress_tasks[task_id]["progress"] = 100.0
                progress_tasks[task_id]["progress_text"] = "数据提取完成"
                progress_tasks[task_id]["result"] = final_results

    except Exception as e:
        error_message = f"任务失败: {e}"
        print(error_message)
        # 发生任何异常, 都将任务状态标记为FAILED
        with progress_lock:
            if task_id in progress_tasks:
                progress_tasks[task_id]["status"] = "FAILED"
                progress_tasks[task_id]["error"] = error_message
                progress_tasks[task_id]["progress"] = progress
