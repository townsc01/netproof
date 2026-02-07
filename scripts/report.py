import csv, re, json, datetime, statistics
from pathlib import Path

DATA = Path("/data")

iperf_path = DATA / "iperf_log.ndjson"
speed_path = DATA / "speed_log.ndjson"   # optional (Ookla mode)
pr_path    = DATA / "ping_router.txt"
pe_path    = DATA / "ping_external.txt"

out_unified = DATA / "unified_timeseries.csv"
out_txt     = DATA / "isp_summary.txt"

# thresholds for flagging
BAD_DL_Mbps = 5.0
BAD_UL_Mbps = 2.0
ROUTER_PING_SPIKE_MS = 50.0
EXTERNAL_PING_SPIKE_MS = 200.0
WINDOW_S = 45

def parse_iso(ts: str):
    # iperf/speedtest timestamps are ISO8601 already
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

def load_iperf(path: Path):
    """
    Returns dict keyed by timestamp-second:
      { ts: { 'download_mbps': float|None, 'upload_mbps': float|None,
              'download_error': str, 'upload_error': str } }
    We merge upload+download that share the same timestamp (your loop does them back-to-back).
    """
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
        direction = j.get("direction")
        if not ts or direction not in ("download", "upload"):
            continue

        ts_dt = dt_floor_second(parse_iso(ts))
        rec = out.setdefault(ts_dt, {
            "download_mbps": None,
            "upload_mbps": None,
            "download_error": "",
            "upload_error": "",
        })

        err = j.get("error", "") or ""
        if err:
            if direction == "download":
                rec["download_error"] = err
            else:
                rec["upload_error"] = err

        # throughput
        mbps = None
        try:
            bps = j["end"]["sum_received"]["bits_per_second"]
            mbps = float(bps) / 1_000_000
        except Exception:
            mbps = None

        if direction == "download":
            rec["download_mbps"] = mbps
        else:
            rec["upload_mbps"] = mbps

    return out

def load_speedtest(path: Path):
    """
    Expects NDJSON records like:
      {timestamp, mode:"speedtest", download_mbps, upload_mbps, ping_ms, jitter_ms, packet_loss, error}
    Returns dict keyed by timestamp-second with those fields.
    """
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

        out[ts_dt] = {
            "download_mbps": j.get("download_mbps", None),
            "upload_mbps": j.get("upload_mbps", None),
            "ping_ms": j.get("ping_ms", None),
            "jitter_ms": j.get("jitter_ms", None),
            "packet_loss": j.get("packet_loss", None),
            "error": j.get("error", "") or "",
        }

    return out

def fmt(x):
    if x is None:
        return ""
    try:
        return f"{float(x):.3f}"
    except Exception:
        return str(x)

# Load sources
ping_r = load_ping(pr_path)
ping_e = load_ping(pe_path)
iperf = load_iperf(iperf_path)
speed = load_speedtest(speed_path)

# Build unified event timeline:
# one row per throughput test moment (iperf merged per second OR speedtest per second)
events = []
for ts_dt, rec in iperf.items():
    events.append((ts_dt, "iperf", rec))
for ts_dt, rec in speed.items():
    events.append((ts_dt, "speedtest", rec))
events.sort(key=lambda x: x[0])

# Write unified CSV
fields = [
    "timestamp",
    "source",
    "download_mbps",
    "upload_mbps",
    "source_error",
    "router_ping_ms",
    "router_timeout",
    "external_ping_ms",
    "external_timeout",
    "jitter_ms",
    "packet_loss",
    "reasons",
]

flagged = 0
dl_vals = []
ul_vals = []
ext_ping_vals = []

with out_unified.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()

    for ts_dt, source, rec in events:
        pr = nearest(ping_r, ts_dt, WINDOW_S) or {}
        pe = nearest(ping_e, ts_dt, WINDOW_S) or {}

        # normalise per-source
        if source == "iperf":
            dl = rec.get("download_mbps", None)
            ul = rec.get("upload_mbps", None)
            derr = rec.get("download_error", "")
            uerr = rec.get("upload_error", "")
            src_err = ";".join([x for x in (derr, uerr) if x])
            jitter = None
            ploss = None
        else:
            dl = rec.get("download_mbps", None)
            ul = rec.get("upload_mbps", None)
            src_err = rec.get("error", "")
            jitter = rec.get("jitter_ms", None)
            ploss = rec.get("packet_loss", None)

        # accumulate stats
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

        if src_err:
            reasons.append(f"{source}_error")

        try:
            if dl is not None and float(dl) < BAD_DL_Mbps:
                reasons.append("download_below_threshold")
        except: pass

        try:
            if ul is not None and float(ul) < BAD_UL_Mbps:
                reasons.append("upload_below_threshold")
        except: pass

        if pr.get("timeout") == "1":
            reasons.append("router_ping_timeout")
        if pe.get("timeout") == "1":
            reasons.append("external_ping_timeout")

        try:
            if pr.get("ping_ms") and float(pr["ping_ms"]) > ROUTER_PING_SPIKE_MS:
                reasons.append("router_ping_spike")
        except: pass
        try:
            if pe.get("ping_ms") and float(pe["ping_ms"]) > EXTERNAL_PING_SPIKE_MS:
                reasons.append("external_ping_spike")
        except: pass

        if reasons:
            flagged += 1

        w.writerow({
            "timestamp": ts_dt.isoformat(),
            "source": source,
            "download_mbps": fmt(dl),
            "upload_mbps": fmt(ul),
            "source_error": src_err,
            "router_ping_ms": pr.get("ping_ms",""),
            "router_timeout": pr.get("timeout","0"),
            "external_ping_ms": pe.get("ping_ms",""),
            "external_timeout": pe.get("timeout","0"),
            "jitter_ms": fmt(jitter),
            "packet_loss": fmt(ploss),
            "reasons": ";".join(reasons),
        })

def stats(vals):
    if not vals:
        return None
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

def pct(n, d):
    return 0.0 if d == 0 else (100.0 * n / d)

with out_txt.open("w") as f:
    f.write("NetProof ISP Evidence Summary\n")
    f.write("============================\n\n")
    f.write(f"unified rows: {len(events)}\n")
    f.write(f"flagged rows: {flagged}\n\n")

    if dl_s:
        f.write("DOWNLOAD\n")
        f.write(f"  samples: {dl_s['count']}\n")
        f.write(f"  min:     {dl_s['min']:.2f} Mbps\n")
        f.write(f"  median:  {dl_s['median']:.2f} Mbps\n")
        f.write(f"  mean:    {dl_s['mean']:.2f} Mbps\n")
        f.write(f"  max:     {dl_s['max']:.2f} Mbps\n\n")

    if ul_s:
        f.write("UPLOAD\n")
        f.write(f"  samples: {ul_s['count']}\n")
        f.write(f"  min:     {ul_s['min']:.2f} Mbps\n")
        f.write(f"  median:  {ul_s['median']:.2f} Mbps\n")
        f.write(f"  mean:    {ul_s['mean']:.2f} Mbps\n")
        f.write(f"  max:     {ul_s['max']:.2f} Mbps\n\n")

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
    f.write("  isp_summary.txt\n")

print(f"Wrote: {out_unified} ({len(events)} rows)")
print(f"Wrote: {out_txt}")
