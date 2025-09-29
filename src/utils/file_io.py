import json
from pathlib import Path


CONFIG_FILE = Path("config/config.json")

def load_config_json():
    """根据默认路径来加载json配置文件"""
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    else:
        return {}

def save_config_json(config_data: dict):
    """将配置字典保存到json配置文件"""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config_data, f, indent=4, ensure_ascii=False)
    