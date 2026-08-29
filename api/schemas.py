from typing import Dict

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool


class PredictResponse(BaseModel):
    label: str
    probability: float
    probabilities: Dict[str, float]


class MetricsResponse(BaseModel):
    request_count: int
    average_latency_ms: float
    predictions: Dict[str, int]
