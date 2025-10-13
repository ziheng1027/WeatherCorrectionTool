# src/db/crud.py
import pandas as pd
from datetime import datetime
from typing import Optional
from sqlalchemy import text, exists
from sqlalchemy.orm import Session
# 导入针对 SQLite 的特殊 insert 语句构造器
from sqlalchemy.dialects.sqlite import insert
from . import db_models
from ..core.data_mapping import ELEMENT_TO_DB_MAPPING


def create_task(db: Session, task_id: str, task_name: str, task_type: str, params: dict, parent_task_id: str = None) -> db_models.TaskProgress:
    """
    创建一个任务(父任务/子任务 都可)。

    :param db: SQLAlchemy数据库会话.
    :param task_id: 任务ID.
    :param task_name: 任务名称.
    :param task_type: 任务类型.
    :param params: 任务参数.
    :param parent_task_id: 父任务ID.
    :return: 创建的任务对象.
    """
    task = db_models.TaskProgress(
        task_id=task_id, 
        task_name=task_name, 
        task_type=task_type, 
        parent_task_id=parent_task_id
    )
    task.set_params(params)
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

def update_task_status(db: Session, task_id: str, status: str, progress: float, text: str):
    """
    更新任务状态, 进度, 进度的文字说明。

    :param db: SQLAlchemy数据库会话.
    :param task_id: 任务ID.
    :param status: 任务状态.
    :param progress: 任务进度.
    """
    task = db.query(db_models.TaskProgress).filter(db_models.TaskProgress.task_id == task_id).first()
    if task:
        task.status = status
        task.cur_progress = progress
        task.progress_text = text
        if status in ["COMPLETED", "FAILED"]:
            task.end_time = datetime.now()
        db.commit()

def cancel_subtask(db: Session, parent_task_id: str):
    """取消指定父任务下所有处于 PENDING/PROCESSING 状态的子任务。"""
    tasks_to_cancel = db.query(db_models.TaskProgress).filter(
        db_models.TaskProgress.parent_task_id == parent_task_id,
        db_models.TaskProgress.status.in_(["PENDING", "PROCESSING"])
    ).all()
    
    if not tasks_to_cancel:
        return

    for task in tasks_to_cancel:
        task.status = "CANCELED"
        task.progress_text = "任务被用户取消"
        task.end_time = datetime.now()
    db.commit()
    return len(tasks_to_cancel)

def is_task_type_processing(db: Session, task_type: str) -> Optional[str]:
    """
    检查指定类型的任务是否有任何一个正处于 'PENDING' 或 'ROCESSING' 状态。

    :param db: SQLAlchemy数据库会话.
    :param task_type: 要检查的任务类型, 例如 "DataProcessing".
    :return: 如果有正在运行的任务则返回 True, 否则返回 False.
    """
    processing_task = db.query(db_models.TaskProgress).filter(
        db_models.TaskProgress.task_type == task_type,
        db_models.TaskProgress.status.in_(["PENDING", "PROCESSING"])
    ).first()
    return processing_task.task_id if processing_task else None
    
"""--------------------查询任务--------------------"""
def get_task_by_id(db: Session, task_id: str) -> db_models.TaskProgress:
    """
    根据任务ID获取任务。

    :param db: SQLAlchemy数据库会话.
    :param task_id: 任务ID.
    :return: 任务对象.
    """
    return db.query(db_models.TaskProgress).filter(db_models.TaskProgress.task_id == task_id).first()

def get_all_tasks(db: Session, skip: int=0, limit: int=82):
    """
    获取历史顶层任务列表 (排除了子任务)。

    :param db: SQLAlchemy数据库会话.
    :param skip: 跳过的任务数量.
    :param limit: 返回的任务数量.
    :return: 任务列表.
    """
    return db.query(db_models.TaskProgress).filter(db_models.TaskProgress.parent_task_id == None).order_by(db_models.TaskProgress.start_time.desc()).offset(skip).limit(limit).all()

def get_subtasks_by_parent_id(db: Session, parent_task_id: str):
    """
    获取指定父任务ID的所有子任务。

    :param db: SQLAlchemy数据库会话.
    :param parent_task_id: 父任务ID.
    :return: 子任务列表.
    """
    return db.query(db_models.TaskProgress).filter(db_models.TaskProgress.parent_task_id == parent_task_id).all()

