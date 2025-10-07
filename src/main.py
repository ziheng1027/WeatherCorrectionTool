# src/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from src.api.routers import config_manage, data_import, data_preview, data_process
from src.core.config import STOP_EVENT



@asynccontextmanager
async def lifespan(app: FastAPI):
    # 在应用启动时创建数据库和表
    print("应用启动...")
    from src.db.database import create_db_and_tables
    create_db_and_tables()
    yield
    print("应用关闭...发送停止信号给后台任务...")
    STOP_EVENT.set()
    print("应用已关闭...")

# 创建FastAPI应用实例
app = FastAPI(
    title="气象数据订正工具 API",
    description="用于数据导入, 数据预览, 数据透析, 预处理, 建模和订正的API接口",
    version="1.0.0",
    lifespan=lifespan   # 关联生命周期事件
)

# 添加跨域支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加根路由
@app.get("/", tags=["首页"])
async def root():
    return {"message": "欢迎使用气象数据订正工具 API!"}

# 添加路由
app.include_router(config_manage.router)
app.include_router(data_import.router)
app.include_router(data_preview.router)
app.include_router(data_process.router)
