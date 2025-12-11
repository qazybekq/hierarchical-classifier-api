#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# train_hier_ext_gpu.py
# GPU-ready training: uses SentenceTransformer + Torch linear heads on GPU if available.
# Artifacts are device-agnostic: weights are stored as CPU numpy arrays
# and moved to the best available device (cuda/mps/cpu) at runtime.

import argparse
import json
import re
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from tqdm import tqdm

import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from sentence_transformers import SentenceTransformer
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score


try:
    import optuna
except ImportError:
    optuna = None


def log(msg: str) -> None:
    print(msg, flush=True)


def pick_device(requested: str = "auto") -> str:
    if requested == "cpu":
        return "cpu"
    if requested == "cuda":
        return "cuda" if torch.cuda.is_available() else "cpu"
    if requested == "mps":
        return "mps" if hasattr(torch.backends, "mps") and torch.backends.mps.is_available() else "cpu"
    if torch.cuda.is_available():
        return "cuda"
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def basic_clean(text: str) -> str:
    if text is None:
        return " "
    t = str(text)
    t = re.sub(r"https?://\S+", " ", t)
    t = re.sub(r"\S+@\S+", " ", t)
    t = re.sub(r"\d+", " ", t)
    t = re.sub(r"[^\w\s]+", " ", t, flags=re.UNICODE)
    t = t.lower()
    t = re.sub(r"\s+", " ", t).strip()
    return t if t else " "


def safe_key(s: str) -> str:
    s = str(s)
    s_norm = re.sub(r"\s+", " ", s, flags=re.UNICODE).strip()
    slug = re.sub(r"[^\w.\-]+", "_", s_norm, flags=re.UNICODE)
    digest = hashlib.md5(s_norm.encode("utf-8")).hexdigest()[:8]
    return f"{slug[:80]}__{digest}"


def ensure_unique_level3_names(
    df: pd.DataFrame,
    sub_col: str = "subissue",
    issue_col: str = "issue",
    out_col: str = "subissue_unique",
) -> Tuple[pd.DataFrame, Dict]:
    d = df.copy()
    d[out_col] = d[sub_col].astype(str)
    grp = d.groupby(sub_col)[issue_col].nunique().reset_index(name="n_issues")
    dup_values = set(grp.loc[grp["n_issues"] > 1, sub_col].astype(str).tolist())
    changed = 0
    if dup_values:
        mask = d[sub_col].astype(str).isin(dup_values)
        d.loc[mask, out_col] = d.loc[mask].apply(
            lambda r: f"{r[sub_col]} ⟨{r[issue_col]}⟩", axis=1
        )
        changed = int(mask.sum())
    log(f"[info] ensure_unique_level3_names: appended suffix for {changed} rows")
    return d, {"duplicates_detected": len(dup_values), "rows_appended_suffix": changed}


def group_lowfreq_subissues(
    df: pd.DataFrame,
    min_count: int = 3,
    top_keep_per_issue: int = 5,
    safety_max_share: float = 0.6,
    min_floor: int = 1,
    col_cat: str = "category",
    col_issue: str = "issue",
    col_subu: str = "subissue_unique",
) -> Tuple[pd.DataFrame, Dict]:
    d = df.copy()
    total = len(d)
    cnt = d.groupby([col_cat, col_issue, col_subu]).size().reset_index(name="cnt")
    d = d.merge(cnt, on=[col_cat, col_issue, col_subu], how="left")
    low_mask = d["cnt"] < int(min_count)

    keep_idx = []
    for (c, i), block in cnt.groupby([col_cat, col_issue]):
        block_sorted = block.sort_values("cnt", ascending=False)
        keep = block_sorted.head(top_keep_per_issue)[col_subu].tolist()
        idx = d.loc[(d[col_cat] == c) & (d[col_issue] == i) & (d[col_subu].isin(keep))].index
        keep_idx.append(idx)
    keep_idx = pd.Index(np.concatenate([x.values for x in keep_idx])) if keep_idx else pd.Index([])

    to_other_mask = low_mask & (~d.index.isin(keep_idx))
    n_low_initial = int(to_other_mask.sum())
    if n_low_initial > 0:
        d.loc[to_other_mask, col_subu] = "others"
    others_share = n_low_initial / max(1, total)

    note = ""
    if others_share > safety_max_share and min_count > min_floor:
        d = df.copy()
        cnt = d.groupby([col_cat, col_issue, col_subu]).size().reset_index(name="cnt")
        d = d.merge(cnt, on=[col_cat, col_issue, col_subu], how="left")
        low_mask2 = d["cnt"] < int(min_floor)
        keep_idx2 = []
        for (c, i), block in cnt.groupby([col_cat, col_issue]):
            block_sorted = block.sort_values("cnt", ascending=False)
            keep = block_sorted.head(top_keep_per_issue)[col_subu].tolist()
            idx = d.loc[(d[col_cat] == c) & (d[col_issue] == i) & (d[col_subu].isin(keep))].index
            keep_idx2.append(idx)
        keep_idx2 = pd.Index(np.concatenate([x.values for x in keep_idx2])) if keep_idx2 else pd.Index([])
        to_other_mask2 = low_mask2 & (~d.index.isin(keep_idx2))
        n_low_final = int(to_other_mask2.sum())
        if n_low_final > 0:
            d.loc[to_other_mask2, col_subu] = "others"
        others_share = n_low_final / max(1, total)
        note = f"auto-relaxed threshold {min_count}->{min_floor}, share={others_share:.4f}"
        n_low_initial = n_low_final

    d.drop(columns=["cnt"], inplace=True)
    return d, {
        "min_count": int(min_count),
        "top_keep_per_issue": int(top_keep_per_issue),
        "final_others_rows": int(n_low_initial),
        "final_others_share": float(round(others_share, 6)),
        "note": note,
    }