def get_global_filenames_by_status(db: Session, task_type: str, status: str) -> list[str]:
    """
    【全局查询】获取所有状态为 `status` 的数据导入子任务，并返回文件名列表(从params中获取文件名-暂时只适用于DataImport任务)。
    
    注意：这个函数不区分父任务，会返回所有历史任务中符合条件的子任务。
    """
    # 查询条件是正确的，符合你的“不按父任务ID查询”的需求
    tasks = db.query(db_models.TaskProgress).filter(
        db_models.TaskProgress.task_type == task_type,
        db_models.TaskProgress.status == status
    ).all()

    file_names = []
    progress = None
    for task in tasks:
        # 修正 #1: 使用 task.get_params() 方法将JSON字符串安全地转换为字典
        params_dict = task.get_params()
        
        # 修正 #3: 从字典中读取的键是 'file'，与创建任务时保持一致
        if params_dict and "file_name" in params_dict:
            file_names.append(params_dict["file_name"])
        # 获取处理中的文件进度
        if status == "PROCESSING":
            progress = task.cur_progress
    
    return file_names, progress

def get_global_task_by_status(db: Session, task_type: str, status: str) -> list[str]:
    """
    【全局查询】获取所有状态为 `status` 的数据导入子任务, 并返回任务参数。

    注意：这个函数不区分父任务，会返回所有历史任务中符合条件的子任务。
    """
    tasks = db.query(db_models.TaskProgress).filter(
        db_models.TaskProgress.task_type == task_type,
        db_models.TaskProgress.status == status
    ).all()
    params_list = []
    for task in tasks:
        params_dict = task.get_params()
        if status == "PROCESSING":
            progress = task.cur_progress
            params_dict["progress"] = progress
        if params_dict:
            params_list.append(params_dict)

    return params_list

"""--------------------数据导入--------------------"""
def delete_pending_data_import_subtasks(db: Session) -> int:
    """
    删除所有状态为 PENDING 且类型为 DataImport_SubTask 的子任务。
    这通常在开始一次新的全局数据导入任务前调用，以清理之前可能中断的残留任务。

    :param db: SQLAlchemy数据库会话.
    :return: 被删除的记录行数.
    """
    num_deleted = db.query(db_models.TaskProgress).filter(
        db_models.TaskProgress.task_type == "DataImport_SubTask",
        db_models.TaskProgress.status == "PENDING"
    ).delete(synchronize_session=False)
    db.commit()
    return num_deleted

def upsert_raw_station_data(db: Session, df: pd.DataFrame):
    """
    使用数据库原生的 "INSERT ... ON CONFLICT DO UPDATE"功能,
    将处理后的站点数据高效的"upsert"到数据库中。
    """
    if df.empty:
        return
    
    records_to_process = df.to_dict(orient="records")
    table = db_models.RawStationData.__table__
    stmt = insert(table)

    # 在冲突时, 更新df中存在的所有列(除了主键和唯一键)
    update_columns = [
        col for col in df.columns
        if col not in ["id", "station_id", "timestamp"] # 不更新主键和唯一约束键
    ]
    update_dict = {col: getattr(stmt.excluded, col) for col in update_columns}

    # 如果没有可更新的列, 则不执行更新操作
    if not update_dict:
        stmt = stmt.on_conflict_do_nothing(index_elements=["station_id", "timestamp"])  # 指定唯一约束键
    else:
        stmt = stmt.on_conflict_do_update(
            index_elements=["station_id", "timestamp"],  # 指定唯一约束键
            set_=update_dict  # 指定需要更新的列
        )

    try:
        result = db.execute(stmt, records_to_process)
        db.commit()
        return result.rowcount
    except Exception as e:
        print(f"Error occurred during upsert: {e}")
        db.rollback()
        raise

