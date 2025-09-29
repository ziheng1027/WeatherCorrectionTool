from fastapi import FastAPI
from src.api.routers import config_manage
from fastapi.middleware.cors import CORSMiddleware


# 创建FastAPI应用实例
app = FastAPI(
    title="气象数据订正工具 API",
    description="用于数据导入, 数据预览, 数据透析, 预处理, 建模和订正的API接口",
    version="1.0.0",
)

# 添加跨域支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加路由
app.include_router(config_manage.router)


@app.get("/", tags=["root"])
async def root():
    return {"message": "欢迎使用气象数据订正工具 API!"}