def drop_empty_texts(df: pd.DataFrame, text_col: str = "text_obr") -> pd.DataFrame:
    d = df.copy()
    d[text_col] = d[text_col].map(basic_clean)
    before = len(d)
    d = d[d[text_col].str.strip().astype(bool)].copy()
    log(f"[info] drop empty texts: {before} -> {len(d)}")
    return d


def encode_texts_st(
    texts: List[str],
    model_name_or_dir: str,
    device: str = "auto",
    batch_size: int = 128,
    out_memmap: Optional[Path] = None,
    dtype: str = "float32",
) -> Tuple[np.ndarray, SentenceTransformer]:
    dev = pick_device(device)
    st_model = SentenceTransformer(model_name_or_dir, device=dev)
    log(f"[info] device = {dev} | model = {model_name_or_dir}")
    _ = st_model.encode(["warmup"], convert_to_numpy=True, batch_size=1, show_progress_bar=False)

    vecs: List[np.ndarray] = []
    iterator = range(0, len(texts), batch_size)
    pbar = tqdm(iterator, desc="Encode", total=(len(texts)+batch_size-1)//batch_size)
    dim = None
    written = 0
    all_vecs = None

    for start in pbar:
        batch = texts[start:start+batch_size]
        emb = st_model.encode(batch, convert_to_numpy=True, batch_size=batch_size, show_progress_bar=False)
        if dim is None:
            dim = emb.shape[1]
            if out_memmap is not None:
                out_memmap.parent.mkdir(parents=True, exist_ok=True)
                all_vecs = np.memmap(out_memmap, dtype=dtype, mode="w+", shape=(len(texts), dim))
        if out_memmap is not None:
            all_vecs[written:written+emb.shape[0]] = emb.astype(dtype, copy=False)
            written += emb.shape[0]
        else:
            vecs.append(emb)

    if out_memmap is not None:
        all_vecs.flush()
        X = np.memmap(out_memmap, dtype=dtype, mode="r", shape=(len(texts), dim))
        return X, st_model
    X = np.vstack(vecs).astype(dtype, copy=False) if vecs else np.zeros((0, dim or 0), dtype=dtype)
    return X, st_model


class LinearHead(nn.Module):
    def __init__(self, in_dim: int, num_classes: int):
        super().__init__()
        self.fc = nn.Linear(in_dim, num_classes)

    def forward(self, x):
        return self.fc(x)


class TorchLinearSklearnLike:
    # CPU-safe, portable wrapper (numpy-serialized weights)
    def __init__(self, in_dim: int, num_classes: int, state_dict: Dict[str, torch.Tensor], device: str = "auto"):
        self.in_dim = int(in_dim)
        self.num_classes = int(num_classes)
        self.state_dict_cpu = {k: v.detach().cpu() for k, v in state_dict.items()}
        self.device_pref = device
        self._device_actual = None
        self._model = None

    def __getstate__(self):
        state_np = {k: v.detach().cpu().numpy() for k, v in self.state_dict_cpu.items()}
        return {
            "in_dim": self.in_dim,
            "num_classes": self.num_classes,
            "device_pref": self.device_pref,
            "state_np": state_np,
        }

    def __setstate__(self, state):
        self.in_dim = int(state.get("in_dim"))
        self.num_classes = int(state.get("num_classes"))
        self.device_pref = state.get("device_pref", "auto")
        self._device_actual = None
        self._model = None
        sd = {}
        if "state_np" in state and isinstance(state["state_np"], dict):
            for k, arr in state["state_np"].items():
                sd[k] = torch.from_numpy(np.asarray(arr)).to("cpu")
        elif "state_dict_cpu" in state and isinstance(state["state_dict_cpu"], dict):
            for k, v in state["state_dict_cpu"].items():
                try:
                    sd[k] = v.detach().cpu()
                except Exception:
                    if isinstance(v, np.ndarray):
                        sd[k] = torch.from_numpy(v).to("cpu")
        self.state_dict_cpu = sd

    def _ensure_model(self):
        dev = pick_device(self.device_pref)
        if (self._model is None) or (self._device_actual != dev):
            m = LinearHead(self.in_dim, self.num_classes)
            m.load_state_dict(self.state_dict_cpu)
            m.to(dev)
            m.eval()
            self._model = m
            self._device_actual = dev

    @torch.inference_mode()
    def predict_proba(self, X: np.ndarray, batch: int = 4096) -> np.ndarray:
        self._ensure_model()
        X = np.asarray(X, dtype=np.float32, order="C")
        ds = TensorDataset(torch.from_numpy(X))
        dl = DataLoader(ds, batch_size=batch, shuffle=False)
        out = []
        for (xb,) in dl:
            xb = xb.to(self._device_actual, dtype=torch.float32)
            logits = self._model(xb)
            proba = torch.softmax(logits, dim=1).cpu().numpy()
            out.append(proba)
        return np.concatenate(out, axis=0)



def train_linear_gpu(
    Xtr: np.ndarray,
    ytr: np.ndarray,
    Xva: np.ndarray,
    yva: np.ndarray,
    device: str = "auto",
    epochs: int = 5,
    batch: int = 2048,
    lr: float = 1e-3,
    weight_decay: float = 1e-4,
) -> Tuple[TorchLinearSklearnLike, np.ndarray, np.ndarray]:
    """
    Train a linear classifier on top of frozen sentence-transformer embeddings.

    Uses AdamW optimizer + CosineAnnealingLR scheduler for better generalization.
    Returns a TorchLinearSklearnLike wrapper along with validation predictions and probabilities.
    """
    dev = pick_device(device)
    in_dim = Xtr.shape[1]
    num_classes = int(np.max(ytr) + 1)

    model = LinearHead(in_dim, num_classes).to(dev)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=max(1, epochs))
    loss_fn = nn.CrossEntropyLoss()

    tr_ds = TensorDataset(torch.from_numpy(Xtr), torch.from_numpy(ytr))
    tr_dl = DataLoader(tr_ds, batch_size=batch, shuffle=True, drop_last=False)

    model.train()
    for _epoch in range(epochs):
        for xb, yb in tr_dl:
            xb = xb.to(dev, dtype=torch.float32)
            yb = yb.to(dev, dtype=torch.long)
            logits = model(xb)
            loss = loss_fn(logits, yb)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            opt.step()
        scheduler.step()

    wrapper = TorchLinearSklearnLike(in_dim, num_classes, model.state_dict(), device=device)
    proba_va = wrapper.predict_proba(Xva)
    preds_va = proba_va.argmax(1)
    return wrapper, preds_va, proba_va


