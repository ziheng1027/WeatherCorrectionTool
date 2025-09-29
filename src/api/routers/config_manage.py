# update_config.py
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from celery.result import AsyncResult
from ...core.schemas import ConfigRequest, DataSourceDirs, MessageResponse
from ...core.config import settings
from ...utils.file_io import load_config_json, save_config_json


router = APIRouter(
    prefix="/settings",
    tags=["settings"],
)


@router.put("/source-dirs", response_model=MessageResponse, summary="更新数据源目录路径")
def update_source_data_dirs(dirs: DataSourceDirs):
    """接收前端输入的站点和格点数据目录, 并安全地更新 config.json 文件"""
    try:
        cur_config = load_config_json()
        cur_config["station_data_dir"] = str(dirs.station_data_dir)
        cur_config["grid_data_dir"] = str(dirs.grid_data_dir)
        # 将更新后的配置写入原来的配置文件
        save_config_json(cur_config)
        return MessageResponse(message="数据源目录路径更新成功")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置文件失败: {str(e)}")
    

@router.get("/all-config-info", summary="获取当前所有配置信息")
def get_all_config():
    """获取当前所有配置信息"""
    return load_config_json()