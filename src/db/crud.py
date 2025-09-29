# src/db/crud.py
import pandas as pd
from sqlalchemy.orm import Session
from . import db_models

def bulk_insert_raw_station_data(db: Session, data_df: pd.DataFrame):
    """
    将Pandas DataFrame中的站点数据批量导入数据库。

    :param db: SQLAlchemy数据库会话.
    :param data_df: 包含待导入数据的DataFrame.
                    列名应与RawStationData模型中的字段名匹配
                    (station_id, station_name, timestamp, temperature, etc.).
    """
    # to_sql 是pandas提供的一个非常高效的批量插入方法
    data_df.to_sql(
        name=db_models.RawStationData.__tablename__,  # 指定要插入的表名，使用模型中的表名
        con=db.bind,        # 获取底层的数据库连接，确保数据能正确写入
        if_exists='append', # 如果表已存在，则追加数据而不是覆盖或报错
        index=False,        # 不将DataFrame的索引写入数据库，只写入实际数据
        chunksize=50000
    )