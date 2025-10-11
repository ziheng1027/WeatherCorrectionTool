# src/core/model_train.py
import os
import json
import numpy as np
import pandas as pd
import xarray as xr


def get_season(month):
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

def get_terrain_feature(ds, lat, lon):
    """根据经纬度提取海拔, 坡度, 坡向"""
    elevation = float(ds['elevation'].sel(lat=lat, lon=lon, method='nearest').values)
    slope = float(ds['slope'].sel(lat=lat, lon=lon, method='nearest').values)
    aspect = float(ds['aspect'].sel(lat=lat, lon=lon, method='nearest').values)
    return elevation, slope, aspect

def get_lags_feature(df, lags_config):
        """获取滞后特征"""
        lags_df = pd.DataFrame()
        vars_grid = [
            ("tmp", "温度_grid"),
            ("rh", "相对湿度_grid"),
            ("pre", "过去1小时降水量_grid"),
            ("wind_velocity", "2分钟平均风速_grid")
        ]
        for ori_var, new_var in vars_grid:
            # 只处理数据中存在的变量
            if ori_var in df.columns:
                lags = lags_config[new_var]
                for lag in lags:
                    lags_df[f"{new_var}_lag{lag}h"] = df[ori_var].shift(lag)
                lags_df[new_var] = df[ori_var]
        return lags_df