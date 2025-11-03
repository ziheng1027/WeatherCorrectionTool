# src/api/routers/model_train.py
import os
import uuid
import json
import pandas as pd
from pathlib import Path
from sqlalchemy.orm import Session
from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException

from ...db import crud
from ...db.database import get_db
from ...core import schemas
from ...core.config import settings
from ...core.config import get_model_config_path, load_model_config, save_model_config
from ...tasks import model_train


router = APIRouter(
    prefix="/model-train",
    tags=["模型训练"],
)


@router.get("/model-config/{model_name}/{element}", response_model=dict, summary="获取指定模型的当前超参数配置")
def get_model_config(model_name: str, element: str):
    """获取指定模型和要素的当前超参数配置"""
    try:
        model_config_path = get_model_config_path(model_name, element)
        config = load_model_config(model_config_path)
        return config
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取配置文件时发生未知错误: {str(e)}")


@router.post("/model-config/{model_name}/{element}", response_model=schemas.MessageResponse,
             summary="更新指定模型的超参数配置, 只会更新请求体中提供的、且在原始配置中已存在的参数")
def update_model_config(
    model_name: str, element: str, request: schemas.ModelParamsUpdateRequest
):
    """
    更新指定模型和要素的超参数配置。
    只会更新请求体中提供的、且在原始配置中已存在的参数。
    """
    try:
        # 1. 加载现有的配置
        model_config_path = get_model_config_path(model_name, element)
        current_config = load_model_config(model_config_path)
        
        # 2. 遍历用户传入的参数并更新
        updated_keys = []
        for key, value in request.params.items():
            if key in current_config:
                current_config[key] = value
                updated_keys.append(key)
            else:
                # 忽略不在原始配置中的键
                print(f"警告: 参数 '{key}' 不在原始配置中, 已忽略。")

        if not updated_keys:
            raise HTTPException(status_code=400, detail="未提供任何有效的参数进行更新。")

        # 3. 保存更新后的配置
        save_model_config(model_config_path, current_config)
        
        return schemas.MessageResponse(message=f"模型参数更新成功, 已更新: {', '.join(updated_keys)}")

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException as e:
        raise e 
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置文件时发生未知错误: {e}")


@router.post("/start", response_model=schemas.TaskCreationResponse, summary="启动模型训练任务")
def start_model_train(
    request: schemas.ModelTrainRequest, backgroud_tasks: BackgroundTasks, db: Session = Depends(get_db)
):
    """启动一个后台模型训练任务"""
    # 检查是否有同类型的任务正在运行
    processing_task_id = crud.is_task_type_processing(db, "ModelTrain")
    if processing_task_id:
        return schemas.TaskCreationResponse(
            message="已有模型训练任务正在进行中, 请等待其完成后再试",
            task_id=processing_task_id
        )
    
    task_id = str(uuid.uuid4())
    task_name = f"模型训练_{request.model}_{request.element}_{request.start_year}-{request.end_year}_{request.season}"
    # 将Pydantic模型转换为字典以便存入数据库
    params_dict = request.model_dump()

    # 创建任务记录
    crud.create_task(
        db=db, task_id=task_id, task_name=task_name, task_type="ModelTrain", params=params_dict
    )

    # 启动后台任务
    backgroud_tasks.add_task(model_train.train, task_id, request)

    return schemas.TaskCreationResponse(
        message="模型训练任务已启动",
        task_id=task_id
    )


@router.post("/get-losses", response_model=schemas.LossesResponse, summary="获取训练损失/验证损失")
async def get_training_losses(request: schemas.ModelInfoRequest):
    """根据模型信息获取训练/验证损失, 用于绘制损失曲线"""
    task_id = request.task_id
    model_name = request.model.lower()
    losses_dir = Path(settings.LOSSES_OUTPUT_DIR) / model_name
    losses_file_name = f"{model_name}_{request.element}_{request.start_year}_{request.end_year}_{request.season}_{task_id}.csv"
    losses_file_path = losses_dir / losses_file_name

    if not losses_file_path.exists():
        raise HTTPException(status_code=404, detail=f"未找到损失文件: {losses_file_path}")
    
    try:
        df = pd.read_csv(losses_file_path)
        return {
            "epochs": df["epoch"].tolist(),
            "train_losses": df["train_loss"].tolist(),
            "test_losses": df["test_loss"].tolist()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取损失文件时发生错误: {str(e)}")


@router.post("get-metrics-testset-all", response_model=schemas.MetricsResponse, summary="获取测试集所有站点的整体评估指标")
async def get_overall_metrics(request: schemas.ModelInfoRequest):
    """根据模型信息获取测试集所有站点的整体评估指标"""
    task_id = request.task_id
    model_name = request.model.lower()
    metrics_dir = Path(settings.METRIC_OUTPUT_DIR) / model_name / "overall"
    metrics_file_name = f"{model_name}_{request.element}_{request.start_year}_{request.end_year}_{request.season}_{task_id}.json"
    metrics_file_path = metrics_dir / metrics_file_name

    if not metrics_file_path.exists():
        raise HTTPException(status_code=404, detail=f"未找到指标文件: {metrics_file_path}")

    try:
        with open(metrics_file_path, "r", encoding="utf-8") as f:
            metrics = json.load(f)
        return metrics
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取指标文件时发生错误: {str(e)}")


@router.get("/global/pending", summary="【全局】获取所有待处理的任务列表")
def get_all_pending_files(db: Session = Depends(get_db)):
    """
    查询历史上所有待处理的任务列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="ModelTrain_SubTask", status="PENDING")
    return task_params


@router.get("/global/processing", summary="【全局】获取所有处理中的任务列表")
def get_all_processing_files(db: Session = Depends(get_db)):
    """
    查询历史上所有处理中的任务列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="ModelTrain_SubTask", status="PROCESSING")
    return task_params


