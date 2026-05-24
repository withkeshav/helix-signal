"""TimesFM 2.5 forecasting model plugin."""

from backend.core.registry import register_model
from backend.core.plugin_base import AbstractModel


@register_model("timesfm")
class TimesFMModel(AbstractModel):
    name = "timesfm"
    version = "2.5.0"
