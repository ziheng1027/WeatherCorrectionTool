# src/core/model_train.py
import pandas as pd
import xarray as xr
from time import time
from sqlalchemy.orm import Session
from ..db import crud
from ..utils.metrics import cal_metrics
from ..utils.file_io import load_model
from ..core.data_mapping import ELEMENT_TO_DB_MAPPING
from ..core.config import settings, get_model_config_path, load_model_config


def get_season(month: int) -> str:
    """根据月份划分季节"""
    if month in [3, 4, 5]:
        return '春季'
    elif month in [6, 7, 8]:
        return '夏季'
    elif month in [9, 10, 11]:
        return '秋季'
    elif month in [12, 1, 2]:
        return '冬季'
    else:
        return '未知(0-12月以外的月份)'

def get_terrain_feature(dem_ds: xr.Dataset, lat: str, lon: str) -> tuple:
    """根据经纬度提取海拔, 坡度, 坡向"""
    try:
        point = dem_ds.sel(lat=lat, lon=lon, method='nearest')
        elevation = float(point['elevation'].values)
        slope = float(point['slope'].values)
        aspect = float(point['aspect'].values)
        return elevation, slope, aspect
    
    except Exception as e:
        print(f"提取地形特征失败(lat:{lat}, lon:{lon}): {e}")
        return None, None, None

def build_dataset_from_db(
        db: Session, dem_file: str, lags_config: dict, element: str, 
        start_year: str, end_year: str, season: str
):
    """指定要素, 起止年份, 季节构建数据集"""
    # 读取地形数据
    dem_ds = xr.open_dataset(dem_file)
    # 根据起始年份从数据库读取数据df
    df = crud.get_proc_data_to_build_dataset(db, element, start_year, end_year)
    # 添加季节用于分组
    df['season'] = df['month'].apply(get_season)
    if season in ['春季', '夏季', '秋季', '冬季']:
        df = df[df['season'] == season]
    
    element_db_column = ELEMENT_TO_DB_MAPPING[element]
    lags = lags_config[element]
    all_station_df = []
    
    # 按照站点分组
    station_dfs = df.groupby('station_id')
    for station_id, station_df in station_dfs:
        print(f"构建数据集... 当前处理站点: {station_id}")
        station_df = station_df.sort_values(by=['year', 'month', 'day', 'hour']).reset_index(drop=True)
        # 添加滞后特征
        for lag in lags:
            station_df[f"{element_db_column}_grid_lag_{lag}"] = station_df[f"{element_db_column}_grid"].shift(lag)
        station_df.dropna(inplace=True)
        if station_df.empty:
            continue
        # 添加地形特征
        lat, lon = station_df.iloc[0]['lat'], station_df.iloc[0]['lon']
        elevation, slope, aspect = get_terrain_feature(dem_ds, lat, lon)
        station_df["elevation"] = elevation
        station_df["slope"] = slope
        station_df["aspect"] = aspect

        all_station_df.append(station_df)
    
    # 合并所有站点
    dataset = pd.concat(all_station_df, axis=0, ignore_index=True)
    print(f"构建完成的数据集形状: {dataset.shape}")

    return dataset

def split_dataset(dataset: pd.DataFrame, split_method: str, test_set_values: list[str]):
    """划分数据["按年份划分", "按站点划分"], 返回train_dataset, test_dataset"""
    if split_method == "按年份划分":
        test_set_values = [int(year) for year in test_set_values]
        train_dataset = dataset[~dataset["year"].isin(test_set_values)]
        test_dataset = dataset[dataset["year"].isin(test_set_values)]
    elif split_method == "按站点划分":
        train_dataset = dataset[~dataset["station_name"].isin(test_set_values)]
        test_dataset = dataset[dataset["station_name"].isin(test_set_values)]
    else:
        raise ValueError(f"不支持的数据集划分方法: {split_method}")

    return train_dataset, test_dataset

def build_model(model_name: str, element: str):
    """根据传入的模型名称构建模型实例"""
    # 加载模型配置文件
    model_config_path = get_model_config_path(model_name, element)
    model_config = load_model_config(model_config_path)

    # 定义模型实例
    if model_name.lower() == "xgboost":
        from xgboost import XGBRegressor
        model = XGBRegressor(**model_config)
    elif model_name.lower() == "lightgbm":
        from lightgbm import LGBMRegressor
        model = LGBMRegressor(**model_config)
    else:
        raise ValueError(f"暂不支持的模型: {model_name}")

    return model

