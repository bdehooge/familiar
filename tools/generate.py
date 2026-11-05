"""Generate a persona's art with the image provider you choose: 1 base sheet (9 moods, 3x3) + 9 animation sheets.

  python tools/generate.py personas/NAME --provider gemini|openai|manual [--only base|idle,sleep,...] [--ref art.png]

Providers
  gemini  Google Gemini image model via API key (env GEMINI_API_KEY; --model, default gemini-3.1-flash-image)
  openai  OpenAI Images edit endpoint (env OPENAI_API_KEY; --model, default gpt-image-2)
  manual  writes each prompt + the reference image to personas/NAME/gen/manual/. Paste them into any
          image app (Gemini app, ChatGPT, ...), save the result as gen/<step>.png, and rerun to continue.

Flow: the base sheet uses your character art (--ref, or persona.json "reference") as reference. Each animation
sheet uses that mood's base pose as reference, so the character stays on-model. After each sheet the frames are
cut and aligned with tools/frames.py. Sheets that already exist in gen/ are skipped, so reruns resume.
"""
import argparse, base64, json, mimetypes, os, shutil, subprocess, sys, urllib.request, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
MOODS = ["idle", "sleep", "happy", "alert", "think", "gpu", "work", "wait", "sad"]
DEFAULT_POSES = {
    "idle": "sitting idle, relaxed, a small smile",
    "sleep": "curled up asleep with eyes closed and a small floating Z",
    "happy": "jumping for joy with arms up and a big grin",
    "alert": "startled, eyes wide, a small exclamation mark above the head",
    "think": "thinking, hand on chin, looking up",
    "gpu": "napping on top of a small black graphics card with glowing lights",
    "work": "sitting and typing on a tiny glowing laptop, focused",
    "wait": "sitting upright looking at the viewer expectantly, one hand raised in a little wave",
    "sad": "sad, drooping posture, small frown",
}
DEFAULT_MOTION = {
    "idle": "gentle breathing, a slow sway, one blink in the middle of the loop",
    "sleep": "slow breathing, the Z drifts upward and fades, a new one appears at the start",
    "happy": "a full bounce: crouch, spring up, top of the jump, come down, land, recover",
    "alert": "a quick nervous shake left and right, the exclamation mark pulses bigger and smaller",
    "think": "eyes glance up and to the side, small head tilt, fingers tap the chin",
    "gpu": "slow breathing, the lights on the graphics card blink in a chasing pattern",
    "work": "hands type in quick bursts, the laptop screen flickers, a brief glance at the viewer",
    "wait": "the raised hand waves gently, head tilts, one blink",
    "sad": "a slow sigh, shoulders drop and rise, a small sniffle",
}
STYLE = ("Keep the character EXACTLY on-model in every cell: same design, colors, markings, clothing, proportions, "
         "art style and outline weight as the reference. The entire background is one solid flat pure chroma-key green "
         "(#00FF00): no gradient, no shadows, no floor, no grid lines, no text, no numbers. Leave lots of empty space "
         "around the character in every cell; nothing touches the cell edges or another cell.")


def base_prompt(p):
    poses = dict(DEFAULT_POSES, **p.get("poses", {}))
    cells = "; ".join("(%d) %s" % (i + 1, poses[m]) for i, m in enumerate(MOODS))
    return ("The attached image shows %s. Make a sprite sheet with NINE poses of this character in a clean 3 by 3 grid, "
            "read left to right then top to bottom, one pose per cell, each centered, all at the same scale: %s. %s"
            % (p.get("description", "my character"), cells, STYLE))


def anim_prompt(p, mood):
    motion = dict(DEFAULT_MOTION, **p.get("motions", {}))[mood]
    return ("The attached image is %s in one pose. Make a 9-frame looping animation of THIS exact pose as a clean 3 by 3 "
            "grid, read left to right then top to bottom. Every frame shows the whole character at the same size and the "
            "same position in its cell so the frames line up when played; only small changes between neighbouring frames, "
            "and frame 9 leads smoothly back into frame 1. Motion: %s. %s" % (p.get("description", "my character"), motion, STYLE))


