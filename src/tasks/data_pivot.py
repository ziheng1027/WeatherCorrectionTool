# src/tasks/data_pivot.py
import json
import pandas as pd
from pathlib import Path
from typing import List
from datetime import datetime
from ..db import crud
from ..db.database import SessionLocal
from ..core import schemas
from ..core.data_mapping import ELEMENT_TO_DB_MAPPING
from ..core.data_pivot import bulid_feature_for_pivot
from ..utils.file_io import load_model
from ..utils.metrics import cal_metrics


def evaluate_model(task_id: str, element: str, station_name: str, start_time: datetime, end_time: datetime, model_paths: List[str]):
    """模型评估分析[后台任务]"""
    db = SessionLocal()
    try:
        # 任务初始化
        crud.update_task_status(db, task_id, "PROCESSING", 0.0, "任务初始化, 准备获取数据...")
        # 获取并准备用于预测的数据和特征
        df_base = crud.get_proc_feature_for_pivot(db, element, station_name, start_time, end_time)

        if df_base.empty:
            crud.update_task_status(db, task_id, "FAILED", 0.0, "在指定条件下没有找到可供分析的数据")
            raise ValueError("在指定条件下没有找到可供分析的数据")
        
        crud.update_task_status(db, task_id, "PROCESSING", 20.0, "数据获取完成, 开始构建特征...")
        element_db_column = ELEMENT_TO_DB_MAPPING[element]
        df_X, df_y = bulid_feature_for_pivot(df_base.copy(), element)
        crud.update_task_status(db, task_id, "PROCESSING", 40.0, "特征构建完成, 开始模型预测...")

        # 计算原始数据的指标
        grid_values = df_X[f"{element_db_column}_grid"].tolist()
        original_metric = cal_metrics(df_y, grid_values)
        
        # 循环处理模型并实时更新进度
        total_models = len(model_paths)
        all_metrics = [{"station_name": station_name, "model_name": "原始数据(清洗后)", "metrics": original_metric}]
        all_predictions = []
        for i, model_path in enumerate(model_paths):
            model_path = Path(model_path)
            model_name = model_path.stem
            # 更新进度
            progress = 40 + (((i + 1) / total_models) * 60)
            progress_text = f"正在处理第 {i + 1} 个模型: {model_name}"
            crud.update_task_status(db, task_id, "PROCESSING", progress, progress_text)
            print(f"正在处理第 {i + 1} 个模型: {model_name}")
            # 加载模型
            model = load_model(model_path)
            # 预测
            pred_y = model.predict(df_X)
            # 添加到结果列表
            all_predictions.append({"station_name": station_name, "model_name": model_name, "pred_values": pred_y.tolist()})
            all_metrics.append({"station_name": station_name, "model_name": model_name, "metrics": cal_metrics(df_y, pred_y)})
            print(f"第 {i + 1} 个模型: {model_name} 预测完成")
        # 组装并保存最终结果
        timestamps = pd.to_datetime(df_base["timestamp"])  # 转换为datetime对象
        final_results = {
            "timestamps": [ts.isoformat() for ts in timestamps],
            "station_values": df_y.tolist(),
            "grid_values": df_X[f"{element_db_column}_grid"].tolist(),
            "pred_values": all_predictions,
            "metrics": all_metrics,
        }
        # 保存结果到本地, 以便api在任务完成后读取数据
        output_dir = Path("output/pivot_model_results")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{element}_{station_name}_{task_id}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(final_results, f, ensure_ascii=False, indent=4)

        # 更新任务状态
        task = crud.get_task_by_id(db, task_id)
        if task:
            params = task.get_params()
            params["result_path"] = str(output_path)
            task.set_params(params)
            db.add(task)
            crud.update_task_status(db, task_id, "COMPLETED", 100.0, "分析完成, 结果已保存")
        else:
            raise ValueError("找不到任务记录以保存结果路径")

    except Exception as e:
        error_msg = f"任务执行失败: {e}"
        print(error_msg)
        crud.update_task_status(db, task_id, "FAILED", 0.0, error_msg)
    finally:
        db.close()