def topk_accuracy(proba: np.ndarray, y_true: np.ndarray, k: int = 3) -> float:
    order = np.argsort(-proba, axis=1)[:, :k]
    hits = sum(yi in order[i] for i, yi in enumerate(y_true))
    return hits / max(1, len(y_true))


def train_pipeline(
    df: pd.DataFrame,
    artifacts_dir: str = "artifacts_best",
    st_model_name: str = "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
    device: str = "auto",
    max_rows: Optional[int] = None,
    text_col: str = "text_obr",
    cat_col: str = "category",
    issue_col: str = "issue",
    sub_col: str = "subissue",
    grade_col: str = "grade",
    use_grade_filter: bool = True,
    min_subissue_count: int = 3,
    top_keep_per_issue: int = 5,
    router_epochs: int = 9,
    head_epochs: int = 6,
    router_lr: float = 0.004983813273703727,
    head_lr: float = 0.003315066871660275,
    batch_encode: int = 128,
    batch_torch: int = 512,
    val_size: float = 0.05,
    test_size: float = 0.05,
    random_state: int = 42,
) -> Dict:
    out = Path(artifacts_dir)
    out.mkdir(parents=True, exist_ok=True)

    before = len(df)
    if use_grade_filter and grade_col in df.columns:
        df = df.copy()
        df[grade_col] = pd.to_numeric(df[grade_col], errors="coerce")
        df = df[df[grade_col].isin([4, 5])]
        log(f"[info] grade filter 4/5: {before} -> {len(df)} rows")
    else:
        log(f"[info] grade filter skipped: {before} rows")

    df = drop_empty_texts(df, text_col=text_col)

    df, _ = ensure_unique_level3_names(df, sub_col=sub_col, issue_col=issue_col, out_col="subissue_unique")
    df, _ = group_lowfreq_subissues(
        df,
        min_count=min_subissue_count,
        top_keep_per_issue=top_keep_per_issue,
        col_cat=cat_col,
        col_issue=issue_col,
        col_subu="subissue_unique",
    )

    if max_rows and len(df) > max_rows:
        df = df.sample(n=int(max_rows), random_state=random_state).copy()
        log(f"[info] sample: down to {len(df)} rows")

    texts = df[text_col].astype(str).apply(basic_clean).tolist()
    X, st_model = encode_texts_st(
        texts,
        model_name_or_dir=st_model_name,
        device=device,
        batch_size=batch_encode,
        out_memmap=None,
        dtype="float32",
    )

    st_dir = out / "st_model"
    if not st_dir.exists():
        st_dir.mkdir(parents=True, exist_ok=True)
        st_model.save(str(st_dir))
    meta = {
        "st_model": st_model_name,
        "device": pick_device(device),
        "min_subissue_count": int(min_subissue_count),
        "top_keep_per_issue": int(top_keep_per_issue),
    }
    (out / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    # Router (L1): category
    y_cat_raw = df[cat_col].astype(str).tolist()
    le_cat = LabelEncoder().fit(y_cat_raw)
    y_cat = le_cat.transform(y_cat_raw)

    # 90/5/5 split for router: 90% train, 5% val, 5% test
    holdout_size = float(val_size + test_size)
    if holdout_size <= 0 or holdout_size >= 1.0:
        raise ValueError(f"Invalid val/test sizes: val_size={val_size}, test_size={test_size}")

    Xtr, Xhold, ytr, yhold = train_test_split(
        X,
        y_cat,
        test_size=holdout_size,
        random_state=random_state,
        stratify=y_cat,
    )

    # For very tiny holdout sets, fall back to using the same data for val & test
    if len(yhold) < 2 or test_size <= 0 or val_size <= 0:
        Xva, yva = Xhold, yhold
        Xte, yte = Xhold, yhold
    else:
        test_ratio_within_hold = float(test_size) / holdout_size
        Xva, Xte, yva, yte = train_test_split(
            Xhold,
            yhold,
            test_size=test_ratio_within_hold,
            random_state=random_state,
        )

    clf_router, preds_va, proba_va = train_linear_gpu(
        Xtr,
        ytr,
        Xva,
        yva,
        device=device,
        epochs=router_epochs,
        batch=batch_torch,
        lr=router_lr,
        weight_decay=1e-4,
    )
    top1_val = accuracy_score(yva, preds_va)
    top3_val = topk_accuracy(proba_va, yva, k=3)

    proba_te = clf_router.predict_proba(Xte)
    preds_te = proba_te.argmax(1)
    top1_test = accuracy_score(yte, preds_te)
    top3_test = topk_accuracy(proba_te, yte, k=3)

    stats_cat = {
        "val_top1_acc": float(top1_val),
        "val_top3_acc": float(top3_val),
        "test_top1_acc": float(top1_test),
        "test_top3_acc": float(top3_test),
    }
    log(
        "[router] "
        f"val top1={stats_cat['val_top1_acc']:.4f} | "
        f"val top3={stats_cat['val_top3_acc']:.4f} | "
        f"test top1={stats_cat['test_top1_acc']:.4f} | "
        f"test top3={stats_cat['test_top3_acc']:.4f}"
    )

    joblib.dump(clf_router, out / "cat_router.joblib")
    joblib.dump(le_cat, out / "cat_label_encoder.joblib")
    (out / "cat_stats.json").write_text(json.dumps(stats_cat, ensure_ascii=False, indent=2), encoding="utf-8")

    # Per-category heads
    models_root = out / "models"
    models_root.mkdir(parents=True, exist_ok=True)

    comp_label = (df[issue_col].astype(str) + "__SEP__" + df["subissue_unique"].astype(str)).tolist()
    keep_categories = sorted(le_cat.classes_.tolist())
    saved = []
    cat_dirnames: Dict[str, str] = {}

    for cat_text in tqdm(keep_categories, desc="[train] per-category heads"):
        mask = (df[cat_col].astype(str) == cat_text)
        idx = np.where(mask.values)[0]
        if len(idx) < 2:
            continue
        Xc = X[idx]
        yc_raw = [comp_label[i] for i in idx]

        # drop too-rare labels (need >=2 for stratify)
        vc = pd.Series(yc_raw).value_counts()
        ok = set(vc[vc >= 2].index)
        if len(ok) < 2:
            # single-class head
            dummy_state = LinearHead(Xc.shape[1], 1).state_dict()
            clf_c = TorchLinearSklearnLike(Xc.shape[1], 1, dummy_state, device="auto")
            cat_folder = safe_key(cat_text)
            cat_dir = models_root / cat_folder
            cat_dir.mkdir(parents=True, exist_ok=True)
            joblib.dump(clf_c, cat_dir / "clf.joblib")
            le_c = LabelEncoder().fit(["__single__"])
            joblib.dump(le_c, cat_dir / "label_encoder.joblib")
            (cat_dir / "stats.json").write_text(json.dumps({"note": "single-class head"}, ensure_ascii=False, indent=2), encoding="utf-8")
            saved.append(cat_text)
            cat_dirnames[cat_text] = cat_folder
            continue

        mask_valid = np.array([y in ok for y in yc_raw])
        Xc = Xc[mask_valid]
        yc_raw = [y for y in yc_raw if y in ok]

        le_c = LabelEncoder().fit(yc_raw)
        yc = le_c.transform(yc_raw)
        if len(le_c.classes_) < 2:
            dummy_state = LinearHead(Xc.shape[1], 1).state_dict()
            clf_c = TorchLinearSklearnLike(Xc.shape[1], 1, dummy_state, device="auto")
            cat_folder = safe_key(cat_text)
            cat_dir = models_root / cat_folder
            cat_dir.mkdir(parents=True, exist_ok=True)
            joblib.dump(clf_c, cat_dir / "clf.joblib")
            joblib.dump(le_c, cat_dir / "label_encoder.joblib")
            (cat_dir / "stats.json").write_text(json.dumps({"note": "single-class head"}, ensure_ascii=False, indent=2), encoding="utf-8")
            saved.append(cat_text)
            cat_dirnames[cat_text] = cat_folder
            continue

        # 90/5/5 split for this category head: 90% train, 5% val, 5% test
        holdout_size = float(val_size + test_size)
        if holdout_size <= 0 or holdout_size >= 1.0:
            raise ValueError(f"Invalid val/test sizes: val_size={val_size}, test_size={test_size}")

        Xtr, Xhold, ytr, yhold = train_test_split(
            Xc,
            yc,
            test_size=holdout_size,
            random_state=random_state,
            stratify=yc,
        )

        # Tiny holdout fallback: re-use the same data for val & test
        if len(yhold) < 2 or test_size <= 0 or val_size <= 0:
            Xva, yva = Xhold, yhold
            Xte, yte = Xhold, yhold
        else:
            test_ratio_within_hold = float(test_size) / holdout_size
            Xva, Xte, yva, yte = train_test_split(
                Xhold,
                yhold,
                test_size=test_ratio_within_hold,
                random_state=random_state,
            )

        clf_c, preds_va, proba_va = train_linear_gpu(
            Xtr,
            ytr,
            Xva,
            yva,
            device=device,
            epochs=head_epochs,
            batch=batch_torch,
            lr=head_lr,
            weight_decay=1e-4,
        )
        acc_val = accuracy_score(yva, preds_va)
        top3_val = topk_accuracy(proba_va, yva, k=3)

        proba_te = clf_c.predict_proba(Xte)
        preds_te = proba_te.argmax(1)
        acc_test = accuracy_score(yte, preds_te)
        top3_test = topk_accuracy(proba_te, yte, k=3)

        stats_c = {
            "val_top1_acc": float(acc_val),
            "val_top3_acc": float(top3_val),
            "test_top1_acc": float(acc_test),
            "test_top3_acc": float(top3_test),
        }

        log(
            f"[head:{cat_text}] "
            f"val top1={stats_c['val_top1_acc']:.4f} | "
            f"val top3={stats_c['val_top3_acc']:.4f} | "
            f"test top1={stats_c['test_top1_acc']:.4f} | "
            f"test top3={stats_c['test_top3_acc']:.4f}"
        )

        cat_folder = safe_key(cat_text)
        cat_dir = models_root / cat_folder
        cat_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(clf_c, cat_dir / "clf.joblib")
        joblib.dump(le_c, cat_dir / "label_encoder.joblib")
        (cat_dir / "stats.json").write_text(json.dumps(stats_c, ensure_ascii=False, indent=2), encoding="utf-8")
        saved.append(cat_text)
        cat_dirnames[cat_text] = cat_folder

    mapping = {
        "subissue_unique_rule": "subissue -> subissue ⟨issue⟩ when ambiguous across different issues",
        "kept_categories": keep_categories,
        "heads_saved": saved,
        "cat_dirnames": cat_dirnames,
    }
    (out / "mapping.json").write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "artifacts_dir": str(out),
        "router_val_top1": stats_cat["val_top1_acc"],
        "router_val_top3": stats_cat["val_top3_acc"],
        "router_test_top1": stats_cat["test_top1_acc"],
        "router_test_top3": stats_cat["test_top3_acc"],
        "kept_categories": keep_categories,
        "heads_saved": saved,
    }



