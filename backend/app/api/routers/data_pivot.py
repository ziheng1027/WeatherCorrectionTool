# src/api/routers/data_pivot.py
import os
import json
import uuid
from pathlib import Path
from threading import Lock
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse
from ...db import crud
from ...db.database import get_db
from ...core import schemas
from ...core.config import settings
from ...core.data_mapping import ELEMENT_TO_DB_MAPPING, get_name_to_id_mapping
from ...core.data_pivot import get_grid_data_for_heatmap, get_correct_grid_time_series_for_coord
from ...tasks.data_pivot import evaluate_model, create_export_zip_task, create_export_images_task, evaluate_models_by_metrics
from ...utils.file_io import find_corrected_nc_file_for_timestamp


# 为数据透视模块的即时查询任务创建一个独立的内存存储和锁
PIVOT_PROGRESS_TASKS = {}
pivot_progress_lock = Lock()


router = APIRouter(
    prefix="/data-pivot",
    tags=["数据透视"],
)


@router.post("/processed-data", response_model=schemas.PivotDataProcessResponse, summary="获取预处理后的站点与格点对比数据")
def get_processed_data(request: schemas.PivotDataProcessRequest, db: Session = Depends(get_db)):
    """
    根据要素、站点和时间范围, 查询数据预处理后的站点观测值和对应的原始格点值, 用于绘制对比折线图。
    """
    try:
        # 调用CRUD函数查询数据
        station_mapping = get_name_to_id_mapping(settings.STATION_INFO_PATH)
        df = crud.get_proc_data_for_pivot(
            db,
            name_to_id_mapping=station_mapping,
            element=request.element,
            station_name=request.station_name,
            start_time=request.start_time,
            end_time=request.end_time
        )

        if df.empty:
            raise HTTPException(status_code=404, detail="未查询到指定条件下的预处理数据")

        # 获取数据库列名
        station_col = ELEMENT_TO_DB_MAPPING.get(request.element)
        grid_col = f"{station_col}_grid"

        # 构造响应体
        response_data = {
            "timestamps": df["timestamp"].tolist(),
            "station_values": df[station_col].tolist(),
            "grid_values": df[grid_col].tolist()
        }

        return schemas.PivotDataProcessResponse(**response_data)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {e}")


@router.post("/model-evaluation", response_model=schemas.TaskCreationResponse, summary="启动数据透视-模型评估任务")
def create_model_evaluate_task(
    request: schemas.PivotModelTrainRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """启动一个模型评估后台任务"""
    # 检查是否有同类型的任务正在运行
    processing_task_id = crud.is_task_type_processing(db, "PivotModelEvaluate")
    if processing_task_id:
        return schemas.TaskCreationResponse(
            message="已有同类型任务正在进行中，请等待其完成后再试",
            task_id=processing_task_id
        )
    # 检查指定时间范围内是否有数据
    station_mapping = get_name_to_id_mapping(settings.STATION_INFO_PATH)
    df_base = crud.get_proc_feature_for_pivot(
        db, 
        station_mapping,
        request.element, 
        request.station_name, 
        request.start_time, 
        request.end_time
    )
    if df_base.empty:
        raise HTTPException(status_code=404, detail="指定时间范围内没有数据")
    
    task_id = str(uuid.uuid4())
    task_name = f"数据透视-模型评估_{request.station_name}_{request.element}"
    
    # 将请求参数转换为可序列化存储的字典
    params = request.model_dump()
    params['model_paths'] = [str(p) for p in params.get('model_paths', [])]
    params['start_time'] = params.get('start_time').isoformat()
    params['end_time'] = params.get('end_time').isoformat()

    # 在数据库中创建任务记录
    crud.create_task(db, task_id, task_name, "PivotModelEvaluate", params)
    
    # 将实际耗时的操作添加到后台任务队列
    background_tasks.add_task(
        evaluate_model,
        task_id=task_id,
        element=request.element,
        station_name=request.station_name,
        start_time=request.start_time,
        end_time=request.end_time,
        model_paths=[str(model_path) for model_path in request.model_paths]
    )
    
    return {"message": "数据透视-模型分析任务已启动", "task_id": task_id}


@router.get("/model-evaluation/status/{task_id}", response_model=schemas.PivotModelTrainStatusResponse, summary="查询数据透视-模型评估任务状态")
def get_model_evaluate_status(task_id: str, db: Session = Depends(get_db)):
    """
    查询模型透视分析任务的状态、进度和最终结果。
    
    前端应轮询此接口以获取最新状态。当 status 为 "COMPLETED" 时，`results` 字段将包含分析结果。
    """
    task = crud.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务ID不存在")

    response_data = {
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.cur_progress,
        "progress_text": task.progress_text,
        "results": None
    }

    if task.status == "COMPLETED":
        params = task.get_params()
        result_path_str = params.get("result_path")
        if not result_path_str:
             raise HTTPException(status_code=404, detail="任务成功但结果文件路径未找到")

        result_path = Path(result_path_str)
        if result_path.exists():
            with open(result_path, 'r', encoding='utf-8') as f:
                results_json = json.load(f)
                # 将结果中的ISO格式时间字符串转换回datetime对象以符合响应模型
                results_json['timestamps'] = [datetime.fromisoformat(ts) for ts in results_json['timestamps']]
                response_data["results"] = results_json
        else:
            # 如果结果文件丢失，更新任务状态为失败
            crud.update_task_status(db, task.task_id, "FAILED", task.cur_progress, "任务失败：结果文件已丢失")
            raise HTTPException(status_code=404, detail="任务结果文件已丢失")

    return response_data


@router.post("/grid-data", response_model=schemas.PivotDataCorrectHeatmapResponse, summary="获取订正前后对比热力图数据")
def get_grid_data(request: schemas.GridDataRequest):
    """根据要素和时刻, 获取用于绘制订正前后对比热力图的格点数据"""
    try:
        find_corrected_nc_file_for_timestamp(request.element, request.timestamp)
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404, 
            detail={
                "message": f"指定时间: {request.timestamp}的订正数据不存在。是否需要执行包含该时段的订正任务？",
                "element": request.element,
                "timestamp": request.timestamp.isoformat()
            }
        )
    
    try:
        data = get_grid_data_for_heatmap(request.element, request.timestamp)
        return data
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {e}")


