"""FinBERT sentiment analysis plugin — ProsusAI/finbert."""

from backend.core.registry import register_model
from backend.core.plugin_base import AbstractModel


_global_pipeline = None


def _load_pipeline():
    global _global_pipeline
    if _global_pipeline is not None:
        return _global_pipeline
    try:
        from transformers import pipeline
        _global_pipeline = pipeline(
            "text-classification",
            model="ProsusAI/finbert",
            top_k=None,
        )
    except Exception:
        _global_pipeline = False
    return _global_pipeline


def _label_to_score(label: str, confidence: float) -> float:
    mapping = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}
    return mapping.get(label.lower(), 0.0) * confidence


@register_model("finbert")
class FinBERTModel(AbstractModel):
    name = "finbert"
    version = "1.0.0"

    def predict(self, features: dict) -> dict:
        text = features.get("text", "")
        if not text:
            return {"score": 0.0, "label": "neutral", "probabilities": {}}

        pipe = _load_pipeline()
        if pipe is False or pipe is None:
            return {"score": 0.0, "label": "neutral", "probabilities": {}, "fallback": True}

        try:
            results = pipe(text[:512], truncation=True)
            probs = {}
            dominant = max(results if isinstance(results, list) else [results], key=lambda r: r["score"])
            if isinstance(results, list) and all(isinstance(r, dict) for r in results):
                for r in results:
                    probs[r["label"].lower()] = round(r["score"], 4)
            return {
                "score": _label_to_score(dominant["label"], dominant["score"]),
                "label": dominant["label"].lower(),
                "probabilities": probs,
                "fallback": False,
            }
        except Exception:
            return {"score": 0.0, "label": "neutral", "probabilities": {}, "fallback": True}

    def predict_batch(self, texts: list[str]) -> list[dict]:
        results = []
        pipe = _load_pipeline()
        if pipe is False or pipe is None:
            return [{"score": 0.0, "label": "neutral", "fallback": True} for _ in texts]

        truncated = [t[:512] for t in texts]
        try:
            batch_results = pipe(truncated, truncation=True)
            for item in batch_results:
                dominant = item[0] if isinstance(item, list) else item
                results.append({
                    "score": _label_to_score(dominant["label"], dominant["score"]),
                    "label": dominant["label"].lower(),
                    "fallback": False,
                })
        except Exception:
            results = [{"score": 0.0, "label": "neutral", "fallback": True} for _ in texts]
        return results
