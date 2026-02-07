import csv, re, json, datetime, statistics
from pathlib import Path

DATA = Path("/data")
cfg_path = DATA / "config.env"

speed_path = DATA / "speed_log.ndjson"
pr_path    = DATA / "ping_router.txt"
pe_path    = DATA / "ping_external.txt"

out_unified = DATA / "unified_timeseries.csv"
out_slow    = DATA / "slowdowns.csv"
out_txt     = DATA / "isp_summary.txt"

WINDOW_S = 45
ROUTER_PING_SPIKE_MS = 50.0
EXTERNAL_PING_SPIKE_MS = 200.0

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

def load_kv_env(path: Path):
    d = {}
    if not path.exists():
        return d
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k.strip()] = v.strip()
    return d

def as_float(x):
    if x is None: return None
    s = str(x).strip()
    if s == "": return None
    try: return float(s)
    except: return None

def as_int(x, default=None):
    try: return int(str(x).strip())
    except: return default

def fmt(x, ndp=3):
    if x is None: return ""
    try: return f"{float(x):.{ndp}f}"
    except: return str(x)

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

def mbps_from_speedtest(j, key):
    # Ookla: download.bandwidth/upload.bandwidth in BYTES/sec
    try:
        bps_bytes = j[key]["bandwidth"]
        return float(bps_bytes) * 8.0 / 1_000_000.0
    except Exception:
        return None

def load_speedtest(path: Path):
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            j = json.loads(line)
        except Exception:
            continue

        ts = j.get("timestamp")
        if not ts:
            continue
        ts_dt = dt_floor_second(parse_iso(ts))

        rec = {
            "download_mbps": mbps_from_speedtest(j, "download"),
            "upload_mbps": mbps_from_speedtest(j, "upload"),
            "speedtest_ping_ms": (j.get("ping") or {}).get("latency", None),
            "jitter_ms": (j.get("ping") or {}).get("jitter", None),
            "packet_loss": j.get("packetLoss", None),
            "isp": j.get("isp", ""),
            "server": ((j.get("server") or {}).get("name","") + " " + (j.get("server") or {}).get("location","")).strip(),
            "error": (j.get("error","") or "").strip(),
        }
        out[ts_dt] = rec
    return out

cfg = load_kv_env(cfg_path)
mode = (cfg.get("MODE") or "speedtest").strip()

adv_down = as_float(cfg.get("ADVERTISED_DOWN_Mbps"))
adv_up   = as_float(cfg.get("ADVERTISED_UP_Mbps"))
slow_pct = as_int(cfg.get("SLOWDOWN_PCT"), 25)

abs_min_down = as_float(cfg.get("ABS_MIN_DOWN_Mbps")) or 5.0
abs_min_up   = as_float(cfg.get("ABS_MIN_UP_Mbps")) or 2.0

use_relative = (adv_down is not None and adv_up is not None)

if use_relative:
    dl_threshold = adv_down * (slow_pct / 100.0)
    ul_threshold = adv_up * (slow_pct / 100.0)
    threshold_desc = f"relative: <{slow_pct}% of advertised ({adv_down:.1f}/{adv_up:.1f} Mbps) => {dl_threshold:.2f}/{ul_threshold:.2f} Mbps"
else:
    dl_threshold = abs_min_down
    ul_threshold = abs_min_up
    threshold_desc = f"absolute: download<{dl_threshold:.2f} Mbps, upload<{ul_threshold:.2f} Mbps"

ping_r = load_ping(pr_path)
ping_e = load_ping(pe_path)
speed = load_speedtest(speed_path)

events = sorted(speed.items(), key=lambda x: x[0])

fields = [
    "timestamp","source","download_mbps","upload_mbps","source_error",
    "router_ping_ms","router_timeout","external_ping_ms","external_timeout",
    "speedtest_ping_ms","jitter_ms","packet_loss","slowdown_flag","reasons",
    "threshold_down_mbps","threshold_up_mbps","isp","server"
]

slow_rows = []
dl_vals, ul_vals, ext_ping_vals = [], [], []