@router.post("/grid-data-timeseries", response_model=schemas.TaskCreationResponse, summary="启动订正前后对比曲线的数据提取任务")
def create_correct_timeseries_task(request: schemas.GridTimeSeriesRequest, background_tasks: BackgroundTasks):
    """启动一个提取订正前后对比曲线数据后台任务"""
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
        find_corrected_nc_file_for_timestamp(request.element, request.start_time)
        find_corrected_nc_file_for_timestamp(request.element, request.end_time)
    except FileNotFoundError:
        # 简单地提示时间范围内数据不完整
        raise HTTPException(
            status_code=404,
            detail={
                "message": f"指定时间范围: {request.start_time} -> {request.end_time} 的订正数据不完整或不存在。请确认是否执行了包含该时段的订正任务？",
                "element": request.element,
                "start_time": request.start_time.isoformat(),
                "end_time": request.end_time.isoformat()
            }
        )

    task_id = str(uuid.uuid4())
    
    with pivot_progress_lock:
        # 清理旧的已完成任务, 防止内存增长
        for old_task_id, task_details in list(PIVOT_PROGRESS_TASKS.items()):
            if task_details["status"] in ["COMPLETED", "FAILED"]:
                del PIVOT_PROGRESS_TASKS[old_task_id]

        PIVOT_PROGRESS_TASKS[task_id] = {
            "status": "PENDING",
            "progress": 0.0,
            "progress_text": "任务已提交, 等待执行...",
            "result": None,
            "error": None
        }

    background_tasks.add_task(
        get_correct_grid_time_series_for_coord,
        task_id=task_id,
        progress_tasks=PIVOT_PROGRESS_TASKS,
        progress_lock=pivot_progress_lock,
        element=request.element,
        lat=request.lat,
        lon=request.lon,
        start_time=request.start_time,
        end_time=request.end_time
    )
    return {"message": "数据透视-订正前后对比曲线数据提取任务已启动", "task_id": task_id}


@router.get("/grid-data-timeseries/status/{task_id}", response_model=schemas.PivotDataCorrectStatusResponse, summary="查询订正前后对比曲线任务状态")
def get_correct_timeseries_status(task_id: str):
    """查询提取订正前后对比曲线数据任务的状态和结果"""
    with pivot_progress_lock:
        task = PIVOT_PROGRESS_TASKS.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务ID不存在")

        # 构造响应
        response_data = {
            "task_id": task_id,
            "status": task["status"],
            "progress": task["progress"],
            "progress_text": task.get("progress_text", ""), # 兼容旧任务
            "results": task["result"],
            "error": task["error"]
        }

    return response_data


