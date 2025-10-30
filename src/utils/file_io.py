# src/utils/file_io.py
import os
import glob
import json
import joblib
import xarray as xr
import pandas as pd
from typing import List, Dict
from pathlib import Path
from datetime import datetime, timedelta
from pathlib import Path
from ..core.config import settings
from ..core.data_mapping import ELEMENT_TO_NC_MAPPING



def get_station_files(dir):
    """获取站点文件列表"""
    if not os.path.isdir(dir):
        raise ValueError(f"{dir} 不是有效目录")
    station_files = [os.path.join(dir, f) for f in os.listdir(dir) if f.endswith('.csv')]
    return station_files

def get_grid_files(dir, var_grid, year):
    """获取格点文件列表"""
    if not os.path.isdir(dir):
        raise ValueError(f"{dir} 不是有效目录")
    dir = os.path.join(dir, f"{var_grid}.hourly", str(year))
    pattern = os.path.join(dir, "*.nc")
    grid_files = sorted(glob.glob(pattern))
    return grid_files

def get_grid_files_for_month(dir, var_grid, year, month):
    """按年和月获取格点文件列表(每个进程一次性读取1个月而非一年,减轻磁盘压力)"""
    if not os.path.isdir(dir):
        raise ValueError(f"{dir} 不是有效目录")
    dir = os.path.join(dir, f"{var_grid}.hourly", str(year))
    if not os.path.isdir(dir):
        print(f"|--> 警告: 目录 {dir} 不存在, 无法获取 {year}年{month}月 的格点文件")
        return []
    pattern = os.path.join(dir, f"CARAS.{year}{month:02d}*.nc")
    grid_files = sorted(glob.glob(pattern))
    return grid_files

def find_nc_file_for_timestamp(element: str, timestamp: datetime) -> Path:
    """根据要素和时间戳定位对应的.nc文件"""
    nc_var = ELEMENT_TO_NC_MAPPING.get(element)
    if not nc_var:
        raise ValueError(f"无效的要素名称: {element}")

    # 构建文件路径: CARAS/tmp.hourly/2008/xxx.nc
    file_name = f"CARAS.{timestamp.strftime('%Y%m%d%H')}.{nc_var}.hourly.nc"
    if nc_var =="pre":
        file_name = f"CARAS.{timestamp.strftime('%Y%m%d%H')}.{nc_var}cip.hourly.nc"
    
    file_path = Path(settings.GRID_DATA_DIR) / f"{nc_var}.hourly" / str(timestamp.year) / file_name

    if not file_path.exists():
        raise FileNotFoundError(f"格点文件不存在: {file_path}")
    
    return file_path

def safe_open_mfdataset(grid_files, **kwargs):
    """安全地打开多个netCDF文件, 处理坐标问题(基于手动合并方案优化)"""
    if not grid_files:
        raise ValueError("没有找到任何格点文件")
    try:
        # 获取第一个文件作为坐标基准
        with xr.open_dataset(grid_files[0]) as ref_ds:
            ref_lat = ref_ds.lat
            ref_lon = ref_ds.lon
            print(f"|--> 使用 {grid_files[0]} 的坐标作为基准打开文件: lat: ({ref_lat.min():.2f}, {ref_lat.max():.2f}) | lon: ({ref_lon.min():.2f}, {ref_lon.max():.2f})")
        
        def _preprocess(ds):
            """在xarray打开每个文件时, 强制分配标准坐标"""
            return ds.assign_coords(lat=ref_lat, lon=ref_lon)

        ds = xr.open_mfdataset(grid_files, preprocess=_preprocess, combine="by_coords", parallel=True, **kwargs)
        print(f"|--> by_coords方案成功打开 {len(grid_files)} 个文件")
        return ds
    except Exception as e:
        print(f"打开文件时发生错误, 尝试使用'nested'合并: {e}")
        try:
            ds = xr.open_mfdataset(grid_files, combine="nested", concat_dim="time", parallel=True, **kwargs)
            ds = ds.assign_coords(lat=ref_lat, lon=ref_lon)
            print(f"|--> nested方案成功打开 {len(grid_files)} 个文件")
            return ds
        except Exception as e:
            print(f"打开文件发生错误, by_coords和nested方案都失败: {e}")
            raise

