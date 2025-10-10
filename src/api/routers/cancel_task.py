# src/api/routers/cancel_task.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...db.database import get_db
from ...db import crud
from ...core import schemas
from ...core.config import STOP_EVENT


router = APIRouter(
    prefix="/cancel-task",
    tags=["取消/中断任务"],
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