# WeatherCorrectionTool
气象要素订正工具

源代码结构:
├── src
│   ├── api                     # api接口
│   │   ├── config_manage.py    # 配置管理api
│   │   ├── data_import.py      # 数据导入模块api
│   │   ├── data_preview.py     # 数据预览模块api
│   │   ├── data_pivot.py       # 数据透视模块api
│   │   ├── data_process.py     # 数据处理模块api
│   │   ├── model_train.py      # 模型训练模块api
│   │   ├── data_correct.py     # 数据订正模块api
│   ├── core                    # 核心模块
│   │   ├── schemas.py          # pydantic模型定义
│   ├── db                      # 数据库模块
│   │   ├── db_models.py        # 数据库模型定义
│   │   ├── database.py         # 数据库连接
│   │   ├── crud.py             # 数据库操作, 增删改查
│   ├── utils                   # 工具模块
│   │   ├── file_io             # 文件读写
│   │   ├── metrics             # 指标计算
├── main

数据结构
├── data
│   ├── dem                     # 数字高程数据
│   │   ├── hubei_terrain.nc    # 湖北地形数据
│   ├── grid                    # 格点数据文件
│   │   ├── CARAS
│   │   │   ├── pre.hourly
│   │   │   │   ├── 2008
│   │   │   │   │   ├── CARAS.2008010100.precip.hourly.nc   # shape:(460, 800)
│   │   │   │   │   ├── ...
│   │   │   │   │   ├── CARAS.2008123123.precip.hourly.nc
│   │   │   │   ├── ...
│   │   │   │   ├── 2023
│   │   │   ├── rh.hourly
│   │   │   ├── tmp.hourly
│   │   │   ├── wind_velocity.hourly
│   ├── station                 # 站点数据文件
│   │   ├── 湖北省82个国家气象站-观测数据
│   │   │   ├── 57249.TMP.PRE.WIN.RHU.csv

配置结构
├── config
│   ├── models                  # 模型配置
│   │   ├── xgboost.json        # xgboost模型配置
│   ├── config.json             # 基础配置文件