from pathlib import Path
import xarray as xr
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

def visualize_time_range(start_date: str, end_date: str, data_dir: str, original_dir: str):
    """
    可视化指定时间范围内的订正前后数据对比
    
    Args:
        start_date: 开始日期，格式：YYYYMMDDHH
        end_date: 结束日期，格式：YYYYMMDDHH
        data_dir: 订正后数据目录路径
        original_dir: 原始数据目录路径
    """
    # 将字符串转换为datetime对象
    start_dt = datetime.strptime(start_date, "%Y%m%d%H")
    end_dt = datetime.strptime(end_date, "%Y%m%d%H")
    
    # 计算时间范围内的小时数
    total_hours = int((end_dt - start_dt).total_seconds() / 3600) + 1
    
    # 遍历每个小时
    for i in range(total_hours):
        current_dt = start_dt + timedelta(hours=i)
        timestamp = current_dt.strftime("%Y%m%d%H")
        
        # 构建文件路径
        corrected_pattern = f"corrected.CARAS.{timestamp}.tmp.hourly.nc"
        original_pattern = f"CARAS.{timestamp}.tmp.hourly.nc"
        
        corrected_path = Path(data_dir) / corrected_pattern
        original_path = Path(original_dir) / original_pattern
        
        # 检查文件是否存在
        if corrected_path.exists() and original_path.exists():
            try:
                # 读取数据
                original_data = xr.open_dataset(original_path)
                corrected_data = xr.open_dataset(corrected_path)
                
                # 创建子图
                fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
                
                # 绘制原始数据
                original_data.tmp.plot(ax=ax1)
                ax1.set_title(f'Original Temperature at {current_dt}')
                
                # 绘制订正后数据
                corrected_data.tmp.plot(ax=ax2)
                ax2.set_title(f'Corrected Temperature at {current_dt}')
                
                plt.tight_layout()
                plt.show()
                
                # 关闭数据集以释放内存
                original_data.close()
                corrected_data.close()
                
            except Exception as e:
                print(f"处理文件时出错: {str(e)}")
                continue
        else:
            if not corrected_path.exists():
                print(f"订正文件不存在: {corrected_path}")
            if not original_path.exists():
                print(f"原始文件不存在: {original_path}")

# 使用示例
visualize_time_range(
    start_date="2020010100",
    end_date="2020011623",
    data_dir="output/correction/tmp.hourly/2020",
    original_dir="data/grid/tmp.hourly/2020"
)
