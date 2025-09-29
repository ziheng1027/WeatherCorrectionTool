# src/api/data_import.py
import uuid
from threading import Thread
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from ...core.schemas import TaskCreationResponse, TaskStatusResponse, DataImportRequest
from ...db import crud
from ...db.database import SessionLocal
from ...tasks.data_import import run_station_data_import
from ...utils.file_io import load_config_json


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

@router.post("/start", response_model=TaskCreationResponse, summary="启动数据导入任务")
def start_data_import(db: Session = Depends(get_db)):
    """启动数据导入任务"""
    config = load_config_json()
    task_id = str(uuid.uuid4())

    # 在数据库预创建任务记录, 标记"排队中PENDING"
    task_params = {
        "station_data_dir": config["station_data_dir"]
    }
    
    try:
        crud.create_task(db, task_id, "站点数据导入数据库", "DataImport", task_params)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")
    
    # 启动任务, target是线程要执行的函数, args是传递给该函数的参数
    thread = Thread(target=run_station_data_import, args=(task_id, task_params["station_data_dir"]))
    thread.start()

    return TaskCreationResponse(message="数据导入任务已启动", task_id=task_id)


@router.get("/status/{task_id}", response_model=TaskStatusResponse, summary="查询任务状态")
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

@router.get("/history", summary="获取历史任务列表")
def get_task_history(skip: int = 0, limit: int = 82, db: Session = Depends(get_db)):
    """获取历史任务列表"""
    tasks = crud.get_all_tasks(db, skip=skip, limit=limit)
    return tasks