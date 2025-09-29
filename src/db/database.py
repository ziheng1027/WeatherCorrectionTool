# src/db/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# 1. 定义数据库连接URL
#    对于SQLite, URL的格式是 "sqlite:///./your_database_name.db"
#    "./" 表示数据库文件将创建在项目根目录下的 `sql_app.db` 文件。
#    `connect_args` 是SQLite特有的，用于允许多线程访问，这对于FastAPI是必需的。
SQLALCHEMY_DATABASE_URL = "sqlite:///output/db/weather.db"

# 2. 创建SQLAlchemy引擎 (Engine)
#    引擎是SQLAlchemy应用的核心接口，负责处理与数据库的连接和通信。
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

# 3. 创建一个SessionLocal类（会话工厂）
#    这个类的实例将是实际的数据库会务。
#    autocommit=False 和 autoflush=False 确保数据操作在事务中进行，需要手动提交。
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. 创建一个Base类（声明性基类）
#    我们之后创建的所有数据库模型（ORM models）都需要继承这个类。
#    它会帮助SQLAlchemy将我们的Python类映射到数据库的表中。
Base = declarative_base()