import csv, re, json, datetime, statistics
from pathlib import Path

DATA = Path("/data")

iperf_path = DATA / "iperf_log.ndjson"
pr_path    = DATA / "ping_router.txt"
pe_path    = DATA / "ping_external.txt"

out_iperf = DATA / "iperf_summary.csv"
out_pr    = DATA / "ping_router.csv"
out_pe    = DATA / "ping_external.csv"
out_bull  = DATA / "bullshit_events.csv"
out_txt   = DATA / "isp_summary.txt"

BAD_Mbps = 5.0
EXTERNAL_PING_SPIKE_MS = 200.0
ROUTER_PING_SPIKE_MS = 50.0
WINDOW_S = 45

def parse_iso(ts: str):
    return datetime.datetime.fromisoformat(ts)

def dt_floor_second(dt):
    return dt.replace(microsecond=0)

def nearest(d, ts, window_s=45):
    best = None
    best_dt = None
    for delta in range(window_s + 1):
        for sign in (-1, 1) if delta else (1,):
            cand = ts + datetime.timedelta(seconds=sign * delta) if delta else ts
            cand = dt_floor_second(cand)
            if cand in d:
                if best_dt is None or abs((cand - ts).total_seconds()) < abs((best_dt - ts).total_seconds()):
                    best = d[cand]
                    best_dt = cand
    return best

def load_ping(path: Path):
    d = {}
    if not path.exists():
        return d

    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        m = re.match(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[^\s]*)\s+(.*)$", line)
        if not m:
            continue
        try:
            ts = dt_floor_second(parse_iso(m.group(1)))
        except Exception:
            continue

        rest = m.group(2)
        if "Request timeout" in rest or "timeout" in rest.lower():
            d[ts] = {"ping_ms": "", "timeout": "1"}
            continue

        tm = re.search(r"time=([\d\.]+)\s*ms", rest)
        if tm:
            d[ts] = {"ping_ms": tm.group(1), "timeout": "0"}

    return d

def write_ping_csv(d, out):
    with out.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp","ping_ms","timeout"])
        for ts, rec in sorted(d.items()):
            w.writerow([ts.isoformat(), rec.get("ping_ms",""), rec.get("timeout","0")])

# ----------------- load ping logs -----------------
ping_r = load_ping(pr_path)
ping_e = load_ping(pe_path)

write_ping_csv(ping_r, out_pr)
write_ping_csv(ping_e, out_pe)

# ----------------- load iperf logs -----------------
if not iperf_path.exists():
    raise SystemExit(f"Missing {iperf_path}")

iperf_rows = []
for line in iperf_path.read_text(errors="ignore").splitlines():
    line = line.strip()
    if not line.startswith("{"):
        continue

    try:
        j = json.loads(line)
    except Exception:
        continue

    ts = j.get("timestamp")
    direction = j.get("direction","")
    if not ts or not direction:
        continue

    mbps = ""
    try:
        bps = j["end"]["sum_received"]["bits_per_second"]
        mbps = float(bps) / 1_000_000
    except Exception:
        mbps = None

    zero_secs = 0
    try:
        for it in j.get("intervals", []):
            s = it.get("sum", {})
            if s.get("bits_per_second", 1) == 0:
                zero_secs += 1
    except Exception:
        zero_secs = 0

    err = j.get("error","")
    exit_code = j.get("exit_code","")

    iperf_rows.append({
        "timestamp": ts,
        "direction": direction,
        "mbps": mbps,
        "zero_secs": zero_secs,
        "error": err,
        "exit_code": exit_code,
    })

