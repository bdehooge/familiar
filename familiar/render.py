"""Pure PIL drawing: sprite + speech bubble + status footer. No windowing here, so it can be previewed headless."""
import datetime
from PIL import Image, ImageDraw, ImageFont

CW = 330
BG, EDGE = (10, 16, 30, 222), (60, 150, 210, 200)
COOL, WARM, HOT, DIM, TEXT = (120, 220, 255, 255), (255, 196, 90, 255), (255, 110, 110, 255), (140, 165, 190, 255), (220, 236, 250, 255)


def font(size, bold=False):
    for name in (["seguisb.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf"] if bold else ["segoeui.ttf", "DejaVuSans.ttf"]):
        for base in ("C:/Windows/Fonts/", "/usr/share/fonts/truetype/dejavu/", "/Library/Fonts/", ""):
            try:
                return ImageFont.truetype(base + name, size)
            except Exception:
                pass
    return ImageFont.load_default()


F_BUBBLE, F_CELL, F_HEAD = font(14), font(12, True), font(11, True)


def level(v, warm, hot):
    if v is None:
        return DIM
    return COOL if v < warm else (WARM if v < hot else HOT)


def until(iso):
    try:
        s = (datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")) - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
    except Exception:
        return ""
    if s <= 0:
        return "now"
    d, h, m = int(s // 86400), int(s % 86400 // 3600), int(s % 3600 // 60)
    return "%dd %dh" % (d, h) if d else "%dh %02dm" % (h, m)


def wrap(dr, text, width, fnt):
    lines, cur = [], ""
    for w in text.split():
        nxt = (cur + " " + w).strip()
        if dr.textlength(nxt, font=fnt) <= width:
            cur = nxt
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines[:6]


HW_H, USAGE_H = 64, 60


def footer_h(hardware=True):
    """Footer height: the usage rows always, the hardware table only when enabled."""
    return USAGE_H + (HW_H if hardware else 0)


def footer(dr, x0, y0, w, sysd, claude, tokens, err=None, codex=None, hardware=True):
    """Optional hardware table:   CPU   GPU   RAM
                       LOAD %    12    87    61
                       TEMP °C   63    62  9.1G free
                       POWER W   73   173  of 31G
       then CLAUDE 5h/wk %, CODEX window % (when signed in) and tokens today."""
    dr.rounded_rectangle([x0, y0, x0 + w, y0 + footer_h(hardware) - 2], radius=11, fill=BG, outline=EDGE, width=1)
    cpu, gpu, ram = (sysd or {}).get("cpu", {}), (sysd or {}).get("gpu", {}), (sysd or {}).get("ram", {})
    label_w, col_w = 72, (w - 20 - 72) / 3
    lx, top = x0 + 10, y0 + 5
    if hardware:
        hardware_table(dr, x0, w, lx, top, label_w, col_w, cpu, gpu, ram)
        y = top + 15 + 3 * 15 + 4
        dr.line([(lx, y - 2), (x0 + w - 10, y - 2)], fill=(40, 60, 85, 255), width=1)
    else:
        y = top - 2
    usage(dr, lx, y, w, label_w, claude, codex, tokens, err)


def hardware_table(dr, x0, w, lx, top, label_w, col_w, cpu, gpu, ram):
    for i, h in enumerate(("CPU", "GPU", "RAM")):
        cx = lx + label_w + col_w * i + col_w / 2
        dr.text((cx - dr.textlength(h, font=F_HEAD) / 2, top), h, font=F_HEAD, fill=DIM)
    rows = [
        ("LOAD %", [(cpu.get("load"), 70, 90, "%d"), (gpu.get("load"), 70, 90, "%d"), (ram.get("load"), 75, 90, "%d")]),
        ("TEMP °C", [(cpu.get("temp"), 75, 88, "%d"), (gpu.get("temp"), 70, 80, "%d"), (None, 0, 0, "")]),
        ("POWER W", [(cpu.get("power"), 1e9, 1e9, "%d"), (gpu.get("power"), 1e9, 1e9, "%d"), (None, 0, 0, "")]),
    ]
    if ram.get("free_gb") is not None:  # RAM has no temp/power: show free and total instead
        rows[1][1][2] = (ram["free_gb"], -1, -1, "%.1fG free")
        rows[2][1][2] = (ram.get("total_gb"), 1e9, 1e9, "of %.0fG")
    for r, (label, cells) in enumerate(rows):
        y = top + 15 + r * 15
        dr.text((lx, y), label, font=F_HEAD, fill=DIM)
        for i, (v, warm, hot, fmt) in enumerate(cells):
            if label == "TEMP °C" and i == 2 and v is not None:
                col = HOT if v < 2.5 else (WARM if v < 4 else COOL)
            else:
                col = level(v, warm, hot)
            s = (fmt % v) if v is not None and fmt else "–"
            cx = lx + label_w + col_w * i + col_w / 2
            dr.text((cx - dr.textlength(s, font=F_CELL) / 2, y - 1), s, font=F_CELL, fill=col if v is not None else DIM)


def usage(dr, lx, y, w, label_w, claude, codex, tokens, err):
    half = (w - 20 - label_w) / 2

    def usage_row(y, label, wins):
        """label, then up to two windows as 'NAME 38% · 2h 10m', colored by how full they are. No bars: % is enough."""
        dr.text((lx, y + 1), label, font=F_HEAD, fill=DIM)
        for i, (name, wd) in enumerate(wins[:2]):
            x = lx + label_w + half * i
            pct = round(wd.get("pct", 0))
            dr.text((x, y + 1), name, font=F_HEAD, fill=DIM)
            x += dr.textlength(name + " ", font=F_HEAD)
            s = "%d%%" % pct
            dr.text((x, y), s, font=F_CELL, fill=level(pct, 70, 90))
            t = until(wd.get("resets") or "")
            if t:
                dr.text((x + dr.textlength(s + " ", font=F_CELL), y + 1), "· " + t, font=F_HEAD, fill=DIM)

    yy = y + 2
    if claude and (claude.get("five") or claude.get("week")):
        usage_row(yy, "CLAUDE", [(n, v) for n, v in (("5h", claude.get("five")), ("wk", claude.get("week"))) if v])
    else:
        dr.text((lx, yy + 1), "CLAUDE  " + ("usage unavailable" if err else "loading…"), font=F_HEAD, fill=DIM)
    yy += 15
    if codex and (codex.get("primary") or codex.get("secondary")):
        usage_row(yy, "CODEX", [(v["name"], v) for v in (codex.get("primary"), codex.get("secondary")) if v])
        yy += 15
    if tokens is not None:
        dr.text((lx, yy + 1), "TODAY", font=F_HEAD, fill=DIM)
        t = ("%.1fM" % (tokens / 1e6) if tokens >= 1e6 else "%dk" % (tokens // 1000)) + " Claude tokens (incl. cache)"
        dr.text((lx + label_w, yy), t, font=F_CELL, fill=TEXT)


def compose(sprite, bob, bubble, stats, ch):
    """stats = None or dict(system, claude, codex, tokens, err, hardware)."""
    img = Image.new("RGBA", (CW, ch), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    fh = footer_h(stats.get("hardware", True)) if stats else 0
    base = ch - (fh + 6 if stats else 8)
    sx, sy = (CW - sprite.width) // 2, base - sprite.height + bob
    img.alpha_composite(sprite, (sx, max(sy, 0)))
    if stats:
        footer(dr, 4, ch - fh - 2, CW - 8, stats.get("system"), stats.get("claude"), stats.get("tokens"), stats.get("err"),
               stats.get("codex"), stats.get("hardware", True))
    if bubble:
        lines = wrap(dr, bubble, CW - 54, F_BUBBLE)
        lh = 19
        bw = int(max(dr.textlength(ln, font=F_BUBBLE) for ln in lines)) + 24
        bh = lh * len(lines) + 14
        bx = (CW - bw) // 2
        by = max(2, base - sprite.height - bh - 14)
        dr.rounded_rectangle([bx, by, bx + bw, by + bh], radius=12, fill=(12, 20, 36, 238), outline=(76, 201, 255, 255), width=2)
        tx = CW // 2 + 18
        dr.polygon([(tx - 9, by + bh - 1), (tx + 5, by + bh - 1), (tx - 6, by + bh + 11)], fill=(12, 20, 36, 238))
        dr.line([(tx - 9, by + bh), (tx - 6, by + bh + 11), (tx + 5, by + bh)], fill=(76, 201, 255, 255), width=2)
        for i, ln in enumerate(lines):
            dr.text((bx + 12, by + 6 + i * lh), ln, font=F_BUBBLE, fill=(232, 244, 255, 255))
    return img
