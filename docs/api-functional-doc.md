# WeatherCorrection 后端功能接口文档

> 共 **62** 个接口，按模块层级组织。
> 前端覆盖情况标注在每个接口右侧。

---

## 1. 根路由

| 方法 | 路径 | 说明 | 前端覆盖 |
|------|------|------|----------|
| GET | `/` | 欢迎信息 | - (无需覆盖) |

---

## 2. 设置模块 `/settings`

| 方法 | 路径 | 说明 | 前端覆盖 |
|------|------|------|----------|
| PUT | `/settings/source-dirs` | 更新数据源目录路径 (station_data_dir, grid_data_dir, station_info_path, dem_data_path) | ✅ |
| GET | `/settings/all-config-info` | 获取全部配置信息 | ✅ |

---

## 3. 数据导入模块 `/data-import`

| 方法 | 路径 | 说明 | 前端覆盖 |
|------|------|------|----------|
| GET | `/data-import/check` | 检查可导入文件数量及文件列表 | ✅ |
| POST | `/data-import/start` | 启动数据导入任务 | ✅ |
| GET | `/data-import/global/pending_files` | 获取全部待导入文件 | ❌ |
| GET | `/data-import/global/processing_files` | 获取全部导入中文件 (含进度) | ❌ |
| GET | `/data-import/global/completed_files` | 获取全部已完成导入文件 | ❌ |
| GET | `/data-import/global/failed_files` | 获取全部导入失败文件 | ❌ |

---

## 4. 数据处理模块 `/data-process`

| 方法 | 路径 | 说明 | 前端覆盖 |
|------|------|------|----------|
| POST | `/data-process/start` | 启动数据预处理任务 (elements, start_year, end_year, num_workers) | ✅ |
| GET | `/data-process/global/pending` | 获取全部待处理任务 | ❌ |
| GET | `/data-process/global/processing` | 获取全部处理中任务 | ❌ |
| GET | `/data-process/global/completed` | 获取全部已完成处理任务 | ❌ |
| GET | `/data-process/global/failed` | 获取全部处理失败任务 | ❌ |

---

## 5. 数据预览模块 `/data-preview`

| 方法 | 路径 | 说明 | 前端覆盖 |
|------|------|------|----------|
| GET | `/data-preview/stations` | 获取全部站点名称及坐标 | ✅ |
| POST | `/data-preview/station-data` | 获取站点时序数据 (折线图) | ✅ |
| POST | `/data-preview/grid-data` | 获取指定时刻网格数据 (热力图) | ✅ |
| POST | `/data-preview/grid-time-series` | 提交网格时序提取任务 (后台) | ✅ |
| GET | `/data-preview/grid-time-series/status/{task_id}` | 查询网格时序任务状态 | ✅ |
| POST | `/data-preview/export-grid-data` | 导出网格数据为 ZIP (NetCDF) | ❌ |
| POST | `/data-preview/export-grid-images` | 导出网格数据为 PNG 图片 ZIP | ❌ |
| GET | `/data-preview/export-grid-data/status/{task_id}` | 查询导出任务状态 | ❌ |
| GET | `/data-preview/download-export/{task_id}` | 下载导出的 ZIP 文件 | ❌ |

---

## 6. 模型训练模块 `/model-train`

| 方法 | 路径 | 说明 | 前端覆盖 |
|------|------|------|----------|
| GET | `/model-train/model-config/{model_name}/{element}` | 获取模型超参数配置 | ❌ |
| POST | `/model-train/model-config/{model_name}/{element}` | 更新模型超参数配置 | ❌ |
| POST | `/model-train/start` | 启动模型训练任务 (XGBoost/LightGBM) | ✅ |
| POST | `/model-train/get-losses` | 获取训练/验证损失曲线数据 | ❌ |
| POST | `/model-train/get-metrics-testset-all` | 获取全部测试站点评估指标 | ❌ |
| GET | `/model-train/global/pending` | 获取全部待训练子任务 | ❌ |
| GET | `/model-train/global/processing` | 获取全部训练中子任务 | ❌ |
| GET | `/model-train/global/completed` | 获取全部已完成训练子任务 | ❌ |
| GET | `/model-train/global/failed` | 获取全部训练失败子任务 | ❌ |
| GET | `/model-train/save-model-record` | 保存模型记录到数据库 | ❌ |
| DELETE | `/model-train/delete-model-record/{task_id}` | 删除模型记录及关联训练任务 | ❌ |

