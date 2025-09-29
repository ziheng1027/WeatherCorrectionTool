# FastAPI 现代Web框架学习笔记

## What - FastAPI 是什么？

**FastAPI** 是一个现代、快速（高性能）的 Web 框架，用于基于标准 Python 类型提示使用 Python 3.8+ 构建 API。它基于 Python 类型提示，自动生成 OpenAPI 文档，并支持异步编程。

### 核心特性
- **高性能**：与 NodeJS 和 Go 相当，是最快的 Python 框架之一
- **快速开发**：代码开发速度提高约 200% 至 300%
- **更少错误**：减少约 40% 的人为错误
- **直观**：强大的编辑器支持，自动补全无处不在
- **简单**：易于使用和学习，减少阅读文档的时间
- **简短**：最小化代码重复，每个参数声明有多种功能
- **健壮**：生产就绪的代码，具有自动交互式文档

## Why - 为什么需要 FastAPI？

### 主要应用场景

1. **构建 RESTful API**
   - 微服务架构
   - 移动应用后端
   - 单页应用后端
   - 机器学习模型服务化

2. **数据验证和序列化**
   - 自动请求数据验证
   - 响应数据序列化
   - 类型安全的 API 开发

3. **实时应用**
   - WebSocket 支持
   - Server-Sent Events
   - 实时数据推送

4. **文档生成**
   - 自动生成 OpenAPI 文档
   - 交互式 API 文档（Swagger UI）
   - 替代文档（ReDoc）

### 解决的问题

- **开发效率**：减少样板代码，自动生成文档
- **代码质量**：类型提示减少运行时错误
- **性能瓶颈**：异步支持提高并发处理能力
- **API 文档维护**：代码即文档，文档与代码同步更新
- **数据验证**：自动验证请求数据，减少手动检查

## Where - 有哪些替代方案？

### 主要替代方案

1. **Flask**
   - 优点：简单灵活，生态系统丰富
   - 缺点：性能相对较低，无内置数据验证

2. **Django**
   - 优点：功能完整，ORM 强大，生态系统成熟
   - 缺点：相对笨重，学习曲线较陡

3. **Sanic**
   - 优点：高性能异步框架
   - 缺点：生态系统不如 FastAPI 成熟

4. **Starlette**
   - 优点：FastAPI 的底层框架，轻量级
   - 缺点：需要更多手动配置

5. **Express.js (Node.js)**
   - 优点：JavaScript 生态系统，高性能
   - 缺点：动态类型语言，缺少类型安全

### 选择 FastAPI 的理由

- **现代标准**：基于 Python 类型提示和 OpenAPI 标准
- **开发体验**：极佳的编辑器支持和自动补全
- **性能优势**：与 NodeJS 和 Go 相当的高性能
- **学习成本低**：直观的 API 设计，易于上手
- **生产就绪**：内置数据验证、序列化、文档生成

## How - 核心概念与使用

### 核心组件

1. **FastAPI Application** - 应用实例
2. **Path Operations** - 路径操作（路由）
3. **Pydantic Models** - 数据模型
4. **Dependency Injection** - 依赖注入
5. **Background Tasks** - 后台任务
6. **Middleware** - 中间件

### 基本使用流程

#### 1. 安装 FastAPI

```bash
# 安装 FastAPI 和标准依赖
# fastapi[standard] 包含常用依赖，如 fastapi-cloud-cli
pip install "fastapi[standard]"

# 仅安装核心 FastAPI
pip install fastapi

# 安装标准依赖但不包含云 CLI
pip install "fastapi[standard-no-fastapi-cloud-cli]"

# 升级 FastAPI 和 Pydantic 到最新版本
pip install --upgrade fastapi pydantic
```

#### 2. 创建 FastAPI 应用

```python
# main.py
from fastapi import FastAPI

# 创建 FastAPI 应用实例
# FastAPI(): 创建应用实例，可以配置各种参数如 title、description、version 等
app = FastAPI()

# 定义根路径操作
# @app.get("/"): 定义 GET 请求的路由装饰器，"/" 表示根路径
# async def read_root(): 异步函数定义，async 关键字表示异步操作
@app.get("/")
async def read_root():
    # 返回 JSON 响应，FastAPI 会自动序列化 Python 字典为 JSON
    return {"message": "Hello World"}

# 定义带路径参数的路由
# {item_id}: 路径参数，从 URL 中提取
# item_id: int: 类型提示，FastAPI 会自动验证和转换类型
# q: str | None = None: 可选查询参数，类型为字符串或 None，默认值为 None
@app.get("/items/{item_id}")
async def read_item(item_id: int, q: str | None = None):
    # 构建响应数据
    result = {"item_id": item_id}
    # 如果提供了查询参数 q，则添加到响应中
    if q:
        result.update({"q": q})
    return result
```

