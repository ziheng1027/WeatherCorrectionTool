# SQLite 轻量级数据库学习笔记

## What - SQLite 是什么？

**SQLite** 是一个 C 语言库，提供轻量级、自包含、无服务器、事务性、功能齐全的 SQL 数据库引擎。它是一个零配置的数据库引擎，意味着不需要服务器进程或安装设置。

### 核心特性
- **轻量级**：整个数据库存储在单个磁盘文件中
- **无服务器**：不需要单独的服务器进程
- **零配置**：开箱即用，无需安装或配置
- **事务性**：支持 ACID 事务
- **跨平台**：支持所有主流操作系统
- **自包含**：不依赖外部库
- **公共领域**：完全开源，无版权限制

## Why - 为什么需要 SQLite？

### 主要应用场景

1. **嵌入式系统**
   - 移动应用（Android、iOS）
   - 桌面应用
   - 物联网设备
   - 游戏数据存储

2. **开发测试**
   - 原型开发
   - 单元测试
   - 配置存储
   - 缓存数据

3. **小型项目**
   - 个人项目
   - 小型网站
   - 数据分析
   - 脚本工具

4. **特殊场景**
   - 文件格式替代
   - 应用内数据库
   - 临时数据处理

### 解决的问题

- **简化部署**：单个文件包含整个数据库
- **降低复杂性**：无需数据库服务器管理
- **提高性能**：本地访问，无网络延迟
- **减少依赖**：不依赖外部数据库服务
- **快速原型**：即时可用的数据库解决方案

## Where - 有哪些替代方案？

### 主要替代方案

1. **MySQL**
   - 优点：功能完整，生态系统成熟
   - 缺点：需要服务器进程，配置复杂

2. **PostgreSQL**
   - 优点：功能强大，标准兼容性好
   - 缺点：资源消耗大，配置复杂

3. **SQL Server**
   - 优点：企业级功能，Windows 集成好
   - 缺点：商业许可，Windows 依赖

4. **Oracle Database**
   - 优点：企业级功能，性能优秀
   - 缺点：商业许可，成本高昂

5. **MongoDB**
   - 优点：文档存储，灵活性强
   - 缺点：NoSQL，事务支持有限

### 选择 SQLite 的理由

- **简单性**：单个文件，零配置
- **轻量级**：占用资源少，启动快速
- **嵌入式**：可直接嵌入应用程序
- **无依赖**：不依赖网络或外部服务
- **开源免费**：完全免费，无许可限制

## How - 核心概念与使用

### 核心组件

1. **SQLite 数据库文件** - 单个文件包含整个数据库
2. **SQLite 命令行工具** - 交互式数据库管理
3. **SQLite API** - 编程接口
4. **SQL 支持** - 完整的 SQL 语法支持

### 基本使用流程

#### 1. Python 中使用 SQLite

```python
import sqlite3

# 连接到数据库（如果不存在则创建）
# sqlite3.connect(filename): 连接到 SQLite 数据库文件
# filename: 数据库文件名，如果不存在则创建新数据库
# :memory: 表示内存数据库，仅在程序运行期间存在
conn = sqlite3.connect('example.db')

# 创建游标对象
# cursor(): 创建游标对象，用于执行 SQL 命令
cursor = conn.cursor()

# 关闭连接
# close(): 关闭数据库连接，释放资源
conn.close()
```

#### 2. 创建表和插入数据

```python
import sqlite3

try:
    # 连接到内存数据库
    # :memory: 创建内存数据库，程序结束后自动销毁
    con = sqlite3.connect(":memory:")
    
    # 创建表
    # execute(sql): 执行 SQL 语句
    # create table: 创建表语句
    # person: 表名
    # id integer primary key: 主键字段，自动递增
    # firstname varchar unique: 唯一字符串字段
    con.execute("create table person (id integer primary key, firstname varchar unique)")
    
    # 使用事务插入数据
    # with con: 使用上下文管理器自动提交事务
    # execute(sql, params): 执行带参数的 SQL 语句
    # ("Joe",): 参数元组，防止 SQL 注入
    with con:
        con.execute("insert into person(firstname) values (?)", ("Joe",))
    
    # 处理唯一约束错误
    try:
        with con:
            con.execute("insert into person(firstname) values (?)", ("Joe",))
    except sqlite3.IntegrityError:
        # 捕获唯一约束错误
        print("无法重复添加 Joe")
        
except sqlite3.Error as error:
    print("SQLite 错误:", error)
    
finally:
    # 确保连接被关闭
    if con:
        con.close()
        print("关闭 SQLite 连接")
```

