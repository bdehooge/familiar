"""Sheet cutting: python -m pytest tests"""
import os, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
import frames  # noqa: E402


def sheet_with_lines(tmp_path, line_rgb):
    """3x3 green sheet, a 40x60 'character' block centered in each cell, grid lines drawn between cells."""
    a = np.zeros((300, 300, 3), np.uint8)
    a[...] = (0, 255, 0)
    for r in range(3):
        for c in range(3):
            a[r * 100 + 20:r * 100 + 80, c * 100 + 30:c * 100 + 70] = (230, 240, 255)
    for k in (99, 100, 199, 200):
        a[k, :] = line_rgb
        a[:100, k + 4] = line_rgb  # top row's vertical lines drawn a few px off, like Gemini does
        a[100:, k] = line_rgb
    a[:3, :] = line_rgb  # outer frame too
    a[:, :3] = line_rgb
    p = tmp_path / "sheet.png"
    Image.fromarray(a).save(p)
    return str(p)


def test_grid_lines_are_not_part_of_the_character(tmp_path):
    for line in ((255, 255, 255), (0, 0, 0)):
        cs = frames.cells(frames.key_green(sheet_with_lines(tmp_path, line)), 3, 3)
        assert all(c is not None for c in cs)
        for c in cs:
            assert c.shape[:2] == (60, 40), (line, c.shape)
