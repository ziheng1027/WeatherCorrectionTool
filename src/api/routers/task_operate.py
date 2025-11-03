# src/api/routers/task_operate.py

from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException
from ...db.database import get_db
from ...db import crud
from ...core import schemas
from ...core.config import STOP_EVENT


router = APIRouter(
    prefix="/task_operate",
    tags=["任务操作[查询/取消]"],
)

@router.post("/{task_id}/cancel", response_model=schemas.MessageResponse, summary="取消正在运行的任务")
def cancel_data_processing(task_id: str, db: Session = Depends(get_db)):
    """
    取消一个正在运行的任务。
    """
    task = crud.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务未找到")

    if task.status not in ["PENDING", "PROCESSING"]:
        raise HTTPException(status_code=400, detail=f"任务状态为 {task.status}, 无法取消。")

    # 设置全局停止事件
    STOP_EVENT.set()
    
    return {"message": f"任务 {task_id} 的取消信号已发送。"}


@router.get("/status/{task_id}", response_model=schemas.TaskStatusResponse, summary="查询任务总体状态(父任务)")
def get_task_status(task_id: str, db: Session = Depends(get_db)):
    """查询任务状态"""
    task = crud.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return schemas.TaskStatusResponse(
        task_id=task.task_id,
        task_name=task.task_name,
        task_type=task.task_type,
        status=task.status,
        progress=task.cur_progress,
        progress_text=task.progress_text
    )


@router.get("/status/{task_id}/details", response_model=schemas.TaskDetailsResponse, summary="查询任务详细状态(包含子任务)")
def get_task_details(task_id: str, db: Session = Depends(get_db)):
    """查询父任务的总体状态及其所有子任务的详细列表"""
    # 获取父任务
    parent_task = crud.get_task_by_id(db, task_id)
    if not parent_task:
        raise HTTPException(status_code=404, detail="父任务不存在")
    # 获取所有子任务
    sub_tasks_db = crud.get_subtasks_by_parent_id(db, task_id)
    # 组装响应数据
    parent_status = schemas.TaskStatusResponse(
        task_id=parent_task.task_id,
        task_name=parent_task.task_name,
        task_type=parent_task.task_type,
        status=parent_task.status,
        progress=parent_task.cur_progress,
        pregress_text=parent_task.progress_text
    )
    sub_tasks_status = [
        schemas.SubTaskStatusResponse(
            task_id=st.task_id,
            task_name=st.task_name,
            status=st.status,
            progress=st.cur_progress,
            progress_text=st.progress_text
        ) for st in sub_tasks_db
    ]
    # 按照 PENDING, PROCESSING, COMPLETED, FAILED 顺序对子任务排序, 便于前端展示
    status_order = {"PENDING": 0, "PROCESSING": 1, "COMPLETED": 2, "FAILED": 3}
    sub_tasks_status.sort(key=lambda x: status_order.get(x.status, 4))
    return schemas.TaskDetailsResponse(parent=parent_status, sub_tasks=sub_tasks_status)


@router.get("/history", summary="获取历史任务列表")
def get_task_history(skip: int = 0, limit: int = 82, db: Session = Depends(get_db)):
    """获取历史任务列表"""
    tasks = crud.get_all_tasks(db, skip=skip, limit=limit)
    return tasks