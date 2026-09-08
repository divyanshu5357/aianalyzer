"""
Phase 11: Historical Replay / Shadow Validation

Read-only evaluation of the 2026 calibrated LightGBM model against real CRM
inquiry records extracted from Phase 7 parquet datasets.

Design principles:
  - No DB writes whatsoever.
  - No model retraining.
  - Phase 7 parquet datasets are read-only.
  - Only the 11 approved t0 features are used.
  - Immature 2026 records (observation_days < 97.86, cy_admission=0)
    are NOT treated as confirmed negatives in outcome evaluation.
  - The API prediction path and the direct model path are compared for
    numerical agreement within tolerance.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd

from app.ml.ml_baseline_trainer import DEFAULT_MODEL_DIR
from app.ml.ml_inference_service import (
    FORBIDDEN_LEAKAGE_FIELDS,
    OPTIMAL_F1_THRESHOLD,
    TOP_10_PCT_PROB_CUTOFF,
    TOP_20_PCT_PROB_CUTOFF,
    MLInferenceService,
)
from app.ml.ml_temporal_split import (
    DEFAULT_DATA_DIR,
    PURE_T0_FEATURE_COLUMNS,
    load_temporal_splits,
)

logger = logging.getLogger(__name__)

SNAPSHOT_DATE = "2026-08-24"
MATURITY_DAYS = 97.86


def _load_artifacts() -> Tuple[Any, Any, Any]:
    """Load preprocessor_2026, raw LightGBM, and calibrated model."""
    prep = joblib.load(os.path.join(DEFAULT_MODEL_DIR, "preprocessor_2026.joblib"))
    raw_model = joblib.load(os.path.join(DEFAULT_MODEL_DIR, "model_2026_lightgbm.joblib"))
    cal_model = joblib.load(os.path.join(DEFAULT_MODEL_DIR, "model_2026_lightgbm_calibrated.joblib"))
    return prep, raw_model, cal_model


def _compute_maturity_mask(df: pd.DataFrame, snapshot: str = SNAPSHOT_DATE) -> pd.Series:
    """
    Return boolean mask: True when a record is 'mature' for outcome evaluation.
    Maturity = observation_days >= MATURITY_DAYS, OR cy_admission == 1
    (admitted records are always mature regardless of observation window).
    """
    snap_dt = pd.to_datetime(snapshot)
    raw_ts = pd.to_datetime(df["raw_created_on"].str[:19], errors="coerce")
    obs_days = (snap_dt - raw_ts).dt.total_seconds() / 86400.0
    return (obs_days >= MATURITY_DAYS) | (df["cy_admission"] == 1), obs_days


def _assign_tier(p: float) -> str:
    if p >= TOP_10_PCT_PROB_CUTOFF:
        return "High Priority (Top 10%)"
    if p >= TOP_20_PCT_PROB_CUTOFF:
        return "Standard Priority (Top 20%)"
    return "Low Priority"


def _assign_recommendation(p: float) -> str:
    return "ADMIT_PRIORITY_OUTREACH" if p >= OPTIMAL_F1_THRESHOLD else "STANDARD_NURTURE"


def run_historical_replay(
    sample_size: Optional[int] = None,
    random_seed: int = 42,
    api_cross_check_n: int = 200,
    data_dir: str = DEFAULT_DATA_DIR,
) -> Dict[str, Any]:
    """
    Execute Phase 11 historical replay / shadow validation.

    Parameters
    ----------
    sample_size : int, optional
        Max 2026 records to score. None = all records.
    random_seed : int
        Seed for deterministic sampling when sample_size is set.
    api_cross_check_n : int
        Number of randomly selected records to cross-check API vs direct model.
    data_dir : str
        Path to Phase 7 parquet datasets.

    Returns
    -------
    dict with full replay statistics.
    """
    logger.info("=== Phase 11 Historical Replay Starting ===")

    # ------------------------------------------------------------------ #
    # 1. Load Phase 7 parquet data — read only
    # ------------------------------------------------------------------ #
    df_train, df_val, df_test = load_temporal_splits(data_dir)

    # Combine all 2026 records from all splits
    df_2026 = pd.concat(
        [
            df_train[df_train["academic_year"] == 2026],
            df_val[df_val["academic_year"] == 2026],
            df_test[df_test["academic_year"] == 2026],
        ],
        ignore_index=True,
    )
    total_available = len(df_2026)
    logger.info(f"Total 2026 records available: {total_available:,}")

    if sample_size and sample_size < total_available:
        df_2026 = df_2026.sample(n=sample_size, random_state=random_seed).reset_index(drop=True)
        logger.info(f"Sampled {len(df_2026):,} records for replay.")

    # ------------------------------------------------------------------ #
    # 2. Leakage guardrail: assert no forbidden columns present
    # ------------------------------------------------------------------ #
    df_cols_lower = {c.lower() for c in df_2026.columns}
    leaked = FORBIDDEN_LEAKAGE_FIELDS.intersection(df_cols_lower)
    if leaked:
        raise AssertionError(f"LEAKAGE: forbidden columns found in replay dataset: {leaked}")

    # ------------------------------------------------------------------ #
    # 3. Load model artifacts (direct path — no API overhead for main batch)
    # ------------------------------------------------------------------ #
    prep, raw_model, cal_model = _load_artifacts()

    # ------------------------------------------------------------------ #
    # 4. Direct model batch inference
    # ------------------------------------------------------------------ #
    X = df_2026[PURE_T0_FEATURE_COLUMNS].copy()

    t_start = time.perf_counter()
    X_proc = prep.transform(X)
    probas_cal = cal_model.predict_proba(X_proc)[:, 1]
    probas_raw = raw_model.predict_proba(X_proc)[:, 1]
    batch_latency_s = time.perf_counter() - t_start

    n_total = len(probas_cal)

    # ------------------------------------------------------------------ #
    # 5. Determinism check — same input must produce same output
    # ------------------------------------------------------------------ #
    X_proc2 = prep.transform(X)
    probas_cal2 = cal_model.predict_proba(X_proc2)[:, 1]
    determinism_ok = bool(np.allclose(probas_cal, probas_cal2, atol=1e-9))

    # ------------------------------------------------------------------ #
    # 6. API vs direct cross-check (on api_cross_check_n records)
    # ------------------------------------------------------------------ #
    svc = MLInferenceService()  # singleton
    rng = np.random.default_rng(random_seed)
    cross_idx = rng.choice(n_total, size=min(api_cross_check_n, n_total), replace=False)

    api_probas: List[float] = []
    api_failures: int = 0
    t_api_start = time.perf_counter()

    for idx in cross_idx:
        row = df_2026.iloc[int(idx)]
        payload = {col: (None if pd.isna(row[col]) else row[col]) for col in PURE_T0_FEATURE_COLUMNS}
        try:
            res = svc.predict_single(payload)
            api_probas.append(res["calibrated_admission_probability"])
        except Exception:
            api_failures += 1
            api_probas.append(float("nan"))

    api_latency_per_call_ms = (time.perf_counter() - t_api_start) / len(cross_idx) * 1000

    direct_cross = probas_cal[cross_idx]
    valid_mask = ~np.isnan(api_probas)
    api_arr = np.array(api_probas)
    mismatch_count = int(
        (~np.isclose(api_arr[valid_mask], direct_cross[valid_mask], atol=1e-4)).sum()
    )
    max_api_diff = float(
        np.abs(api_arr[valid_mask] - direct_cross[valid_mask]).max()
    ) if valid_mask.any() else 0.0

    # ------------------------------------------------------------------ #
    # 7. Summary statistics
    # ------------------------------------------------------------------ #
    prob_valid = probas_cal[~np.isnan(probas_cal)]

    tiers = np.array([_assign_tier(p) for p in probas_cal])
    high_cnt = int((tiers == "High Priority (Top 10%)").sum())
    std_cnt = int((tiers == "Standard Priority (Top 20%)").sum())
    low_cnt = int((tiers == "Low Priority").sum())

    above_threshold = int((probas_cal >= OPTIMAL_F1_THRESHOLD).sum())
    in_top_10 = int((probas_cal >= TOP_10_PCT_PROB_CUTOFF).sum())
    in_top_20 = int((probas_cal >= TOP_20_PCT_PROB_CUTOFF).sum())

    # ------------------------------------------------------------------ #
    # 8. Maturity-gated outcome evaluation
    # ------------------------------------------------------------------ #
    mature_mask, obs_days = _compute_maturity_mask(df_2026)
    df_mature = df_2026[mature_mask].copy()
    probas_mature = probas_cal[mature_mask.values]
    y_mature = df_mature["cy_admission"].values

    outcome_metrics: Dict[str, Any] = {}

    if len(df_mature) >= 100 and y_mature.sum() >= 10:
        from sklearn.metrics import (
            average_precision_score,
            brier_score_loss,
            precision_score,
            recall_score,
            roc_auc_score,
        )

        pr_auc = float(average_precision_score(y_mature, probas_mature))
        roc_auc = float(roc_auc_score(y_mature, probas_mature))
        brier = float(brier_score_loss(y_mature, probas_mature))

        preds_binary = (probas_mature >= OPTIMAL_F1_THRESHOLD).astype(int)
        prec = float(precision_score(y_mature, preds_binary, zero_division=0))
        rec = float(recall_score(y_mature, preds_binary, zero_division=0))

        # Top-10% lift
        top10_n = max(1, int(len(probas_mature) * 0.10))
        top10_idx = np.argsort(probas_mature)[::-1][:top10_n]
        top10_prec = float(y_mature[top10_idx].mean())
        base_rate = float(y_mature.mean())
        top10_lift = top10_prec / base_rate if base_rate > 0 else 1.0

        # Calibration deciles
        decile_rows: List[Dict] = []
        df_cal_check = pd.DataFrame({"p": probas_mature, "y": y_mature})
        try:
            df_cal_check["decile"] = pd.qcut(df_cal_check["p"], q=10, duplicates="drop")
            for _, grp in df_cal_check.groupby("decile", observed=True):
                decile_rows.append({
                    "mean_pred": round(float(grp["p"].mean()), 4),
                    "obs_rate": round(float(grp["y"].mean()), 4),
                    "n": len(grp),
                })
        except Exception:
            pass

        outcome_metrics = {
            "mature_records_used": int(len(df_mature)),
            "mature_admitted": int(y_mature.sum()),
            "base_admission_rate": round(base_rate, 4),
            "pr_auc": round(pr_auc, 4),
            "roc_auc": round(roc_auc, 4),
            "brier_score": round(brier, 4),
            "precision_at_threshold": round(prec, 4),
            "recall_at_threshold": round(rec, 4),
            "top10_precision": round(top10_prec, 4),
            "top10_lift": round(top10_lift, 2),
            "calibration_deciles": decile_rows,
        }
    else:
        outcome_metrics = {
            "mature_records_used": int(len(df_mature)),
            "note": "Insufficient mature records for outcome evaluation",
        }

    # ------------------------------------------------------------------ #
    # 9. Assemble final report
    # ------------------------------------------------------------------ #
    n_success = n_total
    n_fail = 0  # direct model path does not fail on unseen categoricals

    report = {
        # --- Replay scope
        "replay_scope": "2026_crm_inquiry_all_splits_read_only",
        "snapshot_date": SNAPSHOT_DATE,
        "maturity_threshold_days": MATURITY_DAYS,
        "t0_features_used": PURE_T0_FEATURE_COLUMNS,
        "n_t0_features": len(PURE_T0_FEATURE_COLUMNS),
        # --- Volume
        "total_available_2026_records": total_available,
        "records_scored": n_total,
        "prediction_success_count": n_success,
        "prediction_failure_count": n_fail,
        # --- Probability stats
        "prob_min": round(float(prob_valid.min()), 4),
        "prob_max": round(float(prob_valid.max()), 4),
        "prob_mean": round(float(prob_valid.mean()), 4),
        "prob_median": round(float(np.median(prob_valid)), 4),
        "prob_p90": round(float(np.percentile(prob_valid, 90)), 4),
        "prob_p99": round(float(np.percentile(prob_valid, 99)), 4),
        # --- Tier distribution
        "high_priority_count": high_cnt,
        "standard_priority_count": std_cnt,
        "low_priority_count": low_cnt,
        "pct_above_threshold_0_05": round(above_threshold / n_total * 100, 2),
        "pct_in_top_10pct": round(in_top_10 / n_total * 100, 2),
        "pct_in_top_20pct": round(in_top_20 / n_total * 100, 2),
        # --- API vs direct model cross-check
        "api_cross_check_sample_size": len(cross_idx),
        "api_failures": api_failures,
        "api_vs_direct_mismatch_count": mismatch_count,
        "api_vs_direct_max_diff": round(max_api_diff, 8),
        "api_latency_ms_per_call": round(api_latency_per_call_ms, 2),
        # --- Latency
        "batch_inference_latency_s": round(batch_latency_s, 3),
        "avg_latency_ms_per_record": round(batch_latency_s / n_total * 1000, 4),
        # --- Guardrails
        "leakage_guardrail_passed": True,
        "determinism_check_passed": determinism_ok,
        "all_probs_in_01": bool((probas_cal >= 0.0).all() and (probas_cal <= 1.0).all()),
        "model_version": "2026_lightgbm_calibrated_v1",
        "threshold_applied": OPTIMAL_F1_THRESHOLD,
        # --- Mature outcome evaluation
        "outcome_evaluation": outcome_metrics,
    }

    logger.info("=== Phase 11 Historical Replay Complete ===")
    return report
