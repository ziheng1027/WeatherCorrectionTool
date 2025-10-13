# src/core/model_train.py
import os
import numpy as np
import pandas as pd
import xarray as xr
from sqlalchemy.orm import Session
from ..db import crud
from ..core.data_mapping import ELEMENT_TO_DB_MAPPING
from ..core.config import settings, load_model_config


def get_season(month: int) -> str:
    """根据月份划分季节"""
    if month in [3, 4, 5]:
        return '春季'
    elif month in [6, 7, 8]:
        return '夏季'
    elif month in [9, 10, 11]:
        return '秋季'
    elif month in [12, 1, 2]:
        return '冬季'
    else:
        return '未知(0-12月以外的月份)'

def get_terrain_feature(dem_ds: xr.Dataset, lat: str, lon: str) -> tuple:
    """根据经纬度提取海拔, 坡度, 坡向"""
    try:
        point = dem_ds.sel(lat=lat, lon=lon, method='nearest')
        elevation = float(point['elevation'].values)
        slope = float(point['slope'].values)
        aspect = float(point['aspect'].values)
        return elevation, slope, aspect
    
    except Exception as e:
        print(f"提取地形特征失败(lat:{lat}, lon:{lon}): {e}")
        return None, None, None

def build_dataset_from_db(
        db: Session, dem_file: str, lags_config: dict, element: str, 
        start_year: str, end_year: str, season: str
    ):
    """指定要素, 起止年份, 季节构建数据集"""
    # 读取地形数据
    dem_ds = xr.open_dataset(dem_file)
    # 根据起始年份从数据库读取数据df
    df = crud.get_proc_data_to_build_dataset(db, element, start_year, end_year)
    # 添加季节用于分组
    df['season'] = df['month'].apply(get_season)
    if season in ['春季', '夏季', '秋季', '冬季']:
        df = df[df['season'] == season]
    
    element_db_column = ELEMENT_TO_DB_MAPPING[element]
    lags = lags_config[element]
    all_station_df = []
    
    # 按照站点分组
    station_dfs = df.groupby('station_id')
    for station_id, station_df in station_dfs:
        print(f"构建数据集... 当前处理站点: {station_id}")
        station_df = station_df.sort_values(by=['year', 'month', 'day', 'hour']).reset_index(drop=True)
        # 添加滞后特征
        for lag in lags:
            station_df[f"{element_db_column}_grid_lag_{lag}"] = station_df[f"{element_db_column}_grid"].shift(lag)
        station_df.dropna(inplace=True)
        # 添加地形特征
        lat, lon = station_df.iloc[0]['lat'], station_df.iloc[0]['lon']
        elevation, slope, aspect = get_terrain_feature(dem_ds, lat, lon)
        station_df["elevation"] = elevation
        station_df["slope"] = slope
        station_df["aspect"] = aspect

        all_station_df.append(station_df)
    
    # 合并所有站点
    dataset = pd.concat(all_station_df, axis=0, ignore_index=True)
    print(f"构建完成的数据集形状: {dataset.shape}")

    return dataset
    
def split_dataset(dataset: pd.DataFrame, element: str, split_method: str, test_years: list[str], test_stations: list[str]):
    """划分数据[by_year, by_station], 返回train_X, train_y, test_X, test_y"""
    if split_method == "by_year":
        train_dataset = dataset[~dataset["年"].isin(test_years)].iloc[:, 2:]  # 前两列是站号和站名
        test_dataset = dataset[dataset["年"].isin(test_years)].iloc[:, 2:]
    elif split_method == "by_station":
        train_dataset = dataset[~dataset["station_name"].isin(test_stations)].iloc[:, 2:]
        test_dataset = dataset[dataset["station_name"].isin(test_stations)].iloc[:, 2:]
    else:
        raise ValueError(f"不支持的数据集划分方法: {split_method}")
    
    element_db_column = ELEMENT_TO_DB_MAPPING[element]
    label_col = element_db_column
    train_X = train_dataset.drop(columns=["season", label_col])
    train_y = train_dataset[label_col]
    test_X = test_dataset.drop(columns=["season", label_col])
    test_y = test_dataset[label_col]

    return train_X, train_y, test_X, test_y

def build_model(model_name: str, element: str, start_year: str, end_year: str, season: str):
    """根据传入的模型名称构建模型实例"""
    # 加载模型配置文件
    model_name = model_name.lower()
    model_config_dir = settings.MODEL_CONFIG_DIR
    model_config_name = f"{model_name}_{element}_{start_year}_{end_year}_{season}.json"
    model_config_path = os.path.join(model_config_dir, model_name, model_config_name)
    model_config = load_model_config(model_config_path)

    # 定义模型实例
    if model_name == "xgboost":
        from xgboost import XGBRegressor
        model = XGBRegressor(**model_config)
    elif model_name == "lightgbm":
        from lightgbm import LGBMRegressor
        model = LGBMRegressor(**model_config)
    else:
        raise ValueError(f"暂不支持的模型: {model_name}")

    return model

def train_model(model, train_X: pd.DataFrame, train_y: pd.Series):
    """训练模型"""
    pass

def evaluate_model(model, test_X: pd.DataFrame, test_y: pd.Series):
    """评估模型"""
    pass

def get_feature_importance(model, test_X: pd.DataFrame):
    """获取特征重要性"""
    pass

def save_model(model, model_dir: str):
    """保存模型"""
    pass

def load_model(model_dir: str):
    """加载模型"""
    pass


if __name__ == "__main__":
    from ..db.database import SessionLocal
    db = SessionLocal()
    dataset = build_dataset_from_db(db, settings.DEM_DATA_PATH, settings.LAGS_CONFIG, "温度", "2020", "2021", "全年")
    train_X, train_y, test_X, test_y = split_dataset(dataset, "温度", "by_station", [], ["老河口", "十堰", "武穴"])
    
