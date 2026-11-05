"""Headless footer checks: python -m pytest tests"""
import struct
from PIL import Image
from familiar import render, sources

SYS = {"cpu": {"load": 30, "temp": 63, "power": 73}, "gpu": {"load": 20, "temp": 55, "power": 26}, "ram": {"load": 70, "free_gb": 9, "total_gb": 31}}
CLAUDE = {"five": {"pct": 9, "resets": None}, "week": {"pct": 77, "resets": None}}
CODEX = {"primary": {"pct": 7, "resets": None, "name": "30d"}, "secondary": None}


def test_hardware_table_is_optional():
    full, usage_only = render.footer_h(True), render.footer_h(False)
    assert usage_only < full
    spr = Image.new("RGBA", (50, 50))
    for hw, h in ((True, full), (False, usage_only)):
        img = render.compose(spr, 0, None, {"system": SYS, "claude": CLAUDE, "codex": CODEX, "tokens": 5000, "hardware": hw}, 300)
        # footer panel starts exactly footer_h above the bottom: the pixel just above it is transparent
        assert img.getpixel((150, 300 - h - 4))[3] == 0
        assert img.getpixel((150, 300 - h + 4))[3] > 0


def test_afterburner_parse():
    hdr = struct.pack("<IIIII", 0x4D41484D, 0x20000, 32, 3, 1324) + b"\0" * 12
    def entry(name, val, units):
        e = bytearray(1324)
        e[0:len(name)] = name.encode()
        e[260:260 + len(units)] = units.encode()
        struct.pack_into("<f", e, 1300, val)
        return bytes(e)
    buf = hdr + entry("CPU temperature", 63.4, "C") + entry("CPU power", 73.2, "W") + entry("GPU1 usage", 12, "%")
    v = sources.parse_mahm(buf)
    assert round(v["CPU temperature"], 1) == 63.4 and round(v["CPU power"], 1) == 73.2 and v["GPU1 usage"] == 12
