# src/core/data_correct.py
import os
import pandas as pd
import xarray as xr
import numpy as np
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
import psutil

from ..core.model_train import get_season, get_terrain_feature


# 并行配置
MAX_WORKERS = min(8, psutil.cpu_count(logical=False))  # 物理核心数
MEMORY_LIMIT_GB = 16  # 内存限制
GRID_BLOCK_SIZE = 100  # 格点分块大小


def build_feature_for_region(
        dem_file: str, lags_config: dict, element: str, year: str, season: str,
        start_lat: float, end_lat: float, start_lon: float, end_lon: float
) -> pd.DataFrame:
    """为指定区域构建单年的特征数据"""
    # 读取地形数据
    dem_ds = xr.open_dataset(dem_file)
    

