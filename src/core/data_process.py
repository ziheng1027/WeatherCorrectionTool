# src/core/data_process.py
import os
import pandas as pd
import numpy as np
import xarray as xr
from datetime import datetime

from ..db import crud
from ..utils import file_io
from ..core.data_mapping import cst_to_utc, ELEMENT_TO_DB_MAPPING, ELEMENT_TO_NC_MAPPING, NC_TO_DB_MAPPING
from ..core.config import settings


def clean_station_data(df: pd.DataFrame) -> pd.DataFrame:
    """清洗站点数据"""
    df_cleaned = df.copy()
    # 1. 将异常值转换为缺失值
    df_cleaned.loc[df_cleaned['station_value'] > 9999, 'station_value'] = np.nan
    # 处理缺失值: 三次样条插值/线性插值/直接删除
    if df_cleaned['station_value'].isnull().sum() > 0:
        try:
            df_cleaned['station_value'] = df_cleaned['station_value'].interpolate(method="spline", order=3)
        except:
            try:
                df_cleaned['station_value'] = df_cleaned['station_value'].interpolate(method="linear")
            except:
                df_cleaned = df_cleaned.dropna(subset=['station_value'])
    return df_cleaned

def extract_grid_values_for_stations(ds, var_grid: str, station_coords: dict, year: str) -> pd.DataFrame:
    """从数据集中提取网格值"""
    print(f"|-->({year}, {var_grid}) 正在提取所有站点的格点值...")
    lats = [info["lat"] for info in station_coords.values()]
    lons = [info["lon"] for info in station_coords.values()]
    station_ids = list(station_coords.keys())
    sel_data = ds[var_grid].sel(
        lat=xr.DataArray(lats, dims="station"), 
        lon=xr.DataArray(lons, dims="station"), 
        method="nearest"
    )
    df = sel_data.to_dataframe().reset_index()

    # 将grid_var列重命名为DB中的列名
    db_column_name = NC_TO_DB_MAPPING.get(var_grid)
    df.rename(columns={var_grid: f"{db_column_name}_grid"}, inplace=True)

    # 添加站点ID映射
    df["station_id_grid"] = df["station"].apply(lambda x: station_ids[x])
    df.drop(columns=["station", "lat", "lon"], inplace=True)

    # 北京时转换为世界时
    if hasattr(settings, 'CST_YEARS') and year in settings.CST_YEARS:
        df["time"] = cst_to_utc(df["time"])
    return df

def merge_sg_df(df_station: pd.DataFrame, df_grid: pd.DataFrame, element: str) -> pd.DataFrame:
    """合并站点数据以及根据每个站点提取出来的格点数据"""
    # 统一站点ID的数据类型为字符串
    df_station['station_id'] = df_station['station_id'].astype(str)
    df_grid['station_id_grid'] = df_grid['station_id_grid'].astype(str)
    # time的格式为2020010100, timestamp的格式为2020-01-01 00:00:00, 需要将time的格式转换为timestamp
    df_grid['time'] = pd.to_datetime(df_grid['time'], format='%Y%m%d%H')
    df_merged = pd.merge(df_station, df_grid, left_on=['station_id', 'timestamp'], right_on=['station_id_grid', 'time'], how="inner")
    df_merged.drop(columns=['time', 'station_id_grid'], inplace=True)
    return df_merged