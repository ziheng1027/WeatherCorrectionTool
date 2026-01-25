# src/api/routers/multi_station_eval.py
import uuid
import json
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ...db import crud
from ...db.database import get_db
from ...core import schemas
from ...tasks.multi_station_eval import run_multi_station_eval

router = APIRouter(
    prefix="/model-train/multi-station-eval",
    tags=["模型评估(多站点)"],
)

@router.post("/start", response_model=schemas.TaskCreationResponse, summary="启动多站点批量评估任务")
def start_multi_station_eval(
    request: schemas.MultiStationEvalRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    启动全站评估任务:
    1. 加载指定模型
    2. 对每一个站点, 获取指定年份范围的数据
    3. 进行预测并与原始格点数据对比
    4. 生成详细的统计报表(JSON + Excel)
    """
    # 1. 检查是否有同类任务
    # 复用 generic 的检查逻辑，或者新增特定类型 "MultiStationEval"
    processing_task_id = crud.is_task_type_processing(db, "MultiStationEval")
    if processing_task_id:
        return schemas.TaskCreationResponse(
            message="已有评估任务正在进行中，请等待其完成后再试",
            task_id=processing_task_id
        )

    # 2. 创建任务
    task_id = str(uuid.uuid4())
    task_name = f"多站点评估_{request.model_name}_{request.element}_{request.start_year}-{request.end_year}"
    
    crud.create_task(
        db, task_id, task_name, "MultiStationEval", request.model_dump()
    )

    # 3. 后台执行
    background_tasks.add_task(
        run_multi_station_eval,
        task_id=task_id,
        model_name=request.model_name,
        element=request.element,
        model_file=request.model_file,
        start_year=request.start_year,
        end_year=request.end_year,
        season=request.season
    )

    return {"message": "多站点批量评估任务已启动", "task_id": task_id}

@router.get("/status/{task_id}", response_model=schemas.MultiStationEvalStatusResponse, summary="查询评估任务状态")
def get_eval_status(task_id: str, db: Session = Depends(get_db)):
    """查询任务进度，完成后返回JSON格式的统计摘要"""
    task = crud.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    
    response = {
        "task_id": task.task_id,
        "status": task.status,
        "progress": task.cur_progress,
        "progress_text": task.progress_text,
        "results": None
    }

    if task.status == "COMPLETED":
        params = task.get_params()
        json_path_str = params.get("result_json_path")
        if json_path_str and Path(json_path_str).exists():
            with open(json_path_str, "r", encoding="utf-8") as f:
                response["results"] = json.load(f)
    
    return response

@router.get("/export/{task_id}", response_class=FileResponse, summary="下载评估结果Excel")
def export_eval_excel(task_id: str, db: Session = Depends(get_db)):
    """下载生成的Excel报表"""
    task = crud.get_task_by_id(db, task_id)
    if not task or task.status != "COMPLETED":
        raise HTTPException(status_code=404, detail="任务未完成或不存在")
    
    params = task.get_params()
    excel_path_str = params.get("result_excel_path")
    
    if not excel_path_str or not Path(excel_path_str).exists():
        raise HTTPException(status_code=404, detail="结果文件已丢失")
        
    return FileResponse(
        path=excel_path_str, 
        filename=Path(excel_path_str).name,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )