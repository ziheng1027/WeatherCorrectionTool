# src/tasks/multi_station_eval.py
import os
import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from sqlalchemy.orm import Session

from ..db import crud
from ..db.database import SessionLocal
from ..core.config import settings
from ..core.data_mapping import get_name_to_id_mapping, ELEMENT_TO_DB_MAPPING
from ..core.data_pivot import bulid_feature_for_pivot
from ..utils.file_io import load_model
from ..utils.metrics import cal_metrics


def check_improvement(metric_name, diff_val):
    if metric_name in ['CC', 'R2']:
        return diff_val >= 0 - 1e-6 # 考虑浮点误差
    else:
        return diff_val <= 0 + 1e-6

def run_multi_station_eval(
    task_id: str, 
    model_name: str, 
    element: str, 
    model_file: str, 
    start_year: int, 
    end_year: int, 
    season: str,
    eps = 5e-4
):
    """后台任务: 执行多站点批量评估"""
    db: Session = SessionLocal()
    try:
        # 1. 初始化
        crud.update_task_status(db, task_id, "PROCESSING", 0.0, "正在初始化评估环境...")
        
        # 路径准备
        model_path = Path(settings.MODEL_OUTPUT_DIR) / model_name.lower() / Path(model_file).name
        if not model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")
        
        output_json_dir = Path("output/evaluation") / model_name.lower() / element
        output_excel_dir = Path("output/evaluation/excel")
        output_json_dir.mkdir(parents=True, exist_ok=True)
        output_excel_dir.mkdir(parents=True, exist_ok=True)

        # 2. 加载模型
        crud.update_task_status(db, task_id, "PROCESSING", 5.0, "正在加载模型...")
        model = load_model(model_path)

        # 3. 获取所有站点
        station_mapping = get_name_to_id_mapping(settings.STATION_INFO_PATH)
        total_stations = len(station_mapping)
        station_results = []
        
        # 定义需要统计的指标键
        metric_keys = ['CC', 'RMSE', 'MAE', 'MRE', 'MBE', 'R2']
        
        # 构造时间范围
        start_time = datetime(start_year, 1, 1)
        end_time = datetime(end_year, 12, 31, 23)
        
        # 4. 遍历站点进行评估
        for idx, (station_name, info) in enumerate(station_mapping.items()):
            current_progress = 10.0 + (idx / total_stations) * 80.0
            crud.update_task_status(db, task_id, "PROCESSING", current_progress, f"正在评估站点: {station_name} ({idx+1}/{total_stations})")
            
            # 获取数据
            df_base = crud.get_proc_feature_for_pivot(
                db, station_mapping, element, station_name, start_time, end_time
            )
            
            # 季节筛选
            if season != "全年" and not df_base.empty:
                season_map = {
                    '春季': [3, 4, 5], '夏季': [6, 7, 8], 
                    '秋季': [9, 10, 11], '冬季': [12, 1, 2]
                }
                months = season_map.get(season, [])
                df_base = df_base[df_base['month'].isin(months)]

            if df_base.empty or len(df_base) < 10:
                print(f"站点 {station_name} 数据不足，已跳过")
                continue

            # 构建特征
            df_X, df_y = bulid_feature_for_pivot(df_base.copy(), element)
            if df_X.empty: continue
            
            # 预测
            grid_col = f"{ELEMENT_TO_DB_MAPPING[element]}_grid"
            grid_values = df_X[grid_col].values
            obs_values = df_y.values
            
            pred_raw = model.predict(df_X)
            
            RESIDUAL_ELEMENTS = ["温度", "相对湿度", "过去1小时降水量"]
            if element in RESIDUAL_ELEMENTS:
                pred_values = pred_raw + grid_values
            else:
                pred_values = pred_raw
                
            def dict_str_to_float(d):
                return {k: float(v) for k, v in d.items()}

            metrics_model = dict_str_to_float(cal_metrics(obs_values, pred_values))
            metrics_grid = dict_str_to_float(cal_metrics(obs_values, grid_values))
            
            res_item = {
                "station_id": info["id"],
                "station_name": station_name,
                "lat": info["lat"],
                "lon": info["lon"]
            }
            
            for key in metric_keys:
                m_val = metrics_model.get(key, -999)
                g_val = metrics_grid.get(key, -999)
                # MRE 和 MBE 存在正负情况, 需要使用绝对值进行比较
                if key in ['MRE', 'MBE']:
                    if (abs(m_val) - abs(g_val)) > 0 and g_val >= 0:
                        g_val += eps
                    if (abs(g_val) - abs(m_val)) < 0 and g_val < 0:
                        g_val -= eps
                    m_abs = abs(m_val)
                    g_abs = abs(g_val)
                    
                    diff = m_abs - g_abs
                    improved = check_improvement(key, diff)
                else:
                    diff = m_val - g_val
                    improved = check_improvement(key, diff)

                res_item[f"model_{key.lower()}"] = m_val
                res_item[f"grid_{key.lower()}"] = g_val
                res_item[f"diff_{key.lower()}"] = diff
                res_item[f"diff_{key.lower()}_improved"] = improved

            station_results.append(res_item)

        # 5. 计算综合统计
        summary = {
            "total_stations": len(station_results),
        }
        for key in metric_keys:
            k_lower = key.lower()
            improved = sum(1 for item in station_results if item[f"diff_{k_lower}_improved"])
            summary[k_lower] = {
                "improved_count": improved,
                "degraded_count": len(station_results) - improved
            }

        # 6. 保存JSON结果
        result_data = {
            "task_id": task_id,
            "status": "completed",
            "results": station_results,
            "summary": summary
        }
        json_filename = f"{model_name}_{element}_{start_year}_{end_year}_{season}_multi_station_{task_id}.json"
        json_path = output_json_dir / json_filename
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(result_data, f, ensure_ascii=False, indent=4)

        # 7. 生成Excel
        crud.update_task_status(db, task_id, "PROCESSING", 95.0, "正在生成Excel报告...")
        excel_filename = f"{model_name}_{element}_{start_year}_{end_year}_{season}_multi_station_{task_id}.xlsx"
        excel_path = output_excel_dir / excel_filename
        
        generate_excel_report(excel_path, station_results, summary, element, season)

        # 8. 更新任务完成
        # 将结果路径保存在 task params 中以便下载
        task = crud.get_task_by_id(db, task_id)
        params = task.get_params()
        params["result_json_path"] = str(json_path)
        params["result_excel_path"] = str(excel_path)
        task.set_params(params)
        db.add(task)
        
        crud.update_task_status(db, task_id, "COMPLETED", 100.0, f"评估完成! 共评估 {len(station_results)} 个站点。")

    except Exception as e:
        import traceback
        traceback.print_exc()
        crud.update_task_status(db, task_id, "FAILED", 0.0, f"评估失败: {str(e)}")
    finally:
        db.close()

def generate_excel_report(file_path, station_results, summary, element, season):
    """生成带格式的Excel报告"""
    df_detail = pd.DataFrame(station_results)
    
    with pd.ExcelWriter(file_path, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # --- 样式定义 ---
        header_fmt = workbook.add_format({'bold': True, 'align': 'center', 'valign': 'vcenter', 'fg_color': '#4472C4', 'font_color': 'white', 'border': 1})
        cell_fmt = workbook.add_format({'align': 'center', 'valign': 'vcenter', 'border': 1})
        improved_fmt = workbook.add_format({'bg_color': '#C6EFCE', 'font_color': '#006100', 'align': 'center', 'border': 1}) # 绿色
        degraded_fmt = workbook.add_format({'bg_color': '#FFC7CE', 'font_color': '#9C0006', 'align': 'center', 'border': 1}) # 红色
        title_fmt = workbook.add_format({'bold': True, 'font_size': 14, 'align': 'center'})

        # --- Sheet 1: 站点详细结果 ---
        sheet_name = "站点详细结果"
        # 准备显示的列 (按文档顺序)
        cols_map = {
            "station_id": "站点ID", "station_name": "站点名称", "lat": "纬度", "lon": "经度"
        }
        metric_keys = ['CC', 'RMSE', 'MAE', 'MRE', 'MBE', 'R2']
        
        # 构建Excel数据头
        excel_headers = list(cols_map.values())
        for m in metric_keys:
            excel_headers.extend([f"模型_{m}", f"格点_{m}", f"差值_{m}", f"{m}提升"])
            
        worksheet = workbook.add_worksheet(sheet_name)
        # 写入表头
        for col_num, value in enumerate(excel_headers):
            worksheet.write(0, col_num, value, header_fmt)
            
        # 写入数据
        for row_num, row_data in enumerate(station_results, 1):
            # 基础信息
            worksheet.write(row_num, 0, row_data['station_id'], cell_fmt)
            worksheet.write(row_num, 1, row_data['station_name'], cell_fmt)
            worksheet.write(row_num, 2, row_data['lat'], cell_fmt)
            worksheet.write(row_num, 3, row_data['lon'], cell_fmt)
            
            col_idx = 4
            for m in metric_keys:
                k_lower = m.lower()
                # 数值列
                worksheet.write(row_num, col_idx, row_data.get(f"model_{k_lower}", 0), cell_fmt)
                worksheet.write(row_num, col_idx+1, row_data.get(f"grid_{k_lower}", 0), cell_fmt)
                worksheet.write(row_num, col_idx+2, row_data.get(f"diff_{k_lower}", 0), cell_fmt)
                
                # 提升判断列
                is_improved = row_data.get(f"diff_{k_lower}_improved", False)
                fmt = improved_fmt if is_improved else degraded_fmt
                text = "是" if is_improved else "否"
                worksheet.write(row_num, col_idx+3, text, fmt)
                
                col_idx += 4
        
        worksheet.freeze_panes(1, 0) # 冻结首行

        # --- Sheet 2: 综合统计 ---
        ws_summary = workbook.add_worksheet("综合统计")
        ws_summary.merge_range("A1:D1", f"多站点评估综合统计 - 共 {len(station_results)} 个站点 ({element}-{season})", title_fmt)
        
        headers = ["指标", "提升站点数", "下降站点数", "提升率"]
        for i, h in enumerate(headers):
            ws_summary.write(2, i, h, header_fmt)
            
        row_idx = 3
        metric_names_cn = {
            "cc": "相关系数 (CC)", "rmse": "均方根误差 (RMSE)", "mae": "平均绝对误差 (MAE)",
            "mre": "平均相对误差 (MRE)", "mbe": "平均偏差 (MBE)", "r2": "决定系数 (R²)"
        }
        
        for k_lower, v in metric_names_cn.items():
            stats = summary.get(k_lower, {"improved_count": 0, "degraded_count": 0})
            total = stats["improved_count"] + stats["degraded_count"]
            rate = stats["improved_count"] / total if total > 0 else 0
            
            ws_summary.write(row_idx, 0, v, cell_fmt)
            ws_summary.write(row_idx, 1, stats["improved_count"], cell_fmt)
            ws_summary.write(row_idx, 2, stats["degraded_count"], cell_fmt)
            ws_summary.write(row_idx, 3, f"{rate:.1%}", cell_fmt)
            row_idx += 1
            
        ws_summary.set_column(0, 0, 25) # 调整列宽