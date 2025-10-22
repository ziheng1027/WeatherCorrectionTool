# src/core/schemas.py

from datetime import datetime
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, DirectoryPath, FilePath, Field
from .config import settings


class MessageResponse(BaseModel):
    """通用的成功响应模型"""
    message: str


class FileListResponse(BaseModel):
    """用于返回文件列表的响应模型"""
    count: int
    files: List[str]


class TaskCreationResponse(BaseModel):
    """用于返回任务创建结果的响应模型"""
    message: str
    task_id: str


class TaskStatusResponse(BaseModel):
    """用于返回任务状态的响应模型"""
    task_id: str
    task_name: str
    task_type: str
    status: str
    progress: Optional[float] = None


class SubTaskStatusResponse(BaseModel):
    """用于返回子任务状态的响应模型"""
    task_id: str
    task_name: str
    status: str
    progress: Optional[float] = None
    progress_text: Optional[str] = None


class TaskDetailsResponse(BaseModel):
    """用于返回父任务及其所有子任务详细状态的响应模型"""
    parent: TaskStatusResponse
    sub_tasks: List[SubTaskStatusResponse]


class DataSourceRequest(BaseModel):
    """用于接受数据源路径的请求体模型"""
    station_data_dir: DirectoryPath = Field(
        default=settings.STATION_DATA_DIR,
        example = str(settings.STATION_DATA_DIR),
        description="站点数据目录"
    )
    grid_data_dir: DirectoryPath = Field(
        default=settings.GRID_DATA_DIR,
        example = str(settings.GRID_DATA_DIR),
        description="网格数据目录"
    )
    station_info_path: FilePath = Field(
        default=settings.STATION_INFO_PATH,
        example = str(settings.STATION_INFO_PATH),
        description="站点信息路径"
    )
    dem_data_path: FilePath = Field(
        default=settings.DEM_DATA_PATH,
        example = str(settings.DEM_DATA_PATH),
        description="DEM数据路径"
    )


class ConfigRequest(BaseModel):
    """用于接受配置字典的请求体模型"""
    config: dict


AVAILABLE_ELEMENTS = Literal["温度", "相对湿度", "过去1小时降水量", "2分钟平均风速"]

class StationPreviewRequest(BaseModel):
    """用于接受站点预览请求的请求体模型"""
    station_name: str = Field(..., description="站点名称", example="老河口")
    element: AVAILABLE_ELEMENTS
    start_time: datetime
    end_time: datetime


class StationPreviewResponse(BaseModel):
    """用于返回站点预览响应的响应模型"""
    station_name: str
    lat: float
    lon: float
    timestamps: List[datetime]
    values: List[Optional[float]]           # 允许值为空


class GridDataRequest(BaseModel):
    """用于接受网格数据请求的请求体模型"""
    element: AVAILABLE_ELEMENTS
    timestamp: datetime = Field(..., description="查询的特定时刻")


class GridPreviewResponse(BaseModel):
    """用于返回网格预览响应的响应模型"""
    lats: List[float]
    lons: List[float]
    values: List[List[Optional[float]]]     # 2D数组


class GridTimeSeriesRequest(BaseModel):
    """用于接受单个网格值时间序列请求的请求体模型"""
    element: AVAILABLE_ELEMENTS
    lat: float = Field(..., description="纬度")
    lon: float = Field(..., description="经度")
    start_time: datetime
    end_time: datetime


class GridTimeSeriesResponse(BaseModel):
    """用于返回单个网格值时间序列响应的响应模型"""
    lat: float
    lon: float
    timestamps: List[datetime]
    values: List[Optional[float]]


class DataProcessingRequest(BaseModel):
    """用于接受数据处理请求的请求体模型"""
    elements: List[str] = Field(default=["温度", "相对湿度", "过去1小时降水量", "2分钟平均风速"], description="要处理的气象要素", example=["温度", "相对湿度", "过去1小时降水量", "2分钟平均风速"])
    start_year: str = Field(default="2008", description="起始年份", example="2008")
    end_year: str = Field(default="2023", description="结束年份", example="2023")
    num_workers: int = Field(default=48, description="工作进程数", example=48)


class ModelParamsUpdateRequest(BaseModel):
    """用于接受模型参数更新请求的请求体模型"""
    params: dict = Field(
        ..., 
        description="要更新的模型参数字典",
        example={
            "learning_rate": 0.1,
            "n_estimators": 1500,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
        }
    )


class ModelTrainRequest(BaseModel):
    """用于接受模型训练请求的请求体模型"""
    element: list[str] = Field(default=["温度", "相对湿度", "过去1小时降水量", "2分钟平均风速"], description="要训练的气象要素", example=["温度", "相对湿度", "过去1小时降水量", "2分钟平均风速"])
    start_year: str = Field(default="2008", description="数据集的起始年份", example=["2008", "...", "2023"])
    end_year: str = Field(default="2023", description="数据集的结束年份", example=["2008", "...", "2023"])
    season: str = Field(default="春季", description="构建哪个季节的数据集?", example=["春季", "夏季", "秋季", "冬季", "全年"])
    split_method: Literal["按年份划分", "按站点划分"] = Field(default="按年份划分", description="数据集划分方法", example=["按年份划分", "按站点划分"])
    test_set_values: list[str]  # 年份列表或站点列表
    model: Literal["XGBoost", "LightGBM"] = Field(default="XGBoost", description="模型名称", example="XGBoost")
    early_stopping_rounds: str = Field(default="150", description="早停轮数, 模型训练过程中如果连续多少轮的验证集表现没有提升, 则停止训练", example="100")