def post(url, body, headers):
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def gen_gemini(prompt, ref, out, model):
    key = os.environ.get("GEMINI_API_KEY") or sys.exit("set GEMINI_API_KEY")
    data = base64.b64encode(open(ref, "rb").read()).decode()
    body = {"contents": [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": mimetypes.guess_type(ref)[0] or "image/png", "data": data}}]}],
            "generationConfig": {"responseModalities": ["IMAGE"]}}
    j = post("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent" % model, json.dumps(body).encode(),
             {"Content-Type": "application/json", "x-goog-api-key": key})
    for part in j["candidates"][0]["content"]["parts"]:
        blob = part.get("inline_data") or part.get("inlineData")
        if blob:
            open(out, "wb").write(base64.b64decode(blob["data"]))
            return
    sys.exit("no image in Gemini response: " + json.dumps(j)[:300])


def gen_openai(prompt, ref, out, model):
    key = os.environ.get("OPENAI_API_KEY") or sys.exit("set OPENAI_API_KEY")
    b = uuid.uuid4().hex
    parts = []
    for name, val in (("model", model), ("prompt", prompt), ("size", "1536x1024"), ("background", "opaque")):
        parts.append(("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n" % (b, name, val)).encode())
    parts.append(("--%s\r\nContent-Disposition: form-data; name=\"image[]\"; filename=\"%s\"\r\nContent-Type: %s\r\n\r\n"
                  % (b, os.path.basename(ref), mimetypes.guess_type(ref)[0] or "image/png")).encode() + open(ref, "rb").read() + b"\r\n")
    parts.append(("--%s--\r\n" % b).encode())
    j = post("https://api.openai.com/v1/images/edits", b"".join(parts),
             {"Content-Type": "multipart/form-data; boundary=" + b, "Authorization": "Bearer " + key})
    open(out, "wb").write(base64.b64decode(j["data"][0]["b64_json"]))


def gen_manual(prompt, ref, out, step, folder):
    d = os.path.join(folder, "gen", "manual")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, step + "_prompt.txt"), "w", encoding="utf-8").write(prompt)
    shutil.copy(ref, os.path.join(d, step + "_reference" + os.path.splitext(ref)[1]))
    print("[manual] %s: paste gen/manual/%s_prompt.txt + %s_reference into your image app, save the result as %s, then rerun."
          % (step, step, step, os.path.relpath(out, folder)))
    return False


def on_green(src, dst):
    """Image models handle an opaque chroma-green reference better than a transparent PNG."""
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    s = max(im.size) + 80
    bg = Image.new("RGBA", (s, s), (0, 255, 0, 255))
    bg.alpha_composite(im, ((s - im.width) // 2, (s - im.height) // 2))
    bg.convert("RGB").save(dst)
    return dst


def frames(*args):
    subprocess.run([sys.executable, os.path.join(HERE, "frames.py")] + list(args), check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("persona")
    ap.add_argument("--provider", choices=["gemini", "openai", "manual"], required=True)
    ap.add_argument("--model")
    ap.add_argument("--ref")
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    folder = os.path.abspath(a.persona)
    p = json.load(open(os.path.join(folder, "persona.json"), encoding="utf-8"))
    gdir, fdir = os.path.join(folder, "gen"), os.path.join(folder, "frames")
    os.makedirs(gdir, exist_ok=True)
    model = a.model or {"gemini": "gemini-3.1-flash-image", "openai": "gpt-image-2"}.get(a.provider)
    only = [s for s in a.only.split(",") if s]
    steps = (["base"] if not only or "base" in only else []) + [m for m in MOODS if not only or m in only]

    for step in steps:
        out = next((os.path.join(gdir, step + e) for e in (".png", ".jpg", ".jpeg", ".webp") if os.path.exists(os.path.join(gdir, step + e))), None)
        if step == "base":
            ref = a.ref or (p.get("reference") and os.path.join(folder, p["reference"]))
            if not ref or not os.path.exists(ref):
                sys.exit("base sheet needs character art: pass --ref or set persona.json \"reference\"")
            prompt = base_prompt(p)
        else:
            ref = os.path.join(fdir, step + "_0.png")
            if not os.path.exists(ref):
                print("skip %s: no base pose yet" % step)
                continue
            ref = on_green(ref, os.path.join(gdir, "ref_" + step + ".png"))
            prompt = anim_prompt(p, step)
        if not out:
            out = os.path.join(gdir, step + ".png")
            print("generating", step, "with", a.provider)
            if a.provider == "gemini":
                gen_gemini(prompt, ref, out, model)
            elif a.provider == "openai":
                gen_openai(prompt, ref, out, model)
            elif not gen_manual(prompt, ref, out, step, folder):
                if step == "base":
                    return  # every animation needs the base poses first
                continue
        if step == "base":
            frames("base", out, "--out", fdir)
        else:
            frames("anim", out, step, "--out", fdir)
    frames("preview", fdir)


if __name__ == "__main__":
    main()
