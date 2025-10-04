# src/core/data_db_mapping.py
# 原始站点数据字段与数据表字段映射
RAW_STATION_DATA_TO_DB_MAPPING = {
    "区站号(数字)": "station_id",
    "站名": "station_name",
    "纬度": "lat",
    "经度": "lon",
    "年": "year",
    "月": "month",
    "日": "day",
    "时": "hour",
    "温度/气温": "temperature",
    "相对湿度": "humidity",
    "过去1小时降水量": "precipitation_1h",
    "2分钟平均风速": "wind_speed_2min"
}

REQUIRED_COLUMNS = list(RAW_STATION_DATA_TO_DB_MAPPING.keys())

# 将用户界面的要素名称映射到数据库表的列名
ELEMENT_TO_DB_MAPPING = {
    "温度": "temperature",
    "相对湿度": "humidity",
    "过去1小时降水量": "precipitation_1h",
    "2分钟平均风速": "wind_speed_2min"
}

# 将用户界面的要素名称映射到.nc文件中的变量名
ELEMENT_TO_NC_VAR_MAPPING = {
    "温度": "tmp",
    "相对湿度": "rh",
    "过去1小时降水量": "pre",
    "2分钟平均风速": "wind_velocity"
}
