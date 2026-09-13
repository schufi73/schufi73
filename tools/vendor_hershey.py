#!/usr/bin/env python3
"""Copy the two Hershey typefaces the sheets use into tools/hershey.json.

The plot itself needs only the Python standard library; this script is the one
place that needs the Hershey-Fonts package (pinned in requirements.txt). Run it
only to add a typeface or to re-check the vendored data:

    pip install -r tools/requirements.txt
    python3 tools/vendor_hershey.py

Glyph data: the Hershey fonts (A. V. Hershey, 1967), in the data format by James Hurt;
the acknowledgment they ask for is in tools/LICENSE-Hershey-Fonts.txt.
Package: Hershey-Fonts 2.1.0 by apshu, MIT licence, see tools/LICENSE-Hershey-Fonts.txt.
"""
import json
from pathlib import Path

from HersheyFonts import HersheyFonts

FACES = ('futural', 'rowmand')


def main():
    out = {'_source': 'Hershey fonts by A. V. Hershey (U.S. Naval Weapons Laboratory, c. 1967), data format by James Hurt, via Hershey-Fonts 2.1.0 '
                      '(MIT). Acknowledgment and licence: LICENSE-Hershey-Fonts.txt. '
                      'Per glyph: [advance, strokes]; x from the left side bearing, cap line y=-12, baseline y=9.'}
    for face in FACES:
        f = HersheyFonts()
        f.load_default_font(face)
        glyphs = {}
        for code in range(32, 127):
            ch = chr(code)
            g = list(f.glyphs_for_text(ch))
            if not g:
                continue
            g = g[0]
            left = getattr(g, '_HersheyGlyph__left_side')
            right = getattr(g, '_HersheyGlyph__right_side')
            glyphs[ch] = [right - left, [[[x - left, y] for x, y in st] for st in g.strokes]]
        out[face] = glyphs
    path = Path(__file__).with_name('hershey.json')
    text = json.dumps(out, separators=(',', ':'), sort_keys=True, ensure_ascii=True)
    # one glyph per line keeps diffs readable
    text = text.replace('],"', '],\n"')
    path.write_text(text + '\n')
    print(path, len(text), 'bytes')


if __name__ == '__main__':
    main()
