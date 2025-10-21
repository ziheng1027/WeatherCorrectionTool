# src/core/data_pivot.py
import pandas as pd
import xarray as xr
from .config import settings
from .data_mapping import ELEMENT_TO_DB_MAPPING
# 复用模型训练中的特征工程函数
from .model_train import get_terrain_feature


def bulid_feature_for_pivot(df: pd.DataFrame, element: str) -> pd.DataFrame:
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
    df = df[feature_columns]

    return df