def train_model(
        model_name: str, element: str, start_year: str, end_year: str, season: str, 
        early_stopping_rounds: str, train_dataset: pd.DataFrame, test_dataset: pd.DataFrame
    ):
    """训练模型并返回训练和验证损失"""
    # 划分特征和标签
    label_col = ELEMENT_TO_DB_MAPPING[element]
    train_X = train_dataset.drop(columns=['station_id', 'station_name', 'season', label_col])
    train_y = train_dataset[label_col]
    test_X = test_dataset.drop(columns=['station_id', 'station_name', 'season', label_col])
    test_y = test_dataset[label_col]

    eval_set = [(train_X, train_y), (test_X, test_y)]
    eval_name = ["validation_0", "validation_1"]
    
    # 开始训练
    start_time = time()
    print(f"开始训练模型: [{model_name}, {element}, {start_year}-{end_year}, {season}]")
    model = build_model(model_name, element)
    if model_name.lower() == "xgboost":
        model.set_params(
            early_stopping_rounds=int(early_stopping_rounds)
        )
        model.fit(
            train_X, train_y, eval_set=eval_set, verbose=10
        )
        results = model.evals_result()
    elif model_name.lower() == "lightgbm":
        import lightgbm as lgb
        model.fit(
            train_X, train_y, eval_set=eval_set, eval_names=eval_name, 
            callbacks=[
                lgb.log_evaluation(period=10),
                lgb.early_stopping(int(early_stopping_rounds))
            ]
        )
        results = model.evals_result_

    # 计算模型预测指标
    pred_y = model.predict(test_X)
    metrics_test_pred = cal_metrics(test_y, pred_y)
    print(f"[{model_name}, {element}, {start_year}-{end_year}, {season}] 模型评估指标[指定测试集的均值]:")
    print(metrics_test_pred, " \n")

    # 计算原始数据指标
    element_db_column = ELEMENT_TO_DB_MAPPING[element]
    test_grid = test_X[f"{element_db_column}_grid"]
    metrics_test_true = cal_metrics(test_y, test_grid)
    print(f"[{model_name}, {element}, {start_year}-{end_year}, {season}] 原始数据指标[指定测试集的均值]:")
    print(metrics_test_true, " \n")
    
    # 获取训练和验证损失
    train_losses = results["validation_0"]["rmse"]
    test_losses = results["validation_1"]["rmse"]
    end_time = time()
    print(f"[{model_name}, {element}] 训练完成, 耗时: {end_time - start_time:.2f}秒\n")

    return model, train_losses, test_losses, metrics_test_true, metrics_test_pred

def evaluate_model(
        model_name: str, test_dataset: pd.DataFrame,element: str, 
        start_year: str, end_year: str, season: str
):
    """评估模型"""
    # 加载模型
    model = load_model(model_name, element, start_year, end_year, season)

    # 划分特征
    label_col = ELEMENT_TO_DB_MAPPING[element]
    test_X = test_dataset.drop(columns=['station_id', 'station_name', 'season', label_col])

    # 计算特征重要性
    feature_importance_dict = get_feature_importance(model, test_X)
    print(f"[{model_name}, {element}, {start_year}-{end_year}, {season}] 特征重要性:")
    print(feature_importance_dict, " \n")

    element_db_column = ELEMENT_TO_DB_MAPPING[element]
    # 存放原始站点数据, 原始格点数据以及模型预测数据
    results = []
    # 存放原始数据指标和模型预测指标
    metrics_list = []
    # 按照站点分组
    station_dataset = test_dataset.groupby(["station_name"])
    # 计算每个站点的指标(基于当前测试集的起止年份+季节范围内,每个站点所有数据的均值)
    for station_name, station_data in station_dataset:
        # 划分特征和标签
        station_test_X = station_data.drop(columns=['station_id', 'station_name', 'season', label_col])
        station_test_y = station_data[label_col]

        if station_test_X.empty: continue
        
        # 模型预测
        station_test_grid = station_test_X[f"{element_db_column}_grid"]
        station_pred_y = model.predict(station_test_X)

        # 添加到results
        station_results = pd.DataFrame({
            "station_name": [station_name[0]] * len(station_test_y),
            "timestamp": pd.to_datetime(station_data[['year', 'month', 'day', 'hour']]),
            "station_test_y": station_test_y,
            "station_test_grid": station_test_grid,
            "station_pred_y": station_pred_y
        })
        results.append(station_results)

        # 计算指标
        metrics_station_pred = cal_metrics(station_test_y, station_pred_y)
        metrics_station_true = cal_metrics(station_test_y, station_test_grid)

        row_data = {"station_name": station_name[0]}
        for metric in metrics_station_pred:
            row_data[f"原{metric}"] = metrics_station_true[metric]
            row_data[f"新{metric}"] = metrics_station_pred[metric]
        
        # 添加到metrics_list
        metrics_list.append(row_data)

    results_df = pd.concat(results, axis=0, ignore_index=True)
    metrics_df = pd.DataFrame(metrics_list)
    print(f"[{model_name}, {element}, {start_year}-{end_year}, {season}] 评估指标[指定测试集的均值]:")
    print(metrics_df)

    return results_df, metrics_df, feature_importance_dict

def get_feature_importance(model, test_X: pd.DataFrame):
    """获取特征重要性"""
    try:
        if hasattr(model, "feature_importances_"):
            importance = model.feature_importances_
            feature_names = test_X.columns.to_list()

            feature_importance_dict = dict(zip(feature_names, importance))
            
            # 按数值降序排列
            feature_importance_dict = dict(
                sorted(
                    feature_importance_dict.items(),
                    key=lambda item: item[1],
                    reverse=True
                )
            )
            
            # 格式化输出
            return {k: format(v, ".4f") for k, v in feature_importance_dict.items()}
        
    except Exception as e:
        print(f"获取特征重要性失败: {e}")
        return {}


if __name__ == "__main__":
    from ..db.database import SessionLocal
    db = SessionLocal()
    model_name = "lightgbm"
    element = "2分钟平均风速"
    start_year = "2020"
    end_year = "2020"
    season = "全年"
    split_method = "按站点划分"
    test_set_values = ["老河口", "武穴", "竹山", "神农架", "阳新"]


    dataset = build_dataset_from_db(db, settings.DEM_DATA_PATH, settings.LAGS_CONFIG, element, start_year, end_year, season)
    train_dataset, test_dataset = split_dataset(dataset, split_method, test_set_values)
    train_model(
        model_name, element, start_year, end_year, season, settings.EARLY_STOPING_ROUNDS, train_dataset, test_dataset
    )
    
    evaluate_model(model_name, test_dataset, element, start_year, end_year, season)
