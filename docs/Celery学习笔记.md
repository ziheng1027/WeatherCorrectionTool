# Celery 分布式任务队列学习笔记

## What - Celery 是什么？

**Celery** 是一个基于 Python 的分布式任务队列系统，专门用于处理异步任务和定时任务。它允许你将耗时的操作（如数据处理、邮件发送、文件处理等）从主应用程序中分离出来，在后台异步执行。

### 核心特性
- **分布式架构**：支持多台机器上的任务分发和执行
- **异步执行**：任务在后台运行，不阻塞主程序
- **定时任务**：支持周期性任务调度
- **结果存储**：可以存储任务执行结果
- **任务监控**：提供任务状态跟踪和监控

## Why - 为什么需要 Celery？

### 主要应用场景

1. **Web 应用中的耗时操作**
   - 图片处理、视频转码
   - 大数据处理
   - 邮件发送
   - 文件导入导出

2. **分布式计算**
   - 多台机器并行处理任务
   - 负载均衡

3. **定时任务**
   - 数据备份
   - 定时报表生成
   - 缓存清理

### 解决的问题

- **用户体验**：避免用户长时间等待
- **系统性能**：释放主线程，提高响应速度
- **可靠性**：任务失败可以重试
- **可扩展性**：轻松扩展工作节点

## Where - 有哪些替代方案？

### 主要替代方案

1. **RQ (Redis Queue)**
   - 优点：简单易用，基于 Redis
   - 缺点：功能相对简单

2. **Dramatiq**
   - 优点：性能更好，API 更现代化
   - 缺点：生态系统不如 Celery 成熟

3. **Huey**
   - 优点：轻量级，支持 SQLite
   - 缺点：功能相对有限

4. **Apache Airflow**
   - 优点：强大的工作流管理
   - 缺点：配置复杂，更适合数据管道

### 选择 Celery 的理由

- **成熟稳定**：经过多年生产环境验证
- **功能丰富**：支持各种消息代理和结果后端
- **社区活跃**：有大量的文档和第三方库
- **集成性好**：与 Django、Flask 等框架无缝集成

## How - 核心概念与使用

### 核心组件

1. **Celery Application** - 应用实例
2. **Broker** - 消息代理（Redis、RabbitMQ）
3. **Worker** - 任务执行者
4. **Result Backend** - 结果存储
5. **Task** - 任务定义

### 基本使用流程

#### 1. 创建 Celery 应用

```python
# celery_app.py
from celery import Celery

# 创建 Celery 应用实例
app = Celery(
    'myapp',                    # 应用名称，用于日志和监控
    broker='redis://localhost:6379/0',      # 消息代理地址，Redis格式：redis://host:port/db
    backend='redis://localhost:6379/0',     # 结果后端地址，存储任务执行结果
    include=['myapp.tasks']     # 包含的任务模块列表，Celery会自动发现这些模块中的任务
)

# 配置应用
app.conf.update(
    task_serializer='json',     # 任务序列化格式，支持 json/pickle/yaml/msgpack
    result_serializer='json',   # 结果序列化格式
    accept_content=['json'],    # 接受的内容类型白名单
    timezone='Asia/Shanghai',   # 时区设置
    enable_utc=True,            # 启用UTC时间，建议设为True
)
```

#### 2. 定义任务

```python
from .celery_app import app

@app.task  # @app.task 装饰器将普通函数标记为Celery任务
def add(x, y):
    """简单的加法任务"""
    return x + y

@app.task(bind=True)  # bind=True 允许任务访问self（任务实例），用于进度跟踪
def long_running_task(self, data):
    """长时间运行的任务，支持进度跟踪"""
    total_items = len(data)
    
    for i, item in enumerate(data):
        # 处理每个项目
        process_item(item)
        
        # 更新进度 - 让前端可以实时看到任务进度
        self.update_state(
            state='PROGRESS',  # 任务状态：PROGRESS表示进行中
            meta={
                'current': i + 1,        # 当前处理的项目序号
                'total': total_items,    # 总项目数
                'status': f'处理中 {i+1}/{total_items}'  # 状态描述
            }
        )
    
    return {'status': '完成', 'processed': total_items}  # 任务完成返回结果
```

#### 3. 启动 Worker

