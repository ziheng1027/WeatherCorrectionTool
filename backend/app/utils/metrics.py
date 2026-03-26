# src/utils/metrics.py
import numpy as np


def CC(obs, grid):
    """
    相关系数Correlation Coefficient (CC)
    :param obs: 观测值O
    :param grid: 网格值G
    :return: CC值
    """
    return np.corrcoef(obs, grid)[0, 1]

def RMSE(obs, grid):
    """
    均方根误差Root Mean Square Error (RMSE)
    :param obs: 观测值O
    :param grid: 网格值G
    :return: RMSE值
    """
    return np.sqrt(np.mean((obs - grid) ** 2))

def MAE(obs, grid):
    """
    平均绝对误差Mean Absolute Error (MAE)
    :param obs: 观测值O
    :param grid: 网格值G
    :return: MAE值
    """
    return np.mean(np.abs(obs - grid))

def MRE(obs, grid):
    """
    平均相对误差Mean Relative Error (MRE)
    :param obs: 观测值O
    :param grid: 网格值G
    :return: MRE值
    """
    if np.sum(obs) == 0:
        return np.nan
    return np.sum(grid - obs) / np.sum(obs)

def MBE(obs, grid):
    """
    平均偏差Mean Bias Error (MBE)
    :param obs: 观测值O
    :param grid: 网格值G
    :return: MBE值
    """
    return np.mean(obs - grid)

def R2(obs, grid):
    """
    决定系数R^2
    :param obs: 观测值O
    :param grid: 网格值G
    :return: R^2值
    """
    return 1 - np.sum((obs - grid) ** 2) / np.sum((obs - np.mean(obs)) ** 2)

def cal_metrics(obs, pred):
    """
    计算评价指标
    :param obs: 观测值O
    :param pred: 预测值P
    :param epsilon: 避免除零错误
    :return: CC, RMSE, MRE, MBE
    """
    metrics = {}
    metrics['CC'] = format(CC(obs, pred), ".4f")
    metrics['RMSE'] = format(RMSE(obs, pred), ".4f")
    metrics['MAE'] = format(MAE(obs, pred), ".4f")
    metrics['MRE'] = format(MRE(obs, pred), ".4f")
    metrics['MBE'] = format(MBE(obs, pred), ".4f")
    metrics['R2'] = format(R2(obs, pred), ".4f")
    return metrics

def cal_comprehensive_score(metrics_list):
    """
    根据输入的指标列表, 计算每个模型的综合得分S
    :param metrics_list: 指标列表, 每一项是一个字典, 包含'model_name'和'metrics'
    :return: 追加综合得分"S"键的指标列表
    """
    if not metrics_list:
        return []
    # 将字符串转换为浮点数并计算|MRE|和|MBE|
    parsed_metrics = []
    try:
        for item in metrics_list:
            metrics = item['metrics']
            parsed = {
                "R2": float(metrics.get('R2', 0.0)),
                "RMSE": float(metrics.get('RMSE', 0.0)),
                "MAE": float(metrics.get('MAE', 0.0)),
                "MRE_Abs": abs(float(metrics.get('MRE', 0.0))),
                "MBE_Abs": abs(float(metrics.get('MBE', 0.0)))
            }
            parsed_metrics.append(parsed)
    except Exception as e:
        print(f"解析指标时出错: {e}. 请确保metrics字典中的值是数字字符串")
        return metrics_list # 出错时返回原列表
    
    # 提取所有模型的指标值, 用于查找 Min/Max
    all_R2 = [metric["R2"] for metric in parsed_metrics]
    all_RMSE = [metric["RMSE"] for metric in parsed_metrics]
    all_MAE = [metric["MAE"] for metric in parsed_metrics]
    all_MRE_Abs = [metric["MRE_Abs"] for metric in parsed_metrics]
    all_MBE_Abs = [metric["MBE_Abs"] for metric in parsed_metrics]

    # 辅助函数: 标准化
    def _normalize(value, all_values, higher_is_better=True):
        v_max = max(all_values)
        v_min = min(all_values)
        denominator = v_max - v_min

        # 如果所有值都相同, 给予中性得分
        if denominator == 0:
            return 0.5

        if higher_is_better:
            return (value - v_min) / denominator    # R2, CC
        else:
            return (v_max - value) / denominator    # RMSE, MAE, |MRE|, |MBE|
    
    # 计算每个模型的标准化得分和综合得分S
    for i, item in enumerate(metrics_list):
        metric = parsed_metrics[i]
        S_R = _normalize(metric["R2"], all_R2, higher_is_better=True)
        S_RMSE = _normalize(metric["RMSE"], all_RMSE, higher_is_better=False)
        S_MAE = _normalize(metric["MAE"], all_MAE, higher_is_better=False)
        S_MRE_Abs = _normalize(metric["MRE_Abs"], all_MRE_Abs, higher_is_better=False)
        S_MBE_Abs = _normalize(metric["MBE_Abs"], all_MBE_Abs, higher_is_better=False)

        S = (0.2 * S_R + 0.3 * S_RMSE + 0.2 * S_MAE + 0.2 * S_MRE_Abs + 0.1 * S_MBE_Abs)

        # 将 S 添加回原指标字典
        item["metrics"]["S_R"] = round(S_R, 4)
        item["metrics"]["S_RMSE"] = round(S_RMSE, 4)
        item["metrics"]["S_MAE"] = round(S_MAE, 4)
        item["metrics"]["S_MRE_Abs"] = round(S_MRE_Abs, 4)
        item["metrics"]["S_MBE_Abs"] = round(S_MBE_Abs, 4)
        item["metrics"]["S"] = round(S, 4)
    
    # 按综合得分S降序排列
    metrics_list.sort(key=lambda x: x['metrics']['S'], reverse=True)
    return metrics_list
