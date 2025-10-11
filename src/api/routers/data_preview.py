# src/api/routers/data_preview.py
import uuid
from typing import List
from sqlalchemy.orm import Session
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from threading import Lock
from ...db import crud
from ...core import schemas
from ...core.config import settings
from ...core.data_mapping import get_name_to_id_mapping
from ...core.data_preview import get_grid_data_at_time, get_grid_time_series_for_coord
from ...db.database import SessionLocal, get_db


# 存储进度查询任务的状态
PROGRESS_TASKS = {}
progress_lock = Lock()

router = APIRouter(
    prefix="/data-preview",
    tags=["数据预览"],
)


@router.get("/stations", summary="获取所有站点名称和经纬度列表")
def get_all_station_info():
    """
    获取所有站点名称和经纬度
    """
    return {"station": list(get_name_to_id_mapping(settings.STATION_INFO_PATH).items())}


@router.post("/station-data", response_model=schemas.StationPreviewResponse, summary="获取站点时序数据")
def get_station_data(request: schemas.StationPreviewRequest, db: Session = Depends(get_db)):
    """
    根据站点名称、要素和时间范围, 查询对应的时序数据用于绘制折线图。
    """
    data = crud.get_raw_station_data(
        db,
        station_name=request.station_name,
        element=request.element,
        start_time=request.start_time,
        end_time=request.end_time
    )
    if not data:
        raise HTTPException(status_code=404, detail="未查询到相关站点数据")

    # 数据格式化
    response = {
        "station_name": data[0].station_name,
        "lat": data[0].lat,
        "lon": data[0].lon,
        "timestamps": [d.timestamp for d in data],
        "values": [getattr(d, "value") for d in data]
    }
    return response

@router.post("/grid-data", response_model=schemas.GridPreviewResponse, summary="获取指定时刻的格点数据")
def get_grid_data(request: schemas.GridDataRequest):
    """
    根据要素和时刻, 从.nc文件中读取完整的格点数据, 用于绘制热力图。
    """
    try:
        lats, lons, values = get_grid_data_at_time(
            element=request.element,
            timestamp=request.timestamp
        )
        return {
            "lats": lats.tolist(),
            "lons": lons.tolist(),
            "values": values.tolist()
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"未找到 {request.timestamp} 对应的格点数据文件")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/grid-time-series", response_model=schemas.TaskCreationResponse, summary="提交一个获取格点时间序列的后台任务")
def submit_grid_time_series_task(request: schemas.GridTimeSeriesRequest, background_tasks: BackgroundTasks):
    """
    提交一个后台任务来提取指定坐标和时间范围的格点数据时间序列。
    此接口会立即返回一个task_id, 前端需要使用此ID轮询状态接口。
    """
    task_id = str(uuid.uuid4())
    
    # 在任务开始前，在共享字典中为该任务创建一个占位符
    with progress_lock:
        # 清理旧的已完成任务, 防止内存增长
        for old_task_id, task_details in list(PROGRESS_TASKS.items()):
            if task_details["status"] in ["COMPLETED", "FAILED"]:
                del PROGRESS_TASKS[old_task_id]

        PROGRESS_TASKS[task_id] = {
            "status": "PENDING", # 状态: PENDING -> PROCESSING -> COMPLETED / FAILED
            "progress": 0.0,
            "result": None,
            "error": None
        }

    # [核心] 将真正的耗时函数作为后台任务添加
    # FastAPI会在发送响应后，在后台线程中运行此函数
    background_tasks.add_task(
        get_grid_time_series_for_coord,
        task_id=task_id,
        progress_tasks=PROGRESS_TASKS,
        progress_lock=progress_lock,
        element=request.element,
        lat=request.lat,
        lon=request.lon,
        start_time=request.start_time,
        end_time=request.end_time
    )

    # 立即返回，告知前端任务已创建
    return schemas.TaskCreationResponse(message="后台任务已创建", task_id=task_id)


@router.get("/grid-time-series/status/{task_id}", summary="查询格点时间序列任务的状态和结果")
def get_grid_time_series_status(task_id: str):
    """
    前端通过此接口轮询任务状态、进度和最终结果。
    当任务完成时 (`status`为"COMPLETED"), `result`字段会包含完整的数据。
    """
    with progress_lock:
        task = PROGRESS_TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        
        response = {
            "task_id": task_id,
            "status": task["status"], 
            "progress": task["progress"],
            "result": task["result"],
            "error": task["error"]
        }

    return response