# src/tasks/data_preview.py
import zipfile
import shutil
import matplotlib
import pandas as pd
import xarray as xr
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
from ..db import crud
from ..db.database import SessionLocal
from ..core.data_mapping import ELEMENT_TO_NC_MAPPING
from ..utils.file_io import find_nc_file_for_timestamp

matplotlib.use('Agg')  # 使用 'Agg' 后端, 适用于非GUI环境的后台任务
plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号


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

def create_export_images_task(task_id: str, element: str, start_time: datetime, end_time: datetime):
    """
    [新任务] 查找格点.nc文件, 绘制成.png图像, 并压缩为.zip包。
    """
    db = SessionLocal()
    try:
        # 1. 定义临时图片目录和最终zip输出路径
        temp_image_dir = Path("output/temp_data/export_images") / task_id
        temp_image_dir.mkdir(parents=True, exist_ok=True)
        
        zip_output_dir = Path("output/temp_data/export")
        zip_output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = zip_output_dir / f"{task_id}_images.zip"

        # 2. 获取NC变量名和时间戳
        nc_var = ELEMENT_TO_NC_MAPPING.get(element)
        if not nc_var:
            raise ValueError(f"无效的要素名称: {element}")
            
        timestamps = pd.date_range(start=start_time, end=end_time, freq='h')
        total_files = len(timestamps)
        files_found = 0
        
        crud.update_task_status(db, task_id, "PROCESSING", 0, f"准备生成 {total_files} 张图像...")

        # 3. 循环查找、绘图、保存
        for i, ts in enumerate(timestamps):
            try:
                # 查找对应的订正文件
                nc_file_path = find_nc_file_for_timestamp(element, ts)
                
                # 使用 xarray 和 matplotlib 绘图
                with xr.open_dataset(nc_file_path) as ds:
                    data_array = ds[nc_var].isel(time=0)
                    
                    fig, ax = plt.subplots(figsize=(12, 8))
                    
                    # 绘制填色图, 自动添加色标尺
                    data_array.plot.imshow(
                        ax=ax, 
                        cmap='coolwarm',
                        cbar_kwargs={'label': element}
                    )
                    
                    ax.set_title(f"订正前 {element}\n{ts.strftime('%Y-%m-%d %H:%M')}", fontsize=16)
                    
                    # 定义图像输出路径
                    img_filename = f"{nc_var}_{ts.strftime('%Y%m%d%H')}.png"
                    img_path = temp_image_dir / img_filename
                    
                    # 保存图像
                    fig.savefig(img_path, dpi=100, bbox_inches='tight')
                    
                    # [重要] 关闭图像以释放内存
                    plt.close(fig)
                    
                files_found += 1
                
            except FileNotFoundError:
                print(f"警告: 未找到 {ts} 的订正文件, 已跳过")
                pass
            except Exception as plot_e:
                print(f"警告: 绘制 {ts} 时出错: {plot_e}, 已跳过")
                plt.close('all') # 确保关闭所有可能打开的图像
                pass
            
            # 4. 周期性更新进度
            if (i + 1) % 50 == 0 or (i + 1) == total_files:
                progress = ((i + 1) / total_files) * 100
                crud.update_task_status(db, task_id, "PROCESSING", progress, f"正在生成图像... ({i+1}/{total_files})")

        # 5. 压缩所有生成的图像
        crud.update_task_status(db, task_id, "PROCESSING", 95, f"图像生成完毕 ({files_found}张), 开始压缩...")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for img_file in temp_image_dir.glob("*.png"):
                zf.write(img_file, arcname=img_file.name)

        # 6. 任务完成, 更新数据库
        final_message = f"图像打包完成, 共生成 {files_found} / {total_files} 张图像"
        task = crud.get_task_by_id(db, task_id)
        if task:
            params = task.get_params()
            params["result_path"] = str(zip_path) # 存储zip包的路径
            params["files_found"] = files_found
            params["total_requested"] = total_files
            task.set_params(params)
            db.add(task)
            db.commit() # 确保参数写入
        
        crud.update_task_status(db, task_id, "COMPLETED", 100, final_message)

    except Exception as e:
        print(f"图像导出任务 {task_id} 失败: {e}")
        crud.update_task_status(db, task_id, "FAILED", 0, f"任务失败: {e}")
    finally:
        # 7. 清理临时图片目录
        try:
            if temp_image_dir.exists():
                shutil.rmtree(temp_image_dir)
                print(f"临时图片目录已删除: {temp_image_dir}")
        except OSError as e:
            print(f"删除临时图片目录 {temp_image_dir} 失败: {e}")
        
        db.close()