# write iperf summary csv
with out_iperf.open("w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["timestamp","direction","mbps","zero_secs","error","exit_code"])
    for r in iperf_rows:
        w.writerow([
            r["timestamp"],
            r["direction"],
            "" if r["mbps"] is None else f"{r['mbps']:.3f}",
            r["zero_secs"],
            r["error"],
            r["exit_code"],
        ])

# ----------------- bullshit events -----------------
bull = []
for r in iperf_rows:
    ts_dt = dt_floor_second(parse_iso(r["timestamp"]))
    reasons = []

    if r["error"]:
        reasons.append(f"iperf_error:{r['error']}")

    if r["mbps"] is not None and r["mbps"] < BAD_Mbps:
        reasons.append(f"mbps<{BAD_Mbps}")

    if r["zero_secs"] >= 2:
        reasons.append(f"zero_secs={r['zero_secs']}")

    pr = nearest(ping_r, ts_dt, WINDOW_S) or {}
    pe = nearest(ping_e, ts_dt, WINDOW_S) or {}

    if pr.get("timeout") == "1":
        reasons.append("router_ping_timeout")
    if pe.get("timeout") == "1":
        reasons.append("external_ping_timeout")

    try:
        if pr.get("ping_ms") and float(pr["ping_ms"]) > ROUTER_PING_SPIKE_MS:
            reasons.append(f"router_ping>{ROUTER_PING_SPIKE_MS}")
    except Exception:
        pass

    try:
        if pe.get("ping_ms") and float(pe["ping_ms"]) > EXTERNAL_PING_SPIKE_MS:
            reasons.append(f"external_ping>{EXTERNAL_PING_SPIKE_MS}")
    except Exception:
        pass

    if not reasons:
        continue

    bull.append({
        "timestamp": r["timestamp"],
        "direction": r["direction"],
        "mbps": "" if r["mbps"] is None else f"{r['mbps']:.3f}",
        "zero_secs": str(r["zero_secs"]),
        "iperf_error": r["error"],
        "exit_code": str(r["exit_code"]),
        "router_ping_ms": pr.get("ping_ms",""),
        "router_timeout": pr.get("timeout","0"),
        "external_ping_ms": pe.get("ping_ms",""),
        "external_timeout": pe.get("timeout","0"),
        "reasons": ";".join(reasons),
    })

# sort: errors/timeouts first, then lowest mbps
def sev(x):
    s = 0
    if x["iperf_error"]: s += 100
    if x["external_timeout"] == "1": s += 80
    if x["router_timeout"] == "1": s += 60
    try:
        mb = float(x["mbps"]) if x["mbps"] else 999
    except:
        mb = 999
    return (-s, mb)

bull.sort(key=sev)

with out_bull.open("w", newline="") as f:
    fields = [
        "timestamp","direction","mbps","zero_secs","iperf_error","exit_code",
        "router_ping_ms","router_timeout",
        "external_ping_ms","external_timeout",
        "reasons"
    ]
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for row in bull:
        w.writerow(row)

# ----------------- ISP summary text -----------------
def pct(n, d):
    return 0.0 if d == 0 else (100.0 * n / d)

dl = [r for r in iperf_rows if r["direction"] == "download" and r["mbps"] is not None]
ul = [r for r in iperf_rows if r["direction"] == "upload" and r["mbps"] is not None]

def stats(rows):
    if not rows:
        return None
    vals = [r["mbps"] for r in rows]
    return {
        "count": len(vals),
        "min": min(vals),
        "median": statistics.median(vals),
        "mean": statistics.mean(vals),
        "max": max(vals),
    }

dl_stats = stats(dl)
ul_stats = stats(ul)

timeout_router = sum(1 for v in ping_r.values() if v.get("timeout") == "1")
timeout_ext = sum(1 for v in ping_e.values() if v.get("timeout") == "1")

with out_txt.open("w") as f:
    f.write("NetProof ISP Evidence Summary\n")
    f.write("============================\n\n")
    f.write(f"iperf tests logged: {len(iperf_rows)}\n")
    f.write(f"flagged events: {len(bull)}\n\n")

    if dl_stats:
        f.write("DOWNLOAD (iperf3 reverse)\n")
        f.write(f"  samples: {dl_stats['count']}\n")
        f.write(f"  min:     {dl_stats['min']:.2f} Mbps\n")
        f.write(f"  median:  {dl_stats['median']:.2f} Mbps\n")
        f.write(f"  mean:    {dl_stats['mean']:.2f} Mbps\n")
        f.write(f"  max:     {dl_stats['max']:.2f} Mbps\n\n")

    if ul_stats:
        f.write("UPLOAD (iperf3)\n")
        f.write(f"  samples: {ul_stats['count']}\n")
        f.write(f"  min:     {ul_stats['min']:.2f} Mbps\n")
        f.write(f"  median:  {ul_stats['median']:.2f} Mbps\n")
        f.write(f"  mean:    {ul_stats['mean']:.2f} Mbps\n")
        f.write(f"  max:     {ul_stats['max']:.2f} Mbps\n\n")

    f.write("PING SUMMARY\n")
    f.write(f"  router ping samples:   {len(ping_r)}\n")
    f.write(f"  router timeouts:       {timeout_router} ({pct(timeout_router, len(ping_r)):.2f}%)\n")
    f.write(f"  external ping samples: {len(ping_e)}\n")
    f.write(f"  external timeouts:     {timeout_ext} ({pct(timeout_ext, len(ping_e)):.2f}%)\n\n")

    f.write("Generated files:\n")
    f.write("  iperf_summary.csv\n")
    f.write("  ping_router.csv\n")
    f.write("  ping_external.csv\n")
    f.write("  bullshit_events.csv\n")
    f.write("  isp_summary.txt\n")

print(f"Wrote: {out_iperf}")
print(f"Wrote: {out_pr}")
print(f"Wrote: {out_pe}")
print(f"Wrote: {out_bull} ({len(bull)} events)")
print(f"Wrote: {out_txt}")
