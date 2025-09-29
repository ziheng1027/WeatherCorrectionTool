# SQLAlchemy ORM 学习笔记

## What - SQLAlchemy ORM 是什么？

**SQLAlchemy ORM** 是 Python SQLAlchemy 库的 Object Relational Mapper（对象关系映射器）组件，它提供了一种将 Python 对象映射到数据库表的方式，允许开发者使用 Python 类和对象来操作数据库，而无需直接编写 SQL 语句。

### 核心特性
- **声明式映射**：使用 Python 类定义数据库表结构
- **类型安全**：支持 Python 类型提示和类型检查
- **关系映射**：支持一对一、一对多、多对多关系
- **事务管理**：自动管理数据库事务
- **查询构建**：提供强大的查询 API
- **会话管理**：管理对象生命周期和持久化
- **异步支持**：支持异步数据库操作

## Why - 为什么需要 SQLAlchemy ORM？

### 主要应用场景

1. **Web 应用开发**
   - FastAPI、Flask、Django 等框架集成
   - RESTful API 后端开发
   - 企业级应用数据层

2. **数据密集型应用**
   - 数据分析平台
   - 报表系统
   - 数据迁移工具

3. **微服务架构**
   - 服务间数据访问
   - 分布式事务管理
   - 多数据库支持

4. **原型开发**
   - 快速数据模型设计
   - 数据库无关性
   - 代码即文档

### 解决的问题

- **对象-关系阻抗不匹配**：将面向对象编程与关系数据库无缝连接
- **SQL 注入防护**：自动参数化查询，提高安全性
- **代码可维护性**：类型安全的查询和操作
- **数据库抽象**：支持多种数据库后端
- **性能优化**：延迟加载、预加载等优化策略
- **开发效率**：减少样板代码，提高开发速度

## Where - 有哪些替代方案？

### 主要替代方案

1. **Django ORM**
   - 优点：与 Django 框架深度集成，功能完整
   - 缺点：只能在 Django 中使用，灵活性有限

2. **Peewee**
   - 优点：轻量级，简单易用
   - 缺点：功能相对简单，社区较小

3. **Pony ORM**
   - 优点：语法优雅，支持生成器查询
   - 缺点：性能相对较低，生态系统较小

4. **Tortoise ORM**
   - 优点：异步支持好，Django 风格
   - 缺点：相对较新，生态系统在发展中

5. **直接 SQL**
   - 优点：完全控制，性能最优
   - 缺点：开发效率低，易出错

### 选择 SQLAlchemy ORM 的理由

- **功能完整**：支持所有主流数据库特性
- **灵活性高**：支持多种映射方式和查询风格
- **生态系统成熟**：丰富的扩展和工具支持
- **性能优秀**：经过优化的查询和缓存机制
- **社区活跃**：持续更新和维护
- **生产就绪**：被众多大型项目使用

## How - 核心概念与使用

### 核心组件

1. **DeclarativeBase** - 声明式基类
2. **Mapped** - 类型注解
3. **Session** - 数据库会话
4. **Relationship** - 关系映射
5. **Query** - 查询构建器

### 基本使用流程

#### 1. 安装 SQLAlchemy

```bash
# 安装 SQLAlchemy
pip install sqlalchemy

# 检查版本
python -c "import sqlalchemy; print(sqlalchemy.__version__)"
```

#### 2. 定义基础模型

```python
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column

# 定义声明式基类
# DeclarativeBase: 所有 ORM 模型的基类，提供元数据管理
class Base(DeclarativeBase):
    pass
```

#### 3. 定义简单模型

```python
from typing import Optional
from sqlalchemy import String

# 定义用户模型
class User(Base):
    # __tablename__: 指定数据库表名
    __tablename__ = "user_account"

    # id: Mapped[int]: 主键字段，使用 Mapped 类型注解
    # mapped_column(primary_key=True): 定义为主键
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # name: Mapped[str]: 字符串字段
    # mapped_column(String(30)): 指定列类型和长度
    name: Mapped[str] = mapped_column(String(30))
    
    # fullname: Mapped[Optional[str]]: 可选字符串字段
    fullname: Mapped[Optional[str]]

    # __repr__: 对象表示方法，用于调试
    def __repr__(self) -> str:
        return f"User(id={self.id!r}, name={self.name!r}, fullname={self.fullname!r})"
```

