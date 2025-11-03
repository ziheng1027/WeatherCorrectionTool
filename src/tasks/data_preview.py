# src/tasks/data_preview.py
import zipfile
import shutil
import rioxarray
import matplotlib
import pandas as pd
import xarray as xr
import geopandas as gpd
import matplotlib.pyplot as plt
from pathlib import Path
from datetime import datetime
from matplotlib.ticker import FuncFormatter
from ..db import crud
from ..db.database import SessionLocal
from ..core.config import settings
from ..core.data_mapping import ELEMENT_TO_NC_MAPPING
from ..utils.file_io import find_nc_file_for_timestamp

matplotlib.use('Agg')  # 使用 'Agg' 后端, 适用于非GUI环境的后台任务
plt.rcParams['font.sans-serif'] = ['SimHei']  # 用来正常显示中文标签
plt.rcParams['axes.unicode_minus'] = False  # 用来正常显示负号


# 要素到单位的映射，用于在色标上显示单位
ELEMENT_UNIT_MAPPING = {
    '温度': '℃',
    '相对湿度': '%',
    '过去1小时降水量': 'mm',
    '2分钟平均风速': 'm/s'
}

# 要素到色标bar的映射, 降水bar的几个关键刻度设置:0.1, 2, 5, 10, 20, 50, 70, 100, 200, 300
ELEMENT_BAR_MAPPING = {
    '温度': 'RdBu_r',
    '相对湿度': {
        'boundaries': [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        'ticks': [0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        'colors': [
            '#FFFFFF',  # 0-10 白色
            '#E6F9E6',  # 10-20 极浅绿
            '#CFF3CF',  # 20-30 很浅绿
            '#B7EDB7',  # 30-40 浅绿
            '#9FE79F',  # 40-50 绿
            '#87D787',  # 50-60 稍深绿
            '#6FC76F',  # 60-70 中绿
            '#57B757',  # 70-80 深绿
            '#3FA73F',  # 80-90 更深绿
            '#289728'   # 90-100 最深绿
        ]
    },
    '2分钟平均风速': 'RdYlBu_r',
    '过去1小时降水量': {
        'boundaries': [0, 0.1, 2, 5, 10, 20, 50, 70, 100, 200, 300],
        'ticks': [0, 0.1, 2, 5, 10, 20, 50, 70, 100, 200, 300],
        'colors': [
            '#FFFFFF',   # 0-0.1 白色
            '#B7F7B7',   # 0.1-2 浅绿色
            '#008000',   # 2-5 深绿色
            "#34C3C3",   # 5-10 浅蓝色
            '#00008B',   # 10-20 深蓝色
            '#FF00FF',   # 20-50 品红色
            "#6A4B2D",   # 50-70 深褐色
            '#FFA500',   # 70-100 棕黄色
            "#FF6F00",   # 100-200 橘黄色
            '#FF0000',   # 200-300 红色
            "#B8662C"    # >300 褐色
        ]
    }
}

def create_export_zip_task(task_id: str, element: str, start_time: datetime, end_time: datetime):
    """查找指定范围内的所有格点.nc文件, 并将它们压缩成一个zip包[后台任务]"""
    db = SessionLocal()
    
    try:
        # 1. 定义输出路径
        output_dir = Path("output/temp_data/export")
        output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = output_dir / f"{task_id}.zip"

        # 2. 获取所有时间戳
        timestamps = pd.date_range(start=start_time, end=end_time, freq='h')
        total_files = len(timestamps)
        files_found = 0
        
        crud.update_task_status(db, task_id, "PROCESSING", 0, f"准备压缩 {total_files} 个文件...")

        # 3. 循环查找并压缩文件
        # 使用 'w' 模式创建新的zip文件, ZIP_DEFLATED 提供较好的压缩率
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, ts in enumerate(timestamps):
                try:
                    # 查找对应的订正文件
                    file_path = find_nc_file_for_timestamp(element, ts)
                    
                    # 写入zip包, arcname=file_path.name 确保zip包内是扁平结构, 不含服务器绝对路径
                    zf.write(file_path, arcname=file_path.name)
                    files_found += 1
                except FileNotFoundError:
                    # 如果某个时次的文件不存在, 打印警告并跳过
                    print(f"警告: 未找到 {ts} 的订正文件, 已跳过")
                    pass
                
                # 4. 周期性更新进度 (例如每50个文件或最后1个文件)
                if (i + 1) % 50 == 0 or (i + 1) == total_files:
                    progress = ((i + 1) / total_files) * 100
                    crud.update_task_status(db, task_id, "PROCESSING", progress, f"正在压缩文件... ({i+1}/{total_files})")

        # 5. 任务完成, 更新数据库
        final_message = f"打包完成, 共找到 {files_found} / {total_files} 个文件"
        task = crud.get_task_by_id(db, task_id)
        if task:
            params = task.get_params()
            params["result_path"] = str(zip_path)
            params["files_found"] = files_found
            params["total_requested"] = total_files
            task.set_params(params)
            db.add(task)
            db.commit() # 确保参数写入
        
        crud.update_task_status(db, task_id, "COMPLETED", 100, final_message)

    except Exception as e:
        print(f"导出任务 {task_id} 失败: {e}")
        crud.update_task_status(db, task_id, "FAILED", 0, f"任务失败: {e}")
    finally:
        db.close()

def create_export_images_task(task_id: str, element: str, start_time: datetime, end_time: datetime):
    """
    查找格点.nc文件, 绘制成.png图像 (采用 data_pivot 样式), 并压缩为.zip包。
    """
    db = SessionLocal()
    try:
        # 1. 定义临时图片目录和最终zip输出路径
        temp_image_dir = Path("output/temp_data/export_images") / task_id
        temp_image_dir.mkdir(parents=True, exist_ok=True)
        
        zip_output_dir = Path("output/temp_data/export")
        zip_output_dir.mkdir(parents=True, exist_ok=True)
        zip_path = zip_output_dir / f"{task_id}_images.zip"

        # 2. 获取NC变量名和时间戳
        nc_var = ELEMENT_TO_NC_MAPPING.get(element)
        if not nc_var:
            raise ValueError(f"无效的要素名称: {element}")
            
        timestamps = pd.date_range(start=start_time, end=end_time, freq='h')
        total_files = len(timestamps)
        files_found = 0
        
        crud.update_task_status(db, task_id, "PROCESSING", 0, f"准备生成 {total_files} 张图像...")

        # --- 加载行政区划文件用于裁剪和叠加 ---
        province_gdf = None # 用于绘制市界
        hubei_mask_geometry = None # 用于裁剪
        # 假设 settings.HUBEI_MAP_PATH 在 config.py 中定义
        province_geo_path = Path(settings.HUBEI_MAP_PATH) 
        
        if province_geo_path.exists():
            try:
                province_gdf = gpd.read_file(province_geo_path)
                # 确保 CRS (WGS84)
                if province_gdf.crs is None:
                    province_gdf_crs = province_gdf.set_crs("EPSG:4326")
                else:
                    province_gdf_crs = province_gdf.to_crs("EPSG:4326")
                
                # 创建一个合并的省级边界 (保留 province_gdf 不变, 用于绘制市级边界)
                hubei_boundary_dissolved = province_gdf_crs.dissolve()
                hubei_mask_geometry = hubei_boundary_dissolved.geometry
                print(f"信息: 成功加载 GeoJSON 掩膜. 边界范围: {hubei_mask_geometry.bounds}")
            except Exception as geo_e:
                print(f"读取行政区划失败: {geo_e}")
                province_gdf = None
                hubei_mask_geometry = None
        else:
             print(f"警告: 找不到 GeoJSON 文件: {province_geo_path}")

        # 3. 循环查找、绘图、保存
        for i, ts in enumerate(timestamps):
            try:
                # 查找对应的订正文件
                nc_file_path = find_nc_file_for_timestamp(element, ts)
                
                # 使用 xarray 和 matplotlib 绘图
                with xr.open_dataset(nc_file_path) as ds:
                    
                    # --- 应用 rioxarray 裁剪 ---
                    try:
                        ds_spatial = ds.rio.set_spatial_dims(x_dim='lon', y_dim='lat').rio.write_crs("EPSG:4326")
                    except Exception as rio_e:
                        print(f"警告: 设置空间维度失败: {rio_e}。将使用未裁剪的数据。")
                        ds_spatial = ds
                    
                    data_array = ds_spatial[nc_var].isel(time=0)

                    # 相对湿度最大值为100
                    if element == "相对湿度":
                        data_array = data_array.clip(max=100)

                    # 重命名 'lon'/'lat' 为 'x'/'y' 以便裁剪
                    try:
                        data_array = data_array.rename({'lon': 'x', 'lat': 'y'})
                    except Exception as rename_e:
                        # 忽略错误, 可能已经重命名或维度名称不同
                        pass 

                    # 应用裁剪 (边界外为 NaN)
                    if hubei_mask_geometry is not None:
                        try:
                            data_array = data_array.rio.clip(hubei_mask_geometry, all_touched=True, drop=False)
                        except Exception as clip_e:
                            print(f"警告: 裁剪步骤失败: {clip_e}")
                    # --------------------------------------

                    fig, ax = plt.subplots(figsize=(10, 8)) # 单面板
                    
                    # --- 设置色标和单位 ---
                    unit = ELEMENT_UNIT_MAPPING.get(element, '')
                    value_label = f"{element} ({unit})" if unit else element
                    # 默认回退到 'coolwarm'
                    bar_cfg = ELEMENT_BAR_MAPPING.get(element, 'coolwarm') 
                    
                    if isinstance(bar_cfg, dict):
                        boundaries = bar_cfg['boundaries']
                        colors = bar_cfg['colors']
                        ticks = bar_cfg['ticks']
                        cmap = matplotlib.colors.ListedColormap(colors)
                        norm = matplotlib.colors.BoundaryNorm(boundaries, ncolors=len(colors), clip=True)
                    else:
                        cmap = bar_cfg
                        boundaries = None
                        norm = None
                        ticks = None
                    # ---------------------------------

                    # --- 经纬度刻度格式化器 ---
                    def _deg_fmt_lon(x, pos):
                        try:
                            s = f"{x:.2f}"
                            if '.' in s: s = s.rstrip('0').rstrip('.')
                        except Exception: s = str(x)
                        return s + '°E'

                    def _deg_fmt_lat(x, pos):
                        try:
                            s = f"{x:.2f}"
                            if '.' in s: s = s.rstrip('0').rstrip('.')
                        except Exception: s = str(x)
                        return s + '°N'

                    lon_formatter = FuncFormatter(_deg_fmt_lon)
                    lat_formatter = FuncFormatter(_deg_fmt_lat)
                    # ---------------------------------

                    # --- 绘制 pcolormesh 并应用样式 ---
                    if boundaries is not None and norm is not None:
                        im = data_array.plot.pcolormesh(
                            ax=ax,
                            cmap=cmap,
                            norm=norm,
                            vmin=min(boundaries),
                            vmax=max(boundaries),
                            cbar_kwargs={'label': value_label, 'orientation': 'horizontal', 'pad': 0.1}
                        )
                        # 为分段色标设置刻度
                        if ticks:
                            im.colorbar.set_ticks(ticks)
                    else:
                        # 自动范围 (例如温度)
                        im = data_array.plot.pcolormesh(
                            ax=ax,
                            cmap=cmap,
                            cbar_kwargs={'label': value_label, 'orientation': 'horizontal', 'pad': 0.1}
                        )
                    
                    ax.set_title(f"订正前 {element}\n{ts.strftime('%Y-%m-%d %H:%M')}", fontsize=16)
                    
                    # 应用格式化器
                    ax.xaxis.set_major_formatter(lon_formatter)
                    ax.yaxis.set_major_formatter(lat_formatter)
                    ax.set_xlabel('Longitude')
                    ax.set_ylabel('Latitude')

                    # 叠加湖北省行政区划边界
                    if province_gdf is not None:
                        province_gdf.boundary.plot(ax=ax, color='gray', linewidth=1, zorder=10)

                        # 叠加湖北省行政区划边界
                    if province_gdf is not None:
                        province_gdf.boundary.plot(ax=ax, color='gray', linewidth=1, zorder=10)
                        
                        # --- 循环遍历 GeoDataFrame 以添加区域名称 ---
                        for idx, row in province_gdf.iterrows():
                            if row.geometry is not None and hasattr(row.geometry, 'centroid'):
                                centroid = row.geometry.centroid
                                # 尝试获取 "name" 字段, 如果没有则尝试 "NAME"
                                name = row.get('name', row.get('NAME', None))
                                if name:
                                    ax.text(
                                        centroid.x, 
                                        centroid.y, 
                                        name, 
                                        fontsize=8,       # 字体大小
                                        color='black',    # 字体颜色
                                        alpha=0.6,      # 透明度
                                        ha='center',    # 水平居中
                                        va='center',    # 垂直居中
                                        zorder=11       # 确保在边界线之上
                                    )
                    plt.tight_layout()
                    
                    # 定义图像输出路径
                    img_filename = f"{nc_var}_{ts.strftime('%Y%m%d%H')}.png"
                    img_path = temp_image_dir / img_filename
                    
                    # 保存图像 (提高DPI)
                    fig.savefig(img_path, dpi=150, bbox_inches='tight')
                    
                    # 关闭图像以释放内存
                    plt.close(fig)
                    
                files_found += 1
                
            except FileNotFoundError:
                print(f"警告: 未找到 {ts} 的订正文件, 已跳过")
                pass
            except Exception as plot_e:
                print(f"警告: 绘制 {ts} 时出错: {plot_e}, 已跳过")
                plt.close('all') # 确保关闭所有可能打开的图像
                pass
            
            # 4. 周期性更新进度
            if (i + 1) % 50 == 0 or (i + 1) == total_files:
                progress = ((i + 1) / total_files) * 90 # 压缩占10%
                progress = min(progress, 95) # 确保不超过95
                crud.update_task_status(db, task_id, "PROCESSING", progress, f"正在生成图像... ({i+1}/{total_files})")

        # 5. 压缩所有生成的图像
        crud.update_task_status(db, task_id, "PROCESSING", 95, f"图像生成完毕 ({files_found}张), 开始压缩...")
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for img_file in temp_image_dir.glob("*.png"):
                zf.write(img_file, arcname=img_file.name)

        # 6. 任务完成, 更新数据库
        final_message = f"图像打包完成, 共生成 {files_found} / {total_files} 张图像"
        task = crud.get_task_by_id(db, task_id)
        if task:
            params = task.get_params()
            params["result_path"] = str(zip_path) # 存储zip包的路径
            params["files_found"] = files_found
            params["total_requested"] = total_files
            task.set_params(params)
            db.add(task)
            db.commit() # 确保参数写入
        
        crud.update_task_status(db, task_id, "COMPLETED", 100, final_message)

    except Exception as e:
        print(f"图像导出任务 {task_id} 失败: {e}")
        crud.update_task_status(db, task_id, "FAILED", 0, f"任务失败: {e}")
    finally:
        # 7. 清理临时图片目录
        try:
            if temp_image_dir.exists():
                shutil.rmtree(temp_image_dir)
                print(f"临时图片目录已删除: {temp_image_dir}")
        except OSError as e:
            print(f"删除临时图片目录 {temp_image_dir} 失败: {e}")
        
        db.close()