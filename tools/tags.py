#!/usr/bin/env python3
"""tags.py: the link tags under SHEET 01.

    python3 tools/tags.py [out_dir]          (draw.py also writes them)

Each tag is a view title cut from the same paper as the sheets: a reference
bubble (a letter over an arrow, "continued elsewhere") beside a heavy title line,
the destination's name above the line and what it is below. They are the only
clickable images in the README. The <a> around each one lives in README.md,
because an SVG shown through <img> cannot hold a link.

Drawn at 296 x 86 and shown at 148 px wide, so one unit is half a CSS pixel: the
name is lettered at cap 24 (12 px), what it is at cap 19 (9.5 px), and nothing goes
below cap 16 (8 px). 148 px keeps four tags on one line in the 846 px column and two
on a line in a 308 px phone column. A tag has no motion and no data, so every run
writes the same bytes.
"""
import sys
from pathlib import Path

from sheet import BUDGETS, Sheet, M, rect_d, circle_d, paper, fit

W, H = 296, 86
BUDGET = BUDGETS['tag-']  # raw bytes, gzip bytes, per tag
MIN_CAP = 16
# Shown at half size, so the pens are twice the sheet's. Set after the sheet CSS, so they
# also win over the mid and phone pens: a 148 px image matches both of the SVG's max-width queries.
PEN_CSS = '.w1{stroke-width:1.6px}.w2{stroke-width:2.4px}.w3{stroke-width:4px}'

TAGS = [  # file stem, bubble letter, name, what it is, <title> for the standalone file
    ('ergane', 'E', 'ERGANE', 'SHOP-FLOOR SOFTWARE', 'ERGANE, shop-floor software for CNC machine shops'),
    ('netsource', 'N', 'NETSOURCE', 'SAGL · TICINO', 'NetSource Sagl, Ticino'),
    ('discord', 'J', 'DISCORD', 'JARCLOUD COMMUNITY', 'The JarCloud Community on Discord'),
    ('gitlab', 'G', 'GITLAB', 'PRIVATE REPOS', 'schufi73 on GitLab, where the repositories are private'),
]


CX, CY, R = 40, 43, 25        # the bubble: a cap-16 letter needs radius 25 to clear its rim and its diameter
X_TEXT, X_END = 72, W - 16    # lettering starts 6 units right of the bubble; the frame's inner edge is at W - 7
CLEAR = 8                     # the longest subtitle stays this far from the frame
SUB_CAP = 19                  # the largest cap at which the longest subtitle fits at the 0.6 condensation floor
SUB_ROOM = (W - 7 - 1.2) - CLEAR - X_TEXT  # frame line at W - 7, half its pen, the clearance
SUB_COND = min(fit(sub, SUB_CAP, SUB_ROOM, cond=.78) for _, _, _, sub, _ in TAGS)


def build(theme, letter, name, sub, title):
    S = Sheet(theme, W, H, min_cap=MIN_CAP, phone_cap=None)
    mark = S.p['mark']
    paper(S)
    S.path(rect_d(7, 7, W - 14, H - 14), w='w2')

    # reference bubble, in markup colour: letter over arrow
    S.path(circle_d(CX, CY, R) + M((CX - R, CY), (CX + R, CY)), w='w2', color=mark)
    S.text(letter, CX, CY - 4.5, 16, anchor='middle', layer=None, color=mark, pen=2.4)
    S.text('↗', CX, CY + 19.5, 16, anchor='middle', layer=None, color=mark, pen=2.4)

    # view title: name on a heavy line, what it is underneath, every subtitle at one width
    S.text(name, X_TEXT, 38, 24, cond=fit(name, 24, X_END - X_TEXT), layer=None, pen=3.2)
    S.path(M((CX + R + 6, 45), (X_END, 45)), w='w3')
    S.text(sub, X_TEXT, 71, SUB_CAP, cond=SUB_COND, layer=None, pen=2.1)
    return S.svg(title, 'A link tag drawn as a view title: %s.' % title, extra_css=PEN_CSS)


def build_all():
    return [('tag-%s-%s.svg' % (stem, theme), build(theme, letter, name, sub, title))
            for stem, letter, name, sub, title in TAGS for theme in ('dark', 'light')]


def main():
    from sheet import validate
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / 'assets'
    out.mkdir(parents=True, exist_ok=True)
    for fname, svg in build_all():
        raw, gz = validate(fname, svg, *BUDGET)
        (out / fname).write_text(svg)
        print('%-28s %6d bytes  %5d gzip' % (fname, raw, gz))


if __name__ == '__main__':
    main()
