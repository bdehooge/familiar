"""Render a shareable demo video of a persona: every mood, then the pet following a Claude Code prompt, then a boop.

  python tools/demo.py personas/orion9 --out demo/orion_demo.mp4 [--gif demo/orion_demo.gif]

Uses the app's own renderer (familiar.render.compose) and frame timing, so what you see is what the pet draws.
The Claude Code session on the left is a scripted mock-up; the footer numbers are sample values. Needs ffmpeg on PATH.
"""
import argparse, datetime, os, shutil, subprocess, sys, tempfile
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from familiar import render  # noqa: E402
from familiar.persona import Persona, MOODS  # noqa: E402

W, H, FPS = 1280, 720, 30
PET_K = 1.35                     # pet window drawn a bit larger than on the desktop so it reads in a video
CH = 470                         # pet window height with the footer (app.CH_STATS)
MOOD_ORDER = ["idle", "think", "work", "wait", "happy", "alert", "sad", "gpu", "sleep"]
MOOD_TITLES = {"idle": "Idle", "think": "Thinking", "work": "Working", "wait": "Waiting on you", "happy": "Happy",
               "alert": "Alert", "sad": "Sad", "gpu": "GPU busy", "sleep": "Asleep"}


def font(names, size):
    for n in names:
        try:
            return ImageFont.truetype("C:/Windows/Fonts/" + n, size)
        except Exception:
            try:
                return ImageFont.truetype(n, size)
            except Exception:
                pass
    return ImageFont.load_default()


F_MONO = font(["consola.ttf", "DejaVuSansMono.ttf"], 19)
F_TITLE = font(["seguisb.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"], 46)
F_SUB = font(["segoeui.ttf", "DejaVuSans.ttf"], 24)
F_SMALL = font(["segoeui.ttf", "DejaVuSans.ttf"], 18)


def iso_in(minutes):
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=minutes)).isoformat()


def stats(five=38, gpu_load=12, gpu_temp=48, cpu=9):
    return {"system": {"cpu": {"load": cpu, "temp": 52, "power": 41}, "gpu": {"load": gpu_load, "temp": gpu_temp, "power": 60 + gpu_load * 2},
                       "ram": {"load": 48, "free_gb": 16.2, "total_gb": 31}},
            "claude": {"five": {"pct": five, "resets": iso_in(130)}, "week": {"pct": 21, "resets": iso_in(60 * 24 * 3 + 300)}},
            "codex": None, "tokens": 1840000, "err": None, "hardware": True}


class Pet:
    """Loads frames the way app.Familiar does and picks frames with the same timing rule."""

    def __init__(self, folder):
        self.p = Persona(folder)
        self.sprites = {}
        for m in MOODS:
            fs = self.p.frames(m)
            if fs:
                self.sprites[m] = [self.load(f) for f in fs]

    def load(self, f):
        im = Image.open(f).convert("RGBA")
        k = self.p.scale
        return im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)

    def frame(self, mood, t):
        fr = self.sprites[mood]
        sec = self.p.frame_sec.get(mood, 0.25)
        if len(fr) == 1 or t < sec:
            return fr[0]
        return fr[1 + int((t - sec) / sec) % (len(fr) - 1)]

    def window(self, mood, t, bubble, st):
        img = render.compose(self.frame(mood, t), 0, bubble, st, CH)
        return img.resize((int(img.width * PET_K), int(img.height * PET_K)), Image.LANCZOS)


def backdrop():
    bg = Image.new("RGB", (W, H))
    dr = ImageDraw.Draw(bg)
    for y in range(H):
        f = y / H
        dr.line([(0, y), (W, y)], fill=(int(14 + 10 * f), int(20 + 14 * f), int(38 + 22 * f)))
    return bg.convert("RGBA")


def caption(dr, title, sub, y=34, x=48):
    dr.text((x, y), title, font=F_TITLE, fill=(232, 244, 255))
    if sub:
        dr.text((x + 2, y + 60), sub, font=F_SUB, fill=(140, 190, 225))


def terminal(dr, lines, box=(40, 150, 760, 680)):
    x0, y0, x1, y1 = box
    dr.rounded_rectangle(box, radius=12, fill=(18, 20, 26), outline=(60, 70, 90), width=2)
    dr.rounded_rectangle((x0, y0, x1, y0 + 34), radius=12, fill=(34, 38, 48))
    dr.rectangle((x0, y0 + 20, x1, y0 + 34), fill=(34, 38, 48))
    for i, c in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        dr.ellipse((x0 + 16 + i * 22, y0 + 11, x0 + 28 + i * 22, y0 + 23), fill=c)
    dr.text((x0 + 92, y0 + 7), "claude  ~/projects/weather-app", font=F_SMALL, fill=(150, 160, 180))
    y = y0 + 52
    for text, col in lines[-20:]:
        dr.text((x0 + 18, y), text, font=F_MONO, fill=col)
        y += 25