#### 3. 运行开发服务器

```bash
# 使用 FastAPI CLI 启动开发服务器
# fastapi dev main.py: 启动开发服务器，自动重载代码变化
# --reload: 自动重载（已包含在 fastapi dev 中）
fastapi dev main.py

# 或者使用 Uvicorn 直接启动
# uvicorn main:app: 启动 Uvicorn 服务器，main 是模块名，app 是 FastAPI 实例
# --reload: 开发模式下自动重载代码变化
# --host: 绑定主机地址，0.0.0.0 表示所有网络接口
# --port: 绑定端口号
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

#### 4. 访问 API 和文档

启动后访问：
- **API**: http://127.0.0.1:8000
- **交互式文档 (Swagger UI)**: http://127.0.0.1:8000/docs
- **替代文档 (ReDoc)**: http://127.0.0.1:8000/redoc

### 数据模型和验证

#### 使用 Pydantic 模型

```python
from pydantic import BaseModel
from datetime import date

# 定义数据模型
# BaseModel: Pydantic 基础模型类，提供数据验证和序列化
class User(BaseModel):
    # id: int: 字段类型提示，FastAPI 会自动验证数据类型
    id: int
    # name: str: 必填字符串字段
    name: str
    # joined: date: 日期类型字段
    joined: date

# 创建模型实例
# User(): 直接实例化，传递关键字参数
my_user: User = User(id=3, name="John Doe", joined="2018-07-19")

# 从字典创建模型实例
second_user_data = {
    "id": 4,
    "name": "Mary", 
    "joined": "2018-11-30",
}
# **dict: 字典解包，将字典键值对作为关键字参数传递
my_second_user: User = User(**second_user_data)
```

#### 在 API 中使用模型

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

# 定义请求体模型
class Item(BaseModel):
    # name: str: 必填字符串字段
    name: str
    # price: float: 必填浮点数字段
    price: float
    # is_offer: bool | None = None: 可选布尔字段，默认值为 None
    is_offer: bool | None = None

# GET 请求示例
@app.get("/")
def read_root():
    return {"Hello": "World"}

# GET 请求带路径参数和查询参数
@app.get("/items/{item_id}")
def read_item(item_id: int, q: str | None = None):
    return {"item_id": item_id, "q": q}

# PUT 请求带路径参数和请求体
# item: Item: 请求体参数，FastAPI 会自动验证和反序列化
@app.put("/items/{item_id}")
def update_item(item_id: int, item: Item):
    # 返回更新后的项目信息
    return {"item_name": item.name, "item_id": item_id}
```

### 路径参数和查询参数

#### 路径参数

```python
from fastapi import FastAPI

app = FastAPI()

# 基本路径参数
# {item_id}: 路径参数，从 URL 路径中提取
@app.get("/items/{item_id}")
async def read_item(item_id: int):
    return {"item_id": item_id}

# 带类型验证的路径参数
from fastapi import Path

@app.get("/items/{item_id}")
def read_item(
    # Path(): 路径参数验证器
    # gt=0: 必须大于 0
    item_id: int = Path(gt=0)
):
    return {"item_id": item_id}
```

#### 查询参数

```python
from fastapi import FastAPI, Query

app = FastAPI()

# 可选查询参数
@app.get("/items/")
async def read_items(
    # q: str | None = None: 可选字符串查询参数
    q: str | None = None
):
    if q:
        return {"q": q}
    return {"message": "No query parameter q provided"}

# 带验证的查询参数
@app.get("/items/")
async def read_items(
    # Query(): 查询参数验证器
    # max_length=10: 最大长度限制为 10 个字符
    query: str = Query(max_length=10)
):
    return {"query": query}
```

### 请求体和响应模型

#### 请求体示例

