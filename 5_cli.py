"""
5_cli.py  —  Football Injury Intelligence — Master CLI
=======================================================
Single entry point for every pipeline operation.

COMMANDS
  run              Full pipeline: scrape → clean → model → report
  run --seed-only  Full pipeline without HTTP scraping
  clean            Re-run data cleaning only
  predict          Re-run model + predictions only
  report           Regenerate output reports only
  show injured     Print current injured list
  show risk        Print risk-watch list
  show accuracy    Print accuracy stats
  verify           Interactively record prediction outcomes
  verify --player "Name" --outcome correct|wrong   (non-interactive)
  add              Wizard to add a new player to the database
  accuracy-chart   ASCII accuracy-over-time chart

QUICK START
  python 5_cli.py run --seed-only
"""

import argparse, json, logging, subprocess, sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml
from colorama import Fore, Style, init

init(autoreset=True)

def load_config(path="config.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)

CFG   = load_config()
PATHS = CFG["paths"]
TODAY = str(date.today())
PRED_LOG = f"{PATHS['data_dir']}/prediction_log.json"

# ── Colour helpers ────────────────────────────────────────────────────────────
def risk_colour(score):
    if score >= 80: return Fore.RED
    if score >= 60: return Fore.YELLOW
    if score >= 40: return Fore.CYAN
    return Fore.GREEN

def h(text):  return Style.BRIGHT + text + Style.RESET_ALL
def b(text):  return Fore.BLUE   + text + Style.RESET_ALL
def g(text):  return Fore.GREEN  + text + Style.RESET_ALL
def r(text):  return Fore.RED    + text + Style.RESET_ALL
def y(text):  return Fore.YELLOW + text + Style.RESET_ALL

# ── Pipeline wrappers ─────────────────────────────────────────────────────────
def _run_script(path, extra_args=None):
    cmd = [sys.executable, path] + (extra_args or [])
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print(r(f"  ✗ {path} exited with errors — check logs/"))

def step_scrape(seed_only=False):
    print(b(f"\n[1/4] Scraping data {'(seed only)' if seed_only else '(Transfermarkt)'}…"))
    _run_script("1_scraper.py", ["--seed-only"] if seed_only else [])

def step_clean():
    print(b("\n[2/4] Cleaning & feature engineering…"))
    _run_script("2_clean_features.py")

def step_model(force_retrain=False):
    print(b("\n[3/4] Model training & predictions…"))
    _run_script("3_model.py", ["--force-retrain"] if force_retrain else [])

def step_report(also_json=False):
    print(b("\n[4/4] Generating reports…"))
    _run_script("4_report.py", ["--json"] if also_json else [])

# ── Display ───────────────────────────────────────────────────────────────────
def _require(path, hint):
    if not Path(path).exists():
        print(r(f"File not found: {path}"))
        print(f"  Run: {hint}")
        return False
    return True

def show_injured():
    p = f"{PATHS['outputs_dir']}/report_injured.csv"
    if not _require(p, "python 5_cli.py run --seed-only"): return
    df = pd.read_csv(p)
    sep = "─"*82
    print(f"\n{b(sep)}")
    print(h(f"  CURRENTLY INJURED  ({len(df)} players)   {TODAY}"))
    print(b(sep))
    if df.empty:
        print(g("  No players currently injured."))
        return
    fmt = "  {:<26} {:<16} {:<8} {:<26} {}"
    print(h(fmt.format("Player","Club","Risk","Injury","Expected Return")))
    print("  " + "─"*78)
    for _,r in df.iterrows():
        sc  = int(r.get("risk_score",0))
        c   = risk_colour(sc)
        ret = r.get("return_info", r.get("expected_return","?"))
        inj = str(r.get("current_injury",""))[:25]
        print(c + fmt.format(str(r["player_name"])[:25], str(r.get("club",""))[:15],
                             f"{sc}/100", inj, str(ret)[:30]) + Style.RESET_ALL)
    print()

def show_risk():
    p = f"{PATHS['outputs_dir']}/report_risk_watch.csv"
    if not _require(p, "python 5_cli.py run --seed-only"): return
    df  = pd.read_csv(p)
    top = int(CFG["report"].get("top_n_risk_watch", 15))
    sep = "─"*100
    print(f"\n{b(sep)}")
    print(h(f"  INJURY RISK WATCH — FIT PLAYERS   {TODAY}"))
    print(b(sep))
    fmt = "  {:<26} {:<16} {:<5} {:<10} {:<16} {:<6} {}"
    print(h(fmt.format("Player","Club","Risk","Tier","Window","Load%","Recommendation")))
    print("  " + "─"*96)
    for _,row in df.head(top).iterrows():
        sc = int(row.get("risk_score",0))
        c  = risk_colour(sc)
        print(c + fmt.format(
            str(row["player_name"])[:25], str(row.get("club",""))[:15],
            str(sc), str(row.get("risk_tier",""))[:9],
            str(row.get("predicted_injury_window",""))[:15],
            f"{int(row.get('load_pct',0))}%",
            str(row.get("recommendation",""))[:38],
        ) + Style.RESET_ALL)
    print()

def show_accuracy():
    p = f"{PATHS['outputs_dir']}/report_accuracy.json"
    if not _require(p, "python 5_cli.py report"): return
    acc = json.loads(Path(p).read_text())
    sep = "─"*50
    print(f"\n{b(sep)}")
    print(h("  PREDICTION ACCURACY"))
    print(b(sep))
    print(f"  Total predictions : {acc['total']}")
    print(f"  Verified          : {acc['verified']}")
    if not acc["verified"]:
        print(y("  No verified predictions yet."))
        print("  Run: python 5_cli.py verify")
    else:
        pct = acc["accuracy_pct"]
        col = g if pct >= 60 else y if pct >= 40 else r
        print(f"  Correct           : {acc['correct']}")
        print(f"  Wrong             : {acc['wrong']}")
        print(col(f"  Accuracy          : {pct}%"))
        print(f"  Pending           : {acc['pending']}")
        if acc.get("by_tier"):
            print("\n  By risk tier:")
            for tier,s in acc["by_tier"].items():
                bar = "█" * int(s["accuracy_pct"]/5)
                col2 = risk_colour(80 if tier=="Critical" else 65 if tier=="High" else 45 if tier=="Moderate" else 20)
                print(col2 + f"    {tier:<10}: {s['accuracy_pct']:>5.1f}%  {bar}" + Style.RESET_ALL)
    print()

# ── Prediction log helpers ────────────────────────────────────────────────────
def _load_log():
    pl = Path(PRED_LOG)
    return json.loads(pl.read_text()) if pl.exists() else []

def _save_log(entries):
    Path(PRED_LOG).write_text(json.dumps(entries, indent=2, default=str))

def verify_predictions(player_name=None, outcome=None):
    entries = _load_log()
    pending = [e for e in entries if not e.get("outcome")]
    if player_name:
        pending = [e for e in pending if player_name.lower() in e["player_name"].lower()]
    if not pending:
        print(g("No pending predictions to verify."))
        return
    if outcome:
        if outcome not in ("correct","wrong"):
            print(r("--outcome must be 'correct' or 'wrong'"))
            return
        count = 0
        for e in entries:
            if not e.get("outcome") and (not player_name or player_name.lower() in e["player_name"].lower()):
                e["outcome"] = outcome
                e["outcome_date"] = TODAY
                count += 1
        _save_log(entries)
        print(g(f"✓  Marked {count} prediction(s) as '{outcome}'"))
    else:
        print(b(f"\n{len(pending)} predictions to verify  (q = quit)\n"))
        changed = 0
        for e in pending:
            print(h(f"  {e['player_name']}") + f"  |  {e.get('club','')}  |  "
                  f"Tier: {e.get('ml_predicted_tier','')}  |  "
                  f"Window: {e.get('predicted_injury_window','')}  |  "
                  f"Made: {e.get('prediction_date','')}")
            print(f"  {e.get('recommendation','')}")
            ans = input(y("  Outcome? (correct / wrong / skip / q): ")).strip().lower()
            if ans == "q":
                break
            if ans in ("correct","wrong"):
                e["outcome"] = ans
                e["outcome_date"] = TODAY
                changed += 1
                print(g(f"  ✓ Recorded as '{ans}'\n"))
            else:
                print("  Skipped.\n")
        _save_log(entries)
        print(g(f"Saved {changed} verifications."))

def add_player():
    print(h("\n=== Add New Player ==="))
    name = input("Player name: ").strip()
    if not name:
        print(r("Cancelled.")); return
    data = dict(
        player_name=name,
        club=        input("Club: ").strip() or "Unknown",
        position=    input("Position (FW/MF/DF/GK): ").strip().upper() or "FW",
        age=         input("Age: ").strip() or "26",
        nationality= input("Nationality: ").strip() or "Unknown",
        market_value="Unknown",
        matches_last30= input("Matches last 30d: ").strip() or "8",
        minutes_last30= input("Minutes last 30d: ").strip() or "720",
        source="manual",
    )
    inj_rows = []
    ci = input("Current injury (leave blank if fit): ").strip()
    if ci:
        inj_rows.append(dict(
            player_name=name, tm_id=0, season="25/26", injury=ci,
            date_from=  input("  Injury date (YYYY-MM-DD): ").strip(),
            date_until= input("  Expected return (YYYY-MM-DD): ").strip(),
            days_missed= input("  Days missed (estimate): ").strip() or "21",
            games_missed=input("  Games missed (estimate): ").strip() or "4",
            source="manual",
        ))
    hist = input("Past injuries (comma-separated, e.g. 'Hamstring 2023, Ankle 2022'): ").strip()
    for h_item in (hist.split(",") if hist else []):
        inj_rows.append(dict(
            player_name=name, tm_id=0, season="historical",
            injury=h_item.strip(), date_from="2022-01-01", date_until="2022-02-01",
            days_missed="21", games_missed="4", source="manual",
        ))
    d = PATHS["data_dir"]
    Path(d).mkdir(exist_ok=True)
    for path, df_new in [
        (f"{d}/raw_profiles.csv", pd.DataFrame([data])),
        (f"{d}/raw_injuries.csv", pd.DataFrame(inj_rows) if inj_rows else None),
    ]:
        if df_new is None:
            continue
        existing = pd.read_csv(path) if Path(path).exists() else pd.DataFrame()
        pd.concat([existing, df_new], ignore_index=True).to_csv(path, index=False)
    print(g(f"\n✓  {name} added."))
    print(f"  Next step: {b('python 5_cli.py clean && python 5_cli.py predict')}")

def accuracy_chart():
    entries  = _load_log()
    verified = sorted(
        [e for e in entries if e.get("outcome") and e.get("outcome_date")],
        key=lambda e: e["outcome_date"],
    )
    if len(verified) < 2:
        print(y("Need at least 2 verified predictions for a chart."))
        return
    print(h("\n  Cumulative Prediction Accuracy Over Time"))
    fmt = "  {:<14} {:<14} {:<8} {}"
    print(h(fmt.format("Date","Correct/Total","Accuracy","Chart")))
    print("  " + "─"*56)
    correct = 0
    for i, e in enumerate(verified):
        if e["outcome"] == "correct":
            correct += 1
        pct = correct / (i+1) * 100
        bar = "█" * int(pct/5)
        col = g if pct >= 60 else y if pct >= 40 else r
        print(col(fmt.format(e["outcome_date"], f"{correct}/{i+1}", f"{pct:.0f}%", bar)))
    print()

# ── CLI entry point ───────────────────────────────────────────────────────────
def main():
    ap  = argparse.ArgumentParser(prog="python 5_cli.py",
                                  description="Football Injury Intelligence Pipeline")
    sub = ap.add_subparsers(dest="cmd")

    p_run = sub.add_parser("run",     help="Full pipeline")
    p_run.add_argument("--seed-only",     action="store_true", help="No HTTP scraping")
    p_run.add_argument("--force-retrain", action="store_true", help="Retrain model")
    p_run.add_argument("--json",          action="store_true", help="Also write JSON reports")

    p_show = sub.add_parser("show", help="Display a report")
    p_show.add_argument("what", choices=["injured","risk","accuracy"])

    p_ver = sub.add_parser("verify", help="Record prediction outcomes")
    p_ver.add_argument("--player",  default=None)
    p_ver.add_argument("--outcome", default=None, choices=["correct","wrong"])

    sub.add_parser("clean",          help="Re-run data cleaning")
    sub.add_parser("predict",        help="Re-run model + predictions")
    p_rep = sub.add_parser("report", help="Regenerate reports")
    p_rep.add_argument("--json", action="store_true")
    sub.add_parser("add",            help="Add a player interactively")
    sub.add_parser("accuracy-chart", help="ASCII accuracy over time")

    args = ap.parse_args()

    if args.cmd == "run":
        step_scrape(seed_only=getattr(args,"seed_only",False))
        step_clean()
        step_model(force_retrain=getattr(args,"force_retrain",False))
        step_report(also_json=getattr(args,"json",False))
        print(g("\n✓  Pipeline complete.  Outputs in outputs/"))

    elif args.cmd == "clean":   step_clean()
    elif args.cmd == "predict": step_model()
    elif args.cmd == "report":  step_report(also_json=getattr(args,"json",False))
    elif args.cmd == "show":
        if args.what == "injured":    show_injured()
        elif args.what == "risk":     show_risk()
        elif args.what == "accuracy": show_accuracy()
    elif args.cmd == "verify":        verify_predictions(args.player, args.outcome)
    elif args.cmd == "add":           add_player()
    elif args.cmd == "accuracy-chart":accuracy_chart()
    else:
        print(h("\n  Football Injury Intelligence Pipeline"))
        print(b("  ─────────────────────────────────────"))
        print(f"\n  {h('Quick start')}")
        print(f"    {g('python 5_cli.py run --seed-only')}    ← full pipeline, no scraping")
        print(f"    {g('python 5_cli.py show injured')}       ← current injuries")
        print(f"    {g('python 5_cli.py show risk')}          ← risk-watch list")
        print(f"    {g('python 5_cli.py verify')}             ← record prediction outcomes")
        print(f"    {g('python 5_cli.py accuracy-chart')}     ← model accuracy over time\n")
        ap.print_help()

if __name__ == "__main__":
    main()
