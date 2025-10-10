# src/core/config.py
import json
import threading
from typing import Dict, List, Any
from pathlib import Path
from pydantic import BaseModel, DirectoryPath, FilePath
from pydantic_settings import BaseSettings, SettingsConfigDict


# 全局的停止事件
STOP_EVENT = threading.Event()
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


class Settings(BaseSettings):
    """配置文件读取类"""
    config: Dict[str, Any] = load_config_json()
    STATION_DATA_DIR: DirectoryPath = DirectoryPath(config.get("station_data_dir", ""))
    GRID_DATA_DIR: DirectoryPath = DirectoryPath(config.get("grid_data_dir", ""))
    
    STATION_INFO_PATH: FilePath = FilePath(config.get("station_info_path", ""))
    DEM_DATA_PATH: FilePath = FilePath(config.get("dem_data_path", ""))

    MODELS_OUTPUT_DIR: Path = Path(config.get("models_output_dir", ""))
    CORRECTION_OUTPUT_DIR: Path = Path(config.get("correction_output_dir", ""))

    AVAILABLE_ELEMENTS: list[str] = ["温度", "相对湿度", "过去1小时降水量", "2分钟平均风速"]
    CST_YEARS: List[int] = config.get("cst_years", [])


settings = Settings()