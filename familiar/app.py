"""Familiar: a desktop companion that shows what Claude Code is doing, in your persona's voice.

python -m familiar [--persona PATH]      (config: ~/.familiar/config.json)
Left-drag moves it, left-click boops it, right-click opens the menu. Hides over fullscreen apps.
"""
import ctypes, ctypes.wintypes as W, datetime, json, math, os, random, sys, threading, time, traceback
import numpy as np
from PIL import Image

from . import render, sources
from .persona import Persona
from . import win32 as w32
from .win32 import user32, gdi32, kernel32

HOME = os.path.expanduser("~")
CFG_DIR = os.path.join(HOME, ".familiar")
CFG = os.path.join(CFG_DIR, "config.json")
LOGF = os.path.join(CFG_DIR, "familiar.log")
CH_STATS, CH_BARE = 470, 360
GPU_BUSY, HOT_C, COOL_C, SAD_PCT = 60, 83, 78, 95
TOOL_KINDS = [("read", ("Read", "Grep", "Glob", "LS", "NotebookRead", "view_image", "sessions_history", "sessions_search")),
              ("shell", ("Bash", "PowerShell", "exec", "process", "terminal")),
              ("edit", ("Edit", "Write", "MultiEdit", "NotebookEdit")),
              ("web", ("WebFetch", "WebSearch", "web_fetch", "web_search", "browser")),
              ("agent", ("Agent", "Task", "sessions_spawn", "sessions_send", "subagents", "Workflow")),
              ("memory", ("memory_search", "memory_get")),
              ("media", ("image_generate", "music_generate", "video_generate"))]
WORK_KINDS = ("shell", "edit")


