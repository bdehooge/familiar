"""Turn generated chroma-green sheets into aligned, transparent persona frames.

  python tools/frames.py base  <sheet> --out personas/NAME/frames [--grid 3x3] [--moods idle,sleep,...]
      one pose per cell -> <mood>_0.png (the base pose for each mood)
  python tools/frames.py anim  <sheet> <mood> --out personas/NAME/frames [--grid 3x3]
      animation cells -> <mood>_1..N.png, scaled to the base pose and registered onto it so the body holds still
  python tools/frames.py preview personas/NAME/frames
      writes _strips.png (every mood as a strip) and _onion.png (all frames averaged: blur = jitter)

Needs: pillow, numpy, scipy.
"""
import argparse, glob, os, re, sys
import numpy as np
from PIL import Image
from scipy import ndimage

MOODS = ["idle", "sleep", "happy", "alert", "think", "gpu", "work", "wait", "sad"]
MAXSHIFT = 60


def key_green(path):
    """RGBA array with the chroma-green background keyed out and green spill removed."""
    im = np.asarray(Image.open(path).convert("RGB")).astype(np.int32)
    r, g, b = im[..., 0], im[..., 1], im[..., 2]
    gdom = g - np.maximum(r, b)
    alpha = np.clip(255 - (gdom - 40) * 255 // 80, 0, 255).astype(np.uint8)
    g2 = np.where(gdom > 0, np.maximum(r, b), g)
    return np.dstack([r, g2, b, alpha]).astype(np.uint8)


def cells(rgba, cols, rows):
    """Crop the main subject out of each grid cell (drops stray specks), row-major order."""
    H, W = rgba.shape[:2]
    mask = rgba[..., 3] > 60
    # Image models often draw grid lines between cells despite the prompt. A row/column that is almost entirely
    # non-background is a line (characters never span the whole sheet): clear it plus a small band around it.
    # Checked per band of cells, since hand-drawn lines wander a few pixels between rows.
    lines = np.zeros_like(mask)
    for r in range(rows):
        y0, y1 = r * H // rows, (r + 1) * H // rows
        lines[y0:y1, mask[y0:y1].mean(axis=0) > 0.9] = True
    for c in range(cols):
        x0, x1 = c * W // cols, (c + 1) * W // cols
        lines[mask[:, x0:x1].mean(axis=1) > 0.9, x0:x1] = True
    if lines.any():
        lines = ndimage.binary_dilation(lines, iterations=6)
        mask &= ~lines
        rgba = rgba.copy()
        rgba[..., 3] = np.where(lines, 0, rgba[..., 3])
    lab, _ = ndimage.label(ndimage.binary_dilation(mask, iterations=12))
    out = []
    for i in range(cols * rows):
        row, col = divmod(i, cols)
        y0, y1, x0, x1 = row * H // rows, (row + 1) * H // rows, col * W // cols, (col + 1) * W // cols
        cell = lab[y0:y1, x0:x1]
        ids, cnt = np.unique(cell[cell > 0], return_counts=True)
        if not len(ids):
            out.append(None)
            continue
        keep = ids[cnt > max(300, cnt.max() * 0.02)]
        m = np.isin(cell, keep) & mask[y0:y1, x0:x1]
        ys, xs = np.where(m)
        c = rgba[y0:y1, x0:x1][ys.min():ys.max() + 1, xs.min():xs.max() + 1].copy()
        c[..., 3] = np.where(m[ys.min():ys.max() + 1, xs.min():xs.max() + 1], c[..., 3], 0)
        out.append(c)
    return out


def core(a):
    m = ndimage.binary_erosion(a > 128, iterations=6)  # ignore thin moving parts (tails, ears, flames)
    return ndimage.gaussian_filter(m.astype(np.float32), 3)


def shift_of(ref, cur):
    H = max(ref.shape[0], cur.shape[0]) + 2 * MAXSHIFT
    W = max(ref.shape[1], cur.shape[1]) + 2 * MAXSHIFT
    A = np.zeros((H, W), np.float32)
    B = np.zeros((H, W), np.float32)
    A[:ref.shape[0], :ref.shape[1]] = ref
    B[:cur.shape[0], :cur.shape[1]] = cur
    c = np.fft.irfft2(np.fft.rfft2(A) * np.conj(np.fft.rfft2(B)), s=(H, W))
    win = np.full((2 * MAXSHIFT + 1, 2 * MAXSHIFT + 1), -np.inf)
    for dy in range(-MAXSHIFT, MAXSHIFT + 1):
        win[dy + MAXSHIFT] = [c[dy % H, dx % W] for dx in range(-MAXSHIFT, MAXSHIFT + 1)]
    dy, dx = np.unravel_index(np.argmax(win), win.shape)
    return dy - MAXSHIFT, dx - MAXSHIFT


def register(frames):
    """Paste frames on one canvas so each frame's body core lines up with frame 0. Returns PIL images."""
    ref = core(frames[0][..., 3])
    shifts = [(0, 0)] + [shift_of(ref, core(f[..., 3])) for f in frames[1:]]
    Hc = max(f.shape[0] for f in frames) + 2 * MAXSHIFT
    Wc = max(f.shape[1] for f in frames) + 2 * MAXSHIFT
    placed = []
    for f, (dy, dx) in zip(frames, shifts):
        cv = Image.new("RGBA", (Wc, Hc), (0, 0, 0, 0))
        cv.alpha_composite(Image.fromarray(f), (MAXSHIFT + dx, MAXSHIFT + dy))
        placed.append(cv)
    union = np.zeros((Hc, Wc), bool)
    for p in placed:
        union |= np.asarray(p)[..., 3] > 8
    ys, xs = np.where(union)
    box = (max(0, xs.min() - 4), max(0, ys.min() - 4), min(Wc, xs.max() + 5), min(Hc, ys.max() + 5))
    return [p.crop(box) for p in placed], shifts


def resize(a, k):
    im = Image.fromarray(a)
    return np.asarray(im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS))


