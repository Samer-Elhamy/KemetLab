#!/usr/bin/env python3
"""
AutoScientists Kaggle S6E9 Training Runner.
Executes 5-fold cross-validation based on agent hypotheses and prints JSON to stdout.
"""
import os
import sys
import json
import time
import numpy as np
import pandas as pd
from pathlib import Path
from sklearn.metrics import roc_auc_score
import lightgbm as lgb
import xgboost as xgb

DATA_PATH = Path("C:/Users/Samer/kaggle/playground-s6e9/data/folds/train_folds.parquet")

def main():
    if not DATA_PATH.exists():
        print(json.dumps({"error": f"Data not found at {DATA_PATH}", "roc_auc": 0.0}))
        sys.exit(1)

    df_tr = pd.read_parquet(DATA_PATH)
    
    # Hypotheses passed by AutoScientists agents
    exp_id = os.environ.get("EXP_ID", "exp_autoscientist_01")
    model_type = os.environ.get("MODEL_TYPE", "lgbm").lower()
    lr = float(os.environ.get("LR", "0.04"))
    max_depth = int(os.environ.get("MAX_DEPTH", "6"))
    subsample = float(os.environ.get("SUBSAMPLE", "0.8"))
    colsample = float(os.environ.get("COLSAMPLE", "0.75"))
    n_estimators = int(os.environ.get("N_ESTIMATORS", "800"))

    # Feature selection hypothesis
    feature_cols = [c for c in df_tr.columns if c not in ["target", "fold", "id"]]
    use_deotte = os.environ.get("USE_DEOTTE", "1") == "1"

    if use_deotte:
        home = (df_tr["Home_Charging_Possible"] == "Yes").astype(int)
        subsidy = (df_tr["Subsidy_Available"] == "Yes").astype(int)
        df_tr["worry_score"] = df_tr["Daily_Commute_km"] - 5.0 * df_tr["Charging_Stations_Near_Home"] - 5.0 * df_tr["Charging_Stations_Near_Work"] - 150.0 * home
        df_tr["chargers_total"] = df_tr["Charging_Stations_Near_Home"] + df_tr["Charging_Stations_Near_Work"]
        df_tr["income_x_subsidy"] = (df_tr["Annual_Income_USD"] / 1e5) * subsidy
        feature_cols.extend(["worry_score", "chargers_total", "income_x_subsidy"])

    # Categorical handling
    for c in feature_cols:
        if df_tr[c].dtype.kind in ("O", "S", "U") or str(df_tr[c].dtype) in ("str", "string", "object", "category"):
            df_tr[c] = df_tr[c].astype("category")

    # Triple Sklearn Target Encoding hypothesis
    use_triple_te = os.environ.get("USE_TRIPLE_TE", "1") == "1"
    if use_triple_te:
        from sklearn.preprocessing import TargetEncoder
        key_cols = [c for c in ["City_Type", "Current_Car_Type", "Home_Charging_Possible", "Subsidy_Available", "Range_Anxiety_Level"] if c in df_tr.columns]
        for smooth_val, tag in [("auto", "auto"), (10.0, "10"), (100.0, "100")]:
            te = TargetEncoder(shuffle=True, cv=5, smooth=smooth_val, random_state=42)
            encoded = te.fit_transform(df_tr[key_cols], df_tr["target"])
            for idx, k in enumerate(key_cols):
                col_name = f"{k}_te_{tag}"
                df_tr[col_name] = encoded[:, idx].astype(np.float32)
                feature_cols.append(col_name)

    n_splits = 5
    oof_preds = np.zeros(len(df_tr))
    y_true = df_tr["target"].values
    t0 = time.time()

    for fold in range(n_splits):
        trn_idx = df_tr["fold"] != fold
        val_idx = df_tr["fold"] == fold

        X_tr, y_tr = df_tr.loc[trn_idx, feature_cols], y_true[trn_idx]
        X_va, y_va = df_tr.loc[val_idx, feature_cols], y_true[val_idx]

        if model_type == "xgboost":
            clf = xgb.XGBClassifier(
                n_estimators=n_estimators,
                learning_rate=lr,
                max_depth=max_depth,
                subsample=subsample,
                colsample_bytree=colsample,
                tree_method="hist",
                device="cuda",
                enable_categorical=True,
                eval_metric="auc",
                random_state=42
            )
            clf.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], verbose=False)
            oof_preds[val_idx] = clf.predict_proba(X_va)[:, 1]
        else:
            clf = lgb.LGBMClassifier(
                n_estimators=n_estimators,
                learning_rate=lr,
                max_depth=max_depth,
                num_leaves=2 ** min(max_depth, 7) - 1,
                subsample=subsample,
                colsample_bytree=colsample,
                random_state=42,
                n_jobs=-1,
                verbose=-1
            )
            clf.fit(X_tr, y_tr, eval_set=[(X_va, y_va)], callbacks=[lgb.early_stopping(40, verbose=False)])
            oof_preds[val_idx] = clf.predict_proba(X_va)[:, 1]

    score = float(roc_auc_score(y_true, oof_preds))
    elapsed = time.time() - t0

    result = {
        "val_loss": round(1.0 - score, 5),
        "roc_auc": round(score, 5),
        "exp_id": exp_id,
        "model": model_type,
        "params": {
            "lr": lr,
            "max_depth": max_depth,
            "subsample": subsample,
            "colsample": colsample,
            "n_estimators": n_estimators,
            "use_deotte": use_deotte
        },
        "features_count": len(feature_cols),
        "elapsed_seconds": round(elapsed, 2)
    }

    # Standard AutoScientists output
    print(json.dumps(result))
    sys.exit(0)

if __name__ == "__main__":
    main()
