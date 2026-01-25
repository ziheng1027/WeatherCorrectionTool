# src/tasks/data_process.py
import os
import uuid
import hashlib
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import multiprocessing as mp
from time import time, sleep
from pathlib import Path
from typing import List
from sqlalchemy.orm import Session
from ..db.database import SessionLocal
from ..db.db_models import TaskProgress
from ..db.crud import (
    get_raw_station_data_by_year, create_task, update_task_status, 
    check_existed_element_by_year, get_subtasks_by_parent_id, cancel_subtask
)
from ..core.config import settings, STOP_EVENT
from ..core.data_mapping import ELEMENT_TO_DB_MAPPING, ELEMENT_TO_NC_MAPPING
from ..core.data_process import (
    clean_station_data, extract_grid_values_for_stations,
    merge_sg_df, import_proc_data_from_temp_files, add_noise_to_grid_data
)
from ..utils.file_io import get_grid_files_for_month, safe_open_mfdataset


TEMP_DATA_DIR = Path("output/temp_data")

def process_elements(db: Session, elements: List[str], start_year: str, end_year: str):
    """处理所有要素的数据"""
    for element in elements:
        process_element(db, element, start_year, end_year)

def process_element(db: Session, element: str, start_year: str, end_year: str):
    """处理单个要素的数据"""
    for year in range(int(start_year), int(end_year) + 1):
        process_yearly_element(db, element, str(year))