```python
from fastapi import FastAPI, Body
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    description: str | None = None
    price: float
    tax: float | None = None

# 单个请求体示例
@app.put("/items/{item_id}")
async def update_item(
    item_id: int,
    # Body(): 请求体验证器
    # examples: 提供请求体示例，用于文档生成
    item: Item = Body(
        examples=[
            {
                "name": "Foo",
                "description": "A very nice Item", 
                "price": 42.0,
                "tax": 3.2
            }
        ]
    )
):
    results = {"item_id": item_id, "item": item}
    return results

# 多个请求体示例
@app.put("/items/{item_id}")
async def update_item(
    item_id: int,
    item: Item = Body(
        examples=[
            {
                "name": "Foo",
                "description": "A very nice Item",
                "price": 42.0,
                "tax": 3.2
            },
            {
                "name": "Bar", 
                "description": "The bartenders",
                "price": 32.0,
                "tax": 2.2
            }
        ]
    )
):
    results = {"item_id": item_id, "item": item}
    return results
```

#### 响应模型

```python
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: float

class ResponseMessage(BaseModel):
    message: str

# response_model: 指定响应模型，FastAPI 会使用此模型验证和序列化响应数据
@app.post("/items/", response_model=ResponseMessage)
async def create_item(item: Item):
    return {"message": f"Item '{item.name}' with price {item.price} created."}

@app.get("/", response_model=ResponseMessage)
async def read_root():
    return {"message": "Welcome to the FastAPI app!"}
```

### 依赖注入

#### 基本依赖

```python
from fastapi import FastAPI, Depends

app = FastAPI()

# 简单的依赖函数
def query_extractor(q: str | None = None):
    # 返回查询参数 q
    return q

# 使用依赖注入
@app.get("/items/")
async def read_items(
    # Depends(): 依赖注入装饰器，注入 query_extractor 函数的返回值
    query: str = Depends(query_extractor)
):
    return {"query": query}
```

#### 类作为依赖

```python
from fastapi import FastAPI, Depends

app = FastAPI()

# 定义类作为依赖
class Cat:
    def __init__(self, name: str):
        self.name = name

# 创建类实例
fluffy = Cat(name="Mr Fluffy")

@app.get("/cat/")
async def get_cat(cat: Cat = Depends(lambda: fluffy)):
    return {"cat_name": cat.name}
```

### 安全认证

#### HTTP Basic 认证

```python
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import secrets

app = FastAPI()

# 创建 HTTP Basic 认证实例
# HTTPBasic(): HTTP Basic 认证方案
security = HTTPBasic()

# 安全的凭据验证函数
def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
    # 预期的用户名和密码（实际应用中应从数据库获取）
    expected_username = "stanleyjobson"
    expected_password = "swordfish"

    # 安全比较用户名和密码，防止时序攻击
    # secrets.compare_digest(): 安全字符串比较，防止时序攻击
    correct_username = secrets.compare_digest(
        credentials.username.encode("utf-8"), 
        expected_username.encode("utf-8")
    )
    correct_password = secrets.compare_digest(
        credentials.password.encode("utf-8"), 
        expected_password.encode("utf-8")
    )

    # 如果验证失败，抛出 HTTP 异常
    if not (correct_username and correct_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

# 受保护的路由
@app.get("/users/me")
def read_current_user(username: str = Depends(get_current_username)):
    return {"username": username}
```

### 后台任务

```python
from fastapi import FastAPI, BackgroundTasks

app = FastAPI()

# 后台任务函数
def write_log(message: str):
    # 模拟写入日志文件
    with open("log.txt", mode="a") as log:
        log.write(f"Log: {message}\n")

# 使用后台任务
@app.post("/send-notification/{email}")
async def send_notification(
    email: str,
    # BackgroundTasks: 后台任务管理器
    background_tasks: BackgroundTasks
):
    # 添加后台任务
    # add_task(): 添加后台任务，第一个参数是任务函数，后面是任务函数的参数
    background_tasks.add_task(write_log, f"Notification for {email}")
    return {"message": "Notification sent in the background"}
```

### 中间件

```python
from fastapi import FastAPI, Request

app = FastAPI()

# 定义 HTTP 中间件
# @app.middleware("http"): HTTP 中间件装饰器
@app.middleware("http")
async def process_request(request: Request, call_next):
    # 在路径操作执行前的代码（例如：日志记录、认证）
    
    # 调用下一个中间件或路径操作
    response = await call_next(request)
    
    # 在路径操作执行后、返回响应前的代码（例如：修改响应头）
    return response
```

### 测试

#### 使用 TestClient

```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

@app.get("/")
async def read_main():
    return {"msg": "Hello World"}

# 创建测试客户端
# TestClient(app): 创建测试客户端，用于测试 FastAPI 应用
client = TestClient(app)

# 测试函数
def test_read_main():
    # client.get("/"): 发送 GET 请求到根路径
    response = client.get("/")
    # 断言状态码为 200
    assert response.status_code == 200
    # 断言响应 JSON 数据
    assert response.json() == {"msg": "Hello World"}
```