```bash
# 启动 Celery worker
# celery -A <应用模块>:<应用实例> worker --loglevel=<日志级别>
celery -A myapp.celery_app:app worker --loglevel=info

# 启动 Celery beat（定时任务）
# beat 负责调度定时任务，需要单独启动
celery -A myapp.celery_app:app beat --loglevel=info

# 常用启动参数说明：
# -A, --app: 指定Celery应用模块路径
# worker: 启动工作进程
# beat: 启动定时任务调度器  
# --loglevel: 日志级别 (debug/info/warning/error/critical)
# --concurrency: 并发工作进程数，默认CPU核心数
# --queues: 指定监听的队列，多个队列用逗号分隔
# --hostname: 工作节点主机名，用于监控
```

#### 4. 调用任务

```python
from .tasks import add, long_running_task

# 异步调用任务 - .delay() 是 .apply_async() 的快捷方式
result = add.delay(4, 4)  # 立即返回 AsyncResult 对象，不等待任务完成

# 检查任务状态
if result.ready():  # 检查任务是否完成（成功/失败）
    print(f"任务结果: {result.get()}")  # 获取任务结果，如果任务未完成会阻塞等待

# 调用长时间任务并跟踪进度
task_result = long_running_task.delay(large_dataset)  # 返回任务ID，用于后续查询进度

# 其他调用方式：
# result = add.apply_async(args=[4, 4])  # 完整调用方式，支持更多参数
# result = add.apply_async(kwargs={'x': 4, 'y': 4})  # 关键字参数方式
# result = add.apply_async(countdown=10)  # 延迟10秒执行
# result = add.apply_async(eta=datetime.datetime.now() + datetime.timedelta(seconds=10))  # 指定执行时间
```

#### 5. 查询任务状态

```python
from celery.result import AsyncResult

def get_task_status(task_id):
    """查询任务状态 - 前端API调用此函数获取任务进度"""
    result = AsyncResult(task_id)  # 根据任务ID创建AsyncResult对象
    
    # 任务状态说明：
    # PENDING: 任务已发送但未开始执行（排队中）
    # STARTED: 任务已开始执行（需要task_track_started=True）
    # PROGRESS: 任务执行中，有进度信息
    # SUCCESS: 任务成功完成
    # FAILURE: 任务执行失败
    # RETRY: 任务正在重试
    # REVOKED: 任务已被取消
    
    if result.state == 'PENDING':
        return {'status': '排队中'}
    elif result.state == 'PROGRESS':
        return result.info  # 返回任务进度信息（在任务中通过update_state设置）
    elif result.state == 'SUCCESS':
        return {'status': '完成', 'result': result.result}  # 返回任务执行结果
    elif result.state == 'FAILURE':
        return {'status': '失败', 'error': str(result.info)}  # 返回错误信息
    else:
        return {'status': result.state}  # 其他状态直接返回
```

### 高级特性

#### 1. 任务链（Chain）

```python
from celery import chain

# 任务链：A -> B -> C（前一个任务的输出作为后一个任务的输入）
chain_result = chain(
    task_a.s(1),  # .s() 创建任务签名，参数1传递给task_a
    task_b.s(),   # task_b接收task_a的输出作为输入
    task_c.s()    # task_c接收task_b的输出作为输入
).apply_async()   # 异步执行整个任务链

# 等价写法：
# result = (task_a.s(1) | task_b.s() | task_c.s()).apply_async()
# 使用 | 操作符连接任务
```

#### 2. 任务组（Group）

```python
from celery import group

# 并行执行多个任务（所有任务同时执行，无依赖关系）
group_result = group(
    task_a.s(i) for i in range(10)  # 生成10个任务签名，每个任务接收不同的参数
).apply_async()  # 异步执行任务组

# 任务组特点：
# - 所有任务并行执行
# - 任务之间无依赖关系
# - 返回所有任务的结果列表
# - 适合批量处理独立任务
```

#### 3. 和弦（Chord）

```python
from celery import chord

# 和弦：并行执行任务组，所有任务完成后执行回调任务
chord_result = chord(
    [task_a.s(i) for i in range(5)],  # 任务组：5个并行任务
    callback_task.s()                 # 回调任务：接收任务组所有结果的列表作为输入
).apply_async()

# 和弦特点：
# - 先并行执行任务组
# - 所有任务完成后，将结果列表传递给回调任务
# - 回调任务接收一个参数：任务组所有结果的列表
# - 适合Map-Reduce模式

# 等价写法：
# result = (group([task_a.s(i) for i in range(5)]) | callback_task.s()).apply_async()
```

#### 4. 定时任务