# Mock Claude Code session: (start second, mood, bubble, terminal lines revealed at that time)
USER, DOT, DIMC, OK, WARN = (235, 235, 240), (215, 120, 90), (130, 140, 155), (90, 210, 120), (240, 190, 90)
PROMPT = "fix the failing test in forecast.py"
SCRIPT = [
    (2.4, "think", "think", [("● I'll look at the failing test first.", USER)]),
    (3.6, "think", "read", [("● Read(tests/test_forecast.py)", DOT), ("  └  Read 48 lines", DIMC)]),
    (5.6, "think", "read", [("● Read(src/forecast.py)", DOT), ("  └  Read 112 lines", DIMC),
                            ("● The high/low are swapped when the", USER), ("  API returns Fahrenheit.", USER)]),
    (8.4, "work", "edit", [("● Update(src/forecast.py)", DOT), ("  └  Updated with 2 additions, 2 removals", DIMC)]),
    (10.6, "wait", "wait", [("╭ Allow Bash: pytest -q ?", WARN), ("│ > 1. Yes", WARN), ("╰   2. No", WARN)]),
    (12.6, "work", "shell", [("● Bash(pytest -q)", DOT), ("  └  14 passed in 0.82s", OK)]),
    (15.0, "happy", "done", [("● Fixed: the unit conversion now keeps", USER), ("  high/low in order. All 14 tests pass.", USER)]),
    (18.0, "idle", None, []),
]
PROMPT_END = 20.0


