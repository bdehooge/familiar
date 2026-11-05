"""Watch a text file that some other tool writes while something is wrong, and deletes when it's fixed.

Config (~/.familiar/config.json):
  "plugins": {"alert_file": {
      "path": "C:/path/to/ALERT.txt",
      "meanings": {"<check id>": {"text": "plain words, {msg} is the original message", "alarm": true}},
      "default_alarm": false
  }}
Lines are read as "[LEVEL] id: message"; other lines are ignored. A CRIT level always alarms.
"""
import os


class Plugin:
    def __init__(self, opts):
        self.path = opts.get("path", "")
        self.meanings = opts.get("meanings", {})
        self.default_alarm = bool(opts.get("default_alarm", False))
        self.prefix = opts.get("prefix", "")

    def alerts(self):
        try:
            with open(self.path, encoding="utf-8", errors="replace") as f:
                lines = [ln.strip() for ln in f if ln.strip()]
        except FileNotFoundError:
            return []
        out = []
        for ln in lines:
            if not ln.startswith("[") or "]" not in ln:
                continue
            level, rest = ln[1:].split("]", 1)
            cid, _, msg = rest.strip().partition(":")
            cid, msg, level = cid.strip(), msg.strip(), level.strip()
            m = self.meanings.get(cid) or next((v for k, v in self.meanings.items() if k.endswith("*") and cid.startswith(k[:-1])), None)
            text = (m or {}).get("text", cid + ": {msg}").format(msg=msg)
            alarm = level == "CRIT" or (m or {}).get("alarm", self.default_alarm)
            out.append({"id": cid, "text": self.prefix + text, "alarm": alarm})
        return out