```python
from celery.schedules import crontab

app.conf.beat_schedule = {
    'daily-backup': {  # 定时任务名称，用于标识
        'task': 'tasks.backup_database',  # 要执行的任务路径
        'schedule': crontab(hour=2, minute=0),  # 调度时间：每天凌晨2点
        # crontab参数说明：
        # minute: 分钟 (0-59)
        # hour: 小时 (0-23)  
        # day_of_week: 星期几 (0-6, 0=周日)
        # day_of_month: 日期 (1-31)
        # month_of_year: 月份 (1-12)
    },
    'every-5-minutes': {
        'task': 'tasks.check_system',
        'schedule': 300.0,  # 每300秒（5分钟）执行一次
        # 其他可选参数：
        # 'args': (arg1, arg2),  # 任务参数
        # 'kwargs': {'key': 'value'},  # 任务关键字参数
        # 'options': {'queue': 'priority'},  # 任务选项
    },
}

# 其他调度方式：
# schedule = 10.0  # 每10秒执行一次
# schedule = crontab(minute='*/15')  # 每15分钟执行一次
# schedule = crontab(hour=7, minute=30, day_of_week=1)  # 每周一7:30执行
```

### 配置示例

```python
# celery_config.py

# 消息代理配置
broker_url = 'redis://localhost:6379/0'  # Redis作为消息代理
# 其他broker选项：
# broker_url = 'amqp://guest:guest@localhost:5672//'  # RabbitMQ
# broker_url = 'sqs://'  # AWS SQS

# 结果后端配置
result_backend = 'redis://localhost:6379/0'  # Redis存储任务结果
# 其他backend选项：
# result_backend = 'db+sqlite:///results.db'  # SQLite数据库
# result_backend = 'rpc://'  # RPC后端

# 序列化设置
task_serializer = 'json'        # 任务消息序列化格式
result_serializer = 'json'      # 结果序列化格式
accept_content = ['json']       # 接受的内容类型白名单（安全考虑）

# 时区设置
timezone = 'Asia/Shanghai'      # 应用时区
enable_utc = True               # 启用UTC时间，建议生产环境设为True

# 任务执行设置
task_track_started = True       # 跟踪任务开始状态（在任务状态中添加STARTED状态）
task_time_limit = 300           # 任务硬超时时间（秒），超过此时间强制终止任务
task_soft_time_limit = 240      # 任务软超时时间（秒），超过此时间发送SIGUSR1信号

task_ignore_result = False      # 是否忽略任务结果（True=不存储结果，节省空间）
task_store_eager_result = True  # 是否存储eager模式下的任务结果

# Worker进程设置
worker_prefetch_multiplier = 1  # 预取任务倍数（每个worker预取的任务数 = 并发数 × 此值）
worker_max_tasks_per_child = 1000  # 每个子进程执行的最大任务数，达到后重启进程（防止内存泄漏）
worker_disable_rate_limits = False  # 是否禁用速率限制

# 任务路由设置
task_routes = {
    'tasks.import_data': {'queue': 'import'},     # 数据导入任务路由到import队列
    'tasks.send_email': {'queue': 'email'},       # 邮件发送任务路由到email队列
    'tasks.process_image': {'queue': 'image'},    # 图片处理任务路由到image队列
}

# 任务重试设置
task_default_retry_delay = 180  # 默认重试延迟（秒）
task_max_retries = 3            # 最大重试次数

# 安全设置
task_serializer = 'json'        # 使用json而不是pickle（安全考虑）
result_serializer = 'json'
accept_content = ['json']       # 只接受json格式的消息
```

### 最佳实践

1. **任务设计**
   - 任务应该是幂等的（可重复执行）
   - 避免在任务中存储状态
   - 合理设置超时时间

2. **错误处理**
   - 使用重试机制
   - 记录详细的错误信息
   - 设置合理的重试策略

3. **性能优化**
   - 合理设置并发数
   - 使用连接池
   - 监控系统资源

4. **监控和日志**
   - 使用 Flower 监控任务
   - 记录详细的执行日志
   - 设置告警机制

### 总结

Celery 是一个功能强大的分布式任务队列系统，特别适合处理异步任务和定时任务。通过合理的架构设计和配置，可以构建出高性能、高可用的后台任务处理系统。对于需要处理大量后台任务的 Web 应用来说，Celery 是一个不可或缺的工具。

---

*本文档基于 Celery 5.5.2 版本编写，适用于 Python 3.7+ 环境*