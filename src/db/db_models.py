# src/db/models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.sql import func
from .database import Base
import json

class RawStationData(Base):
    """原始站点数据表"""
    __tablename__ = "raw_s_data"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(String, index=True)
    station_name = Column(String, index=True)
    lat = Column(Float)
    lon = Column(Float)
    timestamp = Column(DateTime, index=True)
    year = Column(Integer, index=True)
    month = Column(Integer, index=True)
    day = Column(Integer)
    hour = Column(Integer)
    
    # 气象要素列
    temperature = Column(Float, nullable=True)          # 温度
    humidity = Column(Float, nullable=True)             # 相对湿度
    precipitation_1h = Column(Float, nullable=True)     # 降水
    wind_speed_2min = Column(Float, nullable=True)      # 风速


class ProcStationGridData(Base):
    """处理后的包含站点和格点值的数据表"""
    __tablename__ = "proc_sg_data"

    id = Column(Integer, primary_key=True, index=True)
    station_id = Column(String, index=True)
    station_name = Column(String, index=True)
    lat = Column(Float)
    lon = Column(Float)
    timestamp = Column(DateTime, index=True)
    year = Column(Integer, index=True)
    month = Column(Integer, index=True)
    day = Column(Integer)
    hour = Column(Integer)
    
    # 气象要素列
    temperature = Column(Float, nullable=True)              # 温度
    temperature_grid = Column(Float, nullable=True)         # 温度格点值
    humidity = Column(Float, nullable=True)                 # 相对湿度
    humidity_grid = Column(Float, nullable=True)            # 相对湿度格点值
    precipitation_1h = Column(Float, nullable=True)         # 降水
    precipitation__1h_grid = Column(Float, nullable=True)   # 降水格点值
    wind_speed_2min = Column(Float, nullable=True)          # 风速
    wind_speed_2min_grid = Column(Float, nullable=True)     # 风速格点值
    

class TaskProgress(Base):
    """跟踪所有后台任务进度的数据表"""
    __tablename__ = "task_progress"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(String, unique=True, index=True, comment="任务的唯一ID")
    task_name = Column(String, comment="任务名称, 如:数据导入")
    progress_text = Column(String, default="任务已提交, 等待执行...", comment="任务进度的文字描述")
    task_type = Column(String, comment="任务类型, 如:DataImport")
    status = Column(String, default="PENDING", comment="任务状态, 如: PENDING, PROCESSING, COMPLETED, FAILED")
    start_time = Column(DateTime(timezone=True), server_default=func.now(), comment="任务开始时间")
    end_time = Column(DateTime(timezone=True), nullable=True, comment="任务结束时间")
    task_params = Column(Text, comment="任务参数的JSON字符串")
    cur_progress = Column(Float, default=0.0, comment="当前进度(0.0 to 100.0)")
    
    def set_params(self, params: dict):
        self.task_params = json.dumps(params, ensure_ascii=False)

    def get_params(self) -> dict:
        return json.loads(self.task_params) if self.task_params else {}