"""Data sources, polled on a background thread. Each returns plain dicts; missing data is None, never an exception.

- system():        CPU / GPU / RAM load, temperature and power for the footer table
- claude_usage():  Claude plan 5-hour and weekly utilization (same endpoint Claude Code's /usage shows)
- tokens_today():  tokens Claude Code used today, summed from local transcripts
- claude_code():   what Claude Code is doing right now (written by familiar.hook)
"""
import datetime, glob, json, os, subprocess, time, urllib.request

HOME = os.path.expanduser("~")
CC_STATE = os.path.join(HOME, ".familiar", "cc_state.json")
CC_STALE = 15 * 60
NO_WINDOW = 0x08000000 if os.name == "nt" else 0

try:
    import psutil
except ImportError:  # optional: CPU/RAM columns show a dash without it
    psutil = None


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _lhm():
    """LibreHardwareMonitor's optional web server (Options > Remote Web Server) is the only no-admin
    way to read CPU temperature and package power on Windows. Returns {"cpu_temp", "cpu_power"}."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8085/data.json", timeout=1.5) as r:
            tree = json.load(r)
    except Exception:
        return {}
    out = {}

    def walk(n, path):
        t = n.get("Text", "")
        v = _num(str(n.get("Value", "")).split(" ")[0].replace(",", "."))
        p = path + [t]
        joined = "/".join(p).lower()
        if v is not None and ("cpu" in joined or "ryzen" in joined or "intel" in joined):
            if t in ("CPU Package", "Core (Tctl/Tdie)", "Package") and "temperatures" in joined and "cpu_temp" not in out:
                out["cpu_temp"] = v
            if t in ("CPU Package", "Package") and "powers" in joined and "cpu_power" not in out:
                out["cpu_power"] = v
        for c in n.get("Children", []):
            walk(c, p)

    walk(tree, [])
    return out


def system():
    s = {"cpu": {}, "gpu": {}, "ram": {}}
    if psutil:
        s["cpu"]["load"] = psutil.cpu_percent(interval=None)
        vm = psutil.virtual_memory()
        s["ram"] = {"load": vm.percent, "free_gb": vm.available / 2**30, "total_gb": vm.total / 2**30}
    lhm = _lhm()
    s["cpu"]["temp"], s["cpu"]["power"] = lhm.get("cpu_temp"), lhm.get("cpu_power")
    try:
        q = "utilization.gpu,temperature.gpu,power.draw,memory.used,memory.total"
        line = subprocess.run(["nvidia-smi", "--query-gpu=" + q, "--format=csv,noheader,nounits"], capture_output=True,
                              text=True, timeout=10, creationflags=NO_WINDOW).stdout.strip().splitlines()[0]
        u, t, p, mu, mt = [_num(x.strip()) for x in line.split(",")]
        s["gpu"] = {"load": u, "temp": t, "power": p, "vram_gb": (mu or 0) / 1024, "vram_total_gb": (mt or 0) / 1024}
    except Exception:
        pass
    return s


def claude_usage():
    """5-hour and weekly plan utilization. Reads the OAuth token Claude Code stores locally; read-only."""
    cred = os.path.join(HOME, ".claude", ".credentials.json")
    with open(cred, encoding="utf-8") as f:
        tok = json.load(f).get("claudeAiOauth", {}).get("accessToken", "")
    req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={
        "Authorization": "Bearer " + tok, "anthropic-beta": "oauth-2025-04-20", "User-Agent": "familiar/0.1"})
    with urllib.request.urlopen(req, timeout=15) as r:
        u = json.load(r)
    pick = lambda w: w and {"pct": float(w.get("utilization") or 0), "resets": w.get("resets_at")}
    return {"five": pick(u.get("five_hour")), "week": pick(u.get("seven_day"))}


_tok_cache = {"day": None, "files": {}}


def tokens_today():
    """Sum of input + output + cache tokens in today's Claude Code transcripts (~/.claude/projects/**.jsonl).
    Files are re-read only when they grow."""
    today = datetime.date.today()
    if _tok_cache["day"] != today:
        _tok_cache.update(day=today, files={})
    start = datetime.datetime.combine(today, datetime.time()).timestamp()
    total = 0
    for fn in glob.glob(os.path.join(HOME, ".claude", "projects", "*", "*.jsonl")):
        try:
            st = os.stat(fn)
        except OSError:
            continue
        if st.st_mtime < start:
            continue
        size, n = _tok_cache["files"].get(fn, (0, 0))
        if st.st_size != size:
            n = 0
            with open(fn, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if '"usage"' not in line:
                        continue
                    try:
                        j = json.loads(line)
                        ts = datetime.datetime.fromisoformat(j.get("timestamp", "").replace("Z", "+00:00")).timestamp()
                    except Exception:
                        continue
                    if ts < start:
                        continue
                    u = (j.get("message") or {}).get("usage") or {}
                    n += sum(int(u.get(k) or 0) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            _tok_cache["files"][fn] = (st.st_size, n)
        total += n
    return total


def claude_code(tool_kinds):
    """Most recent live Claude Code session -> activity kind ('think', 'read', 'shell', ..., 'wait') or None."""
    try:
        with open(CC_STATE, encoding="utf-8") as f:
            ss = json.load(f).get("sessions", {})
    except Exception:
        return None
    now = time.time()
    live = [s for s in ss.values() if s.get("state") in ("working", "waiting") and now - s.get("ts", 0) / 1000 < CC_STALE]
    if not live:
        return None
    s = max(live, key=lambda s: s.get("ts", 0))
    if s.get("state") == "waiting":
        return "wait"
    base = (s.get("tool") or "").split("__")[-1]
    for kind, names in tool_kinds:
        if base in names:
            return kind
    return "think"
