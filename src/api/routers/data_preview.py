# src/api/routers/data_preview.py

from typing import List
from sqlalchemy.orm import Session
from fastapi import APIRouter, HTTPException, Depends
from ...db import crud
from ...core import schemas
from ...core.data_preview import get_grid_data_at_time, get_grid_time_series_for_coord
from ...db.database import SessionLocal


router = APIRouter(
    prefix="/data-preview",
    tags=["数据预览"],
)

# 依赖项：获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/stations", response_model=List[str], summary="获取所有站点名称列表")
def get_all_station_names(db: Session = Depends(get_db)):
    """
    从数据库中查询所有不重复的站点名称, 用于前端下拉列表选择。
    """
    stations = crud.get_unique_station_names(db)
    return [station.station_name for station in stations]


@router.post("/station-data", response_model=schemas.StationPreviewResponse, summary="获取站点时序数据")
def get_station_data(request: schemas.StationPreviewRequest, db: Session = Depends(get_db)):
    """
    根据站点名称、要素和时间范围, 查询对应的时序数据用于绘制折线图。
    """
    data = crud.get_raw_station_data(
        db,
        station_name=request.station_name,
        element=request.element,
        start_time=request.start_time,
        end_time=request.end_time
    )
    if not data:
        raise HTTPException(status_code=404, detail="未查询到相关站点数据")

    # 数据格式化
    response = {
        "station_name": data[0].station_name,
        "lat": data[0].lat,
        "lon": data[0].lon,
        "timestamps": [d.timestamp for d in data],
        "values": [getattr(d, "value") for d in data]
    }
    return response

@router.post("/grid-data", response_model=schemas.GridPreviewResponse, summary="获取指定时刻的格点数据")
def get_grid_data(request: schemas.GridDataRequest):
    """
    根据要素和时刻, 从.nc文件中读取完整的格点数据, 用于绘制热力图。
    """
    try:
        lats, lons, values = get_grid_data_at_time(
            element=request.element,
            timestamp=request.timestamp
        )
        return {
            "lats": lats.tolist(),
            "lons": lons.tolist(),
            "values": values.tolist()
        }
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"未找到 {request.timestamp} 对应的格点数据文件")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/grid/timeseries", response_model=schemas.GridTimeSeriesResponse, summary="获取单点格点数据时序")
def get_grid_timeseries(request: schemas.GridTimeSeriesRequest):
    """
    根据经纬度坐标、要素和时间范围，提取并返回该点的格点数据时间序列。
    """
    try:
        timestamps, values = get_grid_time_series_for_coord(
            element=request.element,
            lat=request.lat,
            lon=request.lon,
            start_time=request.start_time,
            end_time=request.end_time
        )
        return schemas.GridTimeSeriesResponse(
            lat=request.lat,
            lon=request.lon,
            timestamps=timestamps,
            values=values
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")