def upsert_proc_station_grid_data(db: Session, df_sg: pd.DataFrame):
    """
    使用数据库原生的 "INSERT ... ON CONFLICT DO UPDATE"功能,
    将处理后的站点+格点数据高效的"upsert"到数据库中。
    """
    if df_sg.empty:
        return
    
    records_to_process = df_sg.to_dict(orient="records")
    table = db_models.ProcStationGridData.__table__
    stmt = insert(table)

    # 动态构建需要更新的列, 确保在重复处理"温度"时, 不会覆盖"湿度"等其他列
    update_columns = [
        col for col in df_sg.columns
        if col not in ["id", "station_id", "timestamp"] # 不更新主键和唯一约束键
    ]
    update_dict = {col: getattr(stmt.excluded, col) for col in update_columns}

    if not update_dict:
        # 如果除了主键外没有其他列, 说明数据有问题或者无需更新
        print("警告: 尝试upsert的数据中没有可更新的列, 操作已跳过")
        return

    stmt = stmt.on_conflict_do_update(
        index_elements=["station_id", "timestamp"],  # 指定唯一约束键
        set_=update_dict  # 指定需要更新的列
    )

    try:
        result = db.execute(stmt, records_to_process)
        db.commit()
        return result.rowcount
    except Exception as e:
        print(f"Error occurred during upsert: {e}")
        db.rollback()
        raise

"""--------------------数据预览--------------------"""
def get_raw_station_data(db: Session, station_name: str, element: str, start_time: datetime, end_time: datetime):
    """
    查询指定站点、要素和时间范围的原始数据。
    """
    try:
        db_column_name = ELEMENT_TO_DB_MAPPING.get(element)
        if not db_column_name:
            raise ValueError(f"无效的要素名称: {element}")

        # 构建查询
        query = text(f"""
            SELECT 
                station_name,
                lat,
                lon,
                timestamp,
                {db_column_name} AS value
            FROM raw_s_data
            WHERE 
                station_name = :station_name
                AND timestamp >= :start_time
                AND timestamp <= :end_time
            ORDER BY timestamp
        """)

        result = db.execute(
            query,
            {
                "station_name": station_name,
                "start_time": start_time,
                "end_time": end_time
            }
        )

        return result.fetchall()
    
    except Exception as e:
        print(f"Error occurred during querying raw station data: {e}")
        db.rollback()
        return None

"""--------------------数据处理--------------------"""
def get_raw_station_data_by_year(db: Session, db_column_name: str, year: int, chunk_size: int = 8760) -> pd.DataFrame:
    """
    查询指定年份和要素的原始站点数据。
    """
    db_column = getattr(db_models.RawStationData, db_column_name)

    query = db.query(
        db_models.RawStationData.station_id,
        db_models.RawStationData.station_name,
        db_models.RawStationData.lat,
        db_models.RawStationData.lon,
        db_models.RawStationData.timestamp,
        db_models.RawStationData.year,
        db_models.RawStationData.month,
        db_models.RawStationData.day,
        db_models.RawStationData.hour,
        db_column.label("station_value")
    ).filter(
        db_models.RawStationData.year == year,
        db_column.isnot(None) # 确保该要素列有数据
    )
    df_iterator = pd.read_sql(query.statement, db.bind, chunksize=chunk_size)
    return df_iterator

def check_existed_element_by_year(db: Session, element: str, year: int) -> bool:
    """
    检查指定年份的指定要素是否已经存在。
    """
    db_column_name = ELEMENT_TO_DB_MAPPING.get(element)
    if not db_column_name:
        raise ValueError(f"无效的要素名称: {element}")

    # 获取模型中对应的列对象
    db_column = getattr(db_models.ProcStationGridData, db_column_name)
    # 构建查询-只检查一条记录是否存在
    query = db.query(
        exists().where(
            db_models.ProcStationGridData.year == year,
            db_column.isnot(None) # 检查该要素列是否有非空值
        )
    )

    # scalar() 方法返回第一个元素的值, 如果存在则为 True, 否则为 False
    return db.execute(query).scalar()

"""--------------------模型训练--------------------"""
def get_proc_data_to_build_dataset(db: Session, element: str, start_year: str, end_year: str):
    """根据起止年份从数据库中获取指定要素的sg数据"""
    try:
        db_column_name = ELEMENT_TO_DB_MAPPING.get(element)
        if not db_column_name:
            raise ValueError(f"无效的要素名称: {element}")

        # 构建查询
        query = text(f"""
            SELECT
                station_id, station_name, lat, lon, year, month, day, hour, {db_column_name}, {db_column_name}_grid
            FROM proc_sg_data
            WHERE
                year >= :start_year
                AND year <= :end_year
        """)
        result = db.execute(
            query,
            {
                "start_year": int(start_year),
                "end_year": int(end_year)
            }
        )
        df = pd.DataFrame(result.fetchall())
        return df
    
    except Exception as e:
        print(f"查询数据时出错: {e}")
        db.rollback()
        raise