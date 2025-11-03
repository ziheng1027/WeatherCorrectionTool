# src/api/routers/data_process.py
import uuid
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException
from ...db import crud
from ...db.database import get_db
from ...core import schemas
from ...core.config import STOP_EVENT
from ...tasks.data_process import process_mp


router = APIRouter(
    prefix="/data-process",
    tags=["数据处理"],
)


@router.post("/start", response_model=schemas.TaskCreationResponse, status_code=202, summary="启动数据处理任务")
def start_data_process(
    request: schemas.DataProcessingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    启动一个后台数据处理任务。

    - **elements**: 要处理的气象要素列表。
    - **start_year**: 起始年份。
    - **end_year**: 结束年份。

    此API会立即返回一个任务ID, 可以使用该ID轮询任务状态。
    """
    # 检查是否有正在进行的任务
    processing_task_id = crud.is_task_type_processing(db, task_type="DataProcess")
    if processing_task_id:
        raise HTTPException(status_code=409, detail=f"有正在进行的任务: {processing_task_id}, 请等待其完成后再启动新任务")
        
    # 在启动新任务前, 清除旧的停止信号
    STOP_EVENT.clear()
    task_id = str(uuid.uuid4())
    task_name = f"数据处理: {', '.join(request.elements)} ({request.start_year}-{request.end_year})"
    
    # 1. 在数据库中创建任务记录
    task = crud.create_task(
        db,
        task_id=task_id,
        task_name=task_name,
        task_type="DataProcess",
        params=request.model_dump()
    )

    # 2. 将耗时的 `process_mp` 函数作为后台任务运行
    background_tasks.add_task(
        process_mp,
        task_id=task.task_id,
        elements=request.elements,
        start_year=request.start_year,
        end_year=request.end_year,
        num_workers=request.num_workers
    )

    return {
        "message": "数据处理任务已成功启动",
        "task_id": task.task_id
    }


@router.get("/global/pending", summary="【全局】获取所有待处理的任务列表")
def get_all_pending_files(db: Session = Depends(get_db)):
    """
    查询历史上所有待处理的任务列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="DataProcess_SubTask", status="PENDING")
    return task_params


@router.get("/global/processing", summary="【全局】获取所有处理中的任务列表")
def get_all_processing_files(db: Session = Depends(get_db)):
    """
    查询历史上所有处理中的任务列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="DataProcess_SubTask", status="PROCESSING")
    return task_params


@router.get("/global/completed", summary="【全局】获取所有已完成的任务列表")
def get_all_completed_files(db: Session = Depends(get_db)):
    """
    查询历史上所有成功的任务列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="DataProcess_SubTask", status="COMPLETED")
    return task_params


@router.get("/global/failed", summary="【全局】获取所有失败的任务列表")
def get_all_failed_files(db: Session = Depends(get_db)):
    """
    查询历史上所有失败的文件名列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="DataProcess_SubTask", status="FAILED")
    return task_params