"""
4_report.py  —  Report Generator
==================================
Reads predictions + prediction log, produces clean CSV/JSON reports
and a human-readable summary.

Reads:   data/predictions.csv
         data/prediction_log.json
Writes:  outputs/report_injured.csv
         outputs/report_risk_watch.csv
         outputs/report_full.csv
         outputs/report_accuracy.json
         outputs/report_summary.txt

Usage:
    python 4_report.py
    python 4_report.py --json   # also write JSON versions
"""

import json, logging
from datetime import date
from pathlib import Path

import pandas as pd, yaml

def load_config(path="config.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)

CFG   = load_config()
PATHS = CFG["paths"]
RCFG  = CFG["report"]
Path(PATHS["logs_dir"]).mkdir(parents=True, exist_ok=True)
Path(PATHS["outputs_dir"]).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{PATHS['logs_dir']}/report.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)
TODAY = date.today()

def load_all():
    d    = PATHS["data_dir"]
    preds = pd.read_csv(f"{d}/predictions.csv")
    feats = pd.read_csv(f"{d}/player_features.csv")
    pl    = Path(f"{d}/prediction_log.json")
    plog  = json.loads(pl.read_text()) if pl.exists() else []
    return preds, feats, plog

def is_injured(row):
    v = str(row.get("current_injury",""))
    return v not in ("","nan","None","NaN")

def fmt_return(row):
    ret  = str(row.get("expected_return",""))
    days = row.get("days_until_return")
    if ret in ("","nan","None","NaN"):
        return "Unknown"
    try:
        d = int(days)
        if d < 0:
            return f"{ret} (overdue {-d}d)"
        return f"{ret} (in {d}d)"
    except Exception:
        return ret

def build_injured_report(preds, feats):
    mask  = preds.apply(is_injured, axis=1)
    inj   = preds[mask].copy()
    inj   = inj.merge(feats[["player_name","total_injuries","total_days_lost",
                               "has_recurring","recurring_parts","dominant_body_part"]],
                      on="player_name", how="left")
    inj["return_info"] = inj.apply(fmt_return, axis=1)
    cols = ["player_name","club","position","age","current_injury",
            "injury_date","return_info","risk_score","risk_tier",
            "injuries_last12m","total_injuries","total_days_lost",
            "has_recurring","dominant_body_part"]
    return inj[[c for c in cols if c in inj.columns]].sort_values("risk_score",ascending=False).reset_index(drop=True)

def build_risk_report(preds, feats):
    mask  = ~preds.apply(is_injured, axis=1)
    fit   = preds[mask].copy()
    fit   = fit.merge(feats[["player_name","inj_per_season","severe_injuries",
                               "recurring_parts","dominant_body_part"]],
                      on="player_name", how="left")
    cols  = ["player_name","club","position","age","risk_score","risk_tier",
             "ml_predicted_tier","predicted_injury_window","recommendation",
             "injuries_last12m","load_pct","days_since_last_inj",
             "inj_per_season","severe_injuries","dominant_body_part"]
    return fit[[c for c in cols if c in fit.columns]].sort_values("risk_score",ascending=False).reset_index(drop=True)

def build_accuracy(plog):
    verified = [e for e in plog if e.get("outcome")]
    pending  = [e for e in plog if not e.get("outcome")]
    if not verified:
        return dict(total=len(plog),verified=0,correct=0,wrong=0,accuracy_pct=None,pending=len(pending),by_tier={})
    correct = sum(1 for e in verified if e["outcome"]=="correct")
    wrong   = len(verified) - correct
    by_tier = {}
    for tier in ["Critical","High","Moderate","Low"]:
        tv = [e for e in verified if e.get("ml_predicted_tier")==tier]
        if tv:
            tc = sum(1 for e in tv if e["outcome"]=="correct")
            by_tier[tier] = dict(total=len(tv),correct=tc,accuracy_pct=round(tc/len(tv)*100,1))
    return dict(total=len(plog),verified=len(verified),correct=correct,wrong=wrong,
                accuracy_pct=round(correct/len(verified)*100,1),pending=len(pending),
                by_tier=by_tier,report_date=str(TODAY))

def write_summary(injured, risk, acc):
    n_risk = RCFG.get("top_n_risk_watch", 15)
    lines  = [
        "FOOTBALL INJURY INTELLIGENCE",
        f"Report generated: {TODAY.strftime('%A, %d %B %Y')}",
        "="*60, "",
        f"CURRENTLY INJURED  ({len(injured)} players)",
        "-"*60,
    ]
    if injured.empty:
        lines.append("  No players currently injured.")
    else:
        for _,r in injured.iterrows():
            lines.append(f"  {r['player_name']:<26}  {r['club']:<16}  "
                         f"{str(r.get('current_injury','')):<25}  Return: {r.get('return_info','?')}")
    lines += ["", f"RISK WATCH — Top {n_risk} Fit Players", "-"*60]
    for _,r in risk.head(n_risk).iterrows():
        lines.append(f"  {r['player_name']:<26}  {r['club']:<16}  "
                     f"Score {int(r['risk_score']):>2}/100  ({r['risk_tier']:<8})  "
                     f"→  {r['recommendation']}")
    lines += ["", "PREDICTION ACCURACY", "-"*60]
    if not acc["verified"]:
        lines += ["  No verified predictions yet.",
                  "  Run: python 5_cli.py verify"]
    else:
        lines.append(f"  Verified: {acc['verified']}  |  Correct: {acc['correct']}  |  "
                     f"Accuracy: {acc['accuracy_pct']}%  |  Pending: {acc['pending']}")
        if acc["by_tier"]:
            for tier,s in acc["by_tier"].items():
                lines.append(f"    {tier:<10}: {s['accuracy_pct']}% ({s['correct']}/{s['total']})")
    lines += ["","="*60]
    return "\n".join(lines)

def main(also_json=False):
    preds, feats, plog = load_all()
    injured = build_injured_report(preds, feats)
    risk    = build_risk_report(preds, feats)
    acc     = build_accuracy(plog)
    o       = PATHS["outputs_dir"]

    injured.to_csv(f"{o}/report_injured.csv", index=False)
    risk.to_csv(f"{o}/report_risk_watch.csv", index=False)
    preds.to_csv(f"{o}/report_full.csv", index=False)
    Path(f"{o}/report_accuracy.json").write_text(json.dumps(acc, indent=2))

    summary = write_summary(injured, risk, acc)
    Path(f"{o}/report_summary.txt").write_text(summary, encoding="utf-8")

    if also_json or RCFG.get("also_write_json"):
        injured.to_json(f"{o}/report_injured.json", orient="records", indent=2)
        risk.to_json(f"{o}/report_risk_watch.json", orient="records", indent=2)

    print(summary)
    log.info(f"✓  Reports saved to {o}/")

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    main(also_json=args.json)