def optuna_objective(trial, df: pd.DataFrame, args) -> float:
    """
    Optuna objective function.

    For each trial:
      * samples router/head learning rates, epochs and batch size
      * runs full hierarchical train_pipeline with these hyperparameters
      * returns router_val_top1 (category-level validation accuracy) as the optimization metric
    """
    # Suggest hyperparameters
    router_lr = trial.suggest_float("router_lr", 5e-5, 5e-3, log=True)
    head_lr = trial.suggest_float("head_lr", 5e-5, 5e-3, log=True)
    router_epochs = trial.suggest_int("router_epochs", 3, 10)
    head_epochs = trial.suggest_int("head_epochs", 3, 10)
    batch_torch = trial.suggest_categorical("batch_torch", [512, 1024, 2048, 4096])

    # Each trial writes its artifacts into a separate folder
    trial_artifacts_dir = f"{args.artifacts}_trial_{trial.number}"

    artifacts = train_pipeline(
        df=df.copy(),
        artifacts_dir=trial_artifacts_dir,
        st_model_name=args.st_model,
        device=args.device,
        max_rows=args.max_rows,
        text_col="text_obr",
        cat_col="category",
        issue_col="issue",
        sub_col="subissue",
        grade_col="grade",
        use_grade_filter=(not args.no_grade_filter),
        min_subissue_count=args.min_subissue_count,
        top_keep_per_issue=args.top_keep_per_issue,
        router_epochs=router_epochs,
        head_epochs=head_epochs,
        router_lr=router_lr,
        head_lr=head_lr,
        batch_encode=args.batch_encode,
        batch_torch=batch_torch,
        val_size=args.val_size,
        test_size=args.test_size,
        random_state=42,
    )

    score = float(artifacts["router_val_top1"])
    log(
        f"[optuna] trial={trial.number} "
        f"score={score:.4f} "
        f"router_lr={router_lr:.2e} head_lr={head_lr:.2e} "
        f"router_epochs={router_epochs} head_epochs={head_epochs} "
        f"batch_torch={batch_torch}"
    )
    return score