class ModelInfoRequest(BaseModel):
    """用于接受模型信息请求的请求体模型, 以便查询结果"""
    task_id: str = Field(..., description="任务ID")
    model: Literal["XGBoost", "LightGBM"] = Field(..., description="模型名称")
    element: AVAILABLE_ELEMENTS
    start_year: str = Field(..., description="数据集的起始年份")
    end_year: str = Field(..., description="数据集的结束年份")
    season: str = Field(..., description="构建哪个季节的数据集?")


class LossesResponse(BaseModel):
    """用于返回模型训练损失的响应模型"""
    epochs: List[int]
    train_losses: List[float]
    test_losses: List[float]


class MetricsDetail(BaseModel):
    """用于返回模型评估指标的详细信息的响应模型"""
    CC: float
    RMSE: float
    MAE: float
    MRE: float
    MBE: float
    R2: float


class MetricsResponse(BaseModel):
    """用于返回模型整体评估指标的响应模型"""
    testset_true: MetricsDetail
    testset_pred: MetricsDetail


class ModelRecordResponse(BaseModel):
    """用于返回模型记录的响应模型"""
    model_name: str
    element: AVAILABLE_ELEMENTS
    model_path: str
    create_time: datetime
    train_params: Dict
    model_params: Dict


class ModelListResponse(BaseModel):
    """用于返回模型列表的响应模型"""
    count: int
    models: List[ModelRecordResponse]


class DataCorrectRequest(BaseModel):
    """用于接收数据订正请求的请求体模型"""
    model_path: FilePath = Field(..., description="模型文件路径")
    element: AVAILABLE_ELEMENTS
    start_year: str = Field(default="2008", description="起始年份", example=["2008", "2023"])
    end_year: str = Field(default="2023", description="结束年份", example=["2008", "2023"])
    season: str = Field(default="全年", description="季节")
    block_size: int = Field(default=100, description="空间大小, 原图大小为460x800", example=100)
    num_workers: int = Field(default=48, description="工作进程数")


class PivotDataProcessRequest(BaseModel):
    """用于接收数据处理阶段的数据透视请求的请求体模型"""
    element: AVAILABLE_ELEMENTS
    station_name: str = Field(..., description="站点名称", example="竹溪")
    start_time: datetime
    end_time: datetime


class PivotDataProcessResponse(BaseModel):
    """用于返回数据处理阶段的数据透视响应的响应模型"""
    timestamps: List[datetime]
    station_values: List[Optional[float]]
    grid_values: List[Optional[float]]


class PivotModelTrainRequest(BaseModel):
    """用于接收模型训练阶段的数据透视模型训练请求的请求体模型"""
    model_paths: List[FilePath] = Field(..., description="一个或多个模型文件的路径列表")
    element: AVAILABLE_ELEMENTS
    station_name: str = Field(..., description="站点名称", example="竹溪")
    start_time: datetime
    end_time: datetime


class ModelPrediction(BaseModel):
    """单个模型的预测值序列"""
    model_name: str
    pred_values: List[Optional[float]]


class ModelMetrics(BaseModel):
    """单个模型在特定站点的评估指标"""
    station_name: str
    model_name: str
    metrics: Dict[str, Any]


class PivotModelTrainResponse(BaseModel):
    """用于返回模型评估透视结果的响应模型"""
    timestamps: List[datetime]
    station_values: List[Optional[float]]
    grid_values: List[Optional[float]]
    pred_values: List[ModelPrediction]
    metrics: List[ModelMetrics]


class PivotModelTrainStatusResponse(BaseModel):
    """用于返回模型透视分析任务状态和结果的响应模型"""
    task_id: str
    status: str
    progress: float
    progress_text: str
    results: Optional[PivotModelTrainResponse] = None


class PivotDataCorrectHeatmapResponse(BaseModel):
    """用于返回数据订正阶段的格点热力图数据的响应模型"""
    lats: List[float]
    lons: List[float]
    values_before: List[List[Optional[float]]]
    values_after: List[List[Optional[float]]]


class PivotDataCorrectTimeseriesResponse(BaseModel):
    """用于返回数据订正阶段的格点时序数据的响应模型"""
    timestamps: List[datetime]
    values_before: List[Optional[float]]
    values_after: List[Optional[float]]


class PivotDataCorrectStatusResponse(BaseModel):
    """用于返回数据订正-格点时序数据提取任务状态和结果的响应模型"""
    task_id: str
    status: str
    progress: float
    progress_text: str
    results: Optional[PivotDataCorrectTimeseriesResponse] = None