def save_model(
        model: object, model_name: str, element: str, start_year: str, 
        end_year: str, season: str, task_id: str
):
    """保存模型"""
    model_name = model_name.lower()
    checkpoint_dir = os.path.join(settings.MODEL_OUTPUT_DIR, model_name)
    os.makedirs(checkpoint_dir, exist_ok=True)
    checkpoint_name = f"{model_name}_{element}_{start_year}_{end_year}_{season}_id={task_id}.ckpt"
    checkpoint_path = os.path.join(checkpoint_dir, checkpoint_name)
    joblib.dump(model, checkpoint_path)
    print(f"模型已保存到: {checkpoint_path}\n")

def load_model(model_path):
    """加载模型"""
    model = joblib.load(model_path)
    return model

def save_losses(
        train_losses: list, test_losses: list, model_name: str, element: str,
        start_year: str, end_year: str, season: str, task_id: str
):
    """保存训练和测试损失"""
    model_name = model_name.lower()
    losses_df = pd.DataFrame({
        "epoch": range(1, len(train_losses) + 1),
        "train_loss": train_losses,
        "test_loss": test_losses
    })
    losses_dir = os.path.join(settings.LOSSES_OUTPUT_DIR, model_name)
    os.makedirs(losses_dir, exist_ok=True)
    losses_file_name = f"{model_name}_{element}_{start_year}_{end_year}_{season}_{task_id}.csv"
    losses_path = os.path.join(losses_dir, losses_file_name)
    losses_df.to_csv(losses_path, index=False)
    print(f"训练损失已保存到: {losses_path}\n")

def save_metrics_in_testset_all(
        metrics_true: dict, metrics_pred: dict, model_name: str, element: str,
        start_year: str, end_year: str, season: str, task_id: str
):
    """保存测试集的整体指标(所有站点均值)"""
    model_name = model_name.lower()
    metrics_dir = os.path.join(settings.METRIC_OUTPUT_DIR, model_name, "overall")
    os.makedirs(metrics_dir, exist_ok=True)
    metrics_file_name = f"{model_name}_{element}_{start_year}_{end_year}_{season}_{task_id}.json"
    metrics_path = os.path.join(metrics_dir, metrics_file_name)
    with open(metrics_path, 'w') as f:
        json.dump({
            "testset_true": metrics_true,
            "testset_pred": metrics_pred
        }, f, indent=4)
    print(f"测试集整体指标已保存到: {metrics_path}\n")

def save_metrics_in_testset_station(
        metrics_df: pd.DataFrame, model_name: str, element: str,
        start_year: str, end_year: str, season: str
):
    """保存测试集的站点指标(每个站点的均值)"""
    model_name = model_name.lower()
    metrics_dir = os.path.join(settings.METRIC_OUTPUT_DIR, model_name, "station")
    os.makedirs(metrics_dir, exist_ok=True)
    metrics_file_name = f"{model_name}_{element}_{start_year}_{end_year}_{season}_testset-station.csv"
    metrics_path = os.path.join(metrics_dir, metrics_file_name)
    metrics_df.to_csv(metrics_path, index=False)
    print(f"测试集站点指标已保存到: {metrics_path}\n")

def save_feature_importance(
        feature_importance: dict, model_name: str, element: str,
        start_year: str, end_year: str, season: str
):
    """保存特征重要性"""
    model_name = model_name.lower()
    importance_dir = os.path.join(settings.FEATURE_IMPORTANCE_OUTPUT_DIR, model_name)
    os.makedirs(importance_dir, exist_ok=True)
    importance_file_name = f"{model_name}_{element}_{start_year}_{end_year}_{season}_feature-importance.json"
    importance_path = os.path.join(importance_dir, importance_file_name)
    with open(importance_path, 'w') as f:
        json.dump(feature_importance, f, indent=4)
    print(f"特征重要性已保存到: {importance_path}\n")

def save_true_pred(
        result_df: pd.DataFrame, model_name: str, element: str,
        start_year: str, end_year: str, season: str
):
    """保存站点数据、格点数据、预测数据"""
    model_name = model_name.lower()
    result_dir = os.path.join(settings.PRED_TRUE_OUTPUT_DIR, model_name)
    os.makedirs(result_dir, exist_ok=True)
    result_file_name = f"{model_name}_{element}_{start_year}_{end_year}_{season}_station-grid-pred.csv"
    result_path = os.path.join(result_dir, result_file_name)
    result_df.to_csv(result_path, index=False)
    print(f"站点数据、格点数据、预测数据已保存到: {result_path}\n")

