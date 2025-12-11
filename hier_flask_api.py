#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Flask API for hierarchical router + per-category heads trained
with train_hier_ext_gpu.py (or train_hier_ext_best.py).

Expected artifacts structure inside `art_dir`:

    art_dir/
        cat_router.joblib
        cat_label_encoder.joblib
        cat_stats.json
        mapping.json            # contains "cat_dirnames"
        models/
            <safe_cat_folder>/
                clf.joblib
                label_encoder.joblib
                stats.json

Request example (POST JSON):

    POST /predict
    {
        "text": "Прошу разобраться с начислением штрафа по налогам...",
        "art_dir": "artifacts_best_gpu",
        "device": "auto",
        "topk_cat": 2,
        "topk_sub": 5
    }

Response example (simplified):

    {
        "art_dir": "artifacts_best_gpu",
        "device_effective": "cuda",
        "st_model_name": "...",
        "router_topk": 2,
        "sub_topk": 5,
        "predictions": [
            {
                "category": "Налоги",
                "proba": 0.87,
                "subissues": [
                    {
                        "label": "Штрафы__SEP__Пени по налогам",
                        "issue": "Штрафы",
                        "subissue_unique": "Пени по налогам",
                        "proba": 0.62
                    },
                    ...
                ]
            },
            ...
        ]
    }

Run:

    export ARTIFACTS_ROOT=/path/to/folder/with/artifacts_dirs
    export ST_MODEL_NAME="sentence-transformers/paraphrase-multilingual-mpnet-base-v2"
    python hier_flask_api.py

or with gunicorn:

    gunicorn -w 2 -b 0.0.0.0:8001 hier_flask_api:app
