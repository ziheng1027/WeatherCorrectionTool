# src/tasks/data_pivot.py
import json
import zipfile
import pandas as pd
from pathlib import Path
from typing import List
from datetime import datetime
from ..db import crud
from ..db.database import SessionLocal
from ..core.data_mapping import ELEMENT_TO_DB_MAPPING
from ..core.data_pivot import bulid_feature_for_pivot
from ..utils.file_io import load_model, find_corrected_nc_file_for_timestamp
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

def create_export_zip_task(task_id: str, element: str, start_time: datetime, end_time: datetime):
    """查找指定范围内的所有订正后.nc文件, 并将它们压缩成一个zip包[后台任务]"""
    db = SessionLocal()
    try:
        # 1. 定义输出路径
        output_dir = Path("output/temp_data/export")
        output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = output_dir / f"{task_id}.zip"

        # 2. 获取所有时间戳
        timestamps = pd.date_range(start=start_time, end=end_time, freq='h')
        total_files = len(timestamps)
        files_found = 0
        
        crud.update_task_status(db, task_id, "PROCESSING", 0, f"准备压缩 {total_files} 个文件...")

        # 3. 循环查找并压缩文件
        # 使用 'w' 模式创建新的zip文件, ZIP_DEFLATED 提供较好的压缩率
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, ts in enumerate(timestamps):
                try:
                    # 查找对应的订正文件
                    file_path = find_corrected_nc_file_for_timestamp(element, ts)
                    
                    # 写入zip包, arcname=file_path.name 确保zip包内是扁平结构, 不含服务器绝对路径
                    zf.write(file_path, arcname=file_path.name)
                    files_found += 1
                except FileNotFoundError:
                    # 如果某个时次的文件不存在, 打印警告并跳过
                    print(f"警告: 未找到 {ts} 的订正文件, 已跳过")
                    pass
                
                # 4. 周期性更新进度 (例如每50个文件或最后1个文件)
                if (i + 1) % 50 == 0 or (i + 1) == total_files:
                    progress = ((i + 1) / total_files) * 100
                    crud.update_task_status(db, task_id, "PROCESSING", progress, f"正在压缩文件... ({i+1}/{total_files})")

        # 5. 任务完成, 更新数据库
        final_message = f"打包完成, 共找到 {files_found} / {total_files} 个文件"
        task = crud.get_task_by_id(db, task_id)
        if task:
            params = task.get_params()
            params["result_path"] = str(zip_path)
            params["files_found"] = files_found
            params["total_requested"] = total_files
            task.set_params(params)
            db.add(task)
            db.commit() # 确保参数写入
        
        crud.update_task_status(db, task_id, "COMPLETED", 100, final_message)

    except Exception as e:
        print(f"导出任务 {task_id} 失败: {e}")
        crud.update_task_status(db, task_id, "FAILED", 0, f"任务失败: {e}")
    finally:
        db.close()
