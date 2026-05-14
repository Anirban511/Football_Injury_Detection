"""
1_scraper.py  —  Transfermarkt Injury Data Scraper
====================================================
Scrapes injury history + player profiles from Transfermarkt.
Falls back gracefully to the built-in seed dataset when
the site blocks the request (anti-bot) or you pass --seed-only.

Reads:  config.yaml
Writes: data/raw_injuries.csv
        data/raw_profiles.csv

Usage:
    python 1_scraper.py                  # scrape + seed fallback
    python 1_scraper.py --seed-only      # skip all HTTP, use seed only
    python 1_scraper.py --players 28003  # override player list
"""

import argparse, logging, random, time
from pathlib import Path

import pandas as pd, requests, yaml
from bs4 import BeautifulSoup

# ── Config ───────────────────────────────────────────────────────────────────
def load_config(path="config.yaml"):
    with open(path) as f:
        return yaml.safe_load(f)

CFG   = load_config()
PATHS = CFG["paths"]
Path(PATHS["logs_dir"]).mkdir(parents=True, exist_ok=True)
Path(PATHS["data_dir"]).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{PATHS['logs_dir']}/scraper.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

TM_BASE = "https://www.transfermarkt.com"
HEADERS = {
    "User-Agent":      CFG["scraper"]["user_agent"],
    "Accept-Language": "en-US,en;q=0.9",
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# ── Scrape helpers ────────────────────────────────────────────────────────────
def scrape_injuries(name, tm_id):
    url = f"{TM_BASE}/player/verletzungen/spieler/{tm_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=CFG["scraper"]["request_timeout"])
        if r.status_code != 200:
            log.warning(f"  {name}: HTTP {r.status_code} — using seed")
            return []
        soup  = BeautifulSoup(r.text, "lxml")
        table = soup.find("table", class_="items")
        if not table:
            log.warning(f"  {name}: no injury table found")
            return []
        rows = []
        for tr in table.find("tbody").find_all("tr"):
            cols = [td.get_text(strip=True) for td in tr.find_all("td")]
            if len(cols) < 5:
                continue
            rows.append(dict(player_name=name, tm_id=tm_id,
                season=cols[0], injury=cols[1], date_from=cols[2],
                date_until=cols[3], days_missed=cols[4],
                games_missed=cols[5] if len(cols)>5 else "", source="transfermarkt"))
        log.info(f"  {name}: {len(rows)} records")
        return rows
    except Exception as e:
        log.warning(f"  {name}: {e}")
        return []

def scrape_profile(name, tm_id):
    url  = f"{TM_BASE}/player/profil/spieler/{tm_id}"
    prof = dict(player_name=name, tm_id=tm_id, club="Unknown", position="Unknown",
                age=26, nationality="Unknown", market_value="Unknown",
                matches_last30=8, minutes_last30=720, source="transfermarkt")
    try:
        r = requests.get(url, headers=HEADERS, timeout=CFG["scraper"]["request_timeout"])
        if r.status_code != 200:
            return prof
        soup = BeautifulSoup(r.text, "lxml")
        c = soup.select_one(".data-header__club a")
        if c:
            prof["club"] = c.get_text(strip=True)
        for li in soup.select(".data-header__details li"):
            t = li.get_text(" ", strip=True)
            if "Position" in t:
                prof["position"] = t.replace("Position:","").strip()
            if "Age" in t or "Born" in t:
                try:
                    prof["age"] = int(li.select_one("span").get_text(strip=True).split()[0])
                except Exception:
                    pass
            if "Nationality" in t:
                prof["nationality"] = t.replace("Nationality:","").strip()
        mv = soup.select_one(".tm-player-market-value-development__current-value")
        if mv:
            prof["market_value"] = mv.get_text(strip=True)
    except Exception as e:
        log.warning(f"  {name} profile: {e}")
    return prof

# ── Seed data ─────────────────────────────────────────────────────────────────
SEED_INJURIES = [
    ("Mohamed Salah",          "Hamstring strain",    "2025-10-15","2025-11-05", 21, 5,"25/26"),
    ("Mohamed Salah",          "Ankle sprain",        "2023-03-12","2023-04-01", 20, 4,"22/23"),
    ("Mohamed Salah",          "Muscle injury",       "2021-07-03","2021-07-25", 22, 0,"21/22"),
    ("Trent Alexander-Arnold", "Thigh strain",        "2026-03-10","2026-04-20", 41, 8,"25/26"),
    ("Trent Alexander-Arnold", "Hamstring",           "2025-01-20","2025-02-15", 26, 5,"24/25"),
    ("Trent Alexander-Arnold", "Ankle",               "2023-10-11","2023-11-10", 30, 7,"23/24"),
    ("Trent Alexander-Arnold", "Knee",                "2022-05-01","2022-05-22", 21, 4,"21/22"),
    ("Trent Alexander-Arnold", "Thigh strain",        "2020-09-03","2020-10-10", 37, 9,"20/21"),
    ("Erling Haaland",         "Hip flexor",          "2025-08-19","2025-09-14", 26, 5,"25/26"),
    ("Erling Haaland",         "Foot injury",         "2021-03-01","2021-04-20", 50,10,"20/21"),
    ("Erling Haaland",         "Muscle strain",       "2023-04-05","2023-04-25", 20, 4,"22/23"),
    ("Bukayo Saka",            "Hamstring",           "2026-03-20","2026-04-28", 39, 8,"25/26"),
    ("Bukayo Saka",            "Ankle sprain",        "2023-08-05","2023-09-01", 27, 6,"23/24"),
    ("Bukayo Saka",            "Hamstring",           "2024-12-01","2024-12-22", 21, 5,"24/25"),
    ("Bukayo Saka",            "Groin",               "2022-04-12","2022-05-01", 19, 4,"21/22"),
    ("Virgil van Dijk",        "ACL rupture",         "2020-10-17","2021-07-01",257,52,"20/21"),
    ("Virgil van Dijk",        "Ankle ligament",      "2023-09-10","2023-10-15", 35, 8,"23/24"),
    ("Virgil van Dijk",        "Thigh",               "2025-12-01","2026-01-10", 40, 8,"25/26"),
    ("Rodri",                  "ACL rupture",         "2024-09-22","2025-05-01",221,45,"24/25"),
    ("Rodri",                  "Knee",                "2026-02-05","2026-03-15", 38, 8,"25/26"),
    ("Rodri",                  "Muscle strain",       "2023-02-11","2023-03-01", 18, 4,"22/23"),
    ("Kevin De Bruyne",        "Hamstring",           "2025-12-01","2026-02-15", 76,16,"25/26"),
    ("Kevin De Bruyne",        "ACL",                 "2019-09-09","2020-01-10",123,25,"19/20"),
    ("Kevin De Bruyne",        "Hamstring",           "2023-06-10","2023-07-22", 42, 0,"22/23"),
    ("Kevin De Bruyne",        "Groin",               "2024-04-05","2024-05-01", 26, 6,"23/24"),
    ("Kevin De Bruyne",        "Shoulder",            "2021-09-15","2021-11-01", 47,10,"21/22"),
    ("Marcus Rashford",        "Muscle",              "2026-02-01","2026-03-10", 37, 8,"25/26"),
    ("Marcus Rashford",        "Ankle sprain",        "2022-01-31","2022-02-28", 28, 7,"21/22"),
    ("Marcus Rashford",        "Shoulder",            "2020-01-20","2020-03-09", 49,10,"19/20"),
    ("Marcus Rashford",        "Stress fracture",     "2022-05-01","2022-09-01",123, 0,"21/22"),
    ("Pedri",                  "Knee ligament",       "2026-02-20","2026-05-01", 70,15,"25/26"),
    ("Pedri",                  "Hamstring",           "2022-07-10","2023-01-15",189,40,"22/23"),
    ("Pedri",                  "Knee",                "2024-08-05","2024-09-20", 46,10,"24/25"),
    ("Pedri",                  "Muscle",              "2025-09-01","2025-10-10", 39, 9,"25/26"),
    ("Vinicius Jr",            "Hamstring",           "2025-10-22","2025-11-25", 34, 8,"25/26"),
    ("Vinicius Jr",            "Ankle sprain",        "2023-04-03","2023-04-28", 25, 5,"22/23"),
    ("Vinicius Jr",            "Muscle",              "2022-11-20","2022-12-10", 20, 4,"22/23"),
    ("Vinicius Jr",            "Thigh",               "2026-02-10","2026-03-05", 23, 5,"25/26"),
    ("Kylian Mbappe",          "Ankle sprain",        "2026-01-05","2026-02-01", 27, 6,"25/26"),
    ("Kylian Mbappe",          "Thigh strain",        "2023-03-25","2023-04-20", 26, 5,"22/23"),
    ("Kylian Mbappe",          "Calf",                "2025-07-01","2025-07-22", 21, 0,"25/26"),
    ("Lamine Yamal",           "Ankle bruise",        "2025-06-20","2025-06-25",  5, 1,"24/25"),
    ("Jude Bellingham",        "Shoulder disloc.",    "2023-10-28","2024-01-07", 71,15,"23/24"),
    ("Jude Bellingham",        "Ankle",               "2025-12-10","2026-01-15", 36, 7,"25/26"),
    ("Phil Foden",             "Appendix op.",        "2024-05-10","2024-05-28", 18, 3,"23/24"),
    ("Phil Foden",             "Hamstring",           "2023-11-14","2023-12-08", 24, 5,"23/24"),
    ("Harry Kane",             "Ankle",               "2025-10-07","2025-11-04", 28, 6,"25/26"),
    ("Harry Kane",             "Hamstring",           "2023-01-16","2023-02-05", 20, 4,"22/23"),
    ("Harry Kane",             "Ankle ligament",      "2020-01-01","2020-01-29", 28, 7,"19/20"),
    ("Leroy Sane",             "ACL",                 "2019-08-11","2020-06-20",313,60,"19/20"),
    ("Leroy Sane",             "Muscle",              "2024-10-12","2024-11-20", 39, 8,"24/25"),
    ("Reece James",            "Hamstring",           "2026-03-01","2026-04-18", 48,10,"25/26"),
    ("Reece James",            "Knee",                "2022-10-09","2023-02-06",120,26,"22/23"),
    ("Reece James",            "Hamstring",           "2024-08-16","2024-09-19", 34, 7,"24/25"),
    ("Reece James",            "Hamstring",           "2025-01-10","2025-02-20", 41, 9,"24/25"),
    ("Ben Chilwell",           "ACL",                 "2021-11-23","2022-09-01",281,55,"21/22"),
    ("Ben Chilwell",           "Hamstring",           "2025-09-07","2025-11-15", 69,15,"25/26"),
    ("Mason Mount",            "Muscle injury",       "2025-11-01","2026-01-20", 80,17,"25/26"),
    ("Mason Mount",            "Hamstring",           "2023-08-22","2023-09-20", 29, 6,"23/24"),
    ("Jadon Sancho",           "Physical deficit",    "2023-09-01","2024-01-15",136,28,"23/24"),
    ("Jadon Sancho",           "Muscle",              "2022-01-20","2022-02-25", 36, 8,"21/22"),
]

SEED_PROFILES = {
    "Mohamed Salah":           dict(club="Liverpool",     position="FW",age=32,nationality="Egyptian",  market_value="€35m", matches_last30=9, minutes_last30=810),
    "Trent Alexander-Arnold":  dict(club="Liverpool",     position="DF",age=26,nationality="English",   market_value="€80m", matches_last30=7, minutes_last30=630),
    "Erling Haaland":          dict(club="Man City",      position="FW",age=24,nationality="Norwegian", market_value="€200m",matches_last30=10,minutes_last30=870),
    "Bukayo Saka":             dict(club="Arsenal",       position="FW",age=23,nationality="English",   market_value="€180m",matches_last30=8, minutes_last30=720),
    "Virgil van Dijk":         dict(club="Liverpool",     position="DF",age=33,nationality="Dutch",     market_value="€30m", matches_last30=9, minutes_last30=810),
    "Rodri":                   dict(club="Man City",      position="MF",age=28,nationality="Spanish",   market_value="€120m",matches_last30=4, minutes_last30=290),
    "Kevin De Bruyne":         dict(club="Man City",      position="MF",age=33,nationality="Belgian",   market_value="€25m", matches_last30=7, minutes_last30=595),
    "Marcus Rashford":         dict(club="Aston Villa",   position="FW",age=27,nationality="English",   market_value="€35m", matches_last30=8, minutes_last30=680),
    "Pedri":                   dict(club="Barcelona",     position="MF",age=22,nationality="Spanish",   market_value="€90m", matches_last30=3, minutes_last30=210),
    "Vinicius Jr":             dict(club="Real Madrid",   position="FW",age=24,nationality="Brazilian", market_value="€180m",matches_last30=10,minutes_last30=900),
    "Kylian Mbappe":           dict(club="Real Madrid",   position="FW",age=26,nationality="French",    market_value="€180m",matches_last30=9, minutes_last30=810),
    "Lamine Yamal":            dict(club="Barcelona",     position="FW",age=17,nationality="Spanish",   market_value="€180m",matches_last30=9, minutes_last30=765),
    "Jude Bellingham":         dict(club="Real Madrid",   position="MF",age=21,nationality="English",   market_value="€180m",matches_last30=10,minutes_last30=900),
    "Phil Foden":              dict(club="Man City",      position="MF",age=24,nationality="English",   market_value="€150m",matches_last30=9, minutes_last30=810),
    "Harry Kane":              dict(club="Bayern Munich", position="FW",age=31,nationality="English",   market_value="€80m", matches_last30=10,minutes_last30=900),
    "Leroy Sane":              dict(club="Bayern Munich", position="FW",age=28,nationality="German",    market_value="€45m", matches_last30=8, minutes_last30=700),
    "Reece James":             dict(club="Chelsea",       position="DF",age=25,nationality="English",   market_value="€70m", matches_last30=2, minutes_last30=150),
    "Ben Chilwell":            dict(club="Chelsea",       position="DF",age=28,nationality="English",   market_value="€30m", matches_last30=5, minutes_last30=405),
    "Mason Mount":             dict(club="Man United",    position="MF",age=26,nationality="English",   market_value="€30m", matches_last30=6, minutes_last30=480),
    "Jadon Sancho":            dict(club="Chelsea",       position="FW",age=24,nationality="English",   market_value="€35m", matches_last30=7, minutes_last30=560),
}

def build_seed_dfs():
    pcfg = CFG.get("players", {})
    inj_rows = [dict(player_name=n,tm_id=pcfg.get(n,0),season=s,injury=i,
                     date_from=df,date_until=du,days_missed=str(dm),
                     games_missed=str(gm),source="seed")
                for n,i,df,du,dm,gm,s in SEED_INJURIES]
    prof_rows = [dict(player_name=n,tm_id=pcfg.get(n,0),**p,source="seed")
                 for n,p in SEED_PROFILES.items()]
    return pd.DataFrame(inj_rows), pd.DataFrame(prof_rows)

# ── Main ──────────────────────────────────────────────────────────────────────
def run(player_ids=None, seed_only=False):
    if player_ids is None:
        player_ids = CFG.get("players", {})
    scraped_inj, scraped_prof = [], []
    if not seed_only:
        log.info(f"=== Scraping {len(player_ids)} players ===")
        for name, tm_id in player_ids.items():
            log.info(f"→ {name} (TM {tm_id})")
            inj = scrape_injuries(name, tm_id)
            scraped_inj.extend(inj)
            if inj:
                scraped_prof.append(scrape_profile(name, tm_id))
            time.sleep(random.uniform(CFG["scraper"]["delay_min"], CFG["scraper"]["delay_max"]))
    log.info("=== Loading seed data ===")
    seed_inj, seed_prof = build_seed_dfs()
    scraped_names = {r["player_name"] for r in scraped_inj}
    all_inj  = pd.concat([pd.DataFrame(scraped_inj), seed_inj[~seed_inj["player_name"].isin(scraped_names)]], ignore_index=True)
    sp_names = {r["player_name"] for r in scraped_prof}
    spdf     = pd.DataFrame(scraped_prof) if scraped_prof else pd.DataFrame()
    all_prof = pd.concat([spdf, seed_prof[~seed_prof["player_name"].isin(sp_names)]], ignore_index=True)
    d = PATHS["data_dir"]
    all_inj.to_csv(f"{d}/raw_injuries.csv", index=False)
    all_prof.to_csv(f"{d}/raw_profiles.csv", index=False)
    log.info(f"✓  {len(all_inj)} injury records  →  {d}/raw_injuries.csv")
    log.info(f"✓  {len(all_prof)} profiles        →  {d}/raw_profiles.csv")
    log.info(f"   Players covered: {all_inj['player_name'].nunique()}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--players", nargs="*", type=int)
    ap.add_argument("--seed-only", action="store_true")
    args = ap.parse_args()
    ids = None
    if args.players:
        rev = {v:k for k,v in CFG.get("players",{}).items()}
        ids = {rev.get(pid,f"Player_{pid}"):pid for pid in args.players}
    run(player_ids=ids, seed_only=args.seed_only)