def log(msg):
    try:
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(LOGF, "a", encoding="utf-8") as f:
            f.write(datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S ") + msg + chr(10))
    except Exception:
        pass


def load_cfg():
    try:
        with open(CFG, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class Poller(threading.Thread):
    daemon = True

    def __init__(self, plugins):
        super().__init__()
        self.plugins = plugins
        self.data = {"system": None, "claude": None, "codex": None, "tokens": None, "err": None, "alerts": []}

    def run(self):
        next_claude = next_tokens = 0
        while True:
            d = dict(self.data)
            try:
                d["system"] = sources.system()
            except Exception:
                log("system " + traceback.format_exc())
            now = time.time()
            if now >= next_claude:
                next_claude = now + 180
                try:
                    d["claude"], d["err"] = sources.claude_usage(), None
                except Exception as e:
                    d["err"] = str(e)[:80]
                try:
                    d["codex"] = sources.codex_usage()
                except Exception:
                    log("codex " + traceback.format_exc())
            if now >= next_tokens:
                next_tokens = now + 60
                try:
                    d["tokens"] = sources.tokens_today()
                except Exception:
                    pass
            alerts = []
            for p in self.plugins:
                try:
                    alerts += p.alerts()
                except Exception:
                    log("plugin " + traceback.format_exc())
            d["alerts"] = alerts
            self.data = d
            time.sleep(5)


class Familiar:
    def __init__(self, persona, cfg):
        self.p, self.cfg = persona, cfg
        self.sprites = {}
        for mood in ("idle", "sleep", "happy", "alert", "think", "work", "wait", "sad", "gpu"):
            files = persona.frames(mood)
            if files:
                self.sprites[mood] = [self.load(f) for f in files]
        if "idle" not in self.sprites:
            raise SystemExit("persona has no idle frames: " + persona.folder)
        self.show_stats = cfg.get("stats", True)
        # Hardware table: "auto" (default) shows it once a CPU sensor source (Afterburner / LibreHardwareMonitor)
        # is found; true/false pins it. The usage rows below it always show with the footer.
        self.hardware = cfg.get("hardware", "auto")
        self.dismissed = cfg.get("dismissed", "")
        self.x, self.y = self.default_pos()
        self.mood, self.mood_t0 = "idle", time.time()
        self.bubble, self.bubble_until = "", 0.0
        self.react_until = 0.0
        self.hidden_until, self.shown, self.last_key, self.drag = 0.0, False, None, None
        self.prev = {"alert": "", "hot": False}
        self.cc = {"working": False, "kind": "think", "since": 0.0, "next_say": 0.0}
        self.next_quip = time.time() + random.uniform(20 * 60, 40 * 60)
        self.next_late = 0.0
        self.poller = Poller(load_plugins(cfg))
        self.poller.start()

    def load(self, f):
        im = Image.open(f).convert("RGBA")
        k = self.p.scale
        return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)

    # -- persistence
    def save(self):
        c = load_cfg()
        c.update(x=self.x, y=self.y, stats=self.show_stats, hardware=self.hardware, dismissed=self.dismissed)
        os.makedirs(CFG_DIR, exist_ok=True)
        with open(CFG, "w", encoding="utf-8") as f:
            json.dump(c, f, indent=2)

    def ch(self):
        return CH_STATS if self.show_stats else CH_BARE

    def default_pos(self):
        c = self.cfg
        if "x" in c and user32.MonitorFromPoint(W.POINT(int(c["x"]) + 150, int(c["y"]) + 150), 0):
            return int(c["x"]), int(c["y"])
        wa = w32.monitor_info(user32.MonitorFromPoint(W.POINT(0, 0), 1)).rcWork
        return wa.right - render.CW - 20, wa.bottom - self.ch()

    def say(self, text, secs=7):
        self.bubble, self.bubble_until = text, time.time() + secs

    # -- alerts (plugins)
    def alert_key(self):
        return ",".join(sorted(a["id"] for a in self.poller.data.get("alerts", [])))

    def active_alerts(self):
        al = self.poller.data.get("alerts", [])
        return [] if (al and self.alert_key() == self.dismissed) else al

    def alert_text(self, al):
        return "; ".join(a["text"] for a in al[:2])[:200]

    # -- state, once a second
    def think(self):
        now, d = time.time(), self.poller.data
        g = (d.get("system") or {}).get("gpu", {})
        temp, util = g.get("temp") or 0, g.get("load") or 0
        five = ((d.get("claude") or {}).get("five") or {}).get("pct", 0)
        al = self.active_alerts()
        key = self.alert_key() if al else ""
        idle, hour = w32.idle_s(), datetime.datetime.now().hour
        late = hour >= 23 or hour < 6
        if not d.get("alerts") and self.dismissed:
            self.dismissed = ""
            self.save()
        if key and key != self.prev["alert"]:
            self.say(self.alert_text(al) + ". Right-click > Dismiss to clear.", 14)
        elif not key and self.prev["alert"] and not d.get("alerts"):
            self.say("All clear again.", 6)
        self.prev["alert"] = key
        alarming = any(a.get("alarm") for a in al)

        kind, cc = sources.claude_code(TOOL_KINDS), self.cc
        if kind:
            if not cc["working"]:
                cc.update(working=True, since=now, next_say=0)
            if kind != cc["kind"] or now > cc["next_say"]:
                if now > self.bubble_until or self.bubble.endswith("…"):
                    self.say(random.choice(self.p.phrases.get(kind) or self.p.phrases["think"]) + "…", 9)
                    cc["next_say"] = now + random.uniform(14, 22)
                cc["kind"] = kind
        elif cc["working"]:
            cc["working"] = False
            if now - cc["since"] > 20:
                self.react_until = now + 3
                self.say(random.choice(self.p.done), 6)

        hot = temp >= HOT_C or (self.prev["hot"] and temp > COOL_C)
        if hot and not self.prev["hot"]:
            self.say("GPU at %d°C." % temp, 8)
        self.prev["hot"] = hot

        if now < self.react_until:
            mood = "happy"
        elif alarming or hot:
            mood = "alert"
        elif kind == "wait":
            mood = "wait"
        elif kind:
            mood = "work" if kind in WORK_KINDS else "think"
        elif five >= SAD_PCT:
            mood = "sad"
        elif util >= GPU_BUSY:
            mood = "gpu"
        elif idle > 600 or (late and idle > 120):
            mood = "sleep"
        else:
            mood = "idle"
        mood = mood if mood in self.sprites else ("think" if mood in ("work", "wait") and "think" in self.sprites else "idle")
        if mood != self.mood:
            self.mood, self.mood_t0 = mood, now

        if idle < 60 and now > self.bubble_until:
            if late and hour < 5 and now > self.next_late and self.p.late:
                self.say(random.choice(self.p.late), 8)
                self.next_late = now + 45 * 60
            elif mood == "idle" and now > self.next_quip and self.p.quips:
                self.say(random.choice(self.p.quips), 7)
                self.next_quip = now + random.uniform(35 * 60, 70 * 60)

        self.set_visible(not (now < self.hidden_until or self.fullscreen_here()))
        if self.shown and int(now) % 30 == 0:
            user32.SetWindowPos(self.hwnd, w32.HWND_TOPMOST, 0, 0, 0, 0, w32.SWP)

    def on_click(self):
        al = self.active_alerts()
        if al:
            self.say(self.alert_text(al), 12)
            return
        self.react_until = time.time() + 2.5
        self.say(random.choice(self.p.boops), 4)

    def fullscreen_here(self):
        fg = user32.GetForegroundWindow()
        if not fg or fg == self.hwnd:
            return False
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(fg, buf, 64)
        if buf.value in ("Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"):
            return False
        r = W.RECT()
        user32.GetWindowRect(fg, ctypes.byref(r))
        mon = user32.MonitorFromWindow(fg, 2)
        if mon != user32.MonitorFromWindow(self.hwnd, 2):
            return False
        m = w32.monitor_info(mon).rcMonitor
        return r.left <= m.left and r.top <= m.top and r.right >= m.right and r.bottom >= m.bottom

    def set_visible(self, vis):
        if vis and not self.shown:
            self.last_key = None
            self.render()
            user32.ShowWindow(self.hwnd, 4)
            self.shown = True
        elif not vis and self.shown:
            user32.ShowWindow(self.hwnd, 0)
            self.shown = False

    # -- drawing
    def frame(self):
        fr = self.sprites[self.mood]
        if len(fr) == 1:
            return 0
        t = time.time() - self.mood_t0
        sec = self.p.frame_sec.get(self.mood, 0.25)
        if t < sec:
            return 0  # base pose first, then loop the animation frames
        return 1 + int((t - sec) / sec) % (len(fr) - 1)

    def stats(self):
        if not self.show_stats:
            return None
        d = self.poller.data
        return {"system": d.get("system"), "claude": d.get("claude"), "codex": d.get("codex"), "tokens": d.get("tokens"),
                "err": d.get("err"), "hardware": self.hardware_on()}

    def hardware_on(self):
        if self.hardware == "auto":
            return bool(((self.poller.data.get("system") or {}).get("sensors")))
        return bool(self.hardware)

    def render(self, force=False):
        if time.time() > self.bubble_until:
            self.bubble = ""
        st = self.stats()
        key = (self.mood, self.frame(), self.bubble, json.dumps(st, default=str, sort_keys=True))
        if key == self.last_key and not force:
            return
        self.last_key = key
        self.blit(render.compose(self.sprites[self.mood][self.frame()], 0, self.bubble, st, self.ch()))

    def blit(self, img):
        a = np.asarray(img, dtype=np.uint16)
        al = a[..., 3:4]
        rgb = (a[..., :3] * al + 127) // 255
        bgra = np.ascontiguousarray(np.concatenate([rgb[..., ::-1], al], axis=2).astype(np.uint8))
        h, w = bgra.shape[:2]
        bmi = w32.BITMAPINFO()
        hd = bmi.bmiHeader
        hd.biSize, hd.biWidth, hd.biHeight, hd.biPlanes, hd.biBitCount, hd.biCompression = ctypes.sizeof(w32.BITMAPINFOHEADER), w, -h, 1, 32, 0
        screen = user32.GetDC(None)
        mem = gdi32.CreateCompatibleDC(screen)
        bits = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(screen, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
        ctypes.memmove(bits, bgra.ctypes.data, bgra.nbytes)
        old = gdi32.SelectObject(mem, hbmp)
        blend = w32.BLENDFUNCTION(0, 0, 255, 1)
        user32.UpdateLayeredWindow(self.hwnd, screen, ctypes.byref(W.POINT(self.x, self.y)), ctypes.byref(W.SIZE(w, h)),
                                   mem, ctypes.byref(W.POINT(0, 0)), 0, ctypes.byref(blend), 2)
        gdi32.SelectObject(mem, old)
        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(None, screen)

    def menu(self):
        m = user32.CreatePopupMenu()
        user32.AppendMenuW(m, 0x8 if self.show_stats else 0, 1, "Show status footer")
        if self.show_stats:
            user32.AppendMenuW(m, 0x8 if self.hardware_on() else 0, 3, "  Hardware table (CPU / GPU / RAM)")
        user32.AppendMenuW(m, 0, 2, "Hide for 1 hour")
        if self.poller.data.get("alerts"):
            user32.AppendMenuW(m, 0x800, 0, None)
            user32.AppendMenuW(m, 0, 4, "Explain the alert")
            if self.active_alerts():
                user32.AppendMenuW(m, 0, 5, "Dismiss alert (until something new fails)")
        user32.AppendMenuW(m, 0x800, 0, None)
        user32.AppendMenuW(m, 0, 9, "Quit " + self.p.name)
        pt = W.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        user32.SetForegroundWindow(self.hwnd)
        cmd = user32.TrackPopupMenu(m, 0x0100 | 0x0002, pt.x, pt.y, 0, self.hwnd, None)
        user32.DestroyMenu(m)
        if cmd == 1:
            self.show_stats = not self.show_stats
            self.save()
            user32.SetWindowPos(self.hwnd, None, self.x, self.y, render.CW, self.ch(), 0x0004 | 0x0010)
        elif cmd == 3:
            self.hardware = not self.hardware_on()
            self.save()
            if self.hardware and not (self.poller.data.get("system") or {}).get("sensors"):
                self.say("No CPU sensors found. Run MSI Afterburner (or LibreHardwareMonitor's web server) for CPU temp and power.", 10)
        elif cmd == 2:
            self.hidden_until = time.time() + 3600
        elif cmd == 4:
            al = self.poller.data.get("alerts", [])
            if al:
                self.say(self.alert_text(al), 14)
        elif cmd == 5:
            self.dismissed = self.alert_key()
            self.save()
            self.say("Dismissed. I'll speak up if something new breaks.", 6)
        elif cmd == 9:
            user32.PostMessageW(self.hwnd, w32.WM_CLOSE, 0, 0)
        self.render(force=True)

    def wndproc(self, hwnd, msg, wp, lp):
        try:
            if msg == w32.WM_TIMER:
                self.render() if wp == 1 else self.think()
                return 0
            if msg == w32.WM_MOUSEACTIVATE:
                return 3
            if msg == w32.WM_LBUTTONDOWN:
                pt = W.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                self.drag = (pt.x, pt.y, self.x, self.y, False)
                user32.SetCapture(hwnd)
                return 0
            if msg == w32.WM_MOUSEMOVE and self.drag:
                pt = W.POINT()
                user32.GetCursorPos(ctypes.byref(pt))
                cx, cy, ox, oy, moved = self.drag
                dx, dy = pt.x - cx, pt.y - cy
                if moved or abs(dx) + abs(dy) > 4:
                    self.drag = (cx, cy, ox, oy, True)
                    self.x, self.y = ox + dx, oy + dy
                    user32.SetWindowPos(hwnd, None, self.x, self.y, 0, 0, 0x0001 | 0x0004 | 0x0010)
                return 0
            if msg == w32.WM_LBUTTONUP and self.drag:
                moved = self.drag[4]
                self.drag = None
                user32.ReleaseCapture()
                if moved:
                    self.save()
                else:
                    self.on_click()
                    self.render(force=True)
                return 0
            if msg == w32.WM_RBUTTONUP:
                self.menu()
                return 0
            if msg == w32.WM_CLOSE:
                self.save()
                user32.DestroyWindow(hwnd)
                return 0
            if msg == w32.WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
        except Exception:
            log("wndproc " + traceback.format_exc())
        return user32.DefWindowProcW(hwnd, msg, wp, lp)

    def run(self):
        hinst = kernel32.GetModuleHandleW(None)
        self._proc = w32.WNDPROC(self.wndproc)
        wc = w32.WNDCLASSEXW()
        wc.cbSize = ctypes.sizeof(w32.WNDCLASSEXW)
        wc.lpfnWndProc = self._proc
        wc.hInstance = hinst
        wc.lpszClassName = "FamiliarWindow"
        wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(32649))
        user32.RegisterClassExW(ctypes.byref(wc))
        self.hwnd = user32.CreateWindowExW(w32.EX, "FamiliarWindow", self.p.name, w32.WS_POPUP, self.x, self.y, render.CW, self.ch(), None, None, hinst, None)
        if not self.hwnd:
            raise RuntimeError("CreateWindowEx failed %d" % ctypes.get_last_error())
        time.sleep(0.3)
        self.say(self.p.greeting, 6)
        self.think()
        self.set_visible(True)
        user32.SetTimer(self.hwnd, 1, 66, None)
        user32.SetTimer(self.hwnd, 2, 1000, None)
        msg = W.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))


def load_plugins(cfg):
    out = []
    for name, opts in (cfg.get("plugins") or {}).items():
        try:
            mod = __import__("familiar.plugins." + name, fromlist=["Plugin"])
            out.append(mod.Plugin(opts or {}))
        except Exception:
            log("plugin load %s: %s" % (name, traceback.format_exc()))
    return out


def main():
    if os.name != "nt":
        raise SystemExit("Familiar's window is Windows-only for now (see README: cross-platform roadmap).")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        user32.SetProcessDPIAware()
    kernel32.CreateMutexW(None, False, "Local/FamiliarSingleton")
    if ctypes.get_last_error() == 183:
        return
    cfg = load_cfg()
    args = sys.argv[1:]
    folder = args[args.index("--persona") + 1] if "--persona" in args else cfg.get("persona") or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "personas", "example")
    log("start persona=" + folder)
    try:
        Familiar(Persona(folder), cfg).run()
    except Exception:
        log("crash " + traceback.format_exc())
    log("exit")