#### 3. 查询数据

```python
import sqlite3

# 连接到数据库
conn = sqlite3.connect('my_database.db')
cursor = conn.cursor()

# 执行查询
# execute(sql): 执行 SQL 查询语句
# SELECT * FROM table: 查询所有字段
# order by column desc: 按指定列降序排序
# limit n: 限制返回行数
cursor.execute('SELECT * FROM Intuse order by percentage desc limit 5')

# 获取所有结果
# fetchall(): 获取所有查询结果，返回列表
output = cursor.fetchall()

# 打印结果
print(*output, sep="\n")

# 关闭连接
conn.close()
```

#### 4. 获取 SQLite 版本

```python
import sqlite3

try:
    # 连接到临时数据库
    sqlite_Connection = sqlite3.connect('temp.db')
    
    # 创建游标
    conn = sqlite_Connection.cursor()
    print("连接到 SQLite.")
    
    # 查询 SQLite 版本
    # select sqlite_version(): SQLite 内置函数，返回版本信息
    sqlite_select_Query = "select sqlite_version();"
    conn.execute(sqlite_select_Query)
    
    # 获取查询结果
    # fetchall(): 获取所有结果行
    record = conn.fetchall()
    print("SQLite 数据库的版本是 ", record)
    
    # 关闭游标
    conn.close()
    
except sqlite3.Error as error:
    print("连接到 SQLite 出错：", error)
    
finally:
    # 确保连接被关闭
    if (sqlite_Connection):
        sqlite_Connection.close()
        print("关闭 SQLite 连接")
```

### 高级特性

#### 1. 事务处理

```python
import sqlite3

# 连接到数据库
conn = sqlite3.connect('example.db')
cursor = conn.cursor()

try:
    # 开始事务
    # 默认情况下，SQLite 在每条语句后自动提交
    # 使用 BEGIN TRANSACTION 开始显式事务
    cursor.execute("BEGIN TRANSACTION")
    
    # 执行多个操作
    cursor.execute("INSERT INTO users (name, email) VALUES (?, ?)", ("Alice", "alice@example.com"))
    cursor.execute("INSERT INTO users (name, email) VALUES (?, ?)", ("Bob", "bob@example.com"))
    
    # 提交事务
    # commit(): 提交当前事务，使所有更改永久生效
    conn.commit()
    print("事务提交成功")
    
except sqlite3.Error as e:
    # 回滚事务
    # rollback(): 回滚当前事务，撤销所有未提交的更改
    conn.rollback()
    print(f"事务失败，已回滚: {e}")
    
finally:
    # 关闭连接
    conn.close()
```

#### 2. 参数化查询

```python
import sqlite3

# 连接到数据库
conn = sqlite3.connect('example.db')
cursor = conn.cursor()

# 使用参数化查询防止 SQL 注入
# ? 占位符：安全的参数传递方式
name = "Alice"
email = "alice@example.com"

# 插入数据
cursor.execute("INSERT INTO users (name, email) VALUES (?, ?)", (name, email))

# 查询数据
user_id = 1
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
user = cursor.fetchone()

# 批量插入数据
users = [
    ("Charlie", "charlie@example.com"),
    ("David", "david@example.com"),
    ("Eve", "eve@example.com")
]

# executemany(): 批量执行相同的 SQL 语句
cursor.executemany("INSERT INTO users (name, email) VALUES (?, ?)", users)

# 提交更改
conn.commit()
conn.close()
```

#### 3. 错误处理

```python
import sqlite3

# 连接到数据库
conn = sqlite3.connect('example.db')
cursor = conn.cursor()

try:
    # 执行可能失败的操作
    cursor.execute("INSERT INTO non_existent_table (col) VALUES (1)")
    
except sqlite3.OperationalError as e:
    print(f"操作错误: {e}")
    
except sqlite3.IntegrityError as e:
    print(f"完整性错误: {e}")
    
except sqlite3.DatabaseError as e:
    print(f"数据库错误: {e}")
    
finally:
    # 确保连接被关闭
    conn.close()
```

### 数据类型

#### SQLite 支持的数据类型

