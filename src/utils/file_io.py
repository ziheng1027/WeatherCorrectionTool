# src/utils/file_io.py
import os
import json
import glob
from pathlib import Path


CONFIG_FILE = Path("config/config.json")

def load_config_json():
    """根据默认路径来加载json配置文件"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {}

def save_config_json(config_data: dict):
    """将配置字典保存到json配置文件"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4, ensure_ascii=False)

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