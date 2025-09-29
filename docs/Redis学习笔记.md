# Redis 内存数据结构存储学习笔记

## What - Redis 是什么？

**Redis** 是一个开源的、基于内存的数据结构存储系统，可以用作数据库、缓存和消息代理。它支持多种数据结构，如字符串、哈希、列表、集合、有序集合等，并提供持久化功能。

### 核心特性
- **内存存储**：数据主要存储在内存中，读写速度极快
- **数据结构丰富**：支持多种高级数据结构
- **持久化**：支持 RDB 快照和 AOF 日志两种持久化方式
- **高可用**：支持主从复制和哨兵模式
- **分布式**：支持集群模式，可水平扩展
- **原子操作**：所有操作都是原子性的

## Why - 为什么需要 Redis？

### 主要应用场景

1. **缓存系统**
   - 减轻数据库压力
   - 提高应用响应速度
   - 存储热点数据

2. **会话存储**
   - 分布式会话管理
   - 用户登录状态存储

3. **消息队列**
   - 异步任务处理
   - 实时消息推送

4. **实时排行榜**
   - 游戏积分排行
   - 商品热度排行

5. **计数器系统**
   - 网站访问统计
   - 用户行为计数

6. **地理位置服务**
   - 附近的人/地点
   - 地理围栏

### 解决的问题

- **性能瓶颈**：解决传统数据库的 I/O 瓶颈
- **并发问题**：提供原子操作避免竞态条件
- **数据一致性**：在分布式系统中保持数据一致性
- **实时性要求**：满足高实时性应用需求

## Where - 有哪些替代方案？

### 主要替代方案

1. **Memcached**
   - 优点：简单、轻量、性能好
   - 缺点：只支持简单的键值对，不支持持久化

2. **Apache Cassandra**
   - 优点：分布式、高可用、可扩展
   - 缺点：配置复杂，学习曲线陡峭

3. **MongoDB**
   - 优点：文档型数据库，支持复杂查询
   - 缺点：内存使用不如 Redis 高效

4. **Apache Kafka**
   - 优点：高吞吐量消息系统
   - 缺点：主要用于消息队列，功能相对单一

5. **etcd**
   - 优点：强一致性，适合配置管理
   - 缺点：功能相对简单

### 选择 Redis 的理由

- **性能卓越**：基于内存，读写速度极快
- **功能丰富**：支持多种数据结构和高级功能
- **社区活跃**：有大量的文档和第三方库
- **成熟稳定**：经过多年生产环境验证
- **生态完善**：与各种编程语言和框架集成良好

## How - 核心概念与使用

### 核心数据结构

#### 1. 字符串（Strings）
最基本的键值对存储

```python
import redis

# 创建Redis客户端连接
# decode_responses=True: 自动将字节数据解码为字符串，避免手动处理编码问题
r = redis.Redis(decode_responses=True)

# 设置和获取字符串
# set(key, value): 设置键值对，key为键名，value为值
r.set('username', 'john_doe')
# get(key): 获取指定键的值
username = r.get('username')
print(username)  # 输出: john_doe

# 设置带过期时间的键
# setex(key, seconds, value): 设置键值对并指定过期时间（秒）
# key: 键名，seconds: 过期时间（秒），value: 值
r.setex('session_token', 3600, 'abc123')

# 自增操作
r.set('counter', 0)
# incr(key): 将键的值增加1，返回增加后的值
r.incr('counter')  # 1
# incrby(key, amount): 将键的值增加指定数量，返回增加后的值
r.incrby('counter', 5)  # 6
```

#### 2. 哈希（Hashes）
存储对象结构的数据

```python
# 存储用户信息
user_data = {
    'name': 'Alice',
    'age': '30',
    'email': 'alice@example.com'
}

# hset(key, mapping=dict): 批量设置哈希字段
# key: 哈希键名，mapping: 字段字典 {field: value, ...}
r.hset('user:1001', mapping=user_data)

# 获取单个字段
# hget(key, field): 获取哈希中指定字段的值
# key: 哈希键名，field: 字段名
name = r.hget('user:1001', 'name')
print(name)  # 输出: Alice

# 获取所有字段
# hgetall(key): 获取哈希中所有字段和值，返回字典
user_info = r.hgetall('user:1001')
print(user_info)  # 输出: {'name': 'Alice', 'age': '30', 'email': 'alice@example.com'}
```

