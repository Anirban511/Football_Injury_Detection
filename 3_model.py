"""
3_model.py  —  Injury Risk ML Model
======================================
Trains a Gradient Boosting classifier on player feature vectors,
generates injury risk predictions with probability scores and
injury windows, and persists predictions to the JSON log for
future accuracy verification.

Reads:   data/player_features.csv  +  config.yaml
Writes:  models/risk_model.pkl
         data/predictions.csv
         data/prediction_log.json   (append-only log)

Usage:
    python 3_model.py                 # train if no model exists, then predict
    python 3_model.py --force-retrain # always retrain from scratch
"""

import argparse, json, logging, warnings
from datetime import date
from pathlib import Path

import joblib, numpy as np, pandas as pd, yaml
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.model_selection import cross_val_score, StratifiedKFold
from sklearn.metrics import classification_report

warnings.filterwarnings("ignore")

def load_config(path="config.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)

CFG      = load_config()
PATHS    = CFG["paths"]
MCFG     = CFG["model"]
TIERS    = CFG["risk_tiers"]
WINDOWS  = CFG["prediction_windows"]
Path(PATHS["logs_dir"]).mkdir(parents=True, exist_ok=True)
Path(PATHS["models_dir"]).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{PATHS['logs_dir']}/model.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

TODAY     = date.today()
MODEL_PATH = f"{PATHS['models_dir']}/risk_model.pkl"
PRED_LOG   = f"{PATHS['data_dir']}/prediction_log.json"

FEATURE_COLS = [
    "age","load_pct","injuries_last12m","total_injuries",
    "severe_injuries","moderate_injuries","total_days_lost",
    "avg_days_per_injury","inj_per_season","has_recurring",
    "days_since_last_inj","is_currently_injured",
    "matches_last30","minutes_last30","injuries_curr_season",
    "position_enc",
]
POSITION_MAP = {"FW":3,"MF":2,"DF":1,"GK":0,"Unknown":1}

def prepare_X(df):
    X = df.copy()
    X["has_recurring"]        = X["has_recurring"].astype(int)
    X["is_currently_injured"] = X["is_currently_injured"].astype(int)
    X["position_enc"]         = df["position"].map(POSITION_MAP).fillna(1)
    X["days_since_last_inj"]  = X["days_since_last_inj"].clip(0,365)
    missing = [c for c in FEATURE_COLS if c not in X.columns]
    for c in missing:
        X[c] = 0
    return X[FEATURE_COLS].fillna(0).values

def risk_score_to_tier(s):
    if s >= TIERS["critical"]: return "Critical"
    if s >= TIERS["high"]:     return "High"
    if s >= TIERS["moderate"]: return "Moderate"
    return "Low"

def build_training_data(df):
    """
    Build synthetic training labels from rule-based risk scores.
    Replace this with real outcome data once prediction_log.json
    has enough verified entries (run: python 5_cli.py verify).
    """
    log.info("Building training data from rule-based risk scores …")
    Xrows, ylabels = [], []
    X = prepare_X(df)
    scores = df["risk_score"].values
    for i, score in enumerate(scores):
        label = risk_score_to_tier(score)
        n_aug = MCFG["augmentation_copies"]
        noise  = MCFG["augmentation_noise"]
        Xrows.append(X[i])
        ylabels.append(label)
        for _ in range(n_aug):
            Xrows.append(np.clip(X[i] + np.random.normal(0, noise, X[i].shape), 0, None))
            ylabels.append(label)
    return np.array(Xrows), np.array(ylabels)

def train(X, y):
    algo = MCFG["algorithm"]
    if algo == "random_forest":
        model = RandomForestClassifier(
            n_estimators=MCFG["n_estimators"],
            max_depth=MCFG["max_depth"],
            random_state=MCFG["random_state"],
        )
    else:
        model = GradientBoostingClassifier(
            n_estimators=MCFG["n_estimators"],
            learning_rate=MCFG["learning_rate"],
            max_depth=MCFG["max_depth"],
            min_samples_split=MCFG["min_samples_split"],
            min_samples_leaf=MCFG["min_samples_leaf"],
            subsample=MCFG["subsample"],
            random_state=MCFG["random_state"],
        )
    cv = StratifiedKFold(n_splits=MCFG["cv_folds"], shuffle=True,
                         random_state=MCFG["random_state"])
    cv_scores = cross_val_score(model, X, y, cv=cv, scoring="accuracy")
    log.info(f"  CV Accuracy: {cv_scores.mean():.3f} ± {cv_scores.std():.3f}")
    model.fit(X, y)
    log.info(f"  Train Accuracy: {(model.predict(X)==y).mean():.3f}")
    return model

def feature_importance(model):
    imp  = model.feature_importances_
    pairs = sorted(zip(FEATURE_COLS, imp), key=lambda x: x[1], reverse=True)
    log.info("\nTop feature importances:")
    for feat, val in pairs[:10]:
        bar = "█" * int(val * 50)
        log.info(f"  {feat:<30} {val:.4f}  {bar}")

def injury_window(risk_score, is_injured):
    if is_injured:
        return "Currently injured"
    for w in WINDOWS:
        if risk_score >= w["risk_min"]:
            return w["label"]
    return "Low probability"

def recommendation(risk_score, is_injured, days_until_return):
    if is_injured:
        if days_until_return and not pd.isna(days_until_return):
            d = int(days_until_return)
            return f"Injured — return in {d}d" if d > 0 else "Overdue return — assess fitness"
        return "Injured — return date unknown"
    if risk_score >= 80: return "Rest 2+ matches immediately"
    if risk_score >= 70: return "Rotate — limit to 60% load"
    if risk_score >= 60: return "Monitor; avoid extra time"
    if risk_score >= 40: return "Standard monitoring"
    return "No action required"

def generate_predictions(df, model):
    X  = prepare_X(df)
    pr = model.predict_proba(X)
    classes = model.classes_

    res = df[["player_name","club","position","age","risk_score","risk_tier",
              "current_injury","injury_date","expected_return","days_until_return",
              "injuries_last12m","load_pct","days_since_last_inj",
              "severe_injuries","inj_per_season"]].copy()

    res["ml_predicted_tier"] = model.predict(X)
    for cls in classes:
        idx = list(classes).index(cls)
        res[f"prob_{cls.lower()}"] = np.round(pr[:, idx], 3)

    _NULL = {"", "nan", "none", "null", "NaN", "None", "NAN"}

    def _is_inj(v) -> bool:
        return str(v).strip() not in _NULL

    res["predicted_injury_window"] = [
        injury_window(row.risk_score, _is_inj(row.current_injury))
        for _, row in res.iterrows()
    ]
    res["recommendation"] = [
        recommendation(row.risk_score, _is_inj(row.current_injury), row.days_until_return)
        for _, row in res.iterrows()
    ]
    res["prediction_date"] = str(TODAY)
    res["outcome"]         = None
    res["outcome_date"]    = None
    return res.sort_values("risk_score", ascending=False).reset_index(drop=True)

def append_prediction_log(preds):
    existing = []
    pl = Path(PRED_LOG)
    if pl.exists():
        try:
            existing = json.loads(pl.read_text())
        except Exception:
            existing = []
    pending_names = {e["player_name"] for e in existing if e["outcome"] is None}
    new_entries = preds[[
        "player_name","club","risk_score","ml_predicted_tier",
        "predicted_injury_window","recommendation",
        "prediction_date","outcome","outcome_date",
    ]].to_dict(orient="records")
    added = 0
    for entry in new_entries:
        if entry["player_name"] not in pending_names:
            existing.append(entry)
            added += 1
    pl.write_text(json.dumps(existing, indent=2, default=str))
    log.info(f"  Appended {added} new entries → prediction_log.json  ({len(existing)} total)")

def accuracy_summary():
    pl = Path(PRED_LOG)
    if not pl.exists():
        return
    entries  = json.loads(pl.read_text())
    verified = [e for e in entries if e.get("outcome")]
    if not verified:
        print("\n[Accuracy] No verified predictions yet.")
        print("  Run: python 5_cli.py verify")
        return
    correct = sum(1 for e in verified if e["outcome"] == "correct")
    pct     = round(correct / len(verified) * 100, 1)
    print(f"\n[Accuracy] {correct}/{len(verified)} correct = {pct}%  |  pending: {len(entries)-len(verified)}")

# ── Main ──────────────────────────────────────────────────────────────────────
def main(force_retrain=False):
    d   = PATHS["data_dir"]
    df  = pd.read_csv(f"{d}/player_features.csv")
    log.info(f"Loaded {len(df)} players")

    mp = Path(MODEL_PATH)
    if mp.exists() and not force_retrain:
        log.info(f"Loading existing model from {MODEL_PATH}")
        bundle = joblib.load(MODEL_PATH)
        model  = bundle["model"]
    else:
        log.info(f"Training {MCFG['algorithm']} …")
        X, y = build_training_data(df)
        model = train(X, y)
        feature_importance(model)
        joblib.dump({"model":model,"feature_cols":FEATURE_COLS,"trained":str(TODAY)}, MODEL_PATH)
        log.info(f"✓  Model saved → {MODEL_PATH}")

    preds = generate_predictions(df, model)
    preds.to_csv(f"{d}/predictions.csv", index=False)
    append_prediction_log(preds)
    accuracy_summary()

    log.info(f"\n✓  Predictions saved → {d}/predictions.csv")

    _NULL_SET = {"", "nan", "none", "null", "NaN", "None", "NAN"}
    injured = preds[preds["current_injury"].apply(lambda v: str(v).strip() not in _NULL_SET)]
    print("\n=== Currently Injured ===")
    if injured.empty:
        print("  None")
    else:
        print(injured[["player_name","club","current_injury","expected_return","days_until_return"]].to_string(index=False))

    fit = preds[~preds.index.isin(injured.index)]
    print(f"\n=== Top 10 At-Risk (Fit Players) ===")
    print(fit[["player_name","club","risk_score","ml_predicted_tier",
               "predicted_injury_window","recommendation"]].head(10).to_string(index=False))

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--force-retrain", action="store_true")
    args = ap.parse_args()
    main(force_retrain=args.force_retrain)
