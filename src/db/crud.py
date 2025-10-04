# src/db/crud.py
import pandas as pd
from datetime import datetime
from sqlalchemy.orm import Session
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

def get_global_filenames_by_status(db: Session, status: str) -> list[str]:
    """
    【全局查询】获取所有状态为 `status` 的数据导入子任务，并返回文件名列表。
    
    注意：这个函数不区分父任务，会返回所有历史任务中符合条件的子任务。
    """
    # 查询条件是正确的，符合你的“不按父任务ID查询”的需求
    # 我在这里硬编码了 task_type，因为这个函数的目标就是获取导入文件的子任务
    tasks = db.query(db_models.TaskProgress).filter(
        db_models.TaskProgress.task_type == "DataImport_SubTask",
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

"""--------------------数据导入--------------------"""
def delete_raw_station_data_by_filename(db: Session, filename: str):
    """
    根据源文件名称删除原始站点数据表中的记录

    :param db: SQLAlchemy数据库会话.
    :param filename: 重复数据的源文件名称.
    :return: 被删除的记录行数.
    """
    num_deleted = db.query(db_models.RawStationData).filter(
        db_models.RawStationData.source_file == filename
    ).delete(synchronize_session=False)
    db.commit()
    return num_deleted

def bulk_insert_raw_station_data(db: Session, data_df: pd.DataFrame):
    """
    将Pandas DataFrame中的站点数据批量导入数据库 - 原始站点数据。

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
        chunksize=40000
    )

def bulk_insert_proc_station_data(db: Session, data_df: pd.DataFrame):
    """
    将Pandas DataFrame中的站点数据批量导入数据库 - 处理与合并后的数据。

    :param db: SQLAlchemy数据库会话.
    :param data_df: 包含待导入数据的DataFrame.
                    列名应与RawStationData模型中的字段名匹配
                    (station_id, station_name, timestamp, temperature, etc.).
    """
    # to_sql 是pandas提供的一个非常高效的批量插入方法
    data_df.to_sql(
        name=db_models.ProcStationGridData.__tablename__,  # 指定要插入的表名，使用模型中的表名
        con=db.bind,        # 获取底层的数据库连接，确保数据能正确写入
        if_exists='append', # 如果表已存在，则追加数据而不是覆盖或报错
        index=False,        # 不将DataFrame的索引写入数据库，只写入实际数据
        chunksize=40000
    )

"""--------------------数据预览--------------------"""
def get_unique_station_names(db: Session):
    """从原始数据表中查询所有唯一的站点名称。"""
    return db.query(db_models.RawStationData.station_name).distinct().all()

def get_raw_station_data(db: Session, station_name: str, element: str, start_time: datetime, end_time: datetime):
    """
    查询指定站点、要素和时间范围的原始数据。
    """
    db_column_name = ELEMENT_TO_DB_MAPPING.get(element)
    if not db_column_name:
        raise ValueError(f"无效的要素名称: {element}")

    # 获取模型中对应的列对象
    db_column = getattr(db_models.RawStationData, db_column_name)

    # 构建查询
    query = db.query(
        db_models.RawStationData.station_name,
        db_models.RawStationData.lat,
        db_models.RawStationData.lon,
        db_models.RawStationData.timestamp,
        db_column.label("value")  # 将查询的列重命名为'value'，方便后续统一处理
    ).filter(
        db_models.RawStationData.station_name == station_name,
        db_models.RawStationData.timestamp >= start_time,
        db_models.RawStationData.timestamp <= end_time
    ).order_by(
        db_models.RawStationData.timestamp
    )
    
    return query.all()