def process_yearly_element(subtask_id: str, element: str, year: str):
    """处理单个要素某一年的数据-多进程的原子任务"""
    # 每个进程单独创建数据库会话
    db: Session = SessionLocal()
    # 动态创建临时目录: output/temp_data/{element}/{year}
    output_dir = TEMP_DATA_DIR/element/year
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, f"{element}_{year}.parquet")

    try:
        # 更新子任务状态为 处理中"PROCESSING"
        update_task_status(db, subtask_id, "PROCESSING", 0.0, f"正在处理 {year} 年的 {element} 数据...")
        print(f"|---> [Worker PID:{mp.current_process().pid}] 正在处理 {year} 年的 {element} 数据...")
        
        # 重复处理检查
        print(f"|---> 正在检查 {year} 年的 {element} 数据是否已存在于数据库中...")
        update_task_status(db, subtask_id, "PROCESSING", 1.0, f"正在检查 {year} 年的 {element} 数据是否已存在于数据库中...")
        is_processed = check_existed_element_by_year(db, element, int(year))
        if is_processed:
            print(f"|---> 警告: {year} 年的 {element} 数据已存在于数据库中, 跳过处理")
            update_task_status(db, subtask_id, "COMPLETED", 100.0, f"{year} 年的 {element} 数据已存在, 跳过处理")
            return
        else:
            print(f"|---> {year} 年的 {element} 数据未处理, 准备处理...")

        # 1. 从数据库读取指定element, year的所有站点数据表df(分块读取)
        try:
            update_task_status(db, subtask_id, "PROCESSING", 5.0, f"正在读取 {year} 年的 {element} 站点数据...")
            db_column_name = ELEMENT_TO_DB_MAPPING.get(element)
            df_itrator = get_raw_station_data_by_year(db, db_column_name, int(year), chunk_size=8760)
        except Exception as e:
            print(f"|---> 警告: 读取 {year} 年的 {element} 站点数据时发生错误: {e}")
            update_task_status(db, subtask_id, "FAILED", 5.0, f"读取 {year} 年的 {element} 站点数据时发生错误: {e}")
            return
        
        # 2. 数据清洗, 分块清洗
        cleaned_chunks = [] # 搜集清洗后的数据块
        total_raws = 0
        update_task_status(db, subtask_id, "PROCESSING", 10.0, f"正在分块清洗 {year} 年的 {element} 站点数据...")
        print(f"|---> 开始分块清洗 {year} 年的 {element} 站点数据...")
        start_time = time()
        for df_chunk in df_itrator:
            total_raws += len(df_chunk)
            df_cleaned_chunk = clean_station_data(df_chunk, element) 
            cleaned_chunks.append(df_cleaned_chunk)

        if not cleaned_chunks:
            print(f"|---> 警告: 在 {year} 年未找到有效的 {element} 站点数据")
            update_task_status(db, subtask_id, "FAILED", 10.0, f"在 {year} 年未找到有效的 {element} 站点数据")
            print(f"|-- [Worker PID:{mp.current_process().pid}] 警告: 在 {year} 年未找到有效的 {element} 站点数据")
            return

        df_cleaned = pd.concat(cleaned_chunks, ignore_index=True)
        # 将"station_value"列重命名为DB中的列名
        df_cleaned.rename(columns={"station_value": db_column_name}, inplace=True)
        del cleaned_chunks
        update_task_status(db, subtask_id, "PROCESSING", 20.0, f"已清洗完成 {year} 年的 {element} 站点数据, 共 {total_raws} 条原始记录, 清洗后剩余 {len(df_cleaned)} 条有效记录")
        print(f"耗时: {time() - start_time:.2f} 秒, 共处理 {total_raws} 条原始记录, 清洗后剩余 {len(df_cleaned)} 条有效记录")

        # 3. 读取所有站点的经纬度表
        update_task_status(db, subtask_id, "PROCESSING", 25.0, f"正在读取所有站点的经纬度坐标...")
        station_info = pd.read_csv(settings.STATION_INFO_PATH, encoding="gbk")
        station_coords = {}
        for _, row in station_info.iterrows():
            station_coords[row["区站号(数字)"]] = {"station_name": row["站名"], "lat": row["纬度"], "lon": row["经度"]}

        # 4. 根据82个站点的经纬度坐标, 按月份一次性提取格点值
        start_time = time()
        nc_var = ELEMENT_TO_NC_MAPPING.get(element)
        parquet_writer = None
        total_records_processed = 0

        for month in range(1, 13):
            progress_month_start = 28.0 + (month -  1) * 6
            update_task_status(db, subtask_id, "PROCESSING", progress_month_start, f"正在提取 {year} 年 {month:02d} 月格点数据...")
            grid_files_month = get_grid_files_for_month(settings.GRID_DATA_DIR, nc_var, year, month)
            if not grid_files_month:
                print(f"|---> 警告: {year} 年 {month:02d} 月未找到 {element} 格点数据文件, 跳过")
                continue
            print(f"|--->({element}, {year}-{month:02d}) 读取 {len(grid_files_month)} 个格点文件")

            # 按月打开数据集(减轻I/O瓶颈)
            try:
                ds = safe_open_mfdataset(grid_files_month)
                print(f"|--->({element}, {year}-{month:02d}) 成功打开 {len(grid_files_month)} 个格点文件")
            except Exception as e:
                print(f"|--->({element}, {year}-{month:02d}) 错误: 无法打开格点数据文件: {e}")
                update_task_status(db, subtask_id, "FAILED", progress_month_start, f"打开{month:02d}月的格点数据文件失败: {e}")
                if parquet_writer:
                    parquet_writer.close()
                return

            # 按月提取格点值
            try:
                grid_df_month = extract_grid_values_for_stations(ds, nc_var, station_coords, year)
                seed_str = f"{element}_{year}_{month}"
                deterministic_seed = int(hashlib.md5(seed_str.encode('utf-8')).hexdigest(), 16) % (2**32)
                grid_df_month = add_noise_to_grid_data(grid_df_month, element, seed=deterministic_seed)
                ds.close()
            except Exception as e:
                print(f"|--->({element}, {year}-{month:02d}) 错误: 无法提取格点数据: {e}")
                update_task_status(db, subtask_id, "FAILED", progress_month_start, f"提取{month:02d}月的格点数据失败: {e}")
                if parquet_writer:
                    parquet_writer.close()
                return

            # 筛选当月站点数据
            df_cleaned_month = df_cleaned[df_cleaned["month"] == month].copy()
            if df_cleaned.month.empty:
                print(f"|--->警告: ({element}, {year}-{month:02d}) 未找到有效的站点数据, 跳过")
                continue

            # 按月合并站点数据和格点数据
            try:
                df_sg_month = merge_sg_df(df_cleaned_month, grid_df_month, element)
                del grid_df_month
                del df_cleaned_month
            except Exception as e:
                print(f"|--->({element}, {year}-{month:02d}) 错误: 站点数据和格点数据合并失败: {e}")
                continue
            
            # 增量写入临时文件
            if not df_sg_month.empty:
                try:
                    table = pa.Table.from_pandas(df_sg_month, preserve_index=False)
                    if parquet_writer is None:
                        # 如果是第一个月, 使用它的schema创建写入器
                        parquet_writer = pq.ParquetWriter(output_file, table.schema)
                    # 写入当月的数据块
                    parquet_writer.write_table(table)
                    total_records_processed += len(df_sg_month)
                    print(f"|--->({element}, {year}-{month:02d}) 成功写入 {len(df_sg_month)} 条记录到临时文件")
                    # 释放已写入的数据内存
                    del df_sg_month
                    del table

                except Exception as e:
                    print(f"|--->({element}, {year}-{month:02d}) 错误: 写入临时文件失败: {e}")
                    update_task_status(db, subtask_id, "FAILED", progress_month_start, f"写入{month:02d}月数据到临时文件失败: {e}")
                    if parquet_writer:
                        parquet_writer.close()
                    return
        # 关闭写入器
        if parquet_writer:
            parquet_writer.close()
        else:
            print(f"|--->警告: ({element}, {year}) 未处理任何月份的数据")
            # 创建一个空文件表示完成, 避免导入器出错
            pd.DataFrame().to_parquet(output_file, index=False)
            update_task_status(db, subtask_id, "COMPLETED", 100.0, f"{year} 年 {element} 未找到有效数据, 已跳过")
            return

        # 释放内存
        del df_cleaned
        
        update_task_status(db, subtask_id, "COMPLETED", 100.0, f"{year} 年的 {element} 数据处理完成, 共得到 {total_records_processed} 条记录, 已保存到临时文件: {output_file}")
        print(f"|-- [Worker PID:{mp.current_process().pid}] {year} 年 {element} 数据处理完成, 共得到 {total_records_processed} 条记录, 耗时: {time() - start_time:.2f} 秒")

    except Exception as e:
        # 捕获任何异常, 更新任务状态为失败"FAILED"
        error_msg = f"处理失败: {str(e)}"
        print(f"|-- [Worker PID:{mp.current_process().pid}] 错误: [{year}年 {element}]: {error_msg}")
        update_task_status(db, subtask_id, "FAILED", 0.0, error_msg)
    finally:
        # 确保数据库会话在使用后关闭
        db.close()

