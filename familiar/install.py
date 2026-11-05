"""Wire (or unwire) the Familiar hooks into Claude Code's user settings.

python -m familiar.install            add hooks to ~/.claude/settings.json (backup first)
python -m familiar.install --remove   remove only Familiar's hooks
"""
import json, os, shutil, sys, time

SETTINGS = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
EVENTS = ["UserPromptSubmit", "PreToolUse", "Notification", "Stop"]
MARK = "familiar.hook"


def command():
    py = sys.executable.replace("python.exe", "pythonw.exe") if os.name == "nt" else sys.executable
    if not os.path.exists(py):
        py = sys.executable
    return '"%s" -m familiar.hook' % py


def load():
    try:
        with open(SETTINGS, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def strip(settings):
    hooks = settings.get("hooks", {})
    for ev in list(hooks):
        groups = []
        for g in hooks[ev]:
            g = dict(g, hooks=[h for h in g.get("hooks", []) if MARK not in h.get("command", "")])
            if g["hooks"]:
                groups.append(g)
        if groups:
            hooks[ev] = groups
        else:
            del hooks[ev]
    if not hooks:
        settings.pop("hooks", None)
    return settings


def main():
    remove = "--remove" in sys.argv
    s = load()
    if os.path.exists(SETTINGS):
        bak = SETTINGS + ".bak-familiar-" + time.strftime("%Y%m%d-%H%M%S")
        shutil.copy2(SETTINGS, bak)
        print("backup:", bak)
    s = strip(s)
    if not remove:
        hooks = s.setdefault("hooks", {})
        for ev in EVENTS:
            entry = {"hooks": [{"type": "command", "command": command(), "timeout": 5}]}
            if ev == "PreToolUse":
                entry["matcher"] = "*"
            hooks.setdefault(ev, []).append(entry)
    os.makedirs(os.path.dirname(SETTINGS), exist_ok=True)
    with open(SETTINGS, "w", encoding="utf-8") as f:
        json.dump(s, f, indent=2)
    print("removed Familiar hooks" if remove else "installed hooks for " + ", ".join(EVENTS))


if __name__ == "__main__":
    main()
