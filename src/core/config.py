from typing import Dict
from pathlib import Path
from pydantic import BaseModel, DirectoryPath, FilePath
from pydantic_settings import BaseSettings, SettingsConfigDict
from ..utils.file_io import load_config_json


class Settings(BaseSettings):
    """配置文件读取类"""
    config: Dict[str, str] = load_config_json()
    STATION_DATA_DIR: DirectoryPath = DirectoryPath(config.get("station_data_dir", ""))
    GRID_DATA_DIR: DirectoryPath = DirectoryPath(config.get("grid_data_dir", ""))
    
    STATION_INFO_PATH: FilePath = FilePath(config.get("station_info_path", ""))
    DEM_DATA_PATH: FilePath = FilePath(config.get("dem_data_path", ""))

    MODELS_OUTPUT_DIR: Path = Path(config.get("models_output_dir", ""))
    CORRECTION_OUTPUT_DIR: Path = Path(config.get("correction_output_dir", ""))

    AVAILABLE_ELEMENTS: list[str] = ["温度", "相对湿度", "1小时降水量", "2分钟平均风速"]


settings = Settings()