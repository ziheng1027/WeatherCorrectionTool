# src/core/data_db_mapping.py
RAW_STATION_DATA_MAPPING = {
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

REQUIRED_COLUMNS = list(RAW_STATION_DATA_MAPPING.keys())