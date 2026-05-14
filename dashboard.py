#!/usr/bin/env python3
"""
dashboard.py  —  Football Injury Intelligence Dashboard
=======================================================
Starts a local HTTP server and opens the dashboard in your browser.

Usage:
    python dashboard.py           # http://localhost:5050
    python dashboard.py --port 8080

Reads outputs/ produced by: python 5_cli.py report
Dashboard auto-refreshes every 60 seconds.
"""
import csv, json, webbrowser, argparse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

BASE    = Path(__file__).parent
OUTPUTS = BASE / "outputs"

def _read_csv(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))

def _load():
    injured = _read_csv(OUTPUTS / "report_injured.csv")
    risk    = _read_csv(OUTPUTS / "report_risk_watch.csv")
    acc_path = OUTPUTS / "report_accuracy.json"
    acc = json.loads(acc_path.read_text(encoding="utf-8")) if acc_path.exists() else {}
    return {"injured": injured, "risk": risk, "accuracy": acc}


# ── HTML ──────────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Football Injury Intelligence</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg:      #0f1117;
    --surface: #1a1d27;
    --card:    #22263a;
    --border:  #2e3450;
    --green:   #22c55e;
    --text:    #e2e8f0;
    --muted:   #8892a4;
    --crit:    #ef4444;
    --high:    #f97316;
    --mod:     #eab308;
    --low:     #22c55e;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', system-ui, sans-serif; font-size: 14px; }

  /* ── Header ── */
  header {
    background: linear-gradient(135deg, #0d1f0d 0%, #1a2e1a 50%, #0f1117 100%);
    border-bottom: 1px solid var(--border);
    padding: 18px 28px;
    display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;
  }
  header h1 { font-size: 1.25rem; font-weight: 700; letter-spacing: .03em; }
  header h1 span { color: var(--green); }
  .header-right { display: flex; align-items: center; gap: 12px; }
  #last-updated { color: var(--muted); font-size: 12px; }
  #countdown { color: var(--muted); font-size: 12px; }
  button#refresh-btn {
    background: var(--green); color: #000; border: none; border-radius: 6px;
    padding: 6px 14px; font-size: 12px; font-weight: 600; cursor: pointer;
  }
  button#refresh-btn:hover { opacity: .85; }

  /* ── Layout ── */
  main { max-width: 1400px; margin: 0 auto; padding: 24px 20px; }

  /* ── Stat cards ── */
  .stats { display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 14px; margin-bottom: 28px; }
  .stat-card {
    background: var(--card); border: 1px solid var(--border); border-radius: 10px;
    padding: 16px 20px;
  }
  .stat-card .label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }
  .stat-card .value { font-size: 2rem; font-weight: 700; line-height: 1; }
  .stat-card .sub { color: var(--muted); font-size: 11px; margin-top: 4px; }
  .v-green { color: var(--green); }
  .v-red   { color: var(--crit); }
  .v-orange{ color: var(--high); }
  .v-yellow{ color: var(--mod); }

  /* ── Section ── */
  .section { margin-bottom: 32px; }
  .section h2 { font-size: .95rem; font-weight: 600; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); margin-bottom: 12px; }

  /* ── Chart ── */
  .chart-wrap { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 20px; }
  canvas { max-height: 280px; }

  /* ── Tables ── */
  .table-wrap { background: var(--card); border: 1px solid var(--border); border-radius: 10px; overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  thead th {
    background: var(--surface); color: var(--muted); font-size: 11px;
    text-transform: uppercase; letter-spacing: .06em;
    padding: 10px 14px; text-align: left; white-space: nowrap;
    border-bottom: 1px solid var(--border);
  }
  tbody tr { border-bottom: 1px solid var(--border); }
  tbody tr:last-child { border-bottom: none; }
  tbody tr:hover { background: rgba(255,255,255,.03); }
  tbody td { padding: 10px 14px; vertical-align: middle; }
  .name { font-weight: 600; }
  .club { color: var(--muted); }

  /* ── Tier badges ── */
  .badge {
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em;
  }
  .badge-Critical { background: rgba(239,68,68,.2);  color: #ef4444; }
  .badge-High     { background: rgba(249,115,22,.2); color: #f97316; }
  .badge-Moderate { background: rgba(234,179,8,.2);  color: #eab308; }
  .badge-Low      { background: rgba(34,197,94,.2);  color: #22c55e; }

  /* ── Score bar ── */
  .score-cell { display: flex; align-items: center; gap: 8px; }
  .score-bar-bg { flex: 1; height: 6px; background: var(--border); border-radius: 3px; min-width: 60px; }
  .score-bar-fill { height: 100%; border-radius: 3px; }
  .score-num { font-weight: 600; font-variant-numeric: tabular-nums; min-width: 28px; }

  /* ── Recommendation ── */
  .rec { color: var(--muted); max-width: 220px; }

  /* ── Empty state ── */
  .empty { padding: 32px; text-align: center; color: var(--muted); }

  /* ── Accuracy ── */
  .acc-grid { display: flex; gap: 12px; flex-wrap: wrap; }
  .acc-box {
    background: var(--card); border: 1px solid var(--border); border-radius: 8px;
    padding: 12px 18px; min-width: 130px;
  }
  .acc-box .al { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .05em; }
  .acc-box .av { font-size: 1.4rem; font-weight: 700; margin-top: 2px; }
</style>
</head>
<body>

<header>
  <h1>Football Injury <span>Intelligence</span></h1>
  <div class="header-right">
    <span id="last-updated">Loading…</span>
    <span id="countdown"></span>
    <button id="refresh-btn" onclick="loadData()">Refresh</button>
  </div>
</header>

<main>
  <!-- Stat cards -->
  <div class="stats" id="stats"></div>

  <!-- Risk score chart -->
  <div class="section">
    <h2>Risk Score — Top Players</h2>
    <div class="chart-wrap">
      <canvas id="riskChart"></canvas>
    </div>
  </div>

  <!-- Currently Injured -->
  <div class="section">
    <h2>Currently Injured</h2>
    <div class="table-wrap" id="injured-wrap"></div>
  </div>

  <!-- Risk Watch -->
  <div class="section">
    <h2>Risk Watch — Fit Players</h2>
    <div class="table-wrap" id="risk-wrap"></div>
  </div>

  <!-- Model Accuracy -->
  <div class="section">
    <h2>Model Accuracy</h2>
    <div class="acc-grid" id="acc-grid"></div>
  </div>
</main>

<script>
let chart = null;
let countdownVal = 60;
let countdownTimer = null;

function tierColor(tier) {
  return { Critical:'#ef4444', High:'#f97316', Moderate:'#eab308', Low:'#22c55e' }[tier] || '#8892a4';
}

function scoreColor(s) {
  s = +s;
  if (s >= 80) return '#ef4444';
  if (s >= 60) return '#f97316';
  if (s >= 40) return '#eab308';
  return '#22c55e';
}

function badge(tier) {
  return `<span class="badge badge-${tier}">${tier}</span>`;
}

function scoreCell(s) {
  const pct = Math.min(+s, 99);
  return `<div class="score-cell">
    <span class="score-num">${s}</span>
    <div class="score-bar-bg"><div class="score-bar-fill" style="width:${pct}%;background:${scoreColor(s)}"></div></div>
  </div>`;
}

function renderStats(data) {
  const injured = data.injured || [];
  const risk    = data.risk    || [];
  const acc     = data.accuracy || {};
  const all     = [...injured, ...risk];
  const total   = all.length;
  const nInj    = injured.length;
  const nHigh   = risk.filter(r => r.risk_tier === 'Critical' || r.risk_tier === 'High').length;
  const nCrit   = injured.filter(r => r.risk_tier === 'Critical').length;
  const accPct  = acc.accuracy_pct != null ? acc.accuracy_pct + '%' : 'N/A';

  document.getElementById('stats').innerHTML = `
    <div class="stat-card">
      <div class="label">Total Players</div>
      <div class="value v-green">${total}</div>
      <div class="sub">in watchlist</div>
    </div>
    <div class="stat-card">
      <div class="label">Currently Injured</div>
      <div class="value v-red">${nInj}</div>
      <div class="sub">${nCrit} critical tier</div>
    </div>
    <div class="stat-card">
      <div class="label">High / Critical Risk</div>
      <div class="value v-orange">${nHigh}</div>
      <div class="sub">fit players flagged</div>
    </div>
    <div class="stat-card">
      <div class="label">Model Accuracy</div>
      <div class="value v-green">${accPct}</div>
      <div class="sub">${acc.verified || 0} verified predictions</div>
    </div>
    <div class="stat-card">
      <div class="label">Report Date</div>
      <div class="value" style="font-size:1.1rem;padding-top:4px">${acc.report_date || '—'}</div>
      <div class="sub">${acc.pending || 0} predictions pending</div>
    </div>
  `;
}

function renderChart(data) {
  const all = [...(data.injured||[]), ...(data.risk||[])];
  all.sort((a,b) => +b.risk_score - +a.risk_score);
  const top = all.slice(0, 20);
  const labels = top.map(r => r.player_name);
  const scores = top.map(r => +r.risk_score);
  const colors = scores.map(scoreColor);

  if (chart) chart.destroy();
  chart = new Chart(document.getElementById('riskChart'), {
    type: 'bar',
    data: {
      labels,
      datasets: [{ data: scores, backgroundColor: colors, borderRadius: 4, borderSkipped: false }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ` Risk Score: ${ctx.parsed.y}  |  ${top[ctx.dataIndex].risk_tier}`
          }
        }
      },
      scales: {
        x: { ticks: { color: '#8892a4', maxRotation: 35, font: { size: 11 } }, grid: { color: '#2e3450' } },
        y: { min: 0, max: 100, ticks: { color: '#8892a4', stepSize: 20 }, grid: { color: '#2e3450' } }
      }
    }
  });
}

function renderInjured(rows) {
  const wrap = document.getElementById('injured-wrap');
  if (!rows.length) {
    wrap.innerHTML = '<div class="empty">No players currently injured.</div>';
    return;
  }
  wrap.innerHTML = `<table>
    <thead><tr>
      <th>Player</th><th>Club</th><th>Pos</th><th>Age</th>
      <th>Injury</th><th>Injury Date</th><th>Return</th>
      <th>Risk Score</th><th>Tier</th><th>Last 12 m</th>
      <th>Career Inj</th><th>Days Lost</th><th>Body Part</th>
    </tr></thead>
    <tbody>${rows.map(r => `<tr>
      <td class="name">${r.player_name}</td>
      <td class="club">${r.club||'—'}</td>
      <td>${r.position||'—'}</td>
      <td>${r.age||'—'}</td>
      <td>${r.current_injury||'—'}</td>
      <td>${r.injury_date||'—'}</td>
      <td>${r.return_info||'—'}</td>
      <td>${scoreCell(r.risk_score)}</td>
      <td>${badge(r.risk_tier)}</td>
      <td>${r.injuries_last12m||'—'}</td>
      <td>${r.total_injuries||'—'}</td>
      <td>${r.total_days_lost||'—'}</td>
      <td>${r.dominant_body_part||'—'}</td>
    </tr>`).join('')}</tbody>
  </table>`;
}

function renderRisk(rows) {
  const wrap = document.getElementById('risk-wrap');
  if (!rows.length) {
    wrap.innerHTML = '<div class="empty">No risk data available.</div>';
    return;
  }
  wrap.innerHTML = `<table>
    <thead><tr>
      <th>Player</th><th>Club</th><th>Pos</th><th>Age</th>
      <th>Risk Score</th><th>Tier</th><th>ML Tier</th>
      <th>Inj Window</th><th>Recommendation</th>
      <th>Last 12 m</th><th>Load %</th><th>Days Since Inj</th><th>Body Part</th>
    </tr></thead>
    <tbody>${rows.map(r => `<tr>
      <td class="name">${r.player_name}</td>
      <td class="club">${r.club||'—'}</td>
      <td>${r.position||'—'}</td>
      <td>${r.age||'—'}</td>
      <td>${scoreCell(r.risk_score)}</td>
      <td>${badge(r.risk_tier)}</td>
      <td>${badge(r.ml_predicted_tier||'Low')}</td>
      <td>${r.predicted_injury_window||'—'}</td>
      <td class="rec">${r.recommendation||'—'}</td>
      <td>${r.injuries_last12m||'—'}</td>
      <td>${r.load_pct != null ? r.load_pct+'%' : '—'}</td>
      <td>${r.days_since_last_inj||'—'}</td>
      <td>${r.dominant_body_part||'—'}</td>
    </tr>`).join('')}</tbody>
  </table>`;
}

function renderAccuracy(acc) {
  if (!acc || !Object.keys(acc).length) {
    document.getElementById('acc-grid').innerHTML = '<div style="color:var(--muted)">No accuracy data yet. Run: python 5_cli.py verify</div>';
    return;
  }
  let html = `
    <div class="acc-box"><div class="al">Predictions</div><div class="av">${acc.total||0}</div></div>
    <div class="acc-box"><div class="al">Verified</div><div class="av">${acc.verified||0}</div></div>
    <div class="acc-box"><div class="al">Correct</div><div class="av" style="color:var(--green)">${acc.correct||0}</div></div>
    <div class="acc-box"><div class="al">Wrong</div><div class="av" style="color:var(--crit)">${acc.wrong||0}</div></div>
    <div class="acc-box"><div class="al">Accuracy</div><div class="av" style="color:var(--green)">${acc.accuracy_pct != null ? acc.accuracy_pct+'%' : 'N/A'}</div></div>
    <div class="acc-box"><div class="al">Pending</div><div class="av" style="color:var(--mod)">${acc.pending||0}</div></div>
  `;
  if (acc.by_tier && Object.keys(acc.by_tier).length) {
    for (const [tier, s] of Object.entries(acc.by_tier)) {
      html += `<div class="acc-box">
        <div class="al">${tier}</div>
        <div class="av" style="color:${tierColor(tier)}">${s.accuracy_pct}%</div>
        <div style="font-size:11px;color:var(--muted)">${s.correct}/${s.total}</div>
      </div>`;
    }
  }
  document.getElementById('acc-grid').innerHTML = html;
}

function startCountdown() {
  clearInterval(countdownTimer);
  countdownVal = 60;
  countdownTimer = setInterval(() => {
    countdownVal--;
    document.getElementById('countdown').textContent = `Auto-refresh in ${countdownVal}s`;
    if (countdownVal <= 0) loadData();
  }, 1000);
}

async function loadData() {
  try {
    const res  = await fetch('/api/data');
    const data = await res.json();
    renderStats(data);
    renderChart(data);
    renderInjured(data.injured || []);
    renderRisk(data.risk || []);
    renderAccuracy(data.accuracy || {});
    const now = new Date();
    document.getElementById('last-updated').textContent =
      'Updated ' + now.toLocaleTimeString();
    startCountdown();
  } catch(e) {
    document.getElementById('last-updated').textContent = 'Error loading data';
    console.error(e);
  }
}

loadData();
</script>
</body>
</html>"""


# ── HTTP Server ───────────────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/data":
            body = json.dumps(_load()).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", len(body))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass  # suppress per-request logs


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Football Injury Dashboard")
    ap.add_argument("--port", type=int, default=5050)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    url = f"http://localhost:{args.port}"
    print(f"  Dashboard → {url}")
    print("  Press Ctrl+C to stop.\n")

    if not args.no_browser:
        webbrowser.open(url)

    HTTPServer(("", args.port), Handler).serve_forever()