```python
import sqlite3

conn = sqlite3.connect('data_types.db')
cursor = conn.cursor()

# 创建包含各种数据类型的表
cursor.execute('''
    CREATE TABLE data_types (
        id INTEGER PRIMARY KEY,
        name TEXT,           -- 文本类型
        age INTEGER,         -- 整数类型
        salary REAL,         -- 浮点类型
        is_active BOOLEAN,   -- 布尔类型
        created_date DATE,   -- 日期类型
        data BLOB            -- 二进制大对象
    )
''')

# 插入各种类型的数据
cursor.execute('''
    INSERT INTO data_types (name, age, salary, is_active, created_date, data)
    VALUES (?, ?, ?, ?, ?, ?)
''', ("John Doe", 30, 50000.50, True, "2023-01-01", b'binary_data'))

conn.commit()
conn.close()
```

### 索引和性能优化

#### 创建索引

```python
import sqlite3

conn = sqlite3.connect('performance.db')
cursor = conn.cursor()

# 创建表
cursor.execute('''
    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        username TEXT UNIQUE,
        email TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
''')

# 创建索引提高查询性能
# CREATE INDEX: 创建索引语句
# idx_username: 索引名称
# ON users(username): 在 users 表的 username 列上创建索引
cursor.execute("CREATE INDEX idx_username ON users(username)")

# 在 email 列上创建索引
cursor.execute("CREATE INDEX idx_email ON users(email)")

# 在 created_at 列上创建索引
cursor.execute("CREATE INDEX idx_created_at ON users(created_at)")

conn.commit()
conn.close()
```

#### 查询优化

```python
import sqlite3
import time

conn = sqlite3.connect('performance.db')
cursor = conn.cursor()

# 启用性能统计
# PRAGMA: SQLite 特有的命令，用于配置数据库
# statistics: 启用统计信息收集
cursor.execute("PRAGMA stats")

# 开始计时
start_time = time.time()

# 执行查询
cursor.execute("SELECT * FROM users WHERE username = ?", ("john_doe",))
result = cursor.fetchone()

# 结束计时
end_time = time.time()
print(f"查询耗时: {end_time - start_time:.4f} 秒")

# 查看查询计划
# EXPLAIN QUERY PLAN: 显示查询执行计划
cursor.execute("EXPLAIN QUERY PLAN SELECT * FROM users WHERE username = ?", ("john_doe",))
plan = cursor.fetchall()
print("查询计划:")
for row in plan:
    print(row)

conn.close()
```

### 备份和恢复

#### 数据库备份

```python
import sqlite3
import shutil

def backup_database(source_db, backup_db):
    """备份 SQLite 数据库"""
    try:
        # 简单的文件复制备份
        shutil.copy2(source_db, backup_db)
        print(f"数据库已备份到: {backup_db}")
    except Exception as e:
        print(f"备份失败: {e}")

def backup_using_sqlite(source_db, backup_db):
    """使用 SQLite 备份 API"""
    try:
        # 连接到源数据库
        source_conn = sqlite3.connect(source_db)
        
        # 连接到目标数据库（备份）
        backup_conn = sqlite3.connect(backup_db)
        
        # 使用 SQLite 备份 API
        # backup: 备份整个数据库
        source_conn.backup(backup_conn)
        
        print(f"数据库已备份到: {backup_db}")
        
    except sqlite3.Error as e:
        print(f"备份失败: {e}")
        
    finally:
        # 关闭连接
        if 'source_conn' in locals():
            source_conn.close()
        if 'backup_conn' in locals():
            backup_conn.close()

# 使用示例
backup_database('example.db', 'example_backup.db')
backup_using_sqlite('example.db', 'example_sqlite_backup.db')
```

### 命令行工具使用

#### 基本命令行操作

```bash
# 启动 SQLite 命令行工具
# sqlite3: 启动 SQLite 命令行界面
# database.db: 要打开的数据库文件（可选）
sqlite3 database.db

# 在命令行中执行 SQL 命令
sqlite> .tables                    # 显示所有表
sqlite> .schema table_name         # 显示表结构
sqlite> .mode column               # 设置输出模式为列格式
sqlite> .headers on                # 显示列标题
sqlite> SELECT * FROM users;       # 查询数据
sqlite> .exit                      # 退出

# 从文件执行 SQL 脚本
sqlite3 database.db < script.sql

# 导出数据到文件
sqlite3 database.db ".output data.txt" "SELECT * FROM users;"

# 导入数据从文件
sqlite3 database.db ".import data.csv users"
```

