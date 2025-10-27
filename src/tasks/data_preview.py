# src/tasks/data_preview.py
import zipfile
import pandas as pd
from pathlib import Path
from datetime import datetime
from ..db import crud
from ..db.database import SessionLocal
from ..utils.file_io import find_nc_file_for_timestamp


def create_export_zip_task(task_id: str, element: str, start_time: datetime, end_time: datetime):
    """查找指定范围内的所有格点.nc文件, 并将它们压缩成一个zip包[后台任务]"""
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
                    file_path = find_nc_file_for_timestamp(element, ts)
                    
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
