# src/api/routers/data_import.py
from fastapi import APIRouter, HTTPException
from celery.result import AsyncResult
from ...tasks.import_worker import import_station_data_task
from ...core.schemas import DataImportRequest, TaskStatusResponse, TaskCreationResponse

# 创建一个API路由器实例
router = APIRouter(
    prefix="/import",      # 所有在这个文件里的路由都会自带 /import 前缀
    tags=["Data Import"],  # 在API文档中为这些路由分组
)


@router.post("/start", response_model=TaskCreationResponse)
def start_data_import(request: DataImportRequest):
    """
    接收前端提供的目录路径，启动后台数据导入任务。
    """
    try:
        # .delay() 是调用Celery任务的方法，它会立即返回一个AsyncResult对象
        # 我们将路径作为参数传递给后台任务
        task = import_station_data_task.delay(request.directory_path.as_posix())
        
        # 将Celery任务的ID返回给前端
        return {"message": "数据导入任务已启动", "task_id": task.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法启动任务: {e}")


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
def get_task_status(task_id: str):
    """
    根据任务ID查询Celery任务的当前状态和进度。
    """
    # 从Celery后端获取任务结果对象
    task_result = AsyncResult(task_id)

    # 调试代码
    print(f"DEBUG: The result backend is: {task_result.backend}")
    
    status = task_result.state
    progress_info = None

    if status == 'PENDING':
        # 任务正在等待被执行
        progress_info = {"status": "任务正在排队..."}
    elif status == 'PROGRESS':
        # 任务正在执行中，task_result.info 就是我们在worker中用 update_state 设置的 meta 字典
        progress_info = task_result.info
    elif status == 'SUCCESS':
        # 任务成功完成
        progress_info = task_result.result # 获取任务的返回值
    elif status == 'FAILURE':
        # 任务执行失败
        progress_info = {"status": "任务失败", "error": str(task_result.info)}
    
    return {"task_id": task_id, "status": status, "progress": progress_info}