#### 4. 创建数据库连接和表

```python
from sqlalchemy import create_engine

# 创建数据库引擎
# create_engine(): 创建数据库连接引擎
# sqlite+pysqlite:///:memory:: 使用内存 SQLite 数据库
# echo=True: 输出执行的 SQL 语句
engine = create_engine("sqlite+pysqlite:///:memory:", echo=True)

# 创建所有表
# Base.metadata.create_all(): 根据模型创建数据库表
Base.metadata.create_all(engine)
```

#### 5. 创建会话并操作数据

```python
from sqlalchemy.orm import Session

# 创建数据库连接
conn = engine.connect()

# 创建会话
# Session(conn): 创建数据库会话，管理对象生命周期
session = Session(conn)

# 开始事务
conn.begin()

# 创建用户对象
# User(): 实例化 ORM 对象，自动提供默认构造函数
squidward = User(name="squidward", fullname="Squidward Tentacles")
krabs = User(name="ehkrabs", fullname="Eugene H. Krabs")

# 添加对象到会话
# session.add(): 将对象添加到会话，标记为待插入
session.add(squidward)
session.add(krabs)

# 提交事务
# session.commit(): 提交所有挂起的更改到数据库
session.commit()

# 关闭连接
conn.close()
```

### 关系映射

#### 1. 一对多关系

```python
from typing import List
from sqlalchemy import ForeignKey
from sqlalchemy.orm import relationship

class User(Base):
    __tablename__ = "user_account"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    
    # addresses: Mapped[List["Address"]]: 一对多关系，用户有多个地址
    # relationship(): 定义关系
    # back_populates="user": 双向关系，指定反向属性名
    # cascade="all, delete-orphan": 级联操作设置
    addresses: Mapped[List["Address"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

class Address(Base):
    __tablename__ = "address"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    email_address: Mapped[str]
    
    # user_id: Mapped[int]: 外键字段
    # mapped_column(ForeignKey("user_account.id")): 定义外键约束
    user_id: Mapped[int] = mapped_column(ForeignKey("user_account.id"))
    
    # user: Mapped["User"]: 多对一关系，地址属于一个用户
    user: Mapped["User"] = relationship(back_populates="addresses")
```

#### 2. 多对多关系

```python
from sqlalchemy import Table, Column

# 定义关联表
# Table(): 定义多对多关系的中间表
# association_table: 关联表名称
order_items_table = Table(
    "order_items",
    Base.metadata,
    # Column(): 定义表列
    # ForeignKey(): 定义外键约束
    Column("order_id", ForeignKey("user_order.id"), primary_key=True),
    Column("item_id", ForeignKey("item.id"), primary_key=True),
)

class Order(Base):
    __tablename__ = "user_order"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user_account.id"))
    
    # items: Mapped[List["Item"]]: 多对多关系
    # relationship(secondary=order_items_table): 通过关联表建立关系
    items: Mapped[List["Item"]] = relationship(secondary=order_items_table)

class Item(Base):
    __tablename__ = "item"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str]
```

#### 3. 一对一关系

```python
class Parent(Base):
    __tablename__ = "parent_table"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    
    # child: Mapped["Child"]: 一对一关系，返回单个对象而非列表
    child: Mapped["Child"] = relationship(back_populates="parent")

class Child(Base):
    __tablename__ = "child_table"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int] = mapped_column(ForeignKey("parent_table.id"))
    
    # parent: Mapped["Parent"]: 一对一关系的反向
    parent: Mapped["Parent"] = relationship(back_populates="child")
```

### 查询操作

#### 1. 基本查询

```python
from sqlalchemy import select

# 创建会话
session = Session(engine)

# 构建查询语句
# select(User): 选择 User 模型的所有字段
stmt = select(User).where(User.name.in_(["spongebob", "sandy"]))

# 执行查询
# session.scalars(stmt): 执行查询并返回标量结果
for user in session.scalars(stmt):
    print(user)
```

