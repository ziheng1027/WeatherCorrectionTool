# src/tasks/model_train.py
import uuid
from time import time
from sqlalchemy.orm import Session

from ..db import crud
from ..db.database import SessionLocal
from ..core.config import settings
from ..core.schemas import ModelTrainRequest
from ..core.model_train import build_dataset_from_db, split_dataset, train_model
from ..utils.file_io import save_model, save_losses, save_metrics_in_testset_all


def train(task_id: str, request: ModelTrainRequest):
    """执行模型训练的后台任务"""
    db: Session = SessionLocal()
    start_time = time()
    num_elements = len(request.element)
    activate_subtask_id = None
    if num_elements == 0:
        raise Exception("没有指定要素进行训练, 请检查请求参数。")
    
    print(f"|--> [Task ID: {task_id}] 开始执行模型训练任务, 共 {len(request.element)} 个要素需要训练。")
    crud.update_task_status(db, task_id, "PROCESSING", 0.0, "任务开始...")
    try:
        # 预创建所有子任务
        sub_tasks = []
        for element in request.element:
            subtask_params = {
                "model": request.model,
                "element": element,
                "start_year": request.start_year,
                "end_year": request.end_year,
                "season": request.season,
                "split_method": request.split_method,
                "test_set_values": request.test_set_values,
                "early_stopping_rounds": request.early_stopping_rounds,
            }
            subtask_id = str(uuid.uuid4())
            sub_task = crud.create_task(
                db=db, task_id=subtask_id, task_name=f"{element} 模型训练", task_type="ModelTrain_SubTask", params=subtask_params
            )
            sub_tasks.append(sub_task)
        print(f"|--> [Task ID: {task_id}] 预创建 {len(sub_tasks)} 个子任务")
        crud.update_task_status(db, task_id, "PROCESSING", 3.0, f"已成功创建 {len(sub_tasks)} 个子任务")

        # 执行所有子任务
        for i, sub_task in enumerate(sub_tasks):
            try:
                base_progress = (i / num_elements) * 100
                activate_subtask_id = sub_task.task_id
                element = sub_task.get_params()["element"]
                print(f"|--> [Task ID: {task_id}] 正在训练 {element} 模型...")
                # 更新任务状态: 正在构建数据集
                crud.update_task_status(db, activate_subtask_id, "PROCESSING", 5.0, "正在构建数据集...")
                dataset = build_dataset_from_db(
                    db, settings.DEM_DATA_PATH, settings.LAGS_CONFIG, element, 
                    request.start_year, request.end_year, request.season
                )
                if dataset.empty:
                    raise Exception("数据集为空, 请检查是否完成了数据处理步骤并导入数据库/时间范围是否符合数据处理步骤设置的起止时间范围。")
                print(f"|--> [Task ID: {activate_subtask_id}] 数据集构建完成, 已耗时: {time() - start_time:.2f}秒, 数据集形状: {dataset.shape}")
                crud.update_task_status(db, activate_subtask_id, "PROCESSING", 25.0, "数据集构建已完成")
                # 更新任务状态: 正在划分数据集
                crud.update_task_status(db, activate_subtask_id, "PROCESSING", 30.0, "正在划分数据集...")
                train_dataset, test_dataset = split_dataset(dataset, request.split_method, request.test_set_values)
                print(f"|--> [Task ID: {activate_subtask_id}] 数据集划分完成, 已耗时: {time() - start_time:.2f}秒, 训练集形状: {train_dataset.shape}, 测试集形状: {test_dataset.shape}")
                crud.update_task_status(db, activate_subtask_id, "PROCESSING", 40.0, "数据集划分已完成")
                # 更新任务状态: 正在训练模型
                crud.update_task_status(db, activate_subtask_id, "PROCESSING", 45.0, "正在训练模型...")
                print(f"|--> [Task ID: {activate_subtask_id}] 正在训练 {element} 模型...")
                model, train_losses, test_losses, metrics_true, metrics_pred = train_model(
                    request.model, element, request.start_year, request.end_year, request.season, 
                    request.early_stopping_rounds, train_dataset, test_dataset
                )
                rmse = metrics_pred["RMSE"]
                print(f"|--> [Task ID: {activate_subtask_id}] {element} 模型训练完成, 已耗时: {time() - start_time:.2f}秒")
                crud.update_task_status(db, activate_subtask_id, "PROCESSING", 90.0, f"{element} 模型训练已完成")
                # 更新任务状态: 正在保存模型、训练损失以及整体指标
                print(f"|--> [Task ID: {activate_subtask_id}] 正在保存模型、训练损失和整体指标...")
                crud.update_task_status(db, activate_subtask_id, "PROCESSING", 95.0, "正在保存模型、训练损失以及整体指标...")

                save_model(model, request.model, element, request.start_year, request.end_year, request.season, activate_subtask_id)
                save_losses(train_losses, test_losses, request.model, element, request.start_year, request.end_year, request.season, activate_subtask_id)
                save_metrics_in_testset_all(metrics_true, metrics_pred, request.model, element, request.start_year, request.end_year, request.season, activate_subtask_id)
                
                print(f"|--> [Task ID: {activate_subtask_id}] {element} 训练损失和整体指标保存完成, 已耗时: {time() - start_time:.2f}秒")
                crud.update_task_status(db, activate_subtask_id, "COMPLETED", 100.0, "模型、训练损失和整体指标保存已完成")
                
            except Exception as e:
                error_message = f"任务失败: {str(e)}"
                print(f"|--> [Task ID: {activate_subtask_id}] 错误: {error_message}")
                crud.update_task_status(db, activate_subtask_id, "FAILED", 0.0, error_message)
                continue

        # 更新父任务状态
        crud.update_task_status(db, task_id, "PROCESSING", base_progress, f"已完成 {i}/{num_elements} 个子任务")
        # 更新父任务状态为: 已完成
        crud.update_task_status(db, task_id, "COMPLETED", 100.0, "所有子任务已完成, 任务完成!")

    except Exception as e:
        error_message = f"任务失败: {str(e)}"
        print(f"|--> [Task ID: {task_id}] 错误: {error_message}")
        crud.update_task_status(db, task_id, "FAILED", 0.0, error_message)
        return
    
    finally:
        db.close()
