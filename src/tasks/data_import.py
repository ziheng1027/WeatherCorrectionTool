# src/tasks/data_import.py
import pandas as pd
from pathlib import Path
from sqlalchemy.orm import Session
from ..db import crud, db_models
from ..db.database import SessionLocal
from ..core.data_db_mapping import RAW_STATION_DATA_MAPPING, REQUIRED_COLUMNS


def run_station_data_import(task_id: str, dir: str):
    """
    导入站点数据

    :param task_id: 任务ID
    :param dir: 包含所有原始站点数据的文件夹目录路径
    """
    db: Session = SessionLocal()
    try:
        # 立刻将任务状态更新为"处理中PROCESSING"
        crud.update_task_status(db, task_id, "PROCESSING", 0.0, "开始扫描文件...")
        source_dir = Path(dir)
        csv_files = sorted(list(source_dir.glob("*.csv")))
        total_files = len(csv_files)

        if total_files == 0:
            crud.update_task_status(db, task_id, "FAILED", 0.0, f"任务失败: 在指定目录{dir}下没有找到csv文件")
            return
        
        # 循环处理每个文件
        for i, file_path in enumerate(csv_files):
            progress = (i + 1) / total_files * 100
            crud.update_task_status(db, task_id, "PROCESSING", progress, f"正在处理文件: {file_path.name} ({i+1}/{total_files})")
            try:
                df_raw = pd.read_csv(file_path, usecols=REQUIRED_COLUMNS)
            except ValueError as e:
                raise ValueError(f"文件 {file_path.name} 中缺少必需的列: {e}")
            
            # 重命名csv的中文列名以匹配数据库模型
            df_renamed = df_raw.rename(columns=RAW_STATION_DATA_MAPPING)
            # 合成timestamp列
            df_renamed["timestamp"] = pd.to_datetime(df_renamed[["year", "month", "day", "hour"]])

            final_columns = [
                "station_id", "station_name", "lat", "lon", "timestamp", "year", "month", "day", "hour",
                "temperature", "humidity", "precipitation_1h", "wind_speed_2min"
            ]
            crud.bulk_insert_raw_station_data(db, df_renamed[final_columns])

        # 所有文件处理完毕后, 将任务状态更新为"完成COMPLETED"
        crud.update_task_status(db, task_id, "COMPLETED", 100.0, "所有文件处理完毕")

    except Exception as e:
        task = crud.get_task_by_id(db, task_id)
        if task:
            crud.status = "FAILED"
            task.cur_progress = task.cur_progress   # 保持失败时的进度不变
            task.progress_text = f"任务失败: {str(e)}"
            db.commit()
    
    finally:
        db.close()