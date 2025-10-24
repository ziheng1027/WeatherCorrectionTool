# src/core/data_process.py
import os
import re
import glob
import pandas as pd
import numpy as np
import xarray as xr
from typing import Optional, Callable
from functools import reduce
from sqlalchemy.orm import Session
from ..db import crud
from ..core.config import settings
from ..core.data_mapping import cst_to_utc, NC_TO_DB_MAPPING



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
    if hasattr(settings, 'CST_YEARS') and int(year) in settings.CST_YEARS:
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

def import_proc_data_from_temp_files(db: Session, temp_dir: str, progress_callback: Optional[Callable[[int, int], None]] = None) -> dict:
    """从临时文件中导入处理后的数据"""
    print("|--> [Importer] 开始扫描临时文件...")
    parquet_files = glob.glob(os.path.join(temp_dir, "**/*.parquet"), recursive=True)
    
    if not parquet_files:
        print("|--> [Importer] 没有找到任何临时文件，导入过程结束。")
        return {"files_processed": 0, "total_rows_affected": 0, "message": "未找到临时文件"}
    
    # 按年份对文件分组
    grouped_files = {}
    for file in parquet_files:
        # 从文件名"element_year.parquet"中提取年份
        match = re.search(r'_(\d{4})\.parquet$', os.path.basename(file))
        if match:
            year = match.group(1)
            if year not in grouped_files:
                grouped_files[year] = []
            grouped_files[year].append(file)
    
    years_to_process = sorted(grouped_files.keys())
    total_years = len(years_to_process)
    total_rows_affected = 0
    print(f"|--> [Importer] 发现 {len(parquet_files)} 个文件, 按年份分为 {total_years} 组, 准备导入...")

    # 逐年处理
    for i, year in enumerate(years_to_process):
        year_files = grouped_files[year]
        # 读取该年份的所有element文件到df列表中
        df_list = [pd.read_parquet(file) for file in year_files if os.path.getsize(file) > 0]

        if not df_list:
            if progress_callback:
                progress_callback(i + 1, total_years)
            continue

        # 使用reduce合并当年的所有element的DataFrame
        merged_df = reduce(
            lambda left, right: pd.merge(
                left, right, 
                on=['station_id', 'station_name', 'lat', 'lon', 'timestamp', 'year', 'month', 'day', 'hour'], 
                how='outer'),
            df_list
        )
        print(f"|--> [Importer] 正在将 {year} 年的 {len(df_list)} 个文件({len(merged_df)}行)合并数据写入数据库...")
        rows_affected = crud.upsert_proc_station_grid_data(db, merged_df)
        total_rows_affected += rows_affected if rows_affected else 0

        if progress_callback:
            progress_callback(i + 1, total_years)

    final_message = f"数据导入完成, 共处理 {len(parquet_files)} 个文件, ({total_years}年), 写入/更新 {total_rows_affected} 行数据"
    print(f"|--> [Importer] {final_message}")
    return {
        "files_processed": len(parquet_files),
        "total_rows_affected": total_rows_affected,
        "message": final_message
    }