---

## 7. 多站点评估模块 `/model-train/multi-station-eval`

| 方法 | 路径 | 说明 | 前端覆盖 |
|------|------|------|----------|
| POST | `/model-train/multi-station-eval/start` | 启动多站点批量评估任务 | ❌ |
| GET | `/model-train/multi-station-eval/status/{task_id}` | 查询评估任务状态及统计摘要 | ❌ |
| GET | `/model-train/multi-station-eval/export/{task_id}` | 下载评估结果 Excel 文件 | ❌ |

---

## 8. 数据订正模块 `/data-correct`

| 方法 | 路径 | 说明 | 前端覆盖 |
|------|------|------|----------|
| GET | `/data-correct/get-models` | 获取全部已保存模型记录 | ✅ |
| POST | `/data-correct/start` | 启动数据订正任务 | ✅ |
| GET | `/data-correct/global/processing-parent` | 获取全部订正中父任务 | ❌ |
| GET | `/data-correct/global/completed-parent` | 获取全部已完成父任务 | ❌ |
| GET | `/data-correct/global/failed-parent` | 获取全部失败父任务 | ❌ |
| GET | `/data-correct/global/pending` | 获取全部待处理订正子任务 | ❌ |
| GET | `/data-correct/global/processing` | 获取全部订正中子任务 | ❌ |
| GET | `/data-correct/global/completed` | 获取全部已完成订正子任务 | ❌ |
| GET | `/data-correct/global/failed` | 获取全部失败订正子任务 | ❌ |

---

## 9. 数据透视模块 `/data-pivot`

| 方法 | 路径 | 说明 | 前端覆盖 |
|------|------|------|----------|
| POST | `/data-pivot/processed-data` | 获取站点与网格对比数据 (折线图) | ✅ |
| POST | `/data-pivot/grid-data` | 获取订正前后网格热力图数据 | ✅ |
| POST | `/data-pivot/grid-data-timeseries` | 提交订正前后时序对比任务 | ✅ |
| GET | `/data-pivot/grid-data-timeseries/status/{task_id}` | 查询时序对比任务状态 | ✅ |
| POST | `/data-pivot/model-evaluation` | 启动模型评估任务 | ❌ |
| GET | `/data-pivot/model-evaluation/status/{task_id}` | 查询模型评估任务状态 | ❌ |
| POST | `/data-pivot/export-corrected-data` | 导出订正后网格数据为 ZIP (NetCDF) | ❌ |
| POST | `/data-pivot/export-corrected-images` | 导出订正后数据为 PNG 图片 ZIP | ❌ |
| GET | `/data-pivot/export-corrected-data/status/{task_id}` | 查询订正数据导出任务状态 | ❌ |
| GET | `/data-pivot/download-export/{task_id}` | 下载导出的订正数据 ZIP | ❌ |
| POST | `/data-pivot/model-ranking` | 启动模型排名任务 (按评估指标排序) | ❌ |
| GET | `/data-pivot/model-ranking/status/{task_id}` | 查询模型排名任务状态 | ❌ |

---

## 10. 任务操作模块 `/task_operate`

| 方法 | 路径 | 说明 | 前端覆盖 |
|------|------|------|----------|
| POST | `/task_operate/{task_id}/cancel` | 取消运行中的任务 | ✅ |
| GET | `/task_operate/status/{task_id}` | 查询任务状态 (父任务概览) | ✅ |
| GET | `/task_operate/status/{task_id}/details` | 查询任务详情 (含全部子任务) | ✅ |
| GET | `/task_operate/history` | 获取历史任务列表 (分页) | ✅ |