def load_df(path: str, sheet: Optional[str] = None) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(path)
    if p.suffix.lower() in [".xlsx", ".xls"]:
        df = pd.read_excel(p, sheet_name=sheet)
    elif p.suffix.lower() == ".csv":
        df = pd.read_csv(p)
    else:
        raise ValueError(f"Unsupported format: {p.suffix}")
    return df



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--sheet", default=0)
    ap.add_argument("--artifacts", default="artifacts_best")
    ap.add_argument("--st_model", default="sentence-transformers/paraphrase-multilingual-mpnet-base-v2")
    ap.add_argument("--device", default="auto", choices=["auto", "cpu", "mps", "cuda"])
    ap.add_argument("--max_rows", type=int, default=None)
    ap.add_argument("--min_subissue_count", type=int, default=3)
    ap.add_argument("--top_keep_per_issue", type=int, default=5)
    ap.add_argument("--router_epochs", type=int, default=9)
    ap.add_argument("--head_epochs", type=int, default=6)
    ap.add_argument("--router_lr", type=float, default=0.004983813273703727)
    ap.add_argument("--head_lr", type=float, default=0.003315066871660275)
    ap.add_argument("--batch_encode", type=int, default=128)
    ap.add_argument("--batch_torch", type=int, default=512)
    ap.add_argument("--val_size", type=float, default=0.05)
    ap.add_argument("--test_size", type=float, default=0.05)
    ap.add_argument("--no_grade_filter", action="store_true")
    # Optuna-related args
    ap.add_argument("--tune", action="store_true", help="Run Optuna hyperparameter search before final training")
    ap.add_argument("--n_trials", type=int, default=20, help="Number of Optuna trials")
    ap.add_argument("--study_name", type=str, default="hier_classifier_tuning", help="Optuna study name")
    ap.add_argument("--storage", type=str, default=None, help="Optuna storage URL (optional, e.g. sqlite:///study.db)")
    args = ap.parse_args()

    df = load_df(args.input, sheet=args.sheet)
    log(f"[info] loaded: {len(df)} rows")

    if args.tune:
        if optuna is None:
            raise RuntimeError(
                "Optuna is not installed. Install it with `pip install optuna` or run without --tune."
            )

        direction = "maximize"
        if args.storage:
            study = optuna.create_study(
                study_name=args.study_name,
                storage=args.storage,
                load_if_exists=True,
                direction=direction,
            )
        else:
            study = optuna.create_study(study_name=args.study_name, direction=direction)

        log(f"[optuna] Starting hyperparameter search: n_trials={args.n_trials}, direction={direction}")
        study.optimize(lambda trial: optuna_objective(trial, df, args), n_trials=args.n_trials)

        best = study.best_trial
        log("[optuna] Best trial:")
        log(f"  value={best.value:.4f}")
        for k, v in best.params.items():
            log(f"  {k}={v}")

        # Train final model with best hyperparameters into the target artifacts folder
        best_router_lr = best.params["router_lr"]
        best_head_lr = best.params["head_lr"]
        best_router_epochs = best.params["router_epochs"]
        best_head_epochs = best.params["head_epochs"]
        best_batch_torch = best.params["batch_torch"]

        log("[optuna] Training final model with best hyperparameters...")
        artifacts = train_pipeline(
            df=df,
            artifacts_dir=args.artifacts,
            st_model_name=args.st_model,
            device=args.device,
            max_rows=args.max_rows,
            text_col="text_obr",
            cat_col="category",
            issue_col="issue",
            sub_col="subissue",
            grade_col="grade",
            use_grade_filter=(not args.no_grade_filter),
            min_subissue_count=args.min_subissue_count,
            top_keep_per_issue=args.top_keep_per_issue,
            router_epochs=best_router_epochs,
            head_epochs=best_head_epochs,
            router_lr=best_router_lr,
            head_lr=best_head_lr,
            batch_encode=args.batch_encode,
            batch_torch=best_batch_torch,
            val_size=args.val_size,
            test_size=args.test_size,
            random_state=42,
        )
    else:
        artifacts = train_pipeline(
            df=df,
            artifacts_dir=args.artifacts,
            st_model_name=args.st_model,
            device=args.device,
            max_rows=args.max_rows,
            text_col="text_obr",
            cat_col="category",
            issue_col="issue",
            sub_col="subissue",
            grade_col="grade",
            use_grade_filter=(not args.no_grade_filter),
            min_subissue_count=args.min_subissue_count,
            top_keep_per_issue=args.top_keep_per_issue,
            router_epochs=args.router_epochs,
            head_epochs=args.head_epochs,
            router_lr=args.router_lr,
            head_lr=args.head_lr,
            batch_encode=args.batch_encode,
            batch_torch=args.batch_torch,
            val_size=args.val_size,
            test_size=args.test_size,
            random_state=42,
        )

    log("\n=== DONE ===")
    log(json.dumps(artifacts, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
