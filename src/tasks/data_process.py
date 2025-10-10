# src/tasks/data_process.py
import os
import uuid
import pandas as pd
import multiprocessing as mp
from time import time, sleep
from pathlib import Path
from typing import List
from sqlalchemy.orm import Session
from ..db.database import SessionLocal
from ..db.db_models import TaskProgress
from ..db.crud import (
    get_raw_station_data_by_year, create_task, update_task_status, 
    check_existed_element_by_year, get_subtasks_by_parent_id
)
from ..core.config import settings, STOP_EVENT
from ..core.data_mapping import ELEMENT_TO_DB_MAPPING, ELEMENT_TO_NC_MAPPING
from ..utils.file_io import get_grid_files, safe_open_mfdataset
from ..core.data_process import (
    clean_station_data, extract_grid_values_for_stations, merge_sg_df,
    import_proc_data_from_temp_files
)



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
        update_task_status(db, subtask_id, "PROCESSING", 0.0, f"开始处理 {year} 年的 {element} 数据...")
        print(f"|---> [Worker PID:{mp.current_process().pid}] 开始处理 {year} 年的 {element} 数据...")
        
        # 重复处理检查
        print(f"|---> 正在检查 {year} 年的 {element} 数据是否已存在于数据库中...")
        is_processed = check_existed_element_by_year(db, element, int(year))
        update_task_status(db, subtask_id, "COMPLETED", 100.0, f"{year} 年的 {element} 数据已存在, 跳过处理")
        if is_processed:
            print(f"|---> 警告: {year} 年的 {element} 数据已存在于数据库中, 跳过处理")
            return
        else:
            print(f"|---> {year} 年的 {element} 数据未处理, 准备开始处理...")

        # 1. 从数据库读取指定element, year的所有站点数据表df(分块读取)
        db_column_name = ELEMENT_TO_DB_MAPPING.get(element)
        df_itrator = get_raw_station_data_by_year(db, db_column_name, int(year), chunk_size=8760)

        # 2. 数据清洗, 分块清洗
        cleaned_chunks = [] # 搜集清洗后的数据块
        total_raws = 0
        print(f"|---> 开始分块清洗 {year} 年的 {element} 站点数据...")
        start_time = time()
        for df_chunk in df_itrator:
            total_raws += len(df_chunk)
            df_cleaned_chunk = clean_station_data(df_chunk) 
            cleaned_chunks.append(df_cleaned_chunk)

        if not cleaned_chunks:
            print(f"|---> 警告: 在 {year} 年未找到有效的 {element} 站点数据")
            print(f"|-- [Worker PID:{mp.current_process().pid}] 警告: 在 {year} 年未找到有效的 {element} 站点数据")
            return
        
        df_cleaned = pd.concat(cleaned_chunks, ignore_index=True)
        # 将"station_value"列重命名为DB中的列名
        df_cleaned.rename(columns={"station_value": db_column_name}, inplace=True)
        update_task_status(db, subtask_id, "PROCESSING", 20.0, f"已清洗完成 {year} 年的 {element} 站点数据, 共 {total_raws} 条原始记录, 清洗后剩余 {len(df_cleaned)} 条有效记录")
        print(f"耗时: {time() - start_time:.2f} 秒, 共处理 {total_raws} 条原始记录, 清洗后剩余 {len(df_cleaned)} 条有效记录")

        # 3. 读取所有站点的经纬度表
        station_info = pd.read_csv(settings.STATION_INFO_PATH, encoding="gbk")
        station_coords = {}
        for _, row in station_info.iterrows():
            station_coords[row["区站号(数字)"]] = {"station_name": row["站名"], "lat": row["纬度"], "lon": row["经度"]}

        # 4. 根据82个站点的经纬度坐标一次性提取格点值
        start_time = time()
        grid_files = get_grid_files(settings.GRID_DATA_DIR, ELEMENT_TO_NC_MAPPING.get(element), year)
        if not grid_files:
            print(f"|---> 警告: 在 {year} 年未找到有效的 {element} 格点数据文件")
            return
        print(f"|--->({element}, {year}) 读取 {len(grid_files)} 个格点文件, 准备提取格点值...")

        # 打开多个netCDF文件, 处理坐标非单调问题
        try:
            ds = safe_open_mfdataset(grid_files)
            print(f"({element}, {year}年) 备选合并方案成功打开格点数据")
        except Exception as e:
            print(f"({element}, {year}年) 错误: 无法打开格点数据文件: {e}")
            return

        grid_df = extract_grid_values_for_stations(ds, ELEMENT_TO_NC_MAPPING.get(element), station_coords, year)
        ds.close()
        update_task_status(db, subtask_id, "PROCESSING", 60.0, f"格点数据提取完成, 已提取 {len(grid_df)} 条格点记录")
        print(f"耗时: {time() - start_time:.2f} 秒, 共提取 {len(grid_df)} 条格点记录")
        print(grid_df.head(2))
        print(grid_df.shape)
        print(df_cleaned.head(2))
        print(df_cleaned.shape)
    
        # 5. 合并站点数据和格点数据
        print(f"|--->({element}, {year}) 开始合并站点数据和格点数据...")
        start_time = time()
        df_sg = merge_sg_df(df_cleaned, grid_df, element)
        update_task_status(db, subtask_id, "PROCESSING", 80.0, f"站点数据和格点数据合并完成, 共得到 {len(df_sg)} 条记录")
        print(f"耗时: {time() - start_time:.2f} 秒, 共合并得到 {len(df_sg)} 条记录")
        print(df_sg.head(2))
        print(df_sg.shape)

        # 6. 将合并后的数据以parquet格式保存到临时目录
        if not df_sg.empty:
            print(f"|--->({element}, {year} 将 {len(df_sg)} 条合并后的数据写入临时文件: {output_file}")
            df_sg.to_parquet(output_file, index=False)
        else:
            print(f"|--->({element}, {year} 警告: 合并后的数据为空, 跳过")
        update_task_status(db, subtask_id, "COMPLETED", "100.0", f"{year} 年的 {element} 数据处理完成, 共得到 {len(df_sg)} 条记录, 已保存到临时文件: {output_file}")
        print(f"|-- [Worker PID:{mp.current_process().pid}] {year} 年 {element} 数据处理完成, 共得到 {len(df_sg)} 条记录")
    
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
        update_task_status(db, task_id, "PROCESSING", 0.0, "正在创建子任务...")
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
        total_tasks = len(sub_tasks_info)
        update_task_status(db, task_id, "PROCESSING", 2.0, "子任务创建完成, 开始处理数据...")
        print(f"|--> 主进程: 已为任务 {task_id} 创建 {total_tasks} 个子任务, 准备开始处理数据...")

        # 2. 设置进程池并分发任务
        mp_context = mp.get_context("spawn")  # 使用spawn启动方法, 避免fork引起的问题
        # 检测CPU核心数, 如果用户指定的工作进程数大于CPU核心数, 则使用CPU核心数
        cpu_count = mp.cpu_count()
        num_workers = min(num_workers, cpu_count - 1) if cpu_count > 1 else 1
        print(f"|--> 主进程: 检测到 CPU 核心数: {cpu_count}, 将使用 {num_workers} 个工作进程")
        pool = mp_context.Pool(processes=num_workers)
        # 准备传递给每个worker的参数
        worker_args = [(info["sub_task_id"], info["element"], info["year"]) for info in sub_tasks_info]
        # 使用starmap_async 异步执行, 这样主进程可以继续监控进度
        pool.starmap_async(process_yearly_element, worker_args)
        # 关闭进程池
        pool.close()
        
        # 3. 监控任务进度并更新父任务状态
        completed_count = 0
        while completed_count < total_tasks:
            # 检查停止信号
            if STOP_EVENT.is_set():
                print(f"|--> 主进程: 检测到关闭信号, 正在终止任务 {task_id}...")
                pool.terminate()  # 立即终止所有工作进程
                update_task_status(db, task_id, "FAILED", (completed_count / total_tasks) * 80, "任务被用户取消")
                break
            
            # 从数据库查询子任务状态来计算进度
            sub_tasks_from_db = get_subtasks_by_parent_id(db, task_id)
            completed_count = sum(1 for t in sub_tasks_from_db if t.status in ["COMPLETED", "FAILED"])
            overall_progress = (completed_count / total_tasks) * 80
            update_task_status(db, task_id, "PROCESSING", overall_progress, f"已完成 {completed_count}/{total_tasks + 1} 个子任务")
            sleep(15)  # 每15秒检查一次进度
        pool.join()  # 确保所有进程都已结束

        # 4. 将所有处理完成的临时文件导入数据库
        import_subtask_id = str(uuid.uuid4())
        create_task(
            db, task_id=import_subtask_id, task_name="导入处理后的数据",
            task_type="DataProcess_Import", params={},
            parent_task_id=task_id 
        )
        
        def import_progress_callback(current, total):
            # 用于将importer的进度更新到数据库
            import_progress = (current / total) * 100
            update_task_status(db, import_subtask_id, "PROCESSING", import_progress, f"正在入库 {current}/{total} 年的数据...")
            # 父任务的进度从80%提升到100%
            overall_progress = 80 + (import_progress * 0.2)
            update_task_status(db, task_id, "PROCESSING", overall_progress, f"正在导入数据({current}/{total})")

        update_task_status(db, import_subtask_id, "PROCESSING", 0.0, "开始从临时文件加载数据...")
        import_stats = import_proc_data_from_temp_files(db, TEMP_DATA_DIR, progress_callback=import_progress_callback)
        update_task_status(db, import_subtask_id, "COMPLETED", 100.0, f"数据导入完成: {import_stats["message"]}")

        # 5. 所有子任务完成后, 更新最终状态
        update_task_status(db, task_id, "COMPLETED", 100.0, " 数据处理任务的所有子任务均已完成")
        print(f"|--> 主进程: 任务 {task_id} 已完成")

    except Exception as e:
        error_msg = f"任务执行失败: {str(e)}"
        current_progress = db.query(TaskProgress.cur_progress).filter(TaskProgress.task_id == task_id).scalar() or 0
        update_task_status(db, task_id, "FAILED", 0.0, error_msg)
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