#### 3. 列表（Lists）
有序的字符串集合

```python
# 消息队列示例
# 从左侧推入消息
# lpush(key, *values): 将一个或多个值插入到列表头部
# key: 列表键名，*values: 要插入的值（可变参数）
r.lpush('message_queue', 'message1')
r.lpush('message_queue', 'message2')

# 从右侧弹出消息
# rpop(key): 移除并返回列表的最后一个元素
message = r.rpop('message_queue')
print(message)  # 输出: message1

# 获取列表范围
# lrange(key, start, stop): 返回列表中指定区间内的元素
# key: 列表键名，start: 起始索引（0开始），stop: 结束索引（-1表示最后一个）
messages = r.lrange('message_queue', 0, -1)
print(messages)  # 输出: ['message2']
```

#### 4. 集合（Sets）
无序的唯一元素集合

```python
# 标签系统示例
# sadd(key, *members): 向集合添加一个或多个成员
# key: 集合键名，*members: 要添加的成员（可变参数）
r.sadd('article:1001:tags', 'python', 'redis', 'database')
r.sadd('article:1002:tags', 'python', 'web', 'framework')

# 获取集合所有成员
# smembers(key): 返回集合中的所有成员
tags = r.smembers('article:1001:tags')
print(tags)  # 输出: {'python', 'redis', 'database'}

# 求交集（共同标签）
# sinter(*keys): 返回给定所有集合的交集
# *keys: 集合键名列表（可变参数）
common_tags = r.sinter('article:1001:tags', 'article:1002:tags')
print(common_tags)  # 输出: {'python'}
```

#### 5. 有序集合（Sorted Sets）
带分数的有序集合

```python
# 排行榜示例
# zadd(key, mapping): 向有序集合添加一个或多个成员，或更新已存在成员的分数
# key: 有序集合键名，mapping: 成员分数字典 {member: score, ...}
r.zadd('leaderboard', {
    'player1': 1000,
    'player2': 1500,
    'player3': 800
})

# 获取前3名
# zrevrange(key, start, stop, withscores): 返回有序集中指定区间内的成员，通过索引，分数从高到低
# key: 有序集合键名，start: 起始索引，stop: 结束索引，withscores: 是否返回分数
leaders = r.zrevrange('leaderboard', 0, 2, withscores=True)
print(leaders)  # 输出: [('player2', 1500.0), ('player1', 1000.0), ('player3', 800.0)]

# 增加分数
# zincrby(key, amount, member): 为有序集合的成员增加分数
# key: 有序集合键名，amount: 要增加的分数，member: 成员名
r.zincrby('leaderboard', 200, 'player1')
```

### 高级功能

#### 1. 发布订阅（Pub/Sub）

```python
import threading
import time

def subscriber():
    """订阅者"""
    # pubsub(): 创建发布订阅对象
    pubsub = r.pubsub()
    # subscribe(*channels): 订阅一个或多个频道
    # *channels: 频道名称列表（可变参数）
    pubsub.subscribe('news_channel')
    
    # listen(): 监听订阅的消息，返回生成器
    for message in pubsub.listen():
        # message类型：'message'表示普通消息，'subscribe'表示订阅成功
        if message['type'] == 'message':
            print(f"收到消息: {message['data']}")

# 启动订阅者线程
thread = threading.Thread(target=subscriber)
thread.daemon = True  # 设置为守护线程，主线程结束时自动退出
thread.start()

# 发布消息
time.sleep(1)  # 等待订阅者准备好
# publish(channel, message): 向指定频道发布消息
# channel: 频道名称，message: 消息内容
r.publish('news_channel', 'Hello, Redis Pub/Sub!')
```

#### 2. 事务（Transactions）

