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

def MRE(obs, grid, epsilon=1e-5):
    """
    平均相对误差Mean Relative Error (MRE)
    :param obs: 观测值O
    :param grid: 网格值G
    :return: MRE值
    """
    return np.mean(np.abs((obs - grid) / (np.abs(obs) + epsilon)))

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

def cal_metrics(obs, pred, epsilon=1e-3):
    """
    计算评价指标
    :param obs: 观测值O
    :param pred: 预测值P
    :param epsilon: 避免除零错误
    :return: CC, RMSE, MRE, MBE
    """
    metrics = {}
    metrics['CC'] = round(CC(obs, pred), 4)
    metrics['RMSE'] = round(RMSE(obs, pred), 4)
    metrics['MAE'] = round(MAE(obs, pred), 4)
    metrics['MRE'] = round(MRE(obs, pred, epsilon), 4)
    metrics['MBE'] = round(MBE(obs, pred), 4)
    metrics['R2'] = round(R2(obs, pred), 4)
    return metrics