@router.get("/global/completed", summary="【全局】获取所有已完成的任务列表")
def get_all_completed_files(db: Session = Depends(get_db)):
    """
    查询历史上所有成功的任务列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="ModelTrain_SubTask", status="COMPLETED")
    return task_params


@router.get("/global/failed", summary="【全局】获取所有失败的任务列表")
def get_all_failed_files(db: Session = Depends(get_db)):
    """
    查询历史上所有失败的任务列表。
    """
    task_params = crud.get_global_task_by_status(db, task_type="ModelTrain_SubTask", status="FAILED")
    return task_params


@router.get("/save-model-record", response_model=schemas.MessageResponse, summary="向数据库保存一条模型记录")
def save_model_record(task_id: str, db: Session = Depends(get_db)):
    """根据已完成的模型训练任务id, 向数据库保存一条模型记录"""
    task = crud.get_task_by_id(db, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"该任务不存在: {task_id}")

    if task.task_type not in ["ModelTrain", "ModelTrain_SubTask"]:
        raise HTTPException(status_code=400, detail=f"该任务不是模型训练任务: {task_id}")
    
    if task.status != "COMPLETED":
        raise HTTPException(status_code=400, detail=f"该任务未完成, 无法保存模型记录: {task_id}")

    # 检查是否已经存在该任务的模型记录
    existing_record = crud.get_model_record_by_task_id(db, task_id)
    if existing_record:
        raise HTTPException(status_code=400, detail=f"该任务的模型记录已经存在: {task_id}")
    
    # 解析所需信息
    params = task.get_params()
    model_name = params.get("model")
    element = params.get("element")
    start_year = params.get("start_year")
    end_year = params.get("end_year")
    season = params.get("season")
    # 构建模型路径
    checkpoint_dir = os.path.join(settings.MODEL_OUTPUT_DIR, model_name.lower())
    checkpoint_name = f"{model_name.lower()}_{element}_{start_year}_{end_year}_{season}_id={task_id}.ckpt"
    checkpoint_path = os.path.join(checkpoint_dir, checkpoint_name)
    # 获取当前的模型参数
    model_config_path = get_model_config_path(model_name, element)
    model_config = load_model_config(model_config_path)
    # 模型记录信息
    model_info = {
        "model_id": str(uuid.uuid4()),
        "model_name": checkpoint_name,
        "element": element,
        "train_params": params,
        "model_params": model_config,
        "model_path": checkpoint_path,
        "task_id": task_id
    }
    
    crud.create_model_record(db, model_info)
    return schemas.MessageResponse(message="模型记录已保存")

@router.delete("/delete-model-record/{model_id}", response_model=schemas.MessageResponse, summary="删除指定的模型记录及其关联的任务")
def delete_model_record(model_id: str, db: Session = Depends(get_db)):
    """
    根据 model_id 删除模型记录 (model_record) 和关联的任务记录 (task_progress)。
    同时会尝试从文件系统删除 .ckpt 模型文件。
    """
    # 1. 查找模型记录
    model_record = crud.get_model_record_by_model_id(db, model_id)
    if not model_record:
        raise HTTPException(status_code=404, detail=f"未找到 model_id 为 {model_id} 的模型记录")

    task_id = model_record.task_id
    model_path_str = model_record.model_path

    # 2. 按顺序执行删除
    try:
        # 步骤 2.1: 删除模型记录 (ModelRecord)
        crud.delete_model_record_by_model_id(db, model_id)
        
        # 步骤 2.2: 删除关联的任务记录 (TaskProgress)
        task_delete_msg = ""
        if task_id:
            if crud.delete_task_by_task_id(db, task_id):
                task_delete_msg = f"关联的任务 {task_id} 已删除。"
            else:
                task_delete_msg = f"未找到关联的任务 {task_id}。"
        else:
            task_delete_msg = "该模型没有关联的任务ID。"

        # 步骤 2.3: (可选, 但推荐) 尝试删除物理文件
        file_delete_msg = ""
        try:
            model_path = Path(model_path_str)
            if model_path.exists():
                os.remove(model_path)
                file_delete_msg = "物理模型文件已删除。"
            else:
                file_delete_msg = "物理模型文件在磁盘上未找到。"
        except Exception as e:
            file_delete_msg = f"删除物理文件时出错: {e}"

        return schemas.MessageResponse(
            message=f"模型记录 {model_id} 已从数据库删除。{task_delete_msg} {file_delete_msg}"
        )
    
    except Exception as e:
        # 回滚, 尽管 crud 函数内部有 commit, 但在此处回滚以防万一
        db.rollback()
        raise HTTPException(status_code=500, detail=f"删除过程中发生数据库错误: {str(e)}")