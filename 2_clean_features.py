"""
2_clean_features.py  —  Data Cleaning & Feature Engineering
============================================================
Reads raw CSVs, parses dates, classifies injuries by severity
and body part, computes 20+ features per player, and
calculates a weighted risk score (0-99).

Reads:  data/raw_injuries.csv  +  data/raw_profiles.csv
Writes: data/clean_injuries.csv
        data/player_features.csv
"""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

def load_config(path="config.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)

CFG   = load_config()
PATHS = CFG["paths"]
WGTS  = CFG["risk_weights"]
TIERS = CFG["risk_tiers"]
Path(PATHS["logs_dir"]).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{PATHS['logs_dir']}/clean.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

TODAY               = date.today()
LOOKBACK_12M        = TODAY - timedelta(days=int(CFG["seasons"]["lookback_days"]))
SEASON_START        = date.fromisoformat(CFG["seasons"]["current_season_start"])

# ── Injury classification ─────────────────────────────────────────────────────
SEVERITY_MAP = {
    "severe":   ["acl","cruciate","rupture","fracture","meniscus","disloc","ligament"],
    "moderate": ["hamstring","thigh","groin","knee","hip","calf","ankle","shoulder","muscle"],
    "mild":     ["strain","sprain","bruise","knock","illness","appendix","physical"],
}
BODY_PARTS = {
    "knee":         ["knee","acl","cruciate","meniscus"],
    "hamstring":    ["hamstring","thigh"],
    "ankle":        ["ankle"],
    "foot":         ["foot","feet","plantar","stress fracture"],
    "groin/hip":    ["groin","hip","adductor"],
    "shoulder":     ["shoulder","disloc"],
    "calf":         ["calf"],
    "muscle/other": ["muscle","strain","sprain","bruise","illness","appendix","physical","deficit"],
}

def classify_severity(text):
    t = str(text).lower()
    for sev, kws in SEVERITY_MAP.items():
        if any(k in t for k in kws):
            return sev
    return "unknown"

def classify_body_part(text):
    t = str(text).lower()
    for part, kws in BODY_PARTS.items():
        if any(k in t for k in kws):
            return part
    return "other"

def parse_date(s):
    if not s or str(s).strip() in ("","nan","None","—","-","NaT"):
        return None
    for fmt in ("%Y-%m-%d","%d/%m/%Y","%b %d, %Y","%d %b %Y","%B %d, %Y"):
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            continue
    return None

def safe_int(s, default=0):
    try:
        return int(str(s).replace("+","").replace("-","0").strip())
    except Exception:
        return default

# ── Cleaning ──────────────────────────────────────────────────────────────────
def clean_injuries(df):
    log.info("Cleaning injury records …")
    df = df.copy()
    df["date_from_p"]  = df["date_from"].apply(parse_date)
    df["date_until_p"] = df["date_until"].apply(parse_date)
    df["days_missed_n"]  = df["days_missed"].apply(safe_int)
    df["games_missed_n"] = df["games_missed"].apply(safe_int)
    df["severity"]    = df["injury"].apply(classify_severity)
    df["body_part"]   = df["injury"].apply(classify_body_part)
    df["is_current"]  = df.apply(lambda r: bool(r["date_until_p"] and r["date_until_p"] >= TODAY), axis=1)
    df["in_last_12m"] = df.apply(lambda r: bool(r["date_from_p"]  and r["date_from_p"]  >= LOOKBACK_12M), axis=1)
    df["in_season"]   = df.apply(lambda r: bool(r["date_from_p"]  and r["date_from_p"]  >= SEASON_START), axis=1)
    before = len(df)
    df = df[df["date_from_p"].notna()].reset_index(drop=True)
    log.info(f"  Dropped {before-len(df)} rows with unparseable dates")
    return df.sort_values(["player_name","date_from_p"], ascending=[True,False]).reset_index(drop=True)

# ── Feature engineering ───────────────────────────────────────────────────────
def build_features(inj, prof):
    log.info("Building player feature table …")
    rows = []
    all_players = list(dict.fromkeys(
        prof["player_name"].tolist() + inj["player_name"].tolist()
    ))
    for name in all_players:
        pi = inj[inj["player_name"] == name]
        pp = prof[prof["player_name"] == name]
        if pp.empty:
            club,pos,age,nat,mv,m30,min30 = "Unknown","Unknown",26,"Unknown","Unknown",8,720
        else:
            r   = pp.iloc[0]
            club,pos = str(r.get("club","Unknown")), str(r.get("position","Unknown"))
            age      = safe_int(r.get("age",26), 26)
            nat      = str(r.get("nationality","Unknown"))
            mv       = str(r.get("market_value","Unknown"))
            m30      = safe_int(r.get("matches_last30",8), 8)
            min30    = safe_int(r.get("minutes_last30",720), 720)

        total_inj   = len(pi)
        inj_12m     = int(pi["in_last_12m"].sum())
        inj_season  = int(pi["in_season"].sum())
        days_lost   = int(pi["days_missed_n"].sum())
        games_lost  = int(pi["games_missed_n"].sum())
        avg_days    = round(pi["days_missed_n"].mean(), 1) if total_inj > 0 else 0.0
        severe_n    = int((pi["severity"]=="severe").sum())
        moderate_n  = int((pi["severity"]=="moderate").sum())

        # Current injury
        curr        = pi[pi["is_current"]]
        cur_inj     = curr.iloc[0]["injury"] if not curr.empty else None
        inj_date    = str(curr.iloc[0]["date_from_p"])  if not curr.empty else None
        exp_return  = str(curr.iloc[0]["date_until_p"]) if not curr.empty else None
        days_to_ret = None
        if exp_return and exp_return not in ("None",""):
            try:
                days_to_ret = (date.fromisoformat(exp_return) - TODAY).days
            except Exception:
                pass

        # Recurring
        part_counts     = pi["body_part"].value_counts()
        recurring_parts = part_counts[part_counts >= 2].index.tolist()
        has_recurring   = len(recurring_parts) > 0
        dominant_part   = part_counts.index[0] if not part_counts.empty else "none"

        # Injury frequency per season
        if not pi.empty and pi["date_from_p"].notna().any():
            span_months = max(((pi["date_from_p"].max() - pi["date_from_p"].min()).days / 30.4), 1)
            inj_per_season = round(total_inj / (span_months / 10), 2)
        else:
            inj_per_season = 0.0

        # Days since last injury cleared
        prev = pi[~pi["is_current"]]
        if not prev.empty and prev.iloc[0]["date_until_p"] is not None:
            days_since = (TODAY - prev.iloc[0]["date_until_p"]).days
        else:
            days_since = 999

        load_pct = min(round((min30 / 900) * 100), 100)

        rows.append(dict(
            player_name=name, club=club, position=pos, age=age,
            nationality=nat, market_value=mv,
            matches_last30=m30, minutes_last30=min30, load_pct=load_pct,
            total_injuries=total_inj, injuries_last12m=inj_12m,
            injuries_curr_season=inj_season, severe_injuries=severe_n,
            moderate_injuries=moderate_n, total_days_lost=days_lost,
            total_games_lost=games_lost, avg_days_per_injury=avg_days,
            inj_per_season=inj_per_season, has_recurring=has_recurring,
            recurring_parts=", ".join(recurring_parts),
            dominant_body_part=dominant_part,
            days_since_last_inj=days_since,
            current_injury=cur_inj, injury_date=inj_date,
            expected_return=exp_return, days_until_return=days_to_ret,
            is_currently_injured=cur_inj is not None,
        ))
    return pd.DataFrame(rows)

# ── Risk scoring ──────────────────────────────────────────────────────────────
def compute_risk(df):
    log.info("Computing risk scores …")
    s = pd.Series(0.0, index=df.index)

    # Injuries last 12m (max 4 → full weight)
    s += (df["injuries_last12m"].clip(0,4) / 4) * WGTS["injuries_last_12m"]
    # Career burden (max 12)
    s += (df["total_injuries"].clip(0,12) / 12) * WGTS["career_burden"]
    # Severity (max 3 severe)
    s += (df["severe_injuries"].clip(0,3) / 3) * WGTS["injury_severity"]
    # Workload
    s += (df["load_pct"].clip(0,100) / 100) * WGTS["workload"]
    # Age
    age_thres = CFG["risk_age_thresholds"]
    max_age_pts = WGTS["age"]
    s += df["age"].apply(lambda a:
        max_age_pts     if a >= age_thres["very_high"] else
        max_age_pts*0.7 if a >= age_thres["high"]     else
        max_age_pts*0.4 if a >= age_thres["moderate"] else
        max_age_pts*0.2 if a >= age_thres["normal"]   else
        max_age_pts*0.1
    )
    # Recurring injury
    s += df["has_recurring"].astype(int) * WGTS["recurring_injury"]
    # Recent return (< 30 days)
    s += (df["days_since_last_inj"] < 30).astype(int) * WGTS["recent_return"]

    df["risk_score"] = s.clip(0, 99).round().astype(int)

    def tier(sc):
        if sc >= TIERS["critical"]: return "Critical"
        if sc >= TIERS["high"]:     return "High"
        if sc >= TIERS["moderate"]: return "Moderate"
        return "Low"

    df["risk_tier"] = df["risk_score"].apply(tier)
    return df

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    d = PATHS["data_dir"]
    inj_raw  = pd.read_csv(f"{d}/raw_injuries.csv")
    prof_raw = pd.read_csv(f"{d}/raw_profiles.csv")
    log.info(f"Loaded {len(inj_raw)} injury records, {len(prof_raw)} profiles")

    inj_clean = clean_injuries(inj_raw)
    features  = build_features(inj_clean, prof_raw)
    features  = compute_risk(features)

    inj_clean.to_csv(f"{d}/clean_injuries.csv", index=False)
    features.sort_values("risk_score", ascending=False).to_csv(f"{d}/player_features.csv", index=False)

    log.info(f"\n=== Feature Summary ===")
    log.info(f"  Total players:       {len(features)}")
    log.info(f"  Currently injured:   {features['is_currently_injured'].sum()}")
    log.info(f"  Critical risk (80+): {(features['risk_score']>=80).sum()}")
    log.info(f"  High risk (60-79):   {((features['risk_score']>=60)&(features['risk_score']<80)).sum()}")
    log.info(f"  Moderate  (40-59):   {((features['risk_score']>=40)&(features['risk_score']<60)).sum()}")
    log.info(f"  Low       (<40):     {(features['risk_score']<40).sum()}")
    log.info(f"\n✓  data/clean_injuries.csv")
    log.info(f"✓  data/player_features.csv")

    print("\nTop 10 players by risk score:")
    print(features[["player_name","club","risk_score","risk_tier",
                     "is_currently_injured","injuries_last12m","load_pct"]].head(10).to_string(index=False))

if __name__ == "__main__":
    main()
