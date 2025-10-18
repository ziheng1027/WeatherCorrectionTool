# src/tasks/data_correct.py
import gc
import numpy as np
import xarray as xr
from pathlib import Path
from typing import List, Dict
from concurrent.futures import ProcessPoolExecutor, as_completed
from ..core.config import settings
from ..core.data_mapping import ELEMENT_TO_NC_MAPPING
from ..core.data_correct import build_feature_for_block
from ..utils.file_io import load_model, get_grid_files_for_season, create_file_packages


def correct_single_file(
        model: object, dem_ds: xr.Dataset, file_package: Dict, 
        element: str, year: str, block_size: int
) -> Path:
    """订正单个nc文件, 生成一张订正后的nc文件[原子性任务]"""
    try:
        nc_var = ELEMENT_TO_NC_MAPPING[element]
        current_file = file_package["current_file"]
        timestamp = file_package["timestamp"]
        lag_files = file_package["lag_files"]   # dict

        # 加载当前时刻的格点数据
        grid_ds = xr.open_dataset(current_file)
        # 创建一个空的、与输入数据同样大小和坐标的结果数组
        corrected_data = np.full_like(grid_ds[nc_var].values, np.nan, dtype=np.float32)

        # 空间分块循环
        lat_size, lon_size = grid_ds.sizes["lat"], grid_ds.sizes["lon"]
        for lat_start in range(0, lat_size, block_size):
            for lon_start in range(0, lon_size, block_size):
                lat_end = min(lat_start + block_size, lat_size)
                lon_end = min(lon_start + block_size, lon_size)
                
                # 获取当前空间块的数据
                grid_block_ds = grid_ds[nc_var][0, lat_start:lat_end, lon_start:lon_end]
                # 为当前空间块构建特征
                feature_df = build_feature_for_block(
                    grid_block_ds, dem_ds, lag_files, element, timestamp
                )

                # 使用模型进行预测
                corrected_block_data = model.predict(feature_df)
                
                # 回填结果
                corrected_nc_data = corrected_block_data.reshape(grid_block_ds.shape)
                corrected_data[0, lat_start:lat_end, lon_start:lon_end] = corrected_nc_data

                # 释放内存
                del feature_df, corrected_block_data, corrected_nc_data
                gc.collect()

        # 保存订正后的nc文件
        output_path = Path(settings.CORRECTION_OUTPUT_DIR) / f"{nc_var}.hourly" / year / f"corrected.{current_file.name}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 创建一个新的xarray.Dataset来保存结果
        corrected_ds = xr.Dataset(
            {nc_var: (["time", "lat", "lon"], corrected_data)},
            coords={"time": grid_ds.time, "lat": grid_ds.lat, "lon": grid_ds.lon}
        )
        corrected_ds.to_netcdf(output_path)
        grid_ds.close()
        return output_path
        
    except Exception as e:
        print(f"Error processing file {current_file}: {e}")
        return None
    

if __name__ == "__main__":
    model_path = r"output\models\xgboost\xgboost_温度_2020_2020_全年_id=19f2906b-980b-4e64-843e-1a9e48c1ed00.ckpt"
    model = load_model(model_path)

    dem_ds = xr.open_dataset(settings.DEM_DATA_PATH)
    grid_files = get_grid_files_for_season(settings.GRID_DATA_DIR, "tmp", "2020", "2020", "全年")
    file_packages = create_file_packages(grid_files, "温度", settings.LAGS_CONFIG)

    corrected_file_path = correct_single_file(model, dem_ds, file_packages[48], "温度", "2020", 20)
