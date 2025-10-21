# src/api/routers/data_pivot.py

from sqlalchemy.orm import Session
from fastapi import APIRouter, HTTPException, Depends
from ...db import crud
from ...db.database import get_db
from ...core import schemas
from ...core.data_mapping import ELEMENT_TO_DB_MAPPING


router = APIRouter(
    prefix="/data-pivot",
    tags=["数据透视"],
)


@router.post("/processed-data", response_model=schemas.PivotProcessResponse, summary="获取预处理后的站点与格点对比数据")
def get_processed_pivot_data(request: schemas.PivotProcessRequest, db: Session = Depends(get_db)):
    """
    根据要素、站点和时间范围, 查询数据预处理后的站点观测值和对应的原始格点值, 用于绘制对比折线图。
    """
    try:
        # 调用CRUD函数查询数据
        df = crud.get_proc_data_for_pivot(
            db,
            element=request.element,
            station_name=request.station_name,
            start_time=request.start_time,
            end_time=request.end_time
        )

        if df.empty:
            raise HTTPException(status_code=404, detail="未查询到指定条件下的预处理数据")

        # 获取数据库列名
        station_col = ELEMENT_TO_DB_MAPPING.get(request.element)
        grid_col = f"{station_col}_grid"

        # 构造响应体
        response_data = {
            "timestamps": df["timestamp"].tolist(),
            "station_values": df[station_col].tolist(),
            "grid_values": df[grid_col].tolist()
        }

        return schemas.PivotProcessResponse(**response_data)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {e}")
