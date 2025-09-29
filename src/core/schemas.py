# src/core/schemas.py
from pydantic import BaseModel, DirectoryPath
from typing import Optional, Any


# Pydantic会自动验证传入的路径是否存在且是一个目录
class DataSourceDirs(BaseModel):
    """用于接受数据源路径的请求体模型"""
    station_data_path: DirectoryPath    # 站点数据路径
    grid_data_path: DirectoryPath       # 网格数据路径


class MessageResponse(BaseModel):
    """通用的成功响应模型"""
    message: str


class ConfigRequest(BaseModel):
    """用于接受配置字典的请求体模型"""
    config: dict


class DataImportRequest(BaseModel):
    """用于接受数据导入请求的请求体模型"""
    directory_path: DirectoryPath


class TaskStatusResponse(BaseModel):
    """用于返回任务状态的响应模型"""
    task_id: str
    status: str
    progress: Optional[Any] = None # 可以是任意类型的进度详情，如dict


class TaskCreationResponse(BaseModel):
    """用于返回任务创建结果的响应模型"""
    message: str
    task_id: str