def grid(s):
    c, r = s.lower().split("x")
    return int(c), int(r)


def cmd_base(a):
    cols, rows = grid(a.grid)
    moods = a.moods.split(",")
    os.makedirs(a.out, exist_ok=True)
    cs = cells(key_green(a.sheet), cols, rows)
    target = max(c.shape[0] for c in cs if c is not None)
    for mood, c in zip(moods, cs):
        if c is None:
            print("empty cell for", mood)
            continue
        Image.fromarray(c).save(os.path.join(a.out, mood + "_0.png"), optimize=True)
    print("base poses:", ", ".join(m for m, c in zip(moods, cs) if c is not None), "(tallest %dpx)" % target)


def cmd_anim(a):
    cols, rows = grid(a.grid)
    base_p = os.path.join(a.out, a.mood + "_0.png")
    if not os.path.exists(base_p):
        sys.exit("run `base` first: missing " + base_p)
    base = np.asarray(Image.open(base_p).convert("RGBA"))
    cs = [c for c in cells(key_green(a.sheet), cols, rows) if c is not None]
    # Scale the animation to the base pose by body area (sqrt), median over frames: robust to wide/flat poses and
    # to one stretched frame, where bounding-box height is not.
    area = lambda a: float((a[..., 3] > 128).sum())
    k = (area(base) / float(np.median([area(c) for c in cs]))) ** 0.5
    cs = [resize(c, k) for c in cs]
    imgs, shifts = register([base] + cs)
    for f in glob.glob(os.path.join(a.out, a.mood + "_*.png")):
        os.remove(f)
    for i, im in enumerate(imgs):
        im.save(os.path.join(a.out, "%s_%d.png" % (a.mood, i)), optimize=True)
    print(a.mood, "%d frames (base + %d), scale %.3f, shifts %s" % (len(imgs), len(cs), k, shifts[1:]))


def cmd_preview(a):
    files = glob.glob(os.path.join(a.folder, "*_*.png"))
    moods = sorted({re.match(r"(.+)_\d+\.png$", os.path.basename(f)).group(1) for f in files if re.match(r".+_\d+\.png$", os.path.basename(f))})
    strips, onions = [], []
    for m in moods:
        fr = sorted(glob.glob(os.path.join(a.folder, m + "_*.png")), key=lambda p: int(re.search(r"_(\d+)\.png$", p).group(1)))
        ims = [Image.open(p).convert("RGBA") for p in fr]
        w, h = max(i.width for i in ims), max(i.height for i in ims)
        s = Image.new("RGBA", (w * len(ims), h), (40, 44, 52, 255))
        acc = np.zeros((h, w, 3), np.float32)
        for j, im in enumerate(ims):
            s.alpha_composite(im, (j * w, h - im.height))
            bg = Image.new("RGBA", (w, h), (40, 44, 52, 255))
            bg.alpha_composite(im, (0, h - im.height))
            acc += np.asarray(bg.convert("RGB"), np.float32)
        strips.append(s.convert("RGB"))
        onions.append(Image.fromarray((acc / len(ims)).astype(np.uint8)))
    for name, parts, vertical in (("_strips.png", strips, True), ("_onion.png", onions, False)):
        if not parts:
            continue
        W = max(p.width for p in parts) if vertical else sum(p.width for p in parts)
        H = sum(p.height for p in parts) if vertical else max(p.height for p in parts)
        out = Image.new("RGB", (W, H), (40, 44, 52))
        o = 0
        for p in parts:
            out.paste(p, (0, o) if vertical else (o, H - p.height))
            o += p.height if vertical else p.width
        out.thumbnail((2400, 2400))
        out.save(os.path.join(a.folder, name))
    print("wrote _strips.png and _onion.png for", ", ".join(moods))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("base")
    b.add_argument("sheet")
    b.add_argument("--out", required=True)
    b.add_argument("--grid", default="3x3")
    b.add_argument("--moods", default=",".join(MOODS))
    n = sub.add_parser("anim")
    n.add_argument("sheet")
    n.add_argument("mood")
    n.add_argument("--out", required=True)
    n.add_argument("--grid", default="3x3")
    p = sub.add_parser("preview")
    p.add_argument("folder")
    a = ap.parse_args()
    {"base": cmd_base, "anim": cmd_anim, "preview": cmd_preview}[a.cmd](a)


if __name__ == "__main__":
    main()
