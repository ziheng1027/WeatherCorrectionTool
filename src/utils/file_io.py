# src/utils/file_io.py
import os
import json
import glob
import xarray as xr
from pathlib import Path
from datetime import datetime
from pathlib import Path
from ..core.config import settings
from ..core.data_mapping import ELEMENT_TO_NC_MAPPING



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
    nc_var = ELEMENT_TO_NC_MAPPING.get(element)
    if not nc_var:
        raise ValueError(f"无效的要素名称: {element}")

    # 构建文件路径: CARAS/tmp.hourly/2008/xxx.nc
    file_name = f"CARAS.{timestamp.strftime('%Y%m%d%H')}.{nc_var}.hourly.nc"
    file_path = Path(settings.GRID_DATA_DIR) / f"{nc_var}.hourly" / str(timestamp.year) / file_name

    if not file_path.exists():
        raise FileNotFoundError(f"格点文件不存在: {file_path}")
    
    return file_path

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