```python
# 使用管道执行事务
# pipeline(): 创建管道对象，用于批量执行命令
pipe = r.pipeline()

try:
    # watch(*keys): 监视一个或多个键，如果在事务执行前被修改，则事务失败
    pipe.watch('balance')
    current_balance = int(pipe.get('balance') or 0)
    
    if current_balance >= 100:
        # multi(): 开启事务模式，后续命令将进入事务队列
        pipe.multi()
        # decrby(key, amount): 将键的值减少指定数量
        pipe.decrby('balance', 100)
        # incrby(key, amount): 将键的值增加指定数量
        pipe.incrby('savings', 100)
        # execute(): 执行事务中的所有命令
        pipe.execute()
        print("转账成功")
    else:
        print("余额不足")
        # unwatch(): 取消对所有键的监视
        pipe.unwatch()
except redis.WatchError:
    print("数据被其他客户端修改，操作失败")
```

#### 3. Lua 脚本

```python
# 执行 Lua 脚本实现原子操作
lua_script = """
local current = redis.call('GET', KEYS[1])
if current then
    current = tonumber(current)
    if current >= tonumber(ARGV[1]) then
        redis.call('DECRBY', KEYS[1], ARGV[1])
        redis.call('INCRBY', KEYS[2], ARGV[1])
        return 'SUCCESS'
    else
        return 'INSUFFICIENT_FUNDS'
    end
else
    return 'ACCOUNT_NOT_FOUND'
end
"""

# register_script(script): 注册Lua脚本，返回可执行对象
# script: Lua脚本字符串
script = r.register_script(lua_script)
# 执行脚本：keys参数传递给KEYS数组，args参数传递给ARGV数组
# keys: 键名列表，args: 参数列表
result = script(keys=['balance', 'savings'], args=[100])
print(result)  # 输出: SUCCESS
```

### Python 客户端使用

#### 基本连接

```python
import redis

# 基本连接
r = redis.Redis(
    host='localhost',      # Redis服务器主机名
    port=6379,            # Redis服务器端口
    db=0,                 # 数据库编号（0-15）
    decode_responses=True,  # 自动解码为字符串，避免手动处理编码
    password='your_password'  # Redis认证密码（如果设置了密码）
)

# 测试连接
# ping(): 测试与Redis服务器的连接，成功返回True
print(r.ping())  # 输出: True
```

#### 连接池

```python
from redis import ConnectionPool

# 创建连接池
pool = ConnectionPool(
    host='localhost',        # Redis服务器主机名
    port=6379,              # Redis服务器端口
    db=0,                   # 数据库编号
    max_connections=20,     # 最大连接数，控制并发连接数量
    decode_responses=True   # 自动解码为字符串
)

# 使用连接池
# connection_pool: 使用指定的连接池创建Redis客户端
r = redis.Redis(connection_pool=pool)
```

#### 异步客户端

```python
import redis.asyncio as redis
import asyncio

async def async_example():
    # from_url(url): 从URL创建异步Redis客户端
    # URL格式: redis://[username:password@]host:port[/db]
    r = await redis.from_url("redis://localhost")
    
    # 异步设置和获取
    # set(key, value): 异步设置键值对
    await r.set("async_key", "async_value")
    # get(key): 异步获取键值
    value = await r.get("async_key")
    print(value)  # 输出: async_value

# 运行异步示例
asyncio.run(async_example())
```

### 配置和部署

#### Docker 部署

```bash
# 启动 Redis 服务器
# -d: 后台运行容器
# --name: 指定容器名称
# -p: 端口映射（主机端口:容器端口）
docker run -d --name redis-server \
  -p 6379:6379 \
  redis:latest

# 带密码启动
# --requirepass: 设置Redis认证密码
docker run -d --name redis-server \
  -p 6379:6379 \
  redis:latest \
  --requirepass "your_password"

# 持久化配置
# -v: 挂载数据卷（主机目录:容器目录）
# --appendonly yes: 启用AOF持久化
docker run -d --name redis-server \
  -p 6379:6379 \
  -v /path/to/redis/data:/data \
  redis:latest \
  --appendonly yes
```

#### 配置文件示例