#### 2. 关联查询

```python
from sqlalchemy.orm import selectinload

# 预加载关联数据
# selectinload(User.addresses): 使用 SELECT IN 策略预加载地址
stmt = select(User).options(selectinload(User.addresses))

# 执行查询
result = session.execute(stmt)

for user in result.scalars():
    print(f"User: {user.name}")
    for address in user.addresses:
        print(f"  Address: {address.email_address}")
```

#### 3. 复杂查询

```python
from sqlalchemy import and_, or_

# 复杂条件查询
stmt = select(User).where(
    and_(
        User.name.like("%s%"),
        or_(
            User.fullname.is_not(None),
            User.id > 1
        )
    )
)

# 排序和限制
stmt = select(User).order_by(User.name.desc()).limit(10)

# 聚合查询
from sqlalchemy import func
stmt = select(func.count(User.id))
count = session.scalar(stmt)
print(f"Total users: {count}")
```

### 数据操作

#### 1. 插入数据

```python
# 创建新用户
new_user = User(name="alice", fullname="Alice Smith")

# 添加地址
address1 = Address(email_address="alice@example.com")
address2 = Address(email_address="alice.work@example.com")

# 建立关系
new_user.addresses = [address1, address2]

# 添加到会话并提交
session.add(new_user)
session.commit()
```

#### 2. 更新数据

```python
# 查询用户
user = session.get(User, 1)

# 更新属性
user.fullname = "Alice Johnson"

# 提交更改
session.commit()
```

#### 3. 删除数据

```python
# 标记对象为删除
# session.delete(): 标记对象为待删除
user = session.get(User, 1)
session.delete(user)

# 批量删除
# 使用查询删除多条记录
deleted_count = session.query(User).filter(User.name.like("test%")).delete()

# 提交删除操作
session.commit()
```

### 高级特性

#### 1. 异步支持

```python
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# 创建异步引擎
# create_async_engine(): 创建异步数据库引擎
# sqlite+aiosqlite://: 异步 SQLite 驱动
engine = create_async_engine("sqlite+aiosqlite://", echo=True)

# 创建异步会话工厂
# async_sessionmaker(): 异步会话工厂
# expire_on_commit=False: 提交后不使对象过期
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def async_main():
    # 创建表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # 使用异步会话
    async with async_session() as session:
        # 插入数据
        new_user = User(name="async_user", fullname="Async User")
        session.add(new_user)
        await session.commit()
        
        # 查询数据
        stmt = select(User)
        result = await session.execute(stmt)
        users = result.scalars().all()
        
        for user in users:
            print(user)

# 运行异步主函数
asyncio.run(async_main())
```

#### 2. 数据类支持

```python
from sqlalchemy.orm import mapped_as_dataclass

# 使用数据类装饰器
# mapped_as_dataclass(): 将 ORM 类映射为数据类
@mapped_as_dataclass
class Data:
    __tablename__ = "data"
    
    # id: Mapped[int]: 主键字段
    # init=False: 不在构造函数中初始化
    id: Mapped[int] = mapped_column(init=False, primary_key=True)
    status: Mapped[str]
    
    # 非映射字段
    ctrl_one: Optional[str] = None
    ctrl_two: Optional[str] = None

# 实例化数据类
d1 = Data(status="s1", ctrl_one="ctrl1", ctrl_two="ctrl2")
```

#### 3. 继承映射

```python
from sqlalchemy.orm import Mapped

class Employee(Base):
    __tablename__ = "employee"
    
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    type: Mapped[str]
    
    # 多态映射配置
    __mapper_args__ = {
        "polymorphic_identity": "employee",
        "polymorphic_on": "type",
    }

class Manager(Employee):
    __tablename__ = "manager"
    
    # 继承主键
    id: Mapped[int] = mapped_column(ForeignKey("employee.id"), primary_key=True)
    manager_name: Mapped[str]
    
    __mapper_args__ = {
        "polymorphic_identity": "manager",
    }

class Engineer(Employee):
    __tablename__ = "engineer"
    
    id: Mapped[int] = mapped_column(ForeignKey("employee.id"), primary_key=True)
    engineer_info: Mapped[str]
    
    __mapper_args__ = {
        "polymorphic_identity": "engineer",
    }
```

