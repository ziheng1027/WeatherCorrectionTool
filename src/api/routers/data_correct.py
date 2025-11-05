# src/api/routers/data_correct.py
import uuid
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from ...db import crud
from ...db.database import get_db
from ...core import schemas
from ...tasks.data_correct import correct_mp


router = APIRouter(
    prefix="/data-correct",
    tags=["数据订正"],
)


@router.get("/get-models", response_model=schemas.ModelListResponse, summary="获取所有已保存的模型")
def get_models(db: Session = Depends(get_db)):
    """从数据库中检索所有已训练并保存的模型记录供前端选择"""
    model_records = crud.get_all_model_records(db)

    response_models = []
    for record in model_records:
        response_models.append(
            schemas.ModelRecordResponse(
                task_id=record.task_id,
                element=record.element,
                model_name=record.model_name,
                model_path=record.model_path,
                create_time=record.create_time,
                train_params=record.get_train_params(),
                model_params=record.get_model_params()
            )
        )
    return schemas.ModelListResponse(count=len(response_models), models=response_models)


@router.post("/start", response_model=schemas.TaskCreationResponse, summary="启动数据订正任务")
def start_data_correct(
    request: schemas.DataCorrectRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """启动一个数据订正后台任务"""
    # 检查是否有同类型的任务正在进行
    processing_task_id = crud.is_task_type_processing(db, "DataCorrect")
    if processing_task_id:
        return schemas.TaskCreationResponse(
            message="已有数据订正任务正在进行中, 请等待其完成后再试",
            task_id=processing_task_id
        )
    # 创建父任务
    parent_task_id = str(uuid.uuid4())
    task_name = f"数据订正_{request.element}_{request.start_year}-{request.end_year}_{request.season}"
    params_dict = request.model_dump()
    # 将路径对象转换为字符串
    params_dict["model_path"] = str(params_dict["model_path"])
    crud.create_task(db, parent_task_id, task_name, "DataCorrect", params_dict)
    # 将耗时任务添加到后台
    background_tasks.add_task(
        correct_mp, parent_task_id, request.model_path, request.element, 
        request.start_year, request.end_year, request.season, request.block_size, request.num_workers
    )

    return schemas.TaskCreationResponse(message="数据订正任务已启动", task_id=parent_task_id)


@router.get("/global/processing-parent", summary="【全局】获取所有处理中的父任务")
def get_all_processing_parent_files(db: Session = Depends(get_db)):
    """
    查询历史上所有处理中的父任务。
    """
    task_params = crud.get_global_task_by_status(db, task_type="DataCorrect", status="PROCESSING")
    return task_params


@router.get("/global/completed-parent", summary="【全局】获取所有已完成的父任务")
def get_all_completed_parent_files(db: Session = Depends(get_db)):
    """
    查询历史上所有成功的父任务。
    """
    task_params = crud.get_global_task_by_status(db, task_type="DataCorrect", status="COMPLETED")
    return task_params


@router.get("/global/failed-parent", summary="【全局】获取所有失败的父任务")
def get_all_failed_parent_files(db: Session = Depends(get_db)):
    """
    查询历史上所有失败的父任务。
    """
    task_params = crud.get_global_task_by_status(db, task_type="DataCorrect", status="FAILED")
    return task_params


@router.get("/global/pending", summary="【全局】获取所有待处理的任务列表")
def get_all_pending_files(db: Session = Depends(get_db)):
    """
    查询历史上所有待处理的任务列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="DataCorrect_SubTask", status="PENDING")
    return task_params


@router.get("/global/processing", summary="【全局】获取所有处理中的任务列表")
def get_all_processing_files(db: Session = Depends(get_db)):
    """
    查询历史上所有处理中的任务列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="DataCorrect_SubTask", status="PROCESSING")
    return task_params


@router.get("/global/completed", summary="【全局】获取所有已完成的任务列表")
def get_all_completed_files(db: Session = Depends(get_db)):
    """
    查询历史上所有成功的任务列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="DataCorrect_SubTask", status="COMPLETED")
    return task_params


@router.get("/global/failed", summary="【全局】获取所有失败的任务列表")
def get_all_failed_files(db: Session = Depends(get_db)):
    """
    查询历史上所有失败的任务列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="DataCorrect_SubTask", status="FAILED")
    return task_params