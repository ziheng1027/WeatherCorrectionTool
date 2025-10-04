# src/utils/file_io.py
import os
import json
import glob
from pathlib import Path
from datetime import datetime
from pathlib import Path
from ..core.config import settings
from ..core.data_mapping import ELEMENT_TO_NC_VAR_MAPPING



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

def find_nc_file_for_timestamp(element: str, timestamp: datetime) -> Path:
    """根据要素和时间戳定位对应的.nc文件"""
    nc_var = ELEMENT_TO_NC_VAR_MAPPING.get(element)
    if not nc_var:
        raise ValueError(f"无效的要素名称: {element}")

    # 构建文件路径: CARAS/tmp.hourly/2008/xxx.nc
    file_name = f"CARAS.{timestamp.strftime('%Y%m%d%H')}.{nc_var}.hourly.nc"
    file_path = Path(settings.GRID_DATA_DIR) / f"{nc_var}.hourly" / str(timestamp.year) / file_name

    if not file_path.exists():
        raise FileNotFoundError(f"格点文件不存在: {file_path}")
    
    return file_path

