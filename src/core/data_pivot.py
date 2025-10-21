# src/core/data_pivot.py
import json
import pandas as pd
import xarray as xr
from datetime import datetime
from pathlib import Path
from sqlalchemy.orm import Session
from ..db import crud
from ..core import schemas
from ..core.config import settings
from ..core.data_mapping import ELEMENT_TO_DB_MAPPING, ELEMENT_TO_NC_MAPPING
from ..utils.metrics import cal_metrics
from ..utils.file_io import find_nc_file_for_timestamp, safe_open_mfdataset


