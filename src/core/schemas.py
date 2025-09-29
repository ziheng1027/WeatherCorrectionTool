# src/core/schemas.py
from pydantic import BaseModel, DirectoryPath, Field
from typing import Optional, Any, Literal
from datetime import datetime


class MessageResponse(BaseModel):
    """通用的成功响应模型"""
    message: str


class TaskStatusResponse(BaseModel):
    """用于返回任务状态的响应模型"""
    task_id: str
    status: str
    progress: Optional[Any] = None # 可以是任意类型的进度详情，如dict


class TaskCreationResponse(BaseModel):
    """用于返回任务创建结果的响应模型"""
    message: str
    task_id: str


class DataSourceDirs(BaseModel):
    """用于接受数据源路径的请求体模型"""
    station_data_dir: DirectoryPath    # 站点数据路径
    grid_data_dir: DirectoryPath       # 网格数据路径


class ConfigRequest(BaseModel):
    """用于接受配置字典的请求体模型"""
    config: dict


class DataImportRequest(BaseModel):
    """用于接受数据导入请求的请求体模型"""
    directory_dir: DirectoryPath


class StationPreviewRequest(BaseModel):
    station_name: str = Field(..., description="站点名称", example="老河口")
    element: Literal["温度", "相对湿度", "1小时降水量", "2分钟平均风速"]    # 使用 Literal 强制只能从预定义列表中选择
    start_time: datetime
    end_time: datetime


class ModelTrainRequest(BaseModel):
    """用于接受模型训练请求的请求体模型"""
    element: Literal["温度", "相对湿度", "1小时降水量", "2分钟平均风速"]    # 使用 Literal 强制只能从预定义列表中选择
    start_time: datetime
    end_time: datetime
    test_split_method: Literal["按年份划分", "按站点划分"]
    test_set_values: list[str]  # 年份列表或站点列表
    model: Literal["XGBoost", "LightGBM", "随机森林"]
    model_params: dict