```conf
# redis.conf

# 基本配置
bind 127.0.0.1          # 绑定的IP地址，127.0.0.1表示只允许本地连接
port 6379               # Redis服务端口

# 认证
requirepass your_password  # Redis认证密码，客户端连接时需要提供

# 持久化
save 900 1              # 900秒（15分钟）内至少有1个键被修改，则保存
save 300 10             # 300秒（5分钟）内至少有10个键被修改，则保存
save 60 10000           # 60秒内至少有10000个键被修改，则保存

appendonly yes          # 启用AOF（Append Only File）持久化
appendfilename "appendonly.aof"  # AOF文件名

# 内存管理
maxmemory 1gb           # 最大内存限制为1GB
maxmemory-policy allkeys-lru  # 内存满时的淘汰策略：所有键使用LRU算法

# 日志
loglevel notice         # 日志级别：debug/verbose/notice/warning
logfile ""              # 日志文件路径，空字符串表示标准输出

# 客户端连接
maxclients 10000        # 最大客户端连接数
timeout 300             # 客户端空闲超时时间（秒），0表示不超时
```

### 最佳实践

#### 1. 键命名规范

```python
# 使用冒号分隔命名空间
user_key = "user:1001:profile"
session_key = "session:abc123"
article_key = "article:2024:latest"

# 避免使用特殊字符
# 推荐：user:1001:orders
# 不推荐：user_1001_orders
```

#### 2. 内存优化

```python
# 使用哈希存储对象
user_data = {
    'id': '1001',
    'name': 'John',
    'email': 'john@example.com'
}
r.hset('user:1001', mapping=user_data)

# 使用压缩列表优化小对象
# 在配置文件中设置：
# hash-max-ziplist-entries 512
# hash-max-ziplist-value 64
```

#### 3. 性能优化

```python
# 使用管道批量操作
# pipeline(): 创建管道对象，用于批量执行命令
pipe = r.pipeline()

for i in range(1000):
    # 将命令添加到管道队列，不立即执行
    pipe.set(f"key:{i}", f"value:{i}")

# execute(): 一次性执行管道中的所有命令
pipe.execute()

# 使用 MGET 批量获取
# mget(keys): 批量获取多个键的值
# keys: 键名列表
keys = [f"key:{i}" for i in range(10)]
values = r.mget(keys)
```

#### 4. 错误处理

```python
try:
    # ping(): 测试连接，成功返回True
    r.ping()
except redis.ConnectionError as e:
    # 连接错误：无法连接到Redis服务器
    print(f"连接错误: {e}")
except redis.TimeoutError as e:
    # 超时错误：操作超时
    print(f"超时错误: {e}")
except redis.RedisError as e:
    # 其他Redis相关错误
    print(f"Redis错误: {e}")
```

### 监控和维护

#### 常用监控命令

```python
# 获取 Redis 信息
# info(section=None): 获取Redis服务器信息
# section: 指定信息部分，None表示获取所有信息
info = r.info()
print(f"已使用内存: {info['used_memory_human']}")
print(f"连接数: {info['connected_clients']}")
print(f"命中率: {info['keyspace_hits'] / (info['keyspace_hits'] + info['keyspace_misses']):.2%}")

# 获取键空间信息
# info('keyspace'): 获取数据库键空间相关信息
keyspace = r.info('keyspace')
print(keyspace)

# 慢查询日志
# slowlog_get(n): 获取最近的n条慢查询记录
slowlog = r.slowlog_get(10)
for log in slowlog:
    print(f"命令: {log['command']}, 执行时间: {log['duration']} 微秒")
```

### 总结

Redis 是一个功能强大、性能卓越的内存数据结构存储系统，特别适合用作缓存、会话存储、消息队列等场景。通过合理的数据结构选择和配置优化，可以构建出高性能、高可用的应用系统。

**核心优势**：
- 极快的读写性能
- 丰富的数据结构
- 原子操作保证
- 完善的持久化机制
- 强大的集群支持

对于需要高性能数据访问的现代应用来说，Redis 是一个不可或缺的基础设施组件。

---

*本文档基于 Redis 8.x 和 redis-py 4.x 版本编写，适用于 Python 3.7+ 环境*