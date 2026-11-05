"""Persona packs: a folder with persona.json and frames/<mood>_<n>.png.

Moods are fixed slots the app knows how to trigger. A pack can leave any out; missing moods fall back
to 'idle'. Frame 0 is the base pose; frames 1..N are the animation loop (N is usually 9, from a 3x3 sheet).
"""
import glob, json, os, re

MOODS = {
    "idle":  "nothing happening",
    "sleep": "you've been away a while (or it's late)",
    "happy": "Claude Code just finished, or you booped it",
    "alert": "a plugin raised a real problem, or the GPU is hot",
    "think": "Claude Code is thinking, reading or searching",
    "work":  "Claude Code is running commands or editing files",
    "wait":  "Claude Code is waiting on you (permission or input)",
    "sad":   "your Claude usage window is (nearly) used up",
    "gpu":   "the GPU is busy (games, renders, local models)",
}

DEFAULT_PHRASES = {
    "think": ["Thinking"], "read": ["Reading"], "shell": ["Running commands"], "edit": ["Editing"],
    "web": ["Browsing"], "agent": ["Delegating"], "memory": ["Remembering"], "media": ["Drawing"], "wait": ["Waiting on you"],
}


class Persona:
    def __init__(self, folder):
        self.folder = os.path.abspath(folder)
        with open(os.path.join(self.folder, "persona.json"), encoding="utf-8") as f:
            self.cfg = json.load(f)
        self.name = self.cfg.get("name", os.path.basename(self.folder))
        self.phrases = dict(DEFAULT_PHRASES, **{k: v for k, v in self.cfg.get("working_phrases", {}).items() if v})
        self.done = self.cfg.get("done_phrases") or ["Done."]
        self.boops = self.cfg.get("boops") or ["Hi."]
        self.quips = self.cfg.get("quips") or []
        self.late = self.cfg.get("late_night") or []
        self.greeting = self.cfg.get("greeting") or (self.name + " is here. Right-click for options.")
        self.frame_sec = self.cfg.get("frame_sec", {})
        self.scale = float(self.cfg.get("scale", 0.5))

    def frames(self, mood):
        """Sorted frame paths for a mood: [base, anim1..animN]."""
        fdir = os.path.join(self.folder, "frames")
        files = glob.glob(os.path.join(fdir, mood + "_*.png"))
        key = lambda p: int(re.search(r"_(\d+)\.png$", p).group(1))
        return sorted([p for p in files if re.search(r"_(\d+)\.png$", p)], key=key)
