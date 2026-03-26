# src/core/data_correct.py
import numpy as np
import pandas as pd
import xarray as xr
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional
from ..core.config import settings
from ..core.data_mapping import ELEMENT_TO_NC_MAPPING, NC_TO_DB_MAPPING
from ..utils.file_io import get_grid_files_for_season, create_file_packages


def build_feature_for_block(
        grid_block_ds: xr.DataArray,  dem_ds: xr.DataArray, 
        lag_files: Dict[str, Optional[Path]], element: str, timestamp: datetime,
) -> pd.DataFrame:
    """为单个空间块构建特征df"""
    nc_var = ELEMENT_TO_NC_MAPPING[element]
    db_var = NC_TO_DB_MAPPING[nc_var]
    # 展平数据并创建df
    grid_block_df = grid_block_ds.to_dataframe(name=f"{db_var}_grid").reset_index()

    # 添加时间特征
    grid_block_df["year"] = timestamp.year
    grid_block_df["month"] = timestamp.month
    grid_block_df["day"] = timestamp.day
    grid_block_df["hour"] = timestamp.hour
    
    # 添加滞后特征
    lags = settings.LAGS_CONFIG.get(element, [])
    # 创建特征列
    for lag in lags:
        lag_key = f"lag_{lag}h"
        db_lag_key = f"{db_var}_grid_{lag_key}"
        # 从传入的lag_files字典中安全获取文件路径
        lag_file = lag_files.get(lag_key)
        if lag_file and lag_file.exists():
            try:
                with xr.open_dataset(lag_file) as lag_ds:
                    lag_block_ds = lag_ds[nc_var].sel(
                        lat=grid_block_df["lat"].to_xarray(),
                        lon=grid_block_df["lon"].to_xarray(),
                        method="nearest"
                    )
                    grid_block_df[db_lag_key] = lag_block_ds.values.flatten()
            except Exception as e:
                print(f"|--> 警告: 读取滞后文件 {lag_file} 失败: {e}. 使用NaN填充")
                grid_block_df[db_lag_key] = np.nan
        else:
            # print(f"|--> 警告: 滞后文件 {lag_file} 不存在. 使用NaN填充")
            grid_block_df[db_lag_key] = np.nan
        
    # 添加地形特征
    terrain_feature = dem_ds.sel(
        lat=grid_block_df["lat"].to_xarray(),
        lon=grid_block_df["lon"].to_xarray(),
        method="nearest"
    )
    grid_block_df["elevation"] = terrain_feature["elevation"].values
    grid_block_df["slope"] = terrain_feature["slope"].values
    grid_block_df["aspect"] = terrain_feature["aspect"].values

    # 定义列的顺序
    base_columns = ["lat", "lon", "year", "month", "day", "hour"]
    grid_columns = [f"{db_var}_grid"]
    lag_columns = [f"{db_var}_grid_lag_{lag}h" for lag in lags]
    terrain_columns = ["elevation", "slope", "aspect"]
    # 重新排列列的顺序
    grid_block_df = grid_block_df[base_columns + grid_columns + lag_columns + terrain_columns]

    return grid_block_df



if __name__ == '__main__':
    grid_files = get_grid_files_for_season(settings.GRID_DATA_DIR, "wind_velocity", "2020", "2020", "全年")
    file_packages = create_file_packages(grid_files, "2分钟平均风速", settings.LAGS_CONFIG)
    print(file_packages[24])
    timestamp = file_packages[24]["timestamp"]
    lag_files = file_packages[24]["lag_files"]
    # print(lag_files)
    grid_ds = xr.open_dataset(file_packages[24]["current_file"])
    dem_ds = xr.open_dataset(settings.DEM_DATA_PATH)
    grid_block_ds = grid_ds["wind_velocity"][0: 100, 0:100]
    feature_df = build_feature_for_block(grid_block_ds, dem_ds, lag_files, "2分钟平均风速", timestamp)
    print(feature_df.head(24).iloc[:, :10])
    print(feature_df.shape)
    print(feature_df.columns)