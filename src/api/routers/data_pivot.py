# src/api/routers/data_pivot.py
import json
import uuid
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from ...db import crud
from ...db.database import get_db
from ...core import schemas
from ...core.data_mapping import ELEMENT_TO_DB_MAPPING
from ...tasks.data_pivot import evaluate_model


router = APIRouter(
    prefix="/data-pivot",
    tags=["数据透视"],
)


@router.post("/processed-data", response_model=schemas.PivotDataProcessResponse, summary="获取预处理后的站点与格点对比数据")
def get_processed_pivot_data(request: schemas.PivotDataProcessRequest, db: Session = Depends(get_db)):
    """
    根据要素、站点和时间范围, 查询数据预处理后的站点观测值和对应的原始格点值, 用于绘制对比折线图。
    """
    try:
        # 调用CRUD函数查询数据
        df = crud.get_proc_data_for_pivot(
            db,
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
def create_pivot_model_evaluate_task(
    request: schemas.PivotModelTrainRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    # 检查是否有同类型的任务正在运行
    processing_task_id = crud.is_task_type_processing(db, "PivotModelEvaluate")
    if processing_task_id:
        return schemas.TaskCreationResponse(
            message="已有同类型任务正在进行中，请等待其完成后再试",
            task_id=processing_task_id
        )
    """启动一个模型评估后台任务"""
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
def get_pivot_model_evaluate_status(task_id: str, db: Session = Depends(get_db)):
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