"""

import os
import json
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
import joblib
from flask import Flask, request, jsonify

from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import LabelEncoder

# ---------------------------------------------------------------------------
# Import training utilities so that joblib can unpickle TorchLinearSklearnLike
# ---------------------------------------------------------------------------
#
# IMPORTANT:
#   - If you trained with `train_hier_ext_gpu.py`, keep that file next to this
#     API script and this import will work as-is.
#   - If your training script has another name, change the import below so that
#     it points to the module where TorchLinearSklearnLike is defined.
#
try:
    from train_hier_ext_gpu import TorchLinearSklearnLike, pick_device, basic_clean  # type: ignore
except ImportError:
    # Fallback to the CPU-safe script name, if that's what you used
    from train_hier_ext_best import TorchLinearSklearnLike, pick_device, basic_clean  # type: ignore


# ---------------------------------------------------------------------------
# Global configuration and caches
# ---------------------------------------------------------------------------

BASE_ARTIFACTS_DIR = Path(os.environ.get("ARTIFACTS_ROOT", "."))
DEFAULT_ST_MODEL_NAME = os.environ.get(
    "ST_MODEL_NAME",
    "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
)

# (model_name, device) -> SentenceTransformer
_ST_MODELS: Dict[Tuple[str, str], SentenceTransformer] = {}

# str(artifacts_path) -> dict(router, le_cat, mapping, models_root, heads_cache)
_ARTIFACTS_CACHE: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def resolve_artifacts_path(art_dir: str) -> Path:
    """
    Resolve `art_dir` against BASE_ARTIFACTS_DIR.

    - If art_dir is an absolute path, return it as-is.
    - Otherwise, interpret it as a subfolder inside BASE_ARTIFACTS_DIR.
    """
    p = Path(art_dir)
    if p.is_absolute():
        return p
    return (BASE_ARTIFACTS_DIR / p).resolve()


def get_st_model(model_name: str, device_requested: str) -> SentenceTransformer:
    """
    Get (and cache) a SentenceTransformer model on a specific device.
    """
    dev = pick_device(device_requested)
    key = (model_name, dev)
    if key not in _ST_MODELS:
        model = SentenceTransformer(model_name, device=dev)
        # warmup call to allocate weights on the device
        _ = model.encode(["warmup"], convert_to_numpy=True, batch_size=1, show_progress_bar=False)
        _ST_MODELS[key] = model
    return _ST_MODELS[key]


def load_artifacts(art_dir: str) -> Dict[str, Any]:
    """
    Load router + label encoder + mapping.json for the given artifacts dir.

    Results are cached in _ARTIFACTS_CACHE, so repeated requests with the
    same art_dir are cheap.
    """
    art_path = resolve_artifacts_path(art_dir)
    key = str(art_path)

    if key in _ARTIFACTS_CACHE:
        return _ARTIFACTS_CACHE[key]

    if not art_path.exists():
        raise FileNotFoundError(f"Artifacts directory not found: {art_path}")

    router_path = art_path / "cat_router.joblib"
    le_cat_path = art_path / "cat_label_encoder.joblib"
    mapping_path = art_path / "mapping.json"
    models_root = art_path / "models"

    if not router_path.exists():
        raise FileNotFoundError(f"Router file not found: {router_path}")
    if not le_cat_path.exists():
        raise FileNotFoundError(f"Category label encoder not found: {le_cat_path}")
    if not mapping_path.exists():
        raise FileNotFoundError(f"mapping.json not found: {mapping_path}")
    if not models_root.exists():
        raise FileNotFoundError(f"Models folder not found: {models_root}")

    # It's important that the module defining TorchLinearSklearnLike is imported
    # BEFORE we call joblib.load, otherwise unpickling will fail.
    router: TorchLinearSklearnLike = joblib.load(router_path)
    le_cat: LabelEncoder = joblib.load(le_cat_path)
    mapping: Dict[str, Any] = json.loads(mapping_path.read_text(encoding="utf-8"))

    cache_entry: Dict[str, Any] = {
        "path": art_path,
        "router": router,
        "le_cat": le_cat,
        "mapping": mapping,
        "models_root": models_root,
        # per-category head cache: cat_text -> {"clf": clf_c, "le": le_c}
        "heads": {},
    }

    _ARTIFACTS_CACHE[key] = cache_entry
    return cache_entry


def load_head(artifacts: Dict[str, Any], cat_text: str) -> Dict[str, Any] | None:
    """
    Load (and cache) per-category head for a given cat_text.

    Returns a dict with:
        {"clf": TorchLinearSklearnLike, "le": LabelEncoder}
    or None if the head is missing.
    """
    heads: Dict[str, Dict[str, Any]] = artifacts["heads"]
    if cat_text in heads:
        return heads[cat_text]

    mapping = artifacts["mapping"]
    models_root: Path = artifacts["models_root"]
    cat_dirnames: Dict[str, str] = mapping.get("cat_dirnames", {})

    folder_name = cat_dirnames.get(cat_text)
    if folder_name is None:
        # This category was not saved as a head (too few samples, etc.)
        return None

    cat_dir = models_root / folder_name
    clf_path = cat_dir / "clf.joblib"
    le_path = cat_dir / "label_encoder.joblib"

    if not clf_path.exists() or not le_path.exists():
        return None

    clf_c: TorchLinearSklearnLike = joblib.load(clf_path)
    le_c: LabelEncoder = joblib.load(le_path)

    info = {"clf": clf_c, "le": le_c}
    heads[cat_text] = info
    return info


def predict_single(
    text: str,
    art_dir: str,
    device: str = "auto",
    topk_cat: int = 2,
    topk_sub: int = 5,
) -> Dict[str, Any]:
    """
    Run full hierarchical inference for a single text.
    """

    # Resolve effective device and load artifacts
    device_effective = pick_device(device)
    artifacts = load_artifacts(art_dir)
    router: TorchLinearSklearnLike = artifacts["router"]
    le_cat: LabelEncoder = artifacts["le_cat"]

    # Sentence-transformer encoder
    st_model = get_st_model(DEFAULT_ST_MODEL_NAME, device_effective)

    # Clean + embed input text
    text_clean = basic_clean(text)
    X = st_model.encode(
        [text_clean],
        convert_to_numpy=True,
        batch_size=1,
        show_progress_bar=False,
    ).astype("float32", copy=False)

    # Router: category probabilities
    router.device_pref = device_effective
    proba_cat = router.predict_proba(X, batch=1)[0]  # (n_cat,)
    n_cat = len(le_cat.classes_)
    proba_cat = proba_cat[:n_cat]  # safety

    topk_cat = max(1, int(topk_cat))
    cat_order = np.argsort(-proba_cat)
    cat_top_idx = cat_order[: min(topk_cat, n_cat)]

    results = []

    for cat_idx in cat_top_idx:
        cat_text = le_cat.inverse_transform([cat_idx])[0]
        cat_prob = float(proba_cat[cat_idx])

        head_info = load_head(artifacts, cat_text)
        subissues = []

        if head_info is not None:
            clf_c: TorchLinearSklearnLike = head_info["clf"]
            le_c: LabelEncoder = head_info["le"]

            clf_c.device_pref = device_effective
            proba_sub = clf_c.predict_proba(X, batch=1)[0]
            n_sub = len(le_c.classes_)
            topk_eff = min(max(1, int(topk_sub)), n_sub)
            sub_order = np.argsort(-proba_sub)
            sub_top_idx = sub_order[:topk_eff]

            for sub_idx in sub_top_idx:
                label_str = le_c.inverse_transform([sub_idx])[0]
                prob_sub = float(proba_sub[sub_idx])

                issue = None
                subuniq = None

                if label_str == "__single__":
                    # Single-class head: mapping to issue/subissue is degenerate.
                    issue = None
                    subuniq = None
                elif "__SEP__" in label_str:
                    issue, subuniq = label_str.split("__SEP__", 1)
                else:
                    # Fallback: treat the whole label as subissue
                    issue = None
                    subuniq = label_str

                subissues.append(
                    {
                        "label": label_str,
                        "issue": issue,
                        "subissue_unique": subuniq,
                        "proba": prob_sub,
                    }
                )

        results.append(
            {
                "category": cat_text,
                "proba": cat_prob,
                "subissues": subissues,
            }
        )

    return {
        "art_dir": art_dir,
        "device_requested": device,
        "device_effective": device_effective,
        "st_model_name": DEFAULT_ST_MODEL_NAME,
        "router_topk": topk_cat,
        "sub_topk": topk_sub,
        "predictions": results,
    }


# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------

app = Flask(__name__)
# So that Russian / Kazakh labels are returned as UTF-8, not \uXXXX
app.config["JSON_AS_ASCII"] = False


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/predict", methods=["POST"])
def predict_endpoint():
    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid or missing JSON"}), 400

    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body must be an object"}), 400

    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        return jsonify({"error": "Field 'text' must be a non-empty string"}), 400

    art_dir = payload.get("art_dir") or os.environ.get("DEFAULT_ARTIFACTS_DIR", "artifacts_best_gpu")
    device = payload.get("device", "auto")
    topk_cat = payload.get("topk_cat", 2)
    topk_sub = payload.get("topk_sub", 5)

    try:
        result = predict_single(
            text=text,
            art_dir=str(art_dir),
            device=str(device),
            topk_cat=int(topk_cat),
            topk_sub=int(topk_sub),
        )
    except FileNotFoundError as e:
        return jsonify({"error": str(e)}), 404
    except Exception as e:  # pragma: no cover - generic safety net
        # For debugging in logs:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

    return jsonify(result)


if __name__ == "__main__":
    host = os.environ.get("FLASK_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_PORT", "8001"))
    debug = bool(int(os.environ.get("FLASK_DEBUG", "0")))
    app.run(host=host, port=port, debug=debug)