def process_mp(task_id: str, elements: List[str], start_year: str, end_year: str, num_workers: int = 4):
    """多进程处理所有要素的数据(任务分发器)"""
    db: Session = SessionLocal()
    sub_tasks_info = []
    try:
        # 1. 创建子任务
        update_task_status(db, task_id, "PROCESSING", 2.0, "正在创建子任务...")
        years = range(int(start_year), int(end_year) + 1)
        for element in elements:
            for year in years:
                sub_task_id = str(uuid.uuid4())
                sub_task_name = f"{year}年 {element} 数据处理"
                params = {"element": element, "year": year}
                create_task(
                    db, task_id=sub_task_id, task_name=sub_task_name,
                    task_type="DataProcess_SubTask", params=params,
                    parent_task_id=task_id 
                )
                sub_tasks_info.append({"sub_task_id": sub_task_id, "element": element, "year": str(year)})
        # 创建数据导入子任务
        import_subtask_id = str(uuid.uuid4())
        import_subtask_name = "导入处理后的数据"
        create_task(
            db, task_id=import_subtask_id, task_name="导入处理后的数据",
            task_type="DataProcess_SubTask", params={"task_name": import_subtask_name},
            parent_task_id=task_id 
        )
        total_tasks = len(sub_tasks_info)
        update_task_status(db, task_id, "PROCESSING", 5.0, "子任务创建完成, 开始处理数据...")
        print(f"|--> 主进程: 已为任务 {task_id} 创建 {total_tasks} 个子任务, 准备开始处理数据...")

        # 2. 设置进程池并分发任务
        mp_context = mp.get_context("spawn")  # 使用spawn启动方法, 避免fork引起的问题
        # 检测CPU核心数, 如果用户指定的工作进程数大于CPU核心数, 则使用CPU核心数
        cpu_count = mp.cpu_count()
        num_workers = min(num_workers, cpu_count - 1) if cpu_count > 1 else 1
        print(f"|--> 主进程: 检测到 CPU 核心数: {cpu_count}, 将使用 {num_workers} 个工作进程")
        pool = mp_context.Pool(processes=num_workers)

        try:
            # 准备传递给每个worker的参数
            worker_args = [(info["sub_task_id"], info["element"], info["year"]) for info in sub_tasks_info]
            # 使用starmap_async 异步执行, 这样主进程可以继续监控进度
            pool.starmap_async(process_yearly_element, worker_args)
        
            # 3. 监控任务进度并更新父任务状态
            completed_count = 0
            while completed_count < total_tasks:
                # 检查停止信号
                if STOP_EVENT.is_set():
                    print(f"|--> 主进程: 检测到关闭信号, 正在终止任务 {task_id}...")
                    pool.terminate()  # 立即终止所有工作进程
                    pool.join()  # 确保所有进程都已结束
                    update_task_status(db, task_id, "FAILED", (completed_count / total_tasks) * 80, "任务被用户取消")
                    canceled_count = cancel_subtask(db, task_id)
                    print(f"|--> 主进程: 任务 {task_id} 已取消, 取消了 {canceled_count} 个子任务")
                    return
            
                # 从数据库查询子任务状态来计算进度
                sub_tasks_from_db = get_subtasks_by_parent_id(db, task_id)
                completed_count = sum(1 for t in sub_tasks_from_db if t.status in ["COMPLETED", "FAILED"])
                overall_progress = (completed_count / total_tasks) * 80
                update_task_status(db, task_id, "PROCESSING", overall_progress, f"已完成 {completed_count}/{total_tasks + 1} 个子任务")
                sleep(15)  # 每15秒检查一次进度
        
        finally:
            pool.close()
            pool.join()  # 确保所有进程都已结束
        
        if STOP_EVENT.is_set():
            print(f"|--> 主进程: 任务 {task_id} 已被取消, 跳过数据导入步骤")
            return

        # 4. 将所有处理完成的临时文件导入数据库
        def import_progress_callback(current, total):
            callback_db: Session = SessionLocal()
            try:
                # 用于将importer的进度更新到数据库
                import_progress = (current / total) * 100
                update_task_status(callback_db, import_subtask_id, "PROCESSING", import_progress, f"正在入库 {current}/{total} 年的数据...")
                # 父任务的进度从80%提升到100%
                overall_progress = 80 + (import_progress * 0.2)
                update_task_status(callback_db, task_id, "PROCESSING", overall_progress, f"正在导入数据({current}/{total})")
            except Exception as e:
                print(f"|--> 主进程: 进度回调发生错误: {str(e)}")
            finally:
                callback_db.close()

        update_task_status(db, import_subtask_id, "PROCESSING", 0.0, "开始从临时文件加载数据...")
        import_stats = import_proc_data_from_temp_files(db, TEMP_DATA_DIR, progress_callback=import_progress_callback)
        update_task_status(db, import_subtask_id, "COMPLETED", 100.0, f"数据导入完成: {import_stats["message"]}")

        # 5. 所有子任务完成后, 更新最终状态
        update_task_status(db, task_id, "COMPLETED", 100.0, " 数据处理任务的所有子任务均已完成")
        print(f"|--> 主进程: 任务 {task_id} 已完成")

    except Exception as e:
        error_msg = f"任务执行失败: {str(e)}"
        current_progress = db.query(TaskProgress.cur_progress).filter(TaskProgress.task_id == task_id).scalar() or 0
        update_task_status(db, task_id, "FAILED", current_progress, error_msg)
        print(f"|--> 主进程: 任务 {task_id} 发生错误: {error_msg}")

    finally:
        db.close()
        # 清理临时文件
        import shutil
        if TEMP_DATA_DIR.exists():
            shutil.rmtree(str(TEMP_DATA_DIR))
            print(f"|--> 主进程: 临时文件已清理")



if __name__ == "__main__":
    db = SessionLocal()
    elements = ["温度", "2分钟平均风速"]
    # process_elements(db, ["温度", "2分钟平均风速"], "2020", "2020")
    test_task_id = str(uuid.uuid4())
    create_task(
        db, task_id=test_task_id, task_name="测试多进程数据处理任务",
        task_type="DataProcess", 
        params={"elements": elements, "start_year": "2020", "end_year": "2020"},
        parent_task_id=None 
    )
    db.close()

    process_mp(test_task_id, elements, "2020", "2020", num_workers=4)