"""Anomaly detection plugin — Isolation Forest."""

from backend.core.registry import register_model
from backend.core.plugin_base import AbstractModel


@register_model("anomaly")
class AnomalyDetector(AbstractModel):
    name = "anomaly"
    version = "1.0.0"

    def __init__(self):
        from sklearn.ensemble import IsolationForest
        self.model = IsolationForest(
            n_estimators=100,
            contamination=0.05,
            random_state=42,
        )
        self.trained = False

    def train(self, historical_data: list[float]):
        import numpy as np
        X = np.array(historical_data).reshape(-1, 1)
        self.model.fit(X)
        self.trained = True

    def predict(self, features: dict) -> dict:
        import numpy as np
        values = features.get("values", [])
        if not values:
            return {"anomalies": [], "anomaly_count": 0}
        if not self.trained:
            return {"anomalies": [], "anomaly_count": 0, "note": "model_not_trained"}

        X = np.array(values).reshape(-1, 1)
        predictions = self.model.predict(X)

        anomalies = []
        for i, pred in enumerate(predictions):
            if pred == -1:
                anomalies.append({
                    "index": i,
                    "value": float(values[i]),
                    "score": float(self.model.score_samples(X[i:i+1])[0]),
                })

        return {
            "anomalies": anomalies,
            "anomaly_count": len(anomalies),
            "total_points": len(values),
            "anomaly_rate": round(len(anomalies) / len(values) * 100, 2) if values else 0,
        }
