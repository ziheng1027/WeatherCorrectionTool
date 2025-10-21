# src/tasks/data_correct.py
import os
import gc
import math
import uuid
import numpy as np
import xarray as xr
from pathlib import Path
from typing import Dict, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed
from ..db import crud
from ..db.database import SessionLocal
from ..core.config import settings, STOP_EVENT
from ..core.data_mapping import ELEMENT_TO_NC_MAPPING
from ..core.data_correct import build_feature_for_block
from ..utils.file_io import load_model, get_grid_files_for_season, create_file_packages


def correct_single_file(
        model: object, dem_ds: xr.Dataset, file_package: Dict, 
        element: str, year: str, block_size: int, sub_task_id: str
) -> Optional[Path]:
    """订正单个nc文件, 生成一张订正后的nc文件[原子性任务]"""
    db = SessionLocal()
    try:
        # 更新子任务状态为: PROCESSING
        crud.update_task_status(db, sub_task_id, "PROCESSING", 0.0, "开始处理...")

        nc_var = ELEMENT_TO_NC_MAPPING[element]
        current_file = file_package["current_file"]
        timestamp = file_package["timestamp"]
        lag_files = file_package["lag_files"]   # dict

        # 加载当前时刻的格点数据
        grid_ds = xr.open_dataset(current_file)
        # 创建一个空的、与输入数据同样大小和坐标的结果数组
        corrected_data = np.full_like(grid_ds[nc_var].values, np.nan, dtype=np.float32)\
        
        # 计算总块数用于进度汇报
        lat_size, lon_size = grid_ds.sizes["lat"], grid_ds.sizes["lon"]
        total_blocks = math.ceil(lat_size / block_size) * math.ceil(lon_size / block_size)
        processed_blocks = 0

        # 对每个空间块进行处理
        for lat_start in range(0, lat_size, block_size):
            for lon_start in range(0, lon_size, block_size):
                lat_end = min(lat_start + block_size, lat_size)
                lon_end = min(lon_start + block_size, lon_size)
                
                # 获取当前空间块的数据
                grid_block_ds = grid_ds[nc_var][0, lat_start:lat_end, lon_start:lon_end]
                # 为当前空间块构建特征
                feature_df = build_feature_for_block(
                    grid_block_ds, dem_ds, lag_files, element, timestamp
                )

                # 使用模型进行预测
                corrected_block_data = model.predict(feature_df)
                
                # 回填结果
                corrected_nc_data = corrected_block_data.reshape(grid_block_ds.shape)
                corrected_data[0, lat_start:lat_end, lon_start:lon_end] = corrected_nc_data

                # 释放内存
                del feature_df, corrected_block_data, corrected_nc_data
                gc.collect()

                # 汇报进度
                processed_blocks += 1
                progress = (processed_blocks / total_blocks) * 100
                progress_text = f"正在处理: {processed_blocks}/{total_blocks} 块"
                crud.update_task_status(db, sub_task_id, "PROCESSING", progress, progress_text)

        # 保存订正后的nc文件
        output_path = Path(settings.CORRECTION_OUTPUT_DIR) / f"{nc_var}.hourly" / year / f"corrected.{current_file.name}"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 创建一个新的xarray.Dataset来保存结果
        corrected_ds = xr.Dataset(
            {nc_var: (["time", "lat", "lon"], corrected_data)},
            coords={"time": grid_ds.time, "lat": grid_ds.lat, "lon": grid_ds.lon}
        )
        corrected_ds.to_netcdf(output_path)
        grid_ds.close()
        
        # 释放内存
        del corrected_ds, corrected_data, grid_ds
        gc.collect()
        return output_path
        
    except Exception as e:
        error_msg = f"子进程错误: {e}"
        crud.update_task_status(db, sub_task_id, "FAILED", 0, error_msg)
        print(f"|--> 处理文件 {current_file} 失败: {e}")
        gc.collect()
        return None
    finally:
        db.close()

