# src/db/models.py
from sqlalchemy import Column, Integer, String, Float, DateTime
from .database import Base

class RawStationData(Base):
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
    temperature = Column(Float, nullable=True)      # 温度
    humidity = Column(Float, nullable=True)         # 相对湿度
    precipitation_1h = Column(Float, nullable=True)    # 降水
    wind_speed_2min = Column(Float, nullable=True)  # 风速


class ProcStationGridData(Base):
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
    temperature = Column(Float, nullable=True)          # 温度
    temperature_grid = Column(Float, nullable=True)     # 温度格点值
    humidity = Column(Float, nullable=True)             # 相对湿度
    humidity_grid = Column(Float, nullable=True)        # 相对湿度格点值
    precipitation_1h = Column(Float, nullable=True)        # 降水
    precipitation__1h_grid = Column(Float, nullable=True)   # 降水格点值
    wind_speed_2min = Column(Float, nullable=True)           # 风速
    wind_speed_2min_grid = Column(Float, nullable=True)      # 风速格点值
    