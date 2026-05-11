# Football Injury Intelligence

A complete data pipeline that tracks current football injuries, scores every player's injury risk, generates predictions, and records outcomes so you can measure model accuracy over time.

---

## Table of Contents

1. [Requirements](#1-requirements)
2. [Setup](#2-setup)
3. [Project layout](#3-project-layout)
4. [Pipeline overview](#4-pipeline-overview)
5. [Running the pipeline](#5-running-the-pipeline)
6. [All CLI commands](#6-all-cli-commands)
7. [Configuring the project](#7-configuring-the-project)
8. [Adding and managing players](#8-adding-and-managing-players)
9. [Tracking prediction accuracy](#9-tracking-prediction-accuracy)
10. [Output files](#10-output-files)
11. [Understanding the risk score](#11-understanding-the-risk-score)
12. [Extending the project](#12-extending-the-project)
13. [Troubleshooting](#13-troubleshooting)

---

## 1. Requirements

| Requirement | Minimum version |
|-------------|----------------|
| Python      | 3.10            |
| pip         | any recent      |

All Python packages are listed in `requirements.txt`. No database server or external service needed.

---

## 2. Setup

**Step 1 — Place all project files in one folder**

The folder must contain: `config.yaml`, `requirements.txt`, `1_scraper.py` through `5_cli.py`, `setup.sh`, `README.md`.

**Step 2 — Create a virtual environment (recommended)**

```bash
python3 -m venv .venv
source .venv/bin/activate      # macOS / Linux
.venv\Scripts\activate         # Windows
```

**Step 3 — Install dependencies**

```bash
pip install -r requirements.txt
```

Or use the bootstrap script (macOS / Linux only):

```bash
bash setup.sh
```

**Step 4 — Run the pipeline**

```bash
python 5_cli.py run --seed-only
```

Done. Reports appear in `outputs/`.

---

## 3. Project layout

```
football_injury/
|
+-- config.yaml              <- all configuration (edit this)
+-- requirements.txt         <- pinned Python packages
+-- setup.sh                 <- one-time setup (Linux / macOS)
+-- README.md
|
+-- 1_scraper.py             <- Step 1: fetch Transfermarkt data
+-- 2_clean_features.py      <- Step 2: clean + build features
+-- 3_model.py               <- Step 3: train model + predict
+-- 4_report.py              <- Step 4: write output reports
+-- 5_cli.py                 <- master CLI entry point
|
+-- data/
|   +-- raw_injuries.csv     <- scraped + seed injury records
|   +-- raw_profiles.csv     <- player profiles
|   +-- clean_injuries.csv   <- parsed, classified records
|   +-- player_features.csv  <- 20+ engineered features per player
|   +-- predictions.csv      <- latest model output
|   +-- prediction_log.json  <- append-only log for accuracy tracking
|
+-- models/
|   +-- risk_model.pkl       <- saved model bundle
|
+-- outputs/
|   +-- report_injured.csv   <- currently injured players
|   +-- report_risk_watch.csv<- fit players ranked by risk
|   +-- report_full.csv      <- all players, all fields
|   +-- report_accuracy.json <- accuracy stats
|   +-- report_summary.txt   <- human-readable text report
|
+-- logs/
    +-- scraper.log
    +-- clean.log
    +-- model.log
    +-- report.log
```

---

## 4. Pipeline overview

```
config.yaml
     |
     v
1_scraper.py
  Fetch injury history + player profiles from Transfermarkt.
  Falls back to built-in seed data if the site blocks requests.
  Output: data/raw_injuries.csv, data/raw_profiles.csv
     |
     v
2_clean_features.py
  Parse dates, classify injury severity (severe/moderate/mild)
  and body part, compute 20+ features per player, calculate
  a weighted risk score (0-99).
  Output: data/clean_injuries.csv, data/player_features.csv
     |
     v
3_model.py
  Train Gradient Boosting or Random Forest classifier.
  Generate per-player predictions: probability scores,
  injury windows, and plain-English recommendations.
  Append new entries to the accuracy-tracking log.
  Output: models/risk_model.pkl, data/predictions.csv,
          data/prediction_log.json (append-only)
     |
     v
4_report.py
  Produce clean reports from predictions.
  Output: outputs/report_injured.csv
          outputs/report_risk_watch.csv
          outputs/report_full.csv
          outputs/report_accuracy.json
          outputs/report_summary.txt
```

---

## 5. Running the pipeline

### Recommended first run (no internet needed)

```bash
python 5_cli.py run --seed-only
```

Uses the built-in seed dataset (20 players, 60+ injury records). No HTTP requests. Completes in under 10 seconds.

### With live Transfermarkt scraping

```bash
python 5_cli.py run
```

Scrapes each player then supplements with seed data for blocked requests. Expect 1-3 minutes depending on network and anti-bot responses.

### Force model retraining

```bash
python 5_cli.py run --seed-only --force-retrain
```

Deletes the cached model and rebuilds from scratch. Use this after adding players or editing risk weights in `config.yaml`.

### Run individual pipeline steps

```bash
python 5_cli.py clean      # cleaning only  (after editing raw CSVs)
python 5_cli.py predict    # model + predictions only
python 5_cli.py report     # reports only
```

### Run scripts directly (same as above, more verbose)

```bash
python 1_scraper.py --seed-only
python 2_clean_features.py
python 3_model.py
python 4_report.py
```

---

## 6. All CLI commands

Run `python 5_cli.py` with no arguments for the help screen.

```
Command                                    What it does
------------------------------------------+--------------------------------------------
run                                        Full pipeline
run --seed-only                            Full pipeline, no HTTP scraping
run --force-retrain                        Full pipeline, retrain model from scratch
run --json                                 Also write .json report files
clean                                      Re-run data cleaning step only
predict                                    Re-run model + predictions only
report                                     Regenerate output reports only
report --json                              Reports + JSON versions
show injured                               Print injured list to terminal
show risk                                  Print risk-watch list to terminal
show accuracy                              Print prediction accuracy stats
verify                                     Interactive: mark past predictions correct/wrong
verify --player "Name"                     Filter verify to one player
verify --player "Name" --outcome correct   Non-interactive single-player verify
add                                        Wizard to add a new player
accuracy-chart                             ASCII chart of model accuracy over time
```

---

## 7. Configuring the project

All settings are in `config.yaml`. Every key is read at runtime — no need to touch Python files to customise behaviour.

### Add / remove players from the roster

```yaml
players:
  "New Player":     123456   # Transfermarkt ID from the URL
  # "Old Player": 789012    # comment out or delete to remove
```

Find a player's ID in their Transfermarkt URL:
```
https://www.transfermarkt.com/erling-haaland/profil/spieler/418560
                                                              ^^^^^^
```

### Tune risk score weights

```yaml
risk_weights:
  injuries_last_12m:  30   # increase to weight recent history more heavily
  workload:           18   # increase to flag high-minute players more
  age:                10   # increase to penalise players over 33 more
  career_burden:      15
  injury_severity:    12
  recurring_injury:    8
  recent_return:       7
```

After editing weights: `python 5_cli.py run --seed-only --force-retrain`

### Change risk tier thresholds

```yaml
risk_tiers:
  critical:  80
  high:      60
  moderate:  40
```

### Switch ML algorithm

```yaml
model:
  algorithm: random_forest   # or: gradient_boosting
```

### Update the current season

```yaml
seasons:
  current_season_start: "2025-07-01"   # update each summer
```

---

## 8. Adding and managing players

### Interactive wizard

```bash
python 5_cli.py add
```

Prompts for name, club, position, age, nationality, current injury (if any), and past injury history. After adding, rebuild:

```bash
python 5_cli.py clean && python 5_cli.py predict
```

### Bulk edit via CSV

Add rows to `data/raw_profiles.csv`:

```
player_name,club,position,age,nationality,market_value,matches_last30,minutes_last30,source
"New Player","Club FC","MF",25,"German","60m",9,810,manual
```

Add injury history to `data/raw_injuries.csv`:

```
player_name,tm_id,season,injury,date_from,date_until,days_missed,games_missed,source
"New Player",0,"25/26","Hamstring","2026-02-01","2026-02-28","28","6",manual
```

Then rebuild: `python 5_cli.py clean && python 5_cli.py predict`

---

## 9. Tracking prediction accuracy

Every pipeline run appends predictions to `data/prediction_log.json`. After the predicted window passes, you record the real outcome. The system calculates rolling accuracy.

### The accuracy loop

```
1. Run pipeline  ->  predictions logged with outcome = null
        |
        |   (wait: prediction window passes)
        |
2. Verify        ->  python 5_cli.py verify
        |
3. Accuracy      ->  python 5_cli.py show accuracy
                     python 5_cli.py accuracy-chart
```

### Interactive verification

```bash
python 5_cli.py verify
```

For each pending prediction:
```
  Bukayo Saka  |  Arsenal  |  Tier: High  |  Window: 2-4 weeks  |  Made: 2026-04-01
  Recommendation: Rotate -- limit to 60% load
  Outcome? (correct / wrong / skip / q):
```

Type `correct` if the player was injured within the window, `wrong` if not.

### Non-interactive verification

```bash
python 5_cli.py verify --player "Bukayo Saka" --outcome correct
python 5_cli.py verify --player "Haaland"     --outcome wrong
```

### View accuracy at any time

```bash
python 5_cli.py show accuracy
python 5_cli.py accuracy-chart
```

---

## 10. Output files

| File | Contents |
|------|----------|
| `outputs/report_summary.txt` | Full text report: injuries + risk watch + accuracy |
| `outputs/report_injured.csv` | Injured players with return dates, history, dominant body part |
| `outputs/report_risk_watch.csv` | Fit players ranked by risk, with predictions + recommendations |
| `outputs/report_full.csv` | All players, all fields |
| `outputs/report_accuracy.json` | Accuracy stats by tier (for scripts / dashboards) |

Enable JSON output:
```bash
python 5_cli.py report --json
```

Or permanently in `config.yaml`:
```yaml
report:
  also_write_json: true
```

---

## 11. Understanding the risk score

The risk score (0-99) combines seven weighted factors:

| Factor | Max pts | What it captures |
|--------|---------|-----------------|
| Injuries last 12 months | 30 | Strongest predictor of near-future injury |
| Workload | 18 | Minutes last 30 days vs 900-min benchmark |
| Career injury burden | 15 | Total career injury count |
| Injury severity | 12 | Severe injuries: ACL, fracture, ligament rupture |
| Age | 10 | Risk increases sharply at >= 33; small youth flag too |
| Recurring injury | 8 | Same body part injured >= 2 times in career |
| Recent return | 7 | Back from injury fewer than 30 days ago |

**Tier thresholds (defaults)**

| Tier | Score | Recommended action |
|------|-------|--------------------|
| Critical | 80-99 | Rest 2+ matches immediately |
| High | 60-79 | Rotate; limit to ~60% of normal load |
| Moderate | 40-59 | Monitor closely |
| Low | 0-39 | No action required |

All weights and thresholds are tunable in `config.yaml`.

---

## 12. Extending the project

### Train on real outcome data

Once `prediction_log.json` has 50+ verified entries, the model can train on real labels instead of synthetic ones. In `3_model.py`, replace `build_training_data()` with a function that joins verified log entries back to `player_features.csv` using player name and prediction date window, and uses `outcome == "correct"` as the positive label.

### Add more players

Edit the `players:` block in `config.yaml`, then run `python 5_cli.py run --seed-only`.

### Schedule automatic runs

On Linux / macOS (cron — runs every day at 07:00):
```bash
0 7 * * * cd /path/to/football_injury && python 5_cli.py run --seed-only >> logs/cron.log 2>&1
```

On Windows, use Task Scheduler pointing at `python 5_cli.py run --seed-only` with the project folder as working directory.

### Connect the dashboard

The React dashboard (in the companion `.jsx` artifact) reads `outputs/report_injured.csv` and `outputs/report_risk_watch.csv`. Run the pipeline on a schedule and point the dashboard at the same outputs folder.

---

## 13. Troubleshooting

**`ModuleNotFoundError`**
```bash
pip install -r requirements.txt
```

**`FileNotFoundError: config.yaml`**
Run all commands from the project root directory (the folder containing `config.yaml`).

**`FileNotFoundError: data/player_features.csv`**
The pipeline has not been run yet:
```bash
python 5_cli.py run --seed-only
```

**Transfermarkt returns HTTP 403 / 503**
Normal. The site uses anti-bot protection. Use `--seed-only` to bypass scraping. The seed data covers all 20 default players with accurate injury histories through May 2026.

**No injured players showing in reports**
Verify that `seasons.current_season_start` in `config.yaml` is in the past, and that `data/raw_injuries.csv` has rows with `date_until` values after today's date for those players.

**Colours not showing on Windows**
```bash
pip install colorama --upgrade
```
Then rerun the CLI.

**Model accuracy stays at 0%**
Accuracy only updates after you verify outcomes:
```bash
python 5_cli.py verify
```

---

## Quick-reference workflow

```bash
# ── First time ──────────────────────────────────────────────
bash setup.sh                                 # install deps, create dirs
python 5_cli.py run --seed-only               # full pipeline

# ── Regular use (weekly) ────────────────────────────────────
python 5_cli.py run --seed-only               # refresh data + predictions

# ── After prediction windows pass (every 2-4 weeks) ─────────
python 5_cli.py verify                        # record correct/wrong
python 5_cli.py show accuracy                 # see how the model is doing

# ── View reports any time ────────────────────────────────────
python 5_cli.py show injured
python 5_cli.py show risk
python 5_cli.py accuracy-chart

# ── Add a new player ────────────────────────────────────────
python 5_cli.py add
python 5_cli.py clean && python 5_cli.py predict

# ── Tune the model ──────────────────────────────────────────
# 1. Edit config.yaml (risk_weights, tiers, model.algorithm)
python 5_cli.py run --seed-only --force-retrain
```