### 会话管理

#### 1. 会话生命周期

```python
from sqlalchemy.orm import sessionmaker

# 创建会话工厂
# sessionmaker(): 创建会话工厂
# bind=engine: 绑定到数据库引擎
SessionLocal = sessionmaker(bind=engine)

# 使用上下文管理器
with SessionLocal() as session:
    # 在上下文中使用会话
    user = session.get(User, 1)
    print(user)
    # 上下文结束时自动关闭会话

# 手动管理会话
session = SessionLocal()
try:
    # 执行操作
    user = session.get(User, 1)
    session.commit()
except Exception:
    session.rollback()
    raise
finally:
    session.close()
```

#### 2. 对象状态管理

```python
# 检查对象状态
from sqlalchemy import inspect

user = User(name="test")

# 创建检查器
# inspect(): 检查 ORM 对象状态
insp = inspect(user)

# 检查对象状态
print(f"Transient: {insp.transient}")      # 瞬态：未与会话关联
print(f"Pending: {insp.pending}")          # 挂起：已添加到会话但未刷新
print(f"Persistent: {insp.persistent}")    # 持久：已在数据库中
print(f"Detached: {insp.detached}")        # 分离：已从会话中分离

# 合并对象
# session.merge(): 将分离对象合并回会话
merged_user = session.merge(user)
```

### 最佳实践

#### 1. 连接管理

```python
from contextlib import contextmanager

@contextmanager
def get_db_session():
    """数据库会话上下文管理器"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

# 使用示例
with get_db_session() as session:
    user = session.get(User, 1)
    user.name = "Updated Name"
```

#### 2. 性能优化

```python
# 批量插入
users = [
    User(name=f"user_{i}", fullname=f"User {i}")
    for i in range(1000)
]

# 使用 bulk_save_objects 提高性能
session.bulk_save_objects(users)
session.commit()

# 使用批量插入
session.execute(
    User.__table__.insert(),
    [{"name": f"user_{i}", "fullname": f"User {i}"} for i in range(1000)]
)
session.commit()
```

#### 3. 错误处理

```python
from sqlalchemy.exc import SQLAlchemyError

try:
    with get_db_session() as session:
        # 执行数据库操作
        user = User(name="test")
        session.add(user)
        session.commit()
        
except SQLAlchemyError as e:
    print(f"数据库错误: {e}")
    # 根据具体错误类型处理
    if "unique constraint" in str(e).lower():
        print("违反唯一约束")
    elif "foreign key" in str(e).lower():
        print("违反外键约束")
    else:
        print("其他数据库错误")
```

### 总结

SQLAlchemy ORM 是一个功能强大、灵活的 Python ORM 框架，特别适合以下场景：

**适用场景**：
- 复杂的业务逻辑和数据关系
- 需要类型安全和代码智能提示的项目
- 多数据库后端支持的需求
- 高性能和高并发的应用
- 需要精细控制数据库操作的项目

**核心优势**：
- **功能完整**：支持所有主流数据库和 SQL 特性
- **类型安全**：完整的 Python 类型提示支持
- **灵活性高**：支持多种映射方式和查询风格
- **性能优秀**：经过优化的查询和缓存机制
- **生态系统成熟**：丰富的扩展和工具支持
- **生产就绪**：被众多大型项目验证

**学习建议**：
1. 从简单的模型定义开始
2. 掌握基本的关系映射
3. 学习查询构建和优化
4. 理解会话管理和事务
5. 实践异步操作和高级特性

对于需要构建复杂、高性能、类型安全的数据库应用的项目，SQLAlchemy ORM 是一个理想的选择。它提供了企业级 ORM 的所有功能，同时保持了 Pythonic 的设计哲学和优秀的开发体验。

---

*本文档基于 SQLAlchemy 2.0+ 版本编写，适用于 Python 3.8+ 环境*