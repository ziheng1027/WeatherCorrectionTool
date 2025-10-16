# src/db/database.py

from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base


DB_FILE = Path("output/db/weather.db")

DB_FILE.parent.mkdir(parents=True, exist_ok=True)

# 1. 定义数据库连接URL
SQLALCHEMY_DATABASE_URL = f"sqlite:///{DB_FILE.resolve()}"

# 2. 创建SQLAlchemy引擎 (Engine)
#    引擎是SQLAlchemy应用的核心接口，负责处理与数据库的连接和通信。
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

# 3. 增加时间监听器来开启WAL模式
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """当每个新连接建立时, 执行PRAGMA命令开启WAL模式"""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

# 4. 创建一个SessionLocal类（会话工厂）
#    这个类的实例将是实际的数据库会务。
#    autocommit=False 和 autoflush=False 确保数据操作在事务中进行，需要手动提交。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 5. 创建一个Base类（声明性基类）
#    我们之后创建的所有数据库模型（ORM models）都需要继承这个类。
#    它会帮助SQLAlchemy将我们的Python类映射到数据库的表中。
Base = declarative_base()

# --- 新增一个函数，用于初始化 ---
def create_db_and_tables():
    # 这个函数将在main.py中被调用
    Base.metadata.create_all(bind=engine)

# 依赖注入函数，用于在FastAPI路由中获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()