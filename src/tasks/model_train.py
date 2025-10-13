import os
import json
import pandas as pd
from time import time
from sqlalchemy.orm import Session

from ..db import crud
from ..db.database import SessionLocal
from ..core.config import settings
from ..core.model_train import build_dataset_from_db, split_dataset, build_model, train_model, evaluate_model, get_feature_importance
from ..core.schemas import ModelTrainRequest


def train(task_id: str, request: ModelTrainRequest):
    pass