def scene_prompt(pet, t, pick):
    """Returns (mood, mood start, bubble, terminal lines) at time t of the prompt scene."""
    typed = PROMPT[:max(0, int((t - 0.4) * 22))]
    lines = [("╭─────────────────────────────────────────────╮", DIMC), ("│ * Welcome to Claude Code", DIMC),
             ("╰─────────────────────────────────────────────╯", DIMC), ("", USER),
             ("> " + typed + ("▌" if t < 2.4 and int(t * 2) % 2 == 0 else ""), USER), ("", USER)]
    mood, t0, bubble = "idle", 0.0, None
    for start, m, kind, ls in SCRIPT:
        if t < start:
            break
        if kind == "wait" or m != mood:
            t0 = start if m != mood else t0
        mood = m
        if kind == "done":
            bubble = pick("done")
        elif kind:
            bubble = pick(kind) + "…"
        else:
            bubble = None
        if kind == "wait":
            lines += ls
        else:
            lines = [l for l in lines if l[1] != WARN] + ls
    if mood == "happy" and t > 17.6:
        bubble = None
    return mood, t0, bubble, lines


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("persona")
    ap.add_argument("--out", required=True)
    ap.add_argument("--gif")
    ap.add_argument("--mood-sec", type=float, default=2.6)
    a = ap.parse_args()
    ff = shutil.which("ffmpeg")
    if not ff:
        sys.exit("ffmpeg not found on PATH")
    pet = Pet(a.persona)
    name = pet.p.name
    phrase = {"think": pet.p.phrases["think"][0], "read": pet.p.phrases["read"][0], "edit": pet.p.phrases["edit"][0],
              "shell": pet.p.phrases["shell"][0], "wait": pet.p.phrases["wait"][0], "done": pet.p.done[0]}
    bg = backdrop()
    moods = [m for m in MOOD_ORDER if m in pet.sprites]
    mood_bubbles = {"happy": pet.p.boops[0], "wait": phrase["wait"] + "…", "think": phrase["think"] + "…",
                    "work": phrase["edit"] + "…", "alert": "GPU at 86°C.", "sleep": None,
                    "sad": "Claude 5h window is nearly used up.", "gpu": None, "idle": pet.p.quips[0] if pet.p.quips else None}
    mood_stats = {"sad": stats(five=97), "gpu": stats(gpu_load=98, gpu_temp=71), "alert": stats(gpu_load=99, gpu_temp=86),
                  "work": stats(cpu=34), "think": stats(cpu=18)}

    T_TITLE, T_MOODS = 2.5, a.mood_sec * len(moods)
    T_PROMPT, T_BOOP = PROMPT_END, 4.5
    total = T_TITLE + T_MOODS + 1.2 + T_PROMPT + T_BOOP
    pet_x = W - int(render.CW * PET_K) - 40
    pet_y = H - int(CH * PET_K) - 6

    tmp = tempfile.mkdtemp(prefix="familiar_demo_")
    n = int(total * FPS)
    for i in range(n):
        t = i / FPS
        img = bg.copy()
        dr = ImageDraw.Draw(img)
        if t < T_TITLE:
            mood, mt, bubble, st = "idle", t, pet.p.greeting, stats()
            caption(dr, "Meet %s" % name, "a desktop companion for Claude Code", y=230, x=80)
            dr.text((82, 340), "9 moods · reacts to your Claude Code session · boopable", font=F_SMALL, fill=(130, 160, 190))
        elif t < T_TITLE + T_MOODS:
            k = min(len(moods) - 1, int((t - T_TITLE) / a.mood_sec))
            mood = moods[k]
            mt = t - T_TITLE - k * a.mood_sec
            bubble, st = mood_bubbles.get(mood), mood_stats.get(mood, stats())
            caption(dr, "%d / %d   %s" % (k + 1, len(moods), MOOD_TITLES[mood]), "When: " + MOODS[mood], y=230, x=80)
            for j, m in enumerate(moods):
                cx = 84 + j * 34
                dr.ellipse((cx, 350, cx + 14, 364), fill=(76, 201, 255) if j == k else (50, 70, 95))
        elif t < T_TITLE + T_MOODS + 1.2:
            mood, mt, bubble, st = "idle", t, None, stats()
            caption(dr, "Now with a real prompt", "%s follows along while Claude Code works" % name, y=230, x=80)
        elif t < T_TITLE + T_MOODS + 1.2 + T_PROMPT:
            ts = t - (T_TITLE + T_MOODS + 1.2)
            mood, t0, bubble, lines = scene_prompt(pet, ts, lambda k: phrase[k])
            mt, st = ts - t0, stats(five=41, cpu=30 if mood == "work" else 12)
            dr.text((44, 40), "Claude Code + %s" % name, font=F_TITLE, fill=(232, 244, 255))
            dr.text((46, 100), "mood: " + MOOD_TITLES[mood], font=F_SUB, fill=(140, 190, 225))
            terminal(dr, lines)
        else:
            tb = t - (T_TITLE + T_MOODS + 1.2 + T_PROMPT)
            caption(dr, "And yes, you can boop him", "left-click: boop · drag: move · right-click: menu", y=230, x=80)
            booped = tb >= 1.0
            mood = "happy" if booped and tb < 3.5 else "idle"
            mt = tb - 1.0 if booped and tb < 3.5 else tb
            bubble, st = (pet.p.boops[0] if booped and tb < 4.0 else None), stats()
        win = pet.window(mood, mt, bubble, st)
        img.alpha_composite(win, (pet_x, pet_y))
        if t >= total - T_BOOP:  # draw the mouse pointer for the boop
            tb = t - (total - T_BOOP)
            f = min(1.0, tb / 0.9)
            px = int(W - 120 + (pet_x + win.width // 2 - (W - 120)) * f)
            py = int(H - 60 + (pet_y + int(win.height * 0.42) - (H - 60)) * f)
            ptr = [(px, py), (px, py + 26), (px + 7, py + 20), (px + 12, py + 31), (px + 17, py + 29), (px + 12, py + 18), (px + 21, py + 18)]
            dr.polygon(ptr, fill=(255, 255, 255), outline=(0, 0, 0))
            if 1.0 <= tb < 1.35:
                r = int(10 + (tb - 1.0) * 80)
                dr.ellipse((px - r, py - r, px + r, py + r), outline=(76, 201, 255), width=3)
        img.convert("RGB").save(os.path.join(tmp, "f%05d.png" % i))

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    src = ["-framerate", str(FPS), "-i", os.path.join(tmp, "f%05d.png")]
    subprocess.run([ff, "-y", "-loglevel", "error"] + src + ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "18",
                    "-movflags", "+faststart", a.out], check=True)
    if a.gif:
        vf = "fps=15,scale=800:-1:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=192[p];[s1][p]paletteuse=dither=bayer:bayer_scale=4"
        subprocess.run([ff, "-y", "-loglevel", "error"] + src + ["-vf", vf, a.gif], check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    print("wrote", a.out, "(%.1fs, %d frames)" % (total, n), ("and " + a.gif) if a.gif else "")


if __name__ == "__main__":
    main()