### 项目结构

#### 推荐的项目结构

```
.
├── app                  # "app" 是 Python 包
│   ├── __init__.py      # 这个文件使 "app" 成为 "Python 包"
│   ├── main.py          # "main" 模块，例如 import app.main
│   ├── dependencies.py  # "dependencies" 模块，例如 import app.dependencies
│   └── routers          # "routers" 是 "Python 子包"
│   │   ├── __init__.py  # 使 "routers" 成为 "Python 子包"
│   │   ├── items.py     # "items" 子模块，例如 import app.routers.items
│   │   └── users.py     # "users" 子模块，例如 import app.routers.users
│   └── internal         # "internal" 是 "Python 子包"
│       ├── __init__.py  # 使 "internal" 成为 "Python 子包"
│       └── admin.py     # "admin" 子模块，例如 import app.internal.admin
```

#### 使用 APIRouter

```python
# app/routers/users.py
from fastapi import APIRouter

# 创建路由器实例
# APIRouter(): 创建路由器，用于模块化组织路由
router = APIRouter()

# 在路由器上定义路径操作
@router.get("/users/", tags=["users"])
async def read_users():
    return [{"username": "Rick"}, {"username": "Morty"}]

@router.get("/users/me", tags=["users"])
async def read_user_me():
    return {"username": "current user"}

@router.get("/users/{username}", tags=["users"])
async def read_user(username: str):
    return {"username": username}
```

```python
# app/main.py
from fastapi import FastAPI
from .routers import users

app = FastAPI()

# 包含路由器
# include_router(): 将路由器包含到主应用中
app.include_router(users.router, prefix="/api/v1")
```

### 配置管理

#### 使用 Pydantic Settings

```python
from pydantic import Field
from pydantic_settings import BaseSettings

# 定义配置类
class Settings(BaseSettings):
    # app_name: str = "Awesome API": 应用名称，带默认值
    app_name: str = "Awesome API"
    # admin_email: str: 管理员邮箱，必填字段
    admin_email: str
    # items_per_user: int = Field(50, gt=0, lt=1000): 带验证的字段
    items_per_user: int = Field(50, gt=0, lt=1000)

# 创建配置实例
settings = Settings()

# 在 FastAPI 中使用配置
from fastapi import FastAPI

app = FastAPI()

@app.get("/info")
async def info():
    return {
        "app_name": settings.app_name,
        "admin_email": settings.admin_email,
        "items_per_user": settings.items_per_user,
    }
```

#### 环境变量文件 (.env)

```bash
# .env 文件
ADMIN_EMAIL="deadpool@example.com"
APP_NAME="ChimichangApp"
```

### 异步支持

#### 异步函数

```python
from fastapi import FastAPI

app = FastAPI()

# 异步路径操作
@app.get("/")
async def read_root():
    # 在异步函数中可以 await 其他异步操作
    return {"Hello": "World"}

# 同步路径操作（适用于 CPU 密集型任务）
@app.get("/sync")
def read_sync():
    return {"message": "This is a synchronous endpoint"}
```

### 最佳实践

#### 1. 代码组织
- 使用 APIRouter 模块化组织路由
- 将依赖项分离到单独的模块
- 使用 Pydantic 模型进行数据验证
- 配置集中管理

#### 2. 错误处理
- 使用 HTTPException 抛出特定错误
- 实现自定义异常处理器
- 记录详细的错误日志

#### 3. 性能优化
- 合理使用异步和同步端点
- 使用连接池管理数据库连接
- 实现缓存机制
- 监控应用性能

#### 4. 安全考虑
- 使用 HTTPS 加密通信
- 实现适当的认证和授权
- 验证和清理所有输入数据
- 定期更新依赖项

### 总结

FastAPI 是一个功能强大、性能卓越的现代 Web 框架，特别适合构建高性能的 API 服务。通过利用 Python 类型提示和 Pydantic 模型，它提供了出色的开发体验、自动文档生成和强大的数据验证功能。

**核心优势**：
- 极快的性能，与 NodeJS 和 Go 相当
- 直观的 API 设计，学习成本低
- 自动生成交互式 API 文档
- 强大的数据验证和序列化
- 完整的异步支持
- 生产就绪的功能和安全性

对于需要构建高性能、类型安全的现代 API 的 Python 开发者来说，FastAPI 是一个理想的选择。

---

*本文档基于 FastAPI 最新版本和 Pydantic v2 编写，适用于 Python 3.8+ 环境*