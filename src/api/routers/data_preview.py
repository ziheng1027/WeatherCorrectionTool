# src/api/routers/data_preview.py

from fastapi import APIRouter, HTTPException
from ...core.schemas import DataSourceRequest, MessageResponse
from ...utils.file_io import load_config_json, save_config_json


router = APIRouter(
    prefix="/data-preview",
    tags=["数据预览"],
)


# @router.get