def correct_mp(
        parent_task_id: str, model_path: str, element: str, start_year: str, end_year: str, 
        season: str, block_size: int, num_workers: int
):
    """多进程订正数据[后台任务]"""
    db = SessionLocal()
    cancel_request = False
    executor = None

    try:
        crud.update_task_status(db, parent_task_id, "PROCESSING", 0, "任务初始化...")
        # 清除旧的停止信号, 确保本次任务不受之前任务的影响
        STOP_EVENT.clear()
        # 检测CPU核心数, 如果用户指定的工作进程数大于CPU核心数, 则使用CPU核心数
        cpu_count = os.cpu_count()
        num_workers = min(num_workers, cpu_count - 1) if cpu_count > 1 else 1
        print(f"|--> 主进程: 检测到 CPU 核心数: {cpu_count}, 将使用 {num_workers} 个工作进程")

        # 主进程中加载共享资源(模型和dem文件)
        model = load_model(model_path)
        dem_ds = xr.open_dataset(settings.DEM_DATA_PATH)

        # 准备需要的文件列表
        nc_var = ELEMENT_TO_NC_MAPPING[element]
        if not nc_var:
            raise ValueError(f"无效的要素: {element}")

        grid_files = get_grid_files_for_season(settings.GRID_DATA_DIR, nc_var, start_year, end_year, season)
        if not grid_files:
            raise ValueError(f"在指定时间范围 ({start_year}-{end_year}, {season}) 未找到任何nc文件")
        
        file_packages = create_file_packages(grid_files, element, settings.LAGS_CONFIG)
        if not file_packages:
            raise ValueError(f"没有找到滞后特征所需的文件: {element} {start_year} {end_year} {season}")

        # 创建并管理进程池
        total_files = len(file_packages)
        if total_files == 0:
            crud.update_task_status(db, parent_task_id, "FAILED", 0.0, "没有需要订正的文件")
            print(f"|--> 主进程: 没有需要订正的文件")
            return
        
        sub_tasks = {}
        for file_package in file_packages:
            sub_task_id = str(uuid.uuid4())
            file_name = file_package["current_file"].name
            sub_task_name = f"订正文件_{file_name}"
            params = {"file_name": file_name, "timestamp": file_package["timestamp"].isoformat()}
            crud.create_task(db, sub_task_id, sub_task_name, "DataCorrect_SubTask", params, parent_task_id)
            sub_tasks[file_name] = sub_task_id
        crud.update_task_status(db, parent_task_id, "PROCESSING", 0, f"任务初始化完成, 准备处理 {total_files} 个文件")

        completed_files = 0
        executor = ProcessPoolExecutor(max_workers=num_workers)

        # 提交所有任务到进程池
        futures = {
            executor.submit(
                correct_single_file, model, dem_ds, file_package, element, 
                file_package["current_file"].parent.name, block_size, 
                sub_tasks[file_package["current_file"].name]
            ): file_package for file_package in file_packages
        }
        print(f"|--> 主进程: 提交了 {len(futures)} 个订正任务到进程池")

        # 处理已经完成的任务
        for future in as_completed(futures):
            if STOP_EVENT.is_set():
                cancel_request = True
                print(f"|--> 主进程: 收到停止信号, 开始终止任务")
                break

            file_package = futures[future]
            original_file_name = file_package["current_file"].name
            sub_task_id = sub_tasks[original_file_name]

            try:
                result_path = future.result()
                if result_path:
                    crud.update_task_status(db, sub_task_id, "COMPLETED", 100.0, f"当前文件订正完成: {result_path.name}")
                    print(f"|--> [成功]: {original_file_name} -> {result_path}")
                else:
                    crud.update_task_status(db, sub_task_id, "FAILED", 0.0, f"当前文件订正失败: {result_path.name}")
                    print(f"|--> [失败]: {original_file_name}")
            except Exception as e:
                crud.update_task_status(db, sub_task_id, "FAILED", 0.0, f"错误: {result_path.name}")
                print(f"|--> [错误]: 处理 {original_file_name} 时出错: {e}")

            completed_files += 1
            progress = (completed_files / total_files) * 100
            progress_text = f"整体进度: {completed_files}/{total_files}"
            crud.update_task_status(db, parent_task_id, "PROCESSING", progress, progress_text)
            print(f"|--> 进度: {completed_files}/{total_files} ({progress:.2f}%)")

        if STOP_EVENT.is_set():
            crud.update_task_status(db, parent_task_id, "FAILED", progress, "任务被用户手动停止")
        else:
            crud.update_task_status(db, parent_task_id, "COMPLETED", 100.0, "所有订正任务已完成")
        
    except Exception as e:
        error_msg = f"任务执行错误: {e}"
        print(f"|--> {error_msg}")
        crud.update_task_status(db, parent_task_id, "FAILED", 0.0, error_msg)
        return
    
    finally:
        if executor:
            print(f"|--> 主进程: 开始关闭进程池...")
            executor.shutdown(wait=True, cancel_futures=True)
            print(f"|--> 主进程: 进程池已关闭")
        if cancel_request:
            print(f"|--> 主进程: 正在更新任务 {parent_task_id} 以及剩余子任务的状态为 FAILED...")
            crud.cancel_subtask(db, parent_task_id)
            print(f"|--> 主进程: 任务 {parent_task_id} 以及剩余子任务的状态已更新为 FAILED")
        elif crud.get_task_by_id(db, parent_task_id).status == "PROCESSING":
            crud.update_task_status(db, parent_task_id, "COMPLETED", 100.0, "所有订正任务已完成")
        db.close()



if __name__ == "__main__":
    model_path = r"output\models\xgboost\xgboost_温度_2020_2020_全年_id=19f2906b-980b-4e64-843e-1a9e48c1ed00.ckpt"
    element = "温度"
    start_year = "2020"
    end_year = "2020"
    season = "全年"
    block_size = 100
    num_workers = 10

    correct_mp(model_path, element, start_year, end_year, season, block_size, num_workers)