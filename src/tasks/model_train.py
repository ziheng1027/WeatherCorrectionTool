# src/tasks/model_train.py
from time import time
from sqlalchemy.orm import Session

from ..db import crud
from ..db.database import SessionLocal
from ..core.config import settings
from ..core.model_train import build_dataset_from_db, split_dataset, train_model, evaluate_model
from ..core.schemas import ModelTrainRequest


def train(task_id: str, request: ModelTrainRequest):
    """执行模型训练的后台任务"""
    db: Session = SessionLocal()
    try:
        start_time = time()
        print(f"|--> [Task ID: {task_id}] 开始执行模型训练任务...")
        # 更新任务状态: 正在构建数据集
        crud.update_task_status(db, task_id, "PROCESSING", 5.0, "正在构建数据集...")
        dataset = build_dataset_from_db(
            db, settings.DEM_DATA_PATH, settings.LAGS_CONFIG, request.element, 
            request.start_year, request.end_year, request.season
        )
        if dataset.empty:
            raise Exception("数据集为空, 请检查是否完成了数据处理步骤并导入数据库/时间范围是否符合数据处理步骤设置的起止时间范围。")
        print(f"|--> [Task ID: {task_id}] 数据集构建完成, 已耗时: {time() - start_time:.2f}秒, 数据集形状: {dataset.shape}")
        crud.update_task_status(db, task_id, "PROCESSING", 30.0, "数据集构建已完成")

        # 更新任务状态: 正在划分数据集
        crud.update_task_status(db, task_id, "PROCESSING", 35.0, "正在划分数据集...")
        train_dataset, test_dataset = split_dataset(dataset, request.split_method, request.test_set_values)
        print(f"|--> [Task ID: {task_id}] 数据集划分完成, 已耗时: {time() - start_time:.2f}秒, 训练集形状: {train_dataset.shape}, 测试集形状: {test_dataset.shape}")
        crud.update_task_status(db, task_id, "PROCESSING", 45.0, "数据集划分已完成")

        # 更新任务状态: 正在训练模型
        crud.update_task_status(db, task_id, "PROCESSING", 50.0, "正在训练模型...")
        train_losses, test_losses = train_model(
            request.model, request.element, request.start_year, request.end_year, request.season, 
            request.early_stopping_rounds, train_dataset, test_dataset
        )
        print(f"|--> [Task ID: {task_id}] 模型训练完成, 已耗时: {time() - start_time:.2f}秒")
        crud.update_task_status(db, task_id, "PROCESSING", 85.0, "模型训练已完成")

        # 更新任务状态: 正在评估模型
        crud.update_task_status(db, task_id, "PROCESSING", 90.0, "正在评估模型...")
        eval_results = evaluate_model(
            request.model, test_dataset, request.element, 
            request.start_year, request.end_year, request.season
        )
        # 将训练损失和验证损失也添加到返回结果中
        eval_results["train_losses_rmse"] = train_losses
        eval_results["test_losses_rmse"] = test_losses

        print(f"|--> [Task ID: {task_id}] 模型评估完成, 总耗时: {time() - start_time:.2f}秒")
        crud.update_task_status(db, task_id, "COMPLETED", 100.0, "模型评估已完成, 任务完成!")
        return eval_results
    
    except Exception as e:
        error_message = f"任务失败: {str(e)}"
        print(f"|--> [Task ID: {task_id}] 错误: {error_message}")
        crud.update_task_status(db, task_id, "FAILED", 0.0, error_message)
        
    finally:
        db.close()
