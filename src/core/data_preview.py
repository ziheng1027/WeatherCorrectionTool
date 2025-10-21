# src/core/data_preview.py
import xarray as xr
import pandas as pd
import numpy as np
from datetime import datetime
from threading import Lock
from typing import Dict, Any
from ..core.data_mapping import ELEMENT_TO_NC_MAPPING
from ..utils.file_io import find_nc_file_for_timestamp


def get_grid_data_at_time(element: str, timestamp: datetime):
    """
    获取指定要素和时刻的完整格点数据。

    :param element: 要素名称 (例如: "温度")
    :param timestamp: 具体时刻
    :return: lats(纬度数组), lons(经度数组), values(二维数值数组)
    """
    file_path = find_nc_file_for_timestamp(element, timestamp)
    nc_var = ELEMENT_TO_NC_MAPPING[element]

    # 使用xarray打开.nc文件
    with xr.open_dataset(file_path) as ds:
        # 通过时间戳选择特定时刻的数据
        target_hour = timestamp.hour
        data_at_time = ds[nc_var].sel(time=target_hour, method='nearest')

        # 降采样
        downsampled_data = data_at_time.coarsen(lat=5, lon=5, boundary='trim').mean()
        
        # 提取纬度、经度和数值
        lats = downsampled_data['lat'].values
        lons = downsampled_data['lon'].values
        values = downsampled_data.values
        
        return lats, lons, values
    
def get_grid_time_series_for_coord(
        task_id: str, progress_tasks: Dict[str, Any], progress_lock: Lock,
        element: str, lat: float, lon: float, start_time: datetime, end_time: datetime
):
    """
    获取指定坐标和时间范围内的格点数据时间序列。

    :param element: 要素名称 (例如: "温度")
    :param lat: 纬度
    :param lon: 经度
    :param start_time: 开始时间
    :param end_time: 结束时间
    :return: timestamps(时间戳列表), values(数值列表)
    """
    try:
        hourly_timestamps = pd.date_range(start=start_time, end=end_time, freq='h')
        total_timestamps = len(hourly_timestamps)
        
        if total_timestamps == 0:
            with progress_lock:
                progress_tasks[task_id]["status"] = "COMPLETED"
                progress_tasks[task_id]["progress"] = 100.0
                progress_tasks[task_id]["result"] = {"lat": lat, "lon": lon, "timestamps": [], "values": []}
            return

        values_out = []
        timestamps_out = []
        nc_var = ELEMENT_TO_NC_MAPPING.get(element)
        if not nc_var:
            raise ValueError(f"无效的要素名称: {element}")

        # 循环遍历每个小时
        for i, ts in enumerate(hourly_timestamps):
            try:
                file_path = find_nc_file_for_timestamp(element, ts)
                with xr.open_dataset(file_path) as ds:
                    value = ds[nc_var].sel(lat=lat, lon=lon, method='nearest').item()
                    if np.isnan(value):
                        values_out.append(None)
                    else:
                        values_out.append(float(value))
            except FileNotFoundError:
                values_out.append(None)
            
            timestamps_out.append(ts.to_pydatetime())

            # [核心] 直接更新共享字典中的进度
            with progress_lock:
                # 确保任务ID仍然存在 (可能用户取消了)
                if task_id in progress_tasks:
                    progress = ((i + 1) / total_timestamps) * 100
                    progress_tasks[task_id]["progress"] = round(progress, 2)
                    progress_tasks[task_id]["status"] = "PROCESSING"

        # 任务完成，存储最终结果
        final_result = {
            "lat": lat,
            "lon": lon,
            "timestamps": timestamps_out,
            "values": values_out
        }
        with progress_lock:
            if task_id in progress_tasks:
                progress_tasks[task_id]["status"] = "COMPLETED"
                progress_tasks[task_id]["result"] = final_result
                progress_tasks[task_id]["progress"] = 100.0

    except Exception as e:
        # 如果发生任何错误, 记录错误状态
        with progress_lock:
            if task_id in progress_tasks:
                progress_tasks[task_id]["status"] = "FAILED"
                progress_tasks[task_id]["error"] = str(e)
