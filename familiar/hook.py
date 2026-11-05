"""Claude Code hook handler: `python -m familiar.hook` (wired by `python -m familiar.install`).

Reads the hook JSON on stdin and records per-session state in ~/.familiar/cc_state.json.
Never prints, never blocks, always exits 0 so it can't disturb Claude Code.
"""
import json, os, sys, time

STATE = os.path.join(os.path.expanduser("~"), ".familiar", "cc_state.json")


def main():
    try:
        h = json.loads(sys.stdin.read() or "{}")
        ev = h.get("hook_event_name") or (sys.argv[1] if len(sys.argv) > 1 else "")
        sid = h.get("session_id") or "unknown"
        state = "idle" if ev in ("Stop", "SessionEnd") else ("waiting" if ev == "Notification" else "working")
        try:
            with open(STATE, encoding="utf-8") as f:
                cur = json.load(f)
        except Exception:
            cur = {}
        ss = cur.get("sessions", {})
        now = time.time() * 1000
        for k in [k for k, v in ss.items() if now - v.get("ts", 0) > 6 * 3600e3]:
            del ss[k]
        prev = ss.get(sid, {})
        tool = h.get("tool_name", "") if ev == "PreToolUse" else ("" if ev == "UserPromptSubmit" or state != "working" else prev.get("tool", ""))
        ss[sid] = {"state": state, "tool": tool, "event": ev, "ts": now}
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        tmp = "%s.%d.tmp" % (STATE, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"sessions": ss}, f)
        os.replace(tmp, STATE)
    except Exception:
        pass
    sys.exit(0)


if __name__ == "__main__":
    main()
