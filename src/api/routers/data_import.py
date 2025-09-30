# src/api/data_import.py
import uuid
from threading import Thread
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from ...core.schemas import (
    TaskCreationResponse, TaskStatusResponse, SubTaskStatusResponse, TaskDetailsResponse,
    MessageResponse, FileListResponse
)
from ...db import crud
from ...db.database import SessionLocal
from ...tasks.data_import import run_station_data_import
from ...utils.file_io import load_config_json, get_station_files


router = APIRouter(
    prefix="/data-import",
    tags=["Data Import"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/check", response_model=FileListResponse, summary="检查文件数量并返回文件列表")
def check_files(db: Session = Depends(get_db)):
    """检查文件数量并返回文件列表"""
    config = load_config_json()
    station_data_dir = config["station_data_dir"]
    file_list = get_station_files(station_data_dir)
    return FileListResponse(count=len(file_list), files=file_list)


@router.post("/start", response_model=TaskCreationResponse, summary="启动数据导入任务")
def start_data_import(db: Session = Depends(get_db)):
    """启动数据导入任务"""
    config = load_config_json()
    task_id = str(uuid.uuid4())

    # 在数据库预创建任务记录, 标记"排队中PENDING"
    task_params = {"station_data_dir": config["station_data_dir"]}
    
    try:
        crud.create_task(db, task_id, "站点数据导入数据库", "DataImport", task_params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")
    
    # 启动任务, target是线程要执行的函数, args是传递给该函数的参数
    thread = Thread(target=run_station_data_import, args=(task_id, task_params["station_data_dir"]))
    thread.start()

    return TaskCreationResponse(message="数据导入任务已启动", task_id=task_id)


@router.get("/status/{task_id}", response_model=TaskStatusResponse, summary="查询任务总体状态(父任务)")
def get_task_status(task_id: str, db: Session = Depends(get_db)):
    """查询任务状态"""
    task = crud.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        progress={"percent": task.cur_progress, "text": task.progress_text}
    )


@router.get("/status/{task_id}/details", response_model=TaskDetailsResponse, summary="查询任务详细状态(包含子任务)")
def get_task_details(task_id: str, db: Session = Depends(get_db)):
    """查询父任务的总体状态及其所有子任务的详细列表"""
    # 获取父任务
    parent_task = crud.get_task_by_id(db, task_id)
    if not parent_task:
        raise HTTPException(status_code=404, detail="父任务不存在")
    # 获取所有子任务
    sub_tasks_db = crud.get_subtasks_by_parent_id(db, task_id)
    # 组装响应数据
    parent_status = TaskStatusResponse(
        task_id=parent_task.task_id,
        status=parent_task.status,
        progress={"percent": parent_task.cur_progress, "text": parent_task.progress_text}
    )
    sub_tasks_status = [
        SubTaskStatusResponse(
            task_id=st.task_id,
            task_name=st.task_name,
            status=st.status,
            progress_text=st.progress_text
        ) for st in sub_tasks_db
    ]
    # 按照 PENDING, PROCESSING, COMPLETED, FAILED 顺序对子任务排序, 便于前端展示
    status_order = {"PENDING": 0, "PROCESSING": 1, "COMPLETED": 2, "FAILED": 3}
    sub_tasks_status.sort(key=lambda x: status_order.get(x.status, 4))
    return TaskDetailsResponse(parent=parent_status, sub_tasks=sub_tasks_status)


@router.get("/history", summary="获取历史任务列表")
def get_task_history(skip: int = 0, limit: int = 82, db: Session = Depends(get_db)):
    """获取历史任务列表"""
    tasks = crud.get_all_tasks(db, skip=skip, limit=limit)
    return tasks