#### 常用命令行命令

```bash
# 设置输出格式
.mode qbox          # 查询框格式
.timer on           # 启用计时器

# 设置参数
.param set $label 'q87'  # 设置参数值

# 查询 JSON 数据
SELECT rowid, x->>$label FROM data1 WHERE x->>$label IS NOT NULL;

# 显示数据库信息
.databases          # 显示连接的数据库
.tables             # 显示所有表
.indexes            # 显示所有索引
.schema             # 显示数据库架构

# 性能分析
.explain            # 显示查询计划
.stats              # 显示统计信息
```

### 最佳实践

#### 1. 连接管理

```python
import sqlite3
from contextlib import contextmanager

@contextmanager
def get_db_connection(db_path):
    """数据库连接上下文管理器"""
    conn = None
    try:
        # 连接到数据库
        conn = sqlite3.connect(db_path)
        # 设置行工厂，返回字典格式的结果
        conn.row_factory = sqlite3.Row
        yield conn
    except sqlite3.Error as e:
        print(f"数据库错误: {e}")
        raise
    finally:
        # 确保连接被关闭
        if conn:
            conn.close()

# 使用示例
with get_db_connection('example.db') as conn:
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()
    
    # 以字典形式访问结果
    for user in users:
        print(f"ID: {user['id']}, Name: {user['name']}")
```

#### 2. 错误处理和重试

```python
import sqlite3
import time

def execute_with_retry(cursor, sql, params=None, max_retries=3):
    """带重试机制的 SQL 执行"""
    for attempt in range(max_retries):
        try:
            if params:
                cursor.execute(sql, params)
            else:
                cursor.execute(sql)
            return True
        except sqlite3.OperationalError as e:
            if "database is locked" in str(e) and attempt < max_retries - 1:
                # 数据库被锁定，等待后重试
                time.sleep(0.1 * (2 ** attempt))  # 指数退避
                continue
            else:
                raise
    return False

# 使用示例
conn = sqlite3.connect('example.db')
cursor = conn.cursor()

try:
    execute_with_retry(cursor, "INSERT INTO users (name) VALUES (?)", ("John",))
    conn.commit()
except sqlite3.Error as e:
    print(f"操作失败: {e}")
    conn.rollback()
finally:
    conn.close()
```

#### 3. 性能优化配置

```python
import sqlite3

def optimize_sqlite_connection(conn):
    """优化 SQLite 连接配置"""
    cursor = conn.cursor()
    
    # 启用外键约束
    cursor.execute("PRAGMA foreign_keys = ON")
    
    # 设置 WAL 模式（Write-Ahead Logging）
    cursor.execute("PRAGMA journal_mode = WAL")
    
    # 设置同步模式为 NORMAL（平衡性能和数据安全）
    cursor.execute("PRAGMA synchronous = NORMAL")
    
    # 设置缓存大小（以页为单位）
    cursor.execute("PRAGMA cache_size = -2000")  # 2000KB 缓存
    
    # 设置临时存储位置为内存
    cursor.execute("PRAGMA temp_store = MEMORY")
    
    # 设置页面大小
    cursor.execute("PRAGMA page_size = 4096")
    
    print("SQLite 连接已优化")

# 使用示例
conn = sqlite3.connect('optimized.db')
optimize_sqlite_connection(conn)

# 执行操作...

conn.close()
```

### 总结

SQLite 是一个功能强大、轻量级的嵌入式数据库引擎，特别适合以下场景：

**适用场景**：
- 移动应用和桌面应用
- 小型网站和原型开发
- 配置文件和缓存存储
- 测试和开发环境
- 嵌入式系统和 IoT 设备

**核心优势**：
- 零配置，开箱即用
- 单个文件包含整个数据库
- 跨平台兼容性好
- 性能优秀，资源占用少
- 完整的 SQL 支持
- 事务性和 ACID 合规

**限制**：
- 不适合高并发写操作
- 缺乏用户管理和权限控制
- 网络访问需要额外包装
- 数据库大小有限制（虽然很大）

对于需要简单、可靠、轻量级数据库解决方案的项目，SQLite 是一个理想的选择。它提供了企业级数据库的大部分功能，同时保持了极简的部署和维护要求。

---

*本文档基于 SQLite 最新版本编写，适用于 Python 3.8+ 环境*