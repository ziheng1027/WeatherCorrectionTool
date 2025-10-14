# src/api/routers/data_import.py
import uuid
from threading import Thread, Lock
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ...core.schemas import TaskCreationResponse, MessageResponse, FileListResponse
from ...db import crud
from ...core.config import STOP_EVENT
from ...db.database import get_db
from ...tasks.data_import import run_station_data_import
from ...core.config import load_config_json
from ...utils.file_io import get_station_files


# 全局任务状态管理器, Lock来保证多线程下对TASK_STATE的读写安全
TASK_STATE = {
    "is_running": False,
    "task_id": None
}
task_lock = Lock()

router = APIRouter(
    prefix="/data-import",
    tags=["数据导入"],
)


@router.post("/clear-pending-import-tasks", response_model=MessageResponse, summary="清理待处理的导入子任务")
def clear_pending_import_tasks(db: Session = Depends(get_db)):
    """
    在开始一次新的数据导入前，调用此接口来清理数据库中所有历史残留的、
    状态为 "PENDING" 的数据导入子任务。
    这可以防止前端在轮询进度时，获取到旧任务和新任务的混合列表。
    """
    deleted_count = crud.delete_pending_data_import_subtasks(db)
    return {"message": f"成功清除了 {deleted_count} 个待处理的导入子任务。"}


def run_station_data_import_wrapper(task_id: str, dir:str):
    """包装原始任务函数, 以确保在任务结束后能够安全地释放全局锁"""
    try:
        run_station_data_import(task_id, dir)
    finally:
        with task_lock:
            TASK_STATE["is_running"] = False
            TASK_STATE["task_id"] = None
            print(f"任务{task_id}已结束, 全局锁已释放")


@router.get("/check", response_model=FileListResponse, summary="检查文件数量并返回文件列表")
def check_files():
    """检查文件数量并返回文件列表"""
    config = load_config_json()
    station_data_dir = config["station_data_dir"]
    file_list = get_station_files(station_data_dir)
    return FileListResponse(count=len(file_list), files=file_list)


@router.post("/start", response_model=TaskCreationResponse, summary="启动数据导入任务")
def start_data_import(db: Session = Depends(get_db)):
    """启动数据导入任务"""
    # 开启信号
    STOP_EVENT.clear()
    # 检查并设置状态锁
    with task_lock:
        if TASK_STATE["is_running"]:
            raise HTTPException(
                status_code=409, # 409 Conflict表示请求与服务器当前状态冲突
                detail=f"已有数据导入任务正在运行(任务ID:{TASK_STATE['task_id']}, 请等待其完成后再试)"
            )
        # 如果没有任务在运行, 则锁定状态, 开始任务
        config = load_config_json()
        task_id = str(uuid.uuid4())
        # 更新全局状态
        TASK_STATE["is_running"] = True
        TASK_STATE["task_id"] = task_id

    # 在数据库预创建任务记录, 标记"排队中PENDING"
    task_params = {"station_data_dir": config["station_data_dir"]}
    
    try:
        crud.create_task(db, task_id, "站点数据导入数据库", "DataImport", task_params)
    except Exception as e:
        # 如果任务创建失败, 重置状态释放锁
        with task_lock:
            TASK_STATE["is_running"] = False
            TASK_STATE["task_id"] = None
        raise HTTPException(status_code=500, detail=f"创建任务失败: {str(e)}")
    
    # 启动任务, target是线程要执行的函数, args是传递给该函数的参数, 将全局状态的解锁操作传递给后台任务
    thread = Thread(target=run_station_data_import_wrapper, args=(task_id, task_params["station_data_dir"]))
    thread.start()

    return TaskCreationResponse(message="数据导入任务已启动", task_id=task_id)


@router.get("/global/pending_files", summary="【全局】获取所有待处理的文件列表")
def get_all_pending_files(db: Session = Depends(get_db)):
    """
    查询历史上所有待处理的文件名列表。
    """
    filenames, _ = crud.get_global_filenames_by_status(db, task_type="DataImport_SubTask", status="PENDING")
    return {"files": filenames}


@router.get("/global/processing_files", summary="【全局】获取所有处理中的文件列表")
def get_all_processing_files(db: Session = Depends(get_db)):
    """
    查询历史上所有导入中的文件名列表。
    """
    filenames, progress = crud.get_global_filenames_by_status(db, task_type="DataImport_SubTask", status="PROCESSING")
    return {"files": filenames, "progress": progress}


@router.get("/global/completed_files", summary="【全局】获取所有已完成的文件列表")
def get_all_completed_files(db: Session = Depends(get_db)):
    """
    查询历史上所有成功导入的文件名列表。
    """
    filenames, _ = crud.get_global_filenames_by_status(db, task_type="DataImport_SubTask", status="COMPLETED")
    return {"files": filenames}


@router.get("/global/failed_files", summary="【全局】获取所有失败的文件列表")
def get_all_failed_files(db: Session = Depends(get_db)):
    """
    查询历史上所有导入失败的文件名列表。
    """
    filenames, _ = crud.get_global_filenames_by_status(db, task_type="DataImport_SubTask", status="FAILED")
    return {"files": filenames}