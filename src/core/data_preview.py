# src/core/data_preview.py
import xarray as xr
import pandas as pd
import numpy as np
from datetime import datetime
from ..core.data_mapping import ELEMENT_TO_NC_VAR_MAPPING
from ..utils.file_io import find_nc_file_for_timestamp


def get_grid_data_at_time(element: str, timestamp: datetime):
    """
    获取指定要素和时刻的完整格点数据。

    :param element: 要素名称 (例如: "温度")
    :param timestamp: 具体时刻
    :return: lats(纬度数组), lons(经度数组), values(二维数值数组)
    """
    file_path = find_nc_file_for_timestamp(element, timestamp)
    nc_var = ELEMENT_TO_NC_VAR_MAPPING[element]

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
    
def get_grid_time_series_for_coord(element: str, lat: float, lon: float, start_time: datetime, end_time: datetime):
    """
    获取指定坐标和时间范围内的格点数据时间序列。

    :param element: 要素名称 (例如: "温度")
    :param lat: 纬度
    :param lon: 经度
    :param start_time: 开始时间
    :param end_time: 结束时间
    :return: timestamps(时间戳列表), values(数值列表)
    """
    # 1. 使用pandas生成每小时的时间戳序列
    hourly_timestamps = pd.date_range(start=start_time, end=end_time, freq='H')
    
    values_out = []
    timestamps_out = []

    nc_var = ELEMENT_TO_NC_VAR_MAPPING.get(element)
    if not nc_var:
        raise ValueError(f"无效的要素名称: {element}")

    # 2. 循环遍历每个小时
    for ts in hourly_timestamps:
        try:
            # 2.1 定位当前时间戳对应的.nc文件
            file_path = find_nc_file_for_timestamp(element, ts)
            
            # 2.2 使用xarray打开文件并提取数据
            with xr.open_dataset(file_path) as ds:
                # 使用 .sel 方法和 'nearest' 策略找到最近点的值
                value = ds[nc_var].sel(lat=lat, lon=lon, method='nearest').item()
                
                # xarray可能会返回numpy的浮点数类型，转换为标准的Python float
                if np.isnan(value):
                    values_out.append(None)
                else:
                    values_out.append(float(value))

        except FileNotFoundError:
            # 如果某个小时的文件找不到，我们记录一个None值
            values_out.append(None)
        except Exception as e:
            # 其他潜在错误（如文件损坏、变量名错误），同样记录None
            print(f"处理时间 {ts} 时出错: {e}")
            values_out.append(None)
        
        timestamps_out.append(ts)

    return timestamps_out, values_out