@router.post("/export-corrected-data", response_model=schemas.TaskCreationResponse, summary="启动订正数据打包导出任务")
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
        find_corrected_nc_file_for_timestamp(request.element, request.start_time)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, 
            detail={
                "message": f"起始时间: {request.start_time} 的订正格点数据不存在, 请确认当前指定时间是否存在订正格点数据",
                "element": request.element,
                "start_time": request.start_time.isoformat()
            }
        )
    try:
        find_corrected_nc_file_for_timestamp(request.element, request.end_time)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, 
            detail={
                "message": f"结束时间: {request.end_time} 的订正格点数据不存在, 请确认当前指定时间是否存在订正格点数据",
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


@router.post("/export-corrected-images", response_model=schemas.TaskCreationResponse, summary="启动订正数据(PNG)打包导出任务")
def export_corrected_images(
    request: schemas.DataExportRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    根据要素和时间范围, 启动一个后台任务, 将订正后的数据绘制为.png并压缩为.zip包。
    """
    # 验证逻辑与 .nc 导出相同
    try:
        find_corrected_nc_file_for_timestamp(request.element, request.start_time)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, 
            detail={
                "message": f"起始时间: {request.start_time} 的订正格点数据不存在, 无法生成图像",
                "element": request.element,
                "start_time": request.start_time.isoformat()
            }
        )
    try:
        find_corrected_nc_file_for_timestamp(request.element, request.end_time)
    except FileNotFoundError:
        raise HTTPException(
            status_code=404, 
            detail={
                "message": f"结束时间: {request.end_time} 的订正格点数据不存在, 无法生成图像",
                "element": request.element,
                "end_time": request.end_time.isoformat()
            }
        )
    
    task_id = str(uuid.uuid4())
    task_name = f"数据导出(PNG)_{request.element}_{request.start_time.date()}_{request.end_time.date()}"
    params = request.model_dump()

    params["start_time"] = params.get("start_time").isoformat()
    params["end_time"] = params.get("end_time").isoformat()

    # 使用新的任务类型 "DataExport_Image"
    crud.create_task(db, task_id, task_name, "DataExport_Image", params)

    background_tasks.add_task(
        create_export_images_task, # 调用新的任务函数
        task_id=task_id,
        element=request.element,
        start_time=request.start_time,
        end_time=request.end_time
    )
    return {"message": "数据导出(PNG)任务已启动", "task_id": task_id}


@router.get("/export-corrected-data/status/{task_id}", response_model=schemas.DataExportStatusResponse, summary="查询订正数据导出任务状态")
def get_export_status(task_id: str, db: Session = Depends(get_db)):
    """
    查询导出任务的状态。任务完成后, 'download_url' 字段将包含下载链接。
    """
    task = crud.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务ID不存在")
    
    # 检查任务类型是否为导出类型
    if task.task_type not in ["DataExport_NC", "DataExport_Image", "DataExport"]: # 兼容旧的 "DataExport"
        raise HTTPException(status_code=400, detail="任务ID非导出任务类型")

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
    if task.task_type == "DataExport_Image":
        file_name = f"corrected_images_{task.task_id[:8]}.zip"
    else: # 默认为 .nc 导出
        file_name = f"corrected_nc_data_{task.task_id[:8]}.zip"

    background_tasks.add_task(cleanup_temp_file, zip_path)
    
    return FileResponse(
        path=zip_path,
        filename=file_name,
        media_type='application/zip'
    )


@router.post("/model-ranking", response_model=schemas.TaskCreationResponse, summary="启动数据透视-模型排序任务")
def create_model_ranking_task(
    request: schemas.PivotModelRankingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """启动一个模型排序后台任务"""
    # 检查是否有同类型的任务正在运行
    processing_task_id = crud.is_task_type_processing(db, "PivotModelRanking")
    if processing_task_id:
        return schemas.TaskCreationResponse(
            message="已有同类型任务正在进行中，请等待其完成后再试",
            task_id=processing_task_id
        )

    task_id = str(uuid.uuid4())
    task_name = f"数据透视-模型排序_{request.element}_{request.season}"

    # 将请求参数转换为可序列化存储的字典
    params = request.model_dump()

    # 在数据库中创建任务记录
    crud.create_task(db, task_id, task_name, "PivotModelRanking", params)

    # 将实际耗时的操作添加到后台任务队列
    background_tasks.add_task(
        evaluate_models_by_metrics,
        task_id=task_id,
        element=request.element,
        season=request.season,
        test_set_values=request.test_set_values
    )

    return {"message": "数据透视-模型排序任务已启动", "task_id": task_id}


@router.get("/model-ranking/status/{task_id}", response_model=schemas.PivotModelRankingStatusResponse, summary="查询数据透视-模型排序任务状态")
def get_model_ranking_status(task_id: str, db: Session = Depends(get_db)):
    """
    查询模型排序任务的状态、进度和最终结果。

    前端应轮询此接口以获取最新状态。当 status 为 "COMPLETED" 时，`results` 字段将包含排序结果。
    """
    task = crud.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务ID不存在")

    response_data = {
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.cur_progress,
        "progress_text": task.progress_text,
        "results": None
    }

    if task.status == "COMPLETED":
        params = task.get_params()
        result_path_str = params.get("result_path")
        if not result_path_str:
             raise HTTPException(status_code=404, detail="任务成功但结果文件路径未找到")

        result_path = Path(result_path_str)
        if result_path.exists():
            with open(result_path, 'r', encoding='utf-8') as f:
                results_json = json.load(f)
                response_data["results"] = results_json
        else:
            # 如果结果文件丢失，更新任务状态为失败
            crud.update_task_status(db, task.task_id, "FAILED", task.cur_progress, "任务失败：结果文件已丢失")
            raise HTTPException(status_code=404, detail="任务结果文件已丢失")

    return response_data