with out_unified.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()

    for ts_dt, rec in events:
        pr = nearest(ping_r, ts_dt, WINDOW_S) or {}
        pe = nearest(ping_e, ts_dt, WINDOW_S) or {}

        dl = rec.get("download_mbps", None)
        ul = rec.get("upload_mbps", None)

        if dl is not None:
            try: dl_vals.append(float(dl))
            except: pass
        if ul is not None:
            try: ul_vals.append(float(ul))
            except: pass
        if pe.get("ping_ms"):
            try: ext_ping_vals.append(float(pe["ping_ms"]))
            except: pass

        reasons = []
        if rec.get("error"):
            reasons.append("speedtest_error")

        try:
            if dl is not None and float(dl) < dl_threshold:
                reasons.append("download_below_threshold")
        except: pass

        try:
            if ul is not None and float(ul) < ul_threshold:
                reasons.append("upload_below_threshold")
        except: pass

        if pr.get("timeout") == "1": reasons.append("router_ping_timeout")
        if pe.get("timeout") == "1": reasons.append("external_ping_timeout")

        try:
            if pr.get("ping_ms") and float(pr["ping_ms"]) > ROUTER_PING_SPIKE_MS:
                reasons.append("router_ping_spike")
        except: pass

        try:
            if pe.get("ping_ms") and float(pe["ping_ms"]) > EXTERNAL_PING_SPIKE_MS:
                reasons.append("external_ping_spike")
        except: pass

        row = {
            "timestamp": ts_dt.isoformat(),
            "source": "speedtest",
            "download_mbps": fmt(dl, 3),
            "upload_mbps": fmt(ul, 3),
            "source_error": rec.get("error",""),
            "router_ping_ms": pr.get("ping_ms",""),
            "router_timeout": pr.get("timeout","0"),
            "external_ping_ms": pe.get("ping_ms",""),
            "external_timeout": pe.get("timeout","0"),
            "speedtest_ping_ms": fmt(rec.get("speedtest_ping_ms", None), 3),
            "jitter_ms": fmt(rec.get("jitter_ms", None), 3),
            "packet_loss": fmt(rec.get("packet_loss", None), 3),
            "slowdown_flag": "1" if reasons else "0",
            "reasons": ";".join(reasons),
            "threshold_down_mbps": fmt(dl_threshold, 3),
            "threshold_up_mbps": fmt(ul_threshold, 3),
            "isp": rec.get("isp",""),
            "server": rec.get("server",""),
        }

        w.writerow(row)
        if reasons:
            slow_rows.append(row)

with out_slow.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for row in slow_rows:
        w.writerow(row)

def stats(vals):
    if not vals: return None
    return {
        "count": len(vals),
        "min": min(vals),
        "median": statistics.median(vals),
        "mean": statistics.mean(vals),
        "max": max(vals),
    }

dl_s = stats(dl_vals)
ul_s = stats(ul_vals)
ep_s = stats(ext_ping_vals)

router_timeouts = sum(1 for v in ping_r.values() if v.get("timeout") == "1")
ext_timeouts = sum(1 for v in ping_e.values() if v.get("timeout") == "1")

def pct(n, d): return 0.0 if d == 0 else (100.0 * n / d)

with out_txt.open("w") as f:
    f.write("NetProof ISP Evidence Summary\n")
    f.write("============================\n\n")
    f.write(f"MODE: {mode}\n")
    f.write(f"Speedtests: {len(events)}\n")
    f.write(f"Slowdowns flagged: {len(slow_rows)}\n\n")
    f.write(f"Threshold used: {threshold_desc}\n\n")

    if dl_s:
        f.write("DOWNLOAD (Mbps)\n")
        f.write(f"  samples: {dl_s['count']}\n")
        f.write(f"  min:     {dl_s['min']:.2f}\n")
        f.write(f"  median:  {dl_s['median']:.2f}\n")
        f.write(f"  mean:    {dl_s['mean']:.2f}\n")
        f.write(f"  max:     {dl_s['max']:.2f}\n\n")

    if ul_s:
        f.write("UPLOAD (Mbps)\n")
        f.write(f"  samples: {ul_s['count']}\n")
        f.write(f"  min:     {ul_s['min']:.2f}\n")
        f.write(f"  median:  {ul_s['median']:.2f}\n")
        f.write(f"  mean:    {ul_s['mean']:.2f}\n")
        f.write(f"  max:     {ul_s['max']:.2f}\n\n")

    f.write("PING SUMMARY\n")
    f.write(f"  router ping samples:   {len(ping_r)}\n")
    f.write(f"  router timeouts:       {router_timeouts} ({pct(router_timeouts, len(ping_r)):.2f}%)\n")
    f.write(f"  external ping samples: {len(ping_e)}\n")
    f.write(f"  external timeouts:     {ext_timeouts} ({pct(ext_timeouts, len(ping_e)):.2f}%)\n")
    if ep_s:
        f.write(f"  external ping median:  {ep_s['median']:.1f} ms\n")
    f.write("\n")

    f.write("Generated files:\n")
    f.write("  unified_timeseries.csv\n")
    f.write("  slowdowns.csv\n")
    f.write("  isp_summary.txt\n")

print(f"Wrote: {out_unified} ({len(events)} rows)")
print(f"Wrote: {out_slow} ({len(slow_rows)} slowdowns)")
print(f"Wrote: {out_txt}")
