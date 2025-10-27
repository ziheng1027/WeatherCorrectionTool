# src/tasks/data_import.py
import uuid
import pandas as pd
from pathlib import Path
from sqlalchemy.orm import Session
from ..db import crud
from ..db.database import SessionLocal
from ..core.data_mapping import RAW_STATION_DATA_TO_DB_MAPPING, REQUIRED_COLUMNS
from ..core.config import STOP_EVENT


def _count_lines_in_file(file_path: Path) -> int:
    """快速计算文件行数(不含表头)"""
    with open(file_path, "r", encoding="utf-8") as f:
        return sum(1 for _ in f) - 1

def run_station_data_import(task_id: str, dir: str):
    """
    导入站点数据

    :param task_id: 任务ID
    :param dir: 包含所有原始站点数据的文件夹目录路径
    """
    db: Session = SessionLocal()
    sub_tasks = []
    try:
        # 更新父任务状态为 处理中"PROCESSING"
        crud.update_task_status(db, task_id, "PROCESSING", 0.0, "开始扫描文件并创建子任务...")
        print(f"|--> 任务 {task_id} 开始扫描文件并创建子任务...")
        source_dir = Path(dir)
        csv_files = sorted(list(source_dir.glob("*.csv")))
        total_files = len(csv_files)

        if total_files == 0:
            crud.update_task_status(db, task_id, "FAILED", 0.0, f"任务失败: 在指定目录{dir}下没有找到csv文件")
            return
        
        # 1. 获取历史上所有已完成的文件名
        try:
            completed_files_list, _, _ = crud.get_global_filenames_by_status(db, "DataImport_SubTask", "COMPLETED")
            completed_files_set = set(completed_files_list)
            print(f"|--> 数据库中检测到 {len(completed_files_set)} 个已完成的文件。")
        except Exception as e:
            print(f"|--> 警告：查询历史已完成文件失败: {e}。将全量导入。")
            completed_files_set = set()
        
        # 2. 过滤文件并创建子任务
        files_to_process = []
        skipped_count = 0
        for file_path in csv_files:
            if file_path.name in completed_files_set:
                print(f"|--> 跳过已完成文件: {file_path.name}")
                skipped_count += 1
                continue
            files_to_process.append(file_path)

        if not files_to_process:
            crud.update_task_status(db, task_id, "COMPLETED", 100.0, "所有文件均已在历史任务中导入。")
            print(f"|--> 所有 {total_files} 个文件均已导入，任务完成。")
            return

        total_tasks_to_run = len(files_to_process)
        print(f"|--> 本次任务需处理 {total_tasks_to_run} 个新文件 (已跳过 {skipped_count} 个)。")

        # 3. 为需要处理的文件创建子任务
        for file_path in files_to_process:
            sub_task_id = str(uuid.uuid4())
            sub_task_name = f"导入文件: {file_path.name}"
            sub_task = crud.create_task(
                db, task_id=sub_task_id, task_name=sub_task_name,
                task_type="DataImport_SubTask", params={"file_name": file_path.name},
                parent_task_id=task_id 
            )
            sub_tasks.append(sub_task)
        
        # 更新父任务状态, 进度=已跳过/总数
        initial_progress = (skipped_count / total_files) * 100
        crud.update_task_status(db, task_id, "PROCESSING", initial_progress, f"已创建 {total_tasks_to_run} 个新文件导入子任务 (跳过 {skipped_count} 个)...")
        print(f"|--> 已创建 {total_tasks_to_run} 个文件导入子任务...")

        # 循环处理每个文件(子任务)
        completed_count = 0
        CHUNK_SIZE = 50000
        for i, sub_task in enumerate(sub_tasks):
            # 在处理每个文件前, 检查停止信号
            if STOP_EVENT.is_set():
                print(f"检测到关闭信号, 任务 {task_id} 中断")
                # 更新下一任务状态为已取消
                crud.update_task_status(db, task_id, "FAILED", (i/total_files) * 100, "任务被用户中断")
                return
            file_name = sub_task.get_params()["file_name"]
            file_path = source_dir / file_name
            rows_processed = 0
            
            try:
                # 获取文件总行数, 用于精确计算进度
                total_rows = _count_lines_in_file(Path(file_path))

                if total_rows == 0:
                    crud.update_task_status(db, sub_task.task_id, "COMPLETED", 100.0, "文件为空, 已跳过")
                    print(f"|--> 文件 {file_name} 为空, 已跳过")
                    completed_count += 1
                    continue

                # 更新子任务状态为 PROCESSING
                crud.update_task_status(db, sub_task.task_id, "PROCESSING", 0.0, "开始处理文件...")
                print(f"|--> 开始处理文件 {file_name}")

                # 使用read_csv的chunksize参数创建迭代器
                df_iterator = pd.read_csv(file_path, usecols=REQUIRED_COLUMNS, chunksize=CHUNK_SIZE)

                # 循环处理每个数据块
                for df_chunk in df_iterator:
                    if STOP_EVENT.is_set():
                        print(f"检测到关闭信号, 文件 {file_name} 处理中断")
                        crud.update_task_status(db, sub_task.task_id, "FAILED", (rows_processed / total_rows) * 100, "任务被用户中断")
                        print("|--> 任务被用户中断")
                    
                    df_renamed = df_chunk.rename(columns=RAW_STATION_DATA_TO_DB_MAPPING)
                    df_renamed["timestamp"] = pd.to_datetime(df_renamed[["year", "month", "day", "hour"]])

                    final_columns = [
                        "station_id", "station_name", "lat", "lon", "timestamp", "year", "month", "day", "hour",
                        "temperature", "humidity", "precipitation_1h", "wind_speed_2min"
                    ]
                    # 将这个小的df存入数据库
                    # crud.bulk_insert_raw_station_data(db, df_renamed[final_columns])
                    crud.upsert_raw_station_data(db, df_renamed[final_columns])

                    # 更新进度
                    rows_processed += len(df_chunk)
                    file_progress = (rows_processed / total_rows) * 100
                    crud.update_task_status(db, sub_task.task_id, "PROCESSING", file_progress, f"已入库 {rows_processed}/{total_rows} 行")
                    print(f"|--> 已入库 {rows_processed}/{total_rows} 行")
                
                # 单个文件的所有数据块处理完毕, 更新子任务为 已完成"COMPLETED"
                crud.update_task_status(db, sub_task.task_id, "COMPLETED", 100.0, f"文件导入成功，共 {total_rows} 行")
                print(f"|--> 文件 {file_name} 导入成功，共 {total_rows} 行")
                completed_count += 1

            except Exception as e:
                error_msg = f"导入失败: {str(e)}"
                crud.update_task_status(db, sub_task.task_id, "FAILED", 0.0, error_msg)
            
            # 更新父任务的总体进度
            overall_progress = (i + 1) / total_files * 100
            crud.update_task_status(db, task_id, "PROCESSING", overall_progress, f"正在处理 {file_path} ({i+1}/{total_files})")
            print(f"|--> 正在处理 {file_path} ({i+1}/{total_files})")

        if completed_count == total_files:
            crud.update_task_status(db, task_id, "COMPLETED", 100.0, f"所有文件导入成功，共 {total_files} 个文件")
            print(f"|--> 所有文件导入成功，共 {total_files} 个文件")
        else:
            failed_count = total_files - completed_count
            crud.update_task_status(db, task_id, "COMPLETED", (completed_count/total_files)*100, f"任务完成，{completed_count}个成功，{failed_count}个失败")
            print(f"|--> 任务完成，{completed_count}个成功，{failed_count}个失败")
    
    except Exception as e:
        crud.update_task_status(db, task_id, "FAILED", 0.0, f"任务失败: {str(e)}")
    
    finally:
        db.close()