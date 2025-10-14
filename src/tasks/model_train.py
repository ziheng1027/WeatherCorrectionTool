# src/tasks/model_train.py
from time import time
from sqlalchemy.orm import Session

from ..db import crud
from ..db.database import SessionLocal
from ..core.config import settings
from ..core.schemas import ModelTrainRequest
from ..core.model_train import build_dataset_from_db, split_dataset, train_model, evaluate_model
from ..utils.file_io import (
    save_model, save_losses, save_metrics_in_testset_all,
    save_true_pred, save_metrics_in_testset_station, save_feature_importance
)


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
        crud.update_task_status(db, task_id, "PROCESSING", 15.0, "数据集构建已完成")

        # 更新任务状态: 正在划分数据集
        crud.update_task_status(db, task_id, "PROCESSING", 20.0, "正在划分数据集...")
        train_dataset, test_dataset = split_dataset(dataset, request.split_method, request.test_set_values)
        print(f"|--> [Task ID: {task_id}] 数据集划分完成, 已耗时: {time() - start_time:.2f}秒, 训练集形状: {train_dataset.shape}, 测试集形状: {test_dataset.shape}")
        crud.update_task_status(db, task_id, "PROCESSING", 25.0, "数据集划分已完成")

        # 更新任务状态: 正在训练模型
        crud.update_task_status(db, task_id, "PROCESSING", 30.0, "正在训练模型...")
        model, train_losses, test_losses, metrics_true, metrics_pred = train_model(
            request.model, request.element, request.start_year, request.end_year, request.season, 
            request.early_stopping_rounds, train_dataset, test_dataset
        )
        print(f"|--> [Task ID: {task_id}] 模型训练完成, 已耗时: {time() - start_time:.2f}秒")
        crud.update_task_status(db, task_id, "PROCESSING", 60.0, "模型训练已完成")

        # 更新任务状态: 正在保存模型、训练损失以及整体指标
        print(f"|--> [Task ID: {task_id}] 正在保存训练损失和整体指标...")
        crud.update_task_status(db, task_id, "PROCESSING", 65.0, "正在保存模型、训练损失以及整体指标...")
        save_model(model, request.model, request.element, request.start_year, request.end_year, request.season)
        save_losses(train_losses, test_losses, request.model, request.element, request.start_year, request.end_year, request.season)
        save_metrics_in_testset_all(metrics_true, metrics_pred, request.model, request.element, request.start_year, request.end_year, request.season)
        print(f"|--> [Task ID: {task_id}] 训练损失和整体指标保存完成, 已耗时: {time() - start_time:.2f}秒")
        crud.update_task_status(db, task_id, "PROCESSING", 70.0, "模型、训练损失和整体指标保存已完成")

        # 更新任务状态: 正在评估模型
        crud.update_task_status(db, task_id, "PROCESSING", 75.0, "正在评估模型...")
        results, metrics, feature_importance = evaluate_model(
            request.model, test_dataset, request.element, 
            request.start_year, request.end_year, request.season
        )
        print(f"|--> [Task ID: {task_id}] 模型评估完成, 总耗时: {time() - start_time:.2f}秒")
        crud.update_task_status(db, task_id, "PROCESSING", 85.0, "模型评估已完成")

        # 更新任务状态: 保存预测结果、每个站点指标、特征重要性
        print(f"|--> [Task ID: {task_id}] 正在保存预测结果、每个站点指标、特征重要性...")
        crud.update_task_status(db, task_id, "PROCESSING", 90.0, "正在保存预测结果、每个站点指标、特征重要性...")
        save_true_pred(results, request.model, request.element, request.start_year, request.end_year, request.season)
        save_metrics_in_testset_station(metrics, request.model, request.element, request.start_year, request.end_year, request.season)
        save_feature_importance(feature_importance, request.model, request.element, request.start_year, request.end_year, request.season)
        print(f"|--> [Task ID: {task_id}] 预测结果、每个站点指标、特征重要性保存完成, 总耗时: {time() - start_time:.2f}秒")
        crud.update_task_status(db, task_id, "COMPLETED", 100.0, "预测结果、每个站点指标、特征重要性保存已完成")
    
    except Exception as e:
        error_message = f"任务失败: {str(e)}"
        print(f"|--> [Task ID: {task_id}] 错误: {error_message}")
        crud.update_task_status(db, task_id, "FAILED", 0.0, error_message)
        
    finally:
        db.close()
