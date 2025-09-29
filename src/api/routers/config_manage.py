# update_config.py
import json
from fastapi import APIRouter, HTTPException
from celery.result import AsyncResult
from ...core.schemas import ConfigRequest, DataSourceDirs, MessageResponse

app_config = {
    "station_data_path": "",
    "grid_data_path": "",
    "dem_data_path": "",
}

router = APIRouter(
    prefix="/config",
    tags=["Config"],
)


@router.post("/input", response_model=ConfigRequest)
def update_config(config: ConfigRequest):
    """
    根据前端输入的配置更新配置文件
    """
    return config


@router.put("/path", response_model=MessageResponse, summary="更新数据源目录路径")
def update_data_paths(paths: DataSourceDirs):
    """
    更新数据源目录路径
    """
    try:
        # 从API获取路径并更新配置对象
        app_config["station_data_path"] = str(paths.station_data_path)
        app_config["grid_data_path"] = str(paths.grid_data_path)

        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(app_config, f, ensure_ascii=False, indent=4)
        print("配置已更新", app_config)

        return MessageResponse(message="配置已更新")
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")


@router.get("/path", response_model=DataSourceDirs, summary="获取当前数据源目录路径")
def get_data_paths():
    """
    获取数据源目录路径
    """
    station_path = app_config.get("station_data_path")
    grid_path = app_config.get("grid_data_path")

    if not station_path or not grid_path:
        raise HTTPException(status_code=404, detail="尚未设置数据源的目录路径")

    return DataSourceDirs(station_data_path=station_path, grid_data_path=grid_path)