---

## 前端覆盖分析总结

### 覆盖统计

| 模块 | 总接口数 | 已覆盖 | 未覆盖 |
|------|----------|--------|--------|
| 设置 | 2 | 2 | 0 |
| 数据导入 | 6 | 2 | 4 |
| 数据处理 | 5 | 1 | 4 |
| 数据预览 | 9 | 5 | 4 |
| 模型训练 | 11 | 1 | 10 |
| 多站点评估 | 3 | 0 | 3 |
| 数据订正 | 9 | 2 | 7 |
| 数据透视 | 12 | 4 | 8 |
| 任务操作 | 4 | 4 | 0 |
| **合计** | **62** | **21** | **41** |

### 未覆盖接口分类

#### 一、各模块全局状态查询接口 (共 20 个)

数据导入、数据处理、模型训练、数据订正 各有 pending/processing/completed/failed 四个全局查询接口。
前端目前通过 `task_operate` 模块统一管理任务，未调用各模块独立的全局状态查询。

> 这类接口功能与任务操作模块重叠，是否需要前端覆盖取决于是否需要模块内独立筛选视图。

- `GET /data-import/global/pending_files`
- `GET /data-import/global/processing_files`
- `GET /data-import/global/completed_files`
- `GET /data-import/global/failed_files`
- `GET /data-process/global/pending`
- `GET /data-process/global/processing`
- `GET /data-process/global/completed`
- `GET /data-process/global/failed`
- `GET /model-train/global/pending`
- `GET /model-train/global/processing`
- `GET /model-train/global/completed`
- `GET /model-train/global/failed`
- `GET /data-correct/global/processing-parent`
- `GET /data-correct/global/completed-parent`
- `GET /data-correct/global/failed-parent`
- `GET /data-correct/global/pending`
- `GET /data-correct/global/processing`
- `GET /data-correct/global/completed`
- `GET /data-correct/global/failed`

#### 二、模型训练管理 (共 5 个)

- `GET /model-train/model-config/{model_name}/{element}` — 查看模型超参数
- `POST /model-train/model-config/{model_name}/{element}` — 修改模型超参数
- `POST /model-train/get-losses` — 损失曲线可视化
- `POST /model-train/get-metrics-testset-all` — 测试集评估指标
- `GET /model-train/save-model-record` — 保存模型记录
- `DELETE /model-train/delete-model-record/{task_id}` — 删除模型记录

#### 三、数据导出 (共 8 个)

- `POST /data-preview/export-grid-data` — 导出原始网格数据
- `POST /data-preview/export-grid-images` — 导出原始网格图片
- `GET /data-preview/export-grid-data/status/{task_id}` — 导出状态查询
- `GET /data-preview/download-export/{task_id}` — 下载原始数据导出
- `POST /data-pivot/export-corrected-data` — 导出订正后数据
- `POST /data-pivot/export-corrected-images` — 导出订正后图片
- `GET /data-pivot/export-corrected-data/status/{task_id}` — 导出状态查询
- `GET /data-pivot/download-export/{task_id}` — 下载订正数据导出

#### 四、高级分析 (共 5 个)

- `POST /data-pivot/model-evaluation` — 模型评估分析
- `GET /data-pivot/model-evaluation/status/{task_id}` — 评估状态查询
- `POST /data-pivot/model-ranking` — 模型排名
- `GET /data-pivot/model-ranking/status/{task_id}` — 排名状态查询
- `POST /model-train/multi-station-eval/start` — 多站点评估启动
- `GET /model-train/multi-station-eval/status/{task_id}` — 多站点评估状态
- `GET /model-train/multi-station-eval/export/{task_id}` — 导出评估 Excel
