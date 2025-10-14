# src/core/data_mapping.py
import pandas as pd


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
ELEMENT_TO_NC_MAPPING = {
    "温度": "tmp",
    "相对湿度": "rh",
    "过去1小时降水量": "pre",
    "2分钟平均风速": "wind_velocity"
}

NC_TO_DB_MAPPING = {
    "tmp": "temperature",
    "rh": "humidity",
    "pre": "precipitation_1h",
    "wind_velocity": "wind_speed_2min"
}

def get_elements_mapping():
    """获取变量名称的映射关系"""
    vars_map = {
        "温度": ("tmp", "温度/气温"),
        "相对湿度": ("rh", "相对湿度"),
        "过去1小时降水量": ("pre", "过去1小时降水量"),
        "2分钟平均风速": ("wind_velocity", "2分钟平均风速"),
    }
    return vars_map

def get_name_to_id_mapping(station_info_file):
    """获取站点名称到ID的映射关系"""
    station_mapping = {}
    station_info = pd.read_csv(station_info_file, encoding='gbk')
    for _, row in station_info.iterrows():
        station_id = str(row['区站号(数字)'])  # 转换为字符串类型
        station_name = row['站名']
        station_mapping[station_name] = {
            "id": station_id,
            "lat": row['纬度'],
            "lon": row['经度']
        }
    return station_mapping

def get_id_to_name_mapping(station_info_file):
    """获取站点ID到名称的映射关系"""
    station_mapping = {}
    station_info = pd.read_csv(station_info_file, encoding='gbk')
    for _, row in station_info.iterrows():
        station_id = str(row['区站号(数字)'])  # 转换为字符串类型
        station_name = row['站名']
        station_mapping[station_id] = {
            "name": station_name,
            "lat": row['纬度'],
            "lon": row['经度']
        }
    return station_mapping

def cst_to_utc(cst_times):
    """北京时转世界时"""
    if isinstance(cst_times, pd.Series):
        # 处理DataFrame列
        cst_datetimes = pd.to_datetime(cst_times.astype(str), format='%Y%m%d%H')
        utc_datetimes = cst_datetimes - pd.Timedelta(hours=8)
        return utc_datetimes.dt.strftime('%Y%m%d%H').astype(int)
    else:
        # 处理列表或单个值
        cst_datetimes = pd.to_datetime(cst_times, format='%Y%m%d%H')
        utc_datetimes = cst_datetimes - pd.Timedelta(hours=8)
        return utc_datetimes.strftime('%Y%m%d%H').astype(int).tolist()