def get_grid_files_for_season(grid_data_dir: str, nc_var: str, start_year: str, end_year: str, season: str) -> List[Path]:
    """根据年份范围和季节筛选出所有需要处理的格点文件"""
    print(f"|--> 开始搜索文件, 年份: {start_year}-{end_year}, 季节: {season} ...")
    all_files = []
    season_months = {
        "春季": [3, 4, 5],
        "夏季": [6, 7, 8],
        "秋季": [9, 10, 11],
        "冬季": [12, 1, 2]
    }
    for year in range(int(start_year), int(end_year) + 1):
        year_dir = Path(grid_data_dir) / f"{nc_var}.hourly" / str(year)
        if not year_dir.exists():
            print(f"|--> {year_dir} 目录不存在, 跳过")
            continue
        files_in_year = list(year_dir.glob("*.nc"))

        # 筛选出属于当前季节的文件
        if season == "全年":
            all_files.extend(files_in_year)
        else:
            months = season_months[season]
            for file in files_in_year:
                try:
                    timestamp = file.stem.split(".")[1]
                    month = int(timestamp[4:6])
                    if month in months:
                        all_files.append(file)
                except:
                    print(f"|--> {file} 文件名不符合规范, 跳过")
                    continue
    # 按照时间顺序排序
    all_files.sort()
    print(f"|--> 共找到 {len(all_files)} 个文件")
    return all_files

def create_file_packages(file_list: List[Path], element: str, lags_config: dict) -> List[Dict]:
    """为每个待处理的文件创建包含滞后项文件路径的文件包"""
    print("|--> 开始创建滞后项所需要的文件包 ...")
    file_packages = []
    
    # 获取当前要素需要的滞后小时数
    lags = lags_config[element]
    if not lags:
        print(f"|--> 警告: 当前要素 {element} 没有在 lags_config 中配置滞后项")
    for file_path in file_list:
        try:
            # 从文件名解析当前时间戳
            timestamp = file_path.stem.split(".")[1]
            current_timestamp = datetime.strptime(timestamp, "%Y%m%d%H")
            
            lag_files = {}
            for lag in lags:
                lag_key = f"lag_{lag}h"
                lag_timestamp = current_timestamp - timedelta(hours=lag)
                try:
                    lag_file_path = find_nc_file_for_timestamp(element, lag_timestamp)
                    lag_files[lag_key] = lag_file_path
                except FileNotFoundError:
                    lag_files[lag_key] = None
            
            file_package = {
                "current_file": file_path,
                "lag_files": lag_files,
                "timestamp": current_timestamp
            }
            file_packages.append(file_package)
        except (IndexError, ValueError):
            print(f"|--> 警告: {file_path} 文件名解析失败(不符合CARAS.2020010100.element.hourly.nc格式), 跳过")
            continue
    print(f"|--> 文件包创建完成, 共 {len(file_packages)} 个文件包")
    return file_packages

def find_corrected_nc_file_for_timestamp(element: str, timestamp: datetime) -> Path:
    """根据要素和时间戳找到对应的校正后的nc文件"""
    nc_var = ELEMENT_TO_NC_MAPPING.get(element)
    if not nc_var:
        raise ValueError(f"无效的要素名称: {element}")

    # 构建文件路径
    file_name = f"corrected.CARAS.{timestamp.strftime('%Y%m%d%H')}.{nc_var}.hourly.nc"
    if nc_var =="pre":
        file_name = f"corrected.CARAS.{timestamp.strftime('%Y%m%d%H')}.{nc_var}cip.hourly.nc"
    
    file_path = Path(settings.CORRECTION_OUTPUT_DIR) / f"{nc_var}.hourly" / str(timestamp.year) / file_name

    # 检查文件是否存在
    if not file_path.exists():
        raise FileNotFoundError(f"订正后的格点文件 {file_path} 不存在, 请确认是否执行了该时段的订正")
    return file_path