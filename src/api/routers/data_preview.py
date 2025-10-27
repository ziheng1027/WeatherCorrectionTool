# src/api/routers/data_preview.py
import os
import uuid
from pathlib import Path
from sqlalchemy.orm import Session
from fastapi.responses import FileResponse
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from threading import Lock
from ...db import crud
from ...db.database import get_db
from ...core import schemas
from ...core.config import settings
from ...core.data_mapping import get_name_to_id_mapping
from ...core.data_preview import get_grid_data_at_time, get_grid_time_series_for_coord
from ...utils.file_io import find_nc_file_for_timestamp
from ...tasks.data_preview import create_export_zip_task


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
    # 坐标范围验证
    if not (28.899 <= request.lat <= 33.361 and 108.249 <= request.lon <= 116.251):
        raise HTTPException(
            status_code=400,
            detail={
                "message": "请求的坐标超出有效范围",
                "valid_lat_range": "28.90 - 33.36",
                "valid_lon_range": "108.25 - 116.25",
                "requested_lat": request.lat,
                "requested_lon": request.lon
            }
        )
    try:
        # 检查时间范围的起始和结束时刻是否存在订正文件
        find_nc_file_for_timestamp(request.element, request.start_time)
        find_nc_file_for_timestamp(request.element, request.end_time)
    except FileNotFoundError:
        # 简单地提示时间范围内数据不完整
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"指定时间范围: {request.start_time} -> {request.end_time} 的格点数据不完整或不存在。请确认是否存在该时段的格点数据？",
                "element": request.element,
                "start_time": request.start_time.isoformat(),
                "end_time": request.end_time.isoformat()
            }
        )

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


@router.post("/export-grid-data", response_model=schemas.TaskCreationResponse, summary="启动格点数据打包导出任务")
def export_corrected_data(
    request: schemas.DataExportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    根据要素和时间范围, 启动一个后台任务, 将订正后的.nc文件压缩为.zip包。
    """
    # 检查起止日期的格点数据是否存在
    try:
        find_nc_file_for_timestamp(request.element, request.start_time)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, 
            detail={
                "message": f"起始时间: {request.start_time} 的格点数据不存在, 请确认当前指定时间是否存在格点数据",
                "element": request.element,
                "start_time": request.start_time.isoformat()
            }
        )
    try:
        find_nc_file_for_timestamp(request.element, request.end_time)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, 
            detail={
                "message": f"结束时间: {request.end_time} 的格点数据不存在, 请确认当前指定时间是否存在格点数据",
                "element": request.element,
                "end_time": request.end_time.isoformat()
            }
        )
    
    task_id = str(uuid.uuid4())
    task_name = f"数据导出_{request.element}_{request.start_time.date()}_{request.end_time.date()}"
    params = request.model_dump()

    # 转换datetime为字符串以便存入数据库
    params["start_time"] = params.get("start_time").isoformat()
    params["end_time"] = params.get("end_time").isoformat()

    crud.create_task(db, task_id, task_name, "DataExport", params)

    background_tasks.add_task(
        create_export_zip_task,
        task_id=task_id,
        element=request.element,
        start_time=request.start_time,
        end_time=request.end_time
    )
    return {"message": "数据导出任务已启动", "task_id": task_id}


@router.get("/export-grid-data/status/{task_id}", response_model=schemas.DataExportStatusResponse, summary="查询格点数据导出任务状态")
def get_export_status(task_id: str, db: Session = Depends(get_db)):
    """
    查询导出任务的状态。任务完成后, 'download_url' 字段将包含下载链接。
    """
    task = crud.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务ID不存在")

    response_data = {
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.cur_progress,
        "progress_text": task.progress_text,
        "download_url": None
    }
    
    if task.status == "COMPLETED":
        # 任务成功, 动态构建下载URL
        response_data["download_url"] = f"/data-pivot/download-export/{task_id}"

    return response_data


def cleanup_temp_file(file_path: Path):
    """
    在后台任务中安全删除文件。
    """
    try:
        if file_path.exists():
            os.remove(file_path)
            print(f"临时文件已删除: {file_path}")
    except OSError as e:
        print(f"删除临时文件 {file_path} 出错: {e}")


@router.get("/download-export/{task_id}", response_class=FileResponse, summary="下载导出的ZIP文件")
def download_export_file(task_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    提供给前端的最终下载接口。
    """
    task = crud.get_task_by_id(db, task_id)
    if not task or task.status != "COMPLETED":
        raise HTTPException(status_code=404, detail="任务不存在或尚未完成")

    params = task.get_params()
    zip_path_str = params.get("result_path")
    if not zip_path_str:
        raise HTTPException(status_code=404, detail="任务结果文件路径未找到")

    zip_path = Path(zip_path_str)
    if not zip_path.exists():
        raise HTTPException(status_code=404, detail="任务结果文件已丢失")

    # 从任务参数中动态生成文件名, 增加可读性
    file_name = f"grid_data_{task.task_id[:8]}.zip"

    background_tasks.add_task(cleanup_temp_file, zip_path)
    
    return FileResponse(
        path=zip_path,
        filename=file_name,
        media_type='application/zip'
    )
