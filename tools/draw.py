#!/usr/bin/env python3
"""draw.py: plots the profile sheets.

    python3 tools/draw.py [out_dir]          (default: assets/ next to tools/)

Reads tools/state.json (WakaTime all-time numbers and the date they last changed)
and tools/commits.json (commit aggregates), writes SHEET 01, SHEET 02 and the
link tags in a dark (blueprint) and a light (drafting film) version.
Same inputs, same bytes: nothing here reads the clock or the network.

This file draws SHEET 01: section A-A through a machine shop, which is where
ERGANE lives, with the stack as the building's zones. The revision table and the
notes are written here by hand on purpose: a new revision is a commit.

Anything that comes from data (shares, names, totals) has a fallback instead of a
raise: a label that does not fit moves or shortens, it never stops the plot. The
fixed geometry checks its own clearances and raises, so a code change that crowds
the sheet fails in plot.py's self-test before it reaches assets/.
"""
import json
import math
import re
import sys
from pathlib import Path

from lettering import fmt, measure
from sheet import MID_MAX, MID_PENS, PENS, Sheet, M, budget, clip, rect_d, circle_d, paper, fit, validate

TOOLS = Path(__file__).resolve().parent
W, H = 1200, 720
# The detail plot has the field under DETAIL B to itself, so it lowers the section with everything tied to it (axes,
# datums, dimensions, zone lettering, the detail boundary on the control) by DROP units, into the middle of that
# field. The mid and phone plots keep it where it is: they letter under it. One copy, moved by a CSS transform that
# the mid query switches off.
DROP = 30
DROP_CSS = '.sx{transform:translate(0,%dpx)}@media (max-width:%dpx){.sx{transform:none}}'

# Latest on top: (rev, date, description, short description for the mid-size plot).
# Dated by month, when the work began; ERGANE by the month it got its name.
REVISIONS = [
    ('H', '2026-07', 'DETAIL B ADDED: ERGANE READ-BACK', 'ERGANE, DETAIL B'),
    ('G', '2026-06', 'LED WALL SOFTWARE, JAPAN MATSURI', 'MATSURI LED WALL'),
    ('F', '2026-05', 'VOIDBORN, A MINECRAFT ACTION-RPG', 'VOIDBORN'),
    ('E', '2026', 'PARTNER · DEVELOPMENT & AI', 'PARTNER'),
    ('D', '—', 'APPRENTICE CIVIL ENG. DRAUGHTSMAN', 'DRAUGHTSMAN'),
    ('C', '—', 'NETWORKS AND SECURITY', 'NETWORKS'),
    ('B', '—', 'CODE, VIA MINECRAFT AND TINKERING', 'CODE'),
    ('A', 'AT 11', 'FIRST COMPUTER', 'FIRST COMPUTER'),
]
CLOUDED = REVISIONS[0][0]  # the cloud marks the latest revision: DETAIL B, ERGANE's read-back

NOTES = [  # {commits} and {month} come from tools/commits.json
    'DIMENSIONS IN HOURS OR %. DO NOT SCALE.',
    'BUILD TOOL: GRADLE KOTLIN DSL. NEVER MAVEN.',
    'THE ONLY CLOUD HERE IS THE REVISION CLOUD.',
    '{commits} COMMITS IN 12 MONTHS, ALMOST ALL PRIVATE ({month}).',
]

# The stack, as the building's zones: (zone, what lives there). Lettered into the section on the
# detail layer and keyed by item balloons on the mid layer.
ZONES = [
    ('LOCAL-FIRST AI', 'OLLAMA'),
    ('SERVICES', 'SPRING BOOT · N8N · MARIADB'),
    ('FOUNDATION', 'LINUX · JAVA 21/25'),
]


# ---------------------------------------------------------------------- data
def load(tools=TOOLS):
    state = json.loads((tools / 'state.json').read_text())
    commits = json.loads((tools / 'commits.json').read_text())
    return state, commits


def thousands(v):
    return '{:,}'.format(int(round(v)))


def hm(seconds):
    """WakaTime style, floored: 9052 s -> '2 h 30 min'."""
    m = int(seconds // 60)
    return '%d h %02d min' % (m // 60, m % 60) if m >= 60 else '%d min' % m


def pct(part, whole):
    return 100.0 * part / whole if whole else 0.0


def commits_floor(n):
    """5,500 -> '5,500+'. commits.json already holds the count rounded down to a hundred."""
    return '{:,}+'.format(int(n)) if n >= 100 else 'A FEW'


MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']


def month(iso):
    """'2026-09-13' -> 'SEP 2026'."""
    y, m = iso.split('-')[:2]
    return '%s %s' % (MONTHS[int(m) - 1], y)


def sheet_date(state, commits):
    """The date in both sheets' title blocks: the later of the day the WakaTime numbers last changed and the day
    the commits were counted, so no sheet is dated before the data it carries. It moves only when one of them does.
    A revision dated after it would put the table ahead of the title block: that raises, on the push that adds it."""
    date = max(d for d in (state.get('changed'), commits.get('as_of')) if d)
    for rev, when, _, _ in REVISIONS:
        if re.match(r'\d{4}(-\d\d)?$', when) and when > date[:len(when)]:
            raise ValueError('revision %s is dated %s, after the sheet date %s' % (rev, when, date))
    return date


def facts(state, commits):
    n = state['numbers']
    return dict(
        total_h=n['total_seconds'] / 3600.0,
        per_day=hm(n['daily_average_seconds']),
        date=sheet_date(state, commits),
        commits=commits_floor(commits['commits_floor']),
        commits_month=month(commits['as_of']),
    )


def wrap(text, cap, width, cond):
    words, line, lines = text.split(' '), '', []
    for wd in words:
        trial = (line + ' ' + wd).strip()
        if measure(trial, cap, cond=cond) > width and line:
            lines.append(line)
            line = wd
        else:
            line = trial
    return lines + [line]


# ---------------------------------------------------------------------- geometry checks
def gap(a, b):
    """Clear distance between two boxes (x0, y0, x1, y1); negative when they overlap."""
    return max(b[0] - a[2], a[0] - b[2], b[1] - a[3], a[1] - b[3])


def keep_clear(what, a, b, least):
    if gap(a, b) < least - 1e-9:
        raise ValueError('%s: %.1f units apart, needs %s' % (what, gap(a, b), least))


# ---------------------------------------------------------------------- sheet 01
def patterns(S):
    bg = S.p['sheet']
    tri = ''
    for (x, y, r, a) in ((4, 5, 2.2, 10), (15, 3, 1.6, 70), (21, 13, 2.4, 140), (9, 17, 1.8, 200), (3, 22, 1.4, 40),
                         (17, 22, 2, 300)):
        tri += M(*[(x + r * math.cos(math.radians(a + k * 120)), y + r * math.sin(math.radians(a + k * 120)))
                   for k in range(3)], close=True)
    dots = ''.join('M%d %dh.01' % xy for xy in ((11, 9), (2, 13), (19, 7), (13, 24), (24, 19), (7, 11)))
    S.defs += [
        # concrete (ISO 128-50): aggregate and dots
        '<pattern id="_hc" width="26" height="26" patternUnits="userSpaceOnUse"><rect width="26" height="26" fill="%s"/>'
        '<path d="%s" stroke-width=".8" stroke-opacity=".8"/><path d="%s" stroke-width="1.6" stroke-opacity=".8"/></pattern>'
        % (bg, tri, dots),
        # cut wall panels: 45 degree hatch
        '<pattern id="_hm" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
        '<rect width="6" height="6" fill="%s"/><path d="M0 0V6" stroke-width=".8" stroke-opacity=".85"/></pattern>' % bg,
        # earth: short diagonal pairs and a few grains
        '<pattern id="_he" width="18" height="18" patternUnits="userSpaceOnUse">'
        '<path d="M2 16L12 6M6 18L16 8" stroke-width=".8" stroke-opacity=".55"/>'
        '<path d="M13 15h.01M4 5h.01" stroke-width="1.4" stroke-opacity=".55"/></pattern>',
        # hardcore under the slab: gravel
        '<pattern id="_hg" width="12" height="12" patternUnits="userSpaceOnUse"><rect width="12" height="12" fill="%s"/>'
        '<path d="M1 3a2 2 0 1 0 4 0a2 2 0 1 0-4 0M7 8a1.6 1.6 0 1 0 3.2 0a1.6 1.6 0 1 0-3.2 0" stroke-width=".7" '
        'stroke-opacity=".7"/></pattern>' % bg,
    ]


def cloud(x0, y0, x1, y1, r=11):
    """Revision cloud: arcs bulging outward along a rectangle, clockwise. Returns (path, outer box)."""
    pts = []
    for ax, ay, bx, by in ((x0, y0, x1, y0), (x1, y0, x1, y1), (x1, y1, x0, y1), (x0, y1, x0, y0)):
        n = max(2, int(round(math.hypot(bx - ax, by - ay) / (1.7 * r))))
        pts += [(ax + (bx - ax) * k / n, ay + (by - ay) * k / n) for k in range(n)]
    pts.append(pts[0])
    d = 'M%s %s' % (fmt(pts[0][0]), fmt(pts[0][1]))
    bulge = 0.0
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        half = math.hypot(xb - xa, yb - ya) / 2
        rr = half * 1.08
        bulge = max(bulge, rr - math.sqrt(rr * rr - half * half))
        d += 'A%s %s 0 0 1 %s %s' % (fmt(rr), fmt(rr), fmt(xb), fmt(yb))
    return d, (x0 - bulge, y0 - bulge, x1 + bulge, y1 + bulge)


def grow(box, by):
    return (box[0] - by, box[1] - by, box[2] + by, box[3] + by)


def ref_bubble(S, cx, cy, letter, sheet, t, r=19):
    """A view reference bubble: letter over sheet number."""
    S.path(circle_d(cx, cy, r) + 'M%s %sh%s' % (fmt(cx - r), fmt(cy), fmt(2 * r)), w='w1', t=t, dur=.25, layer='dt')
    S.text(letter, cx, cy - 3, 12, anchor='middle', t=t + .15, dur=.1, pen=1.5)
    S.text(sheet, cx, cy + 15, 12, anchor='middle', t=t + .2, dur=.1, pen=1.3)


def item_balloon(S, cx, cy, label, t, r=17, layer='md'):
    """An item balloon (ISO 6433) on paper, so it reads on a hatch."""
    S.raw('<path class="w2 %s %s" fill="%s" d="%s"/>' % (layer, S.motion.cls('fd', t, .2), S.p['sheet'],
                                                         circle_d(cx, cy, r)))
    S.text(label, cx, cy + 11, 22, anchor='middle', cond=.76, t=t + .1, dur=.1, pen=2.4, layer=layer)


def build(theme, state, commits):
    f = facts(state, commits)
    S = Sheet(theme, W, H, end=4.0)
    p = S.p
    mark = p['mark']
    paper(S)
    patterns(S)

    L, R, T, B = 40, 1176, 22, 698
    COL = 770

    # ============================================================ pre-printed sheet form (static)
    S.path(rect_d(10, 10, W - 20, H - 20), w='w1', op=.5)
    S.path(rect_d(L, T, R - L, B - T), w='w4')
    zx = (R - L) / 6.0
    zy = (B - T) / 4.0
    ticks = ''.join('M%s 10V%sM%s %sV%s' % (fmt(L + i * zx), T, fmt(L + i * zx), B, H - 10) for i in range(1, 6))
    ticks += ''.join('M10 %sH%sM%s %sH%s' % (fmt(T + i * zy), L, R, fmt(T + i * zy), W - 10) for i in range(1, 4))
    S.path(ticks, w='w1', layer='dt', op=.7)

    # ---- right strip: revisions, notes, title block (frames pre-printed, entries plotted)
    X0, X1 = COL, R
    S.path(M((X0, T), (X0, B)), w='w4', layer='dm')
    RH = 24
    rev_head = T + 32
    col_head = rev_head + 22
    cols = [X0, X0 + 38, X0 + 114, X1]
    rev_bot = col_head + RH * len(REVISIONS)
    S.text('REVISIONS', X0 + 12, T + 22, 14, pen=1.6)
    S.text('LATEST ON TOP', X1 - 12, T + 22, 12, anchor='end', op=.8)
    S.path(M((X0, rev_head), (X1, rev_head)) + M((X0, col_head), (X1, col_head)), w='w2', layer='dt')
    S.text('REV', (cols[0] + cols[1]) / 2.0, rev_head + 16.5, 12, anchor='middle', op=.8, cond=.7)
    S.text('DATE', cols[1] + 8, rev_head + 16.5, 12, op=.8)
    S.text('DESCRIPTION', cols[2] + 8, rev_head + 16.5, 12, op=.8)
    S.path(M((cols[1], rev_head), (cols[1], col_head)) + M((cols[2], rev_head), (cols[2], col_head)), w='w1',
           layer='dt', op=.85)
    S.path(M((X0, rev_bot), (X1, rev_bot)), w='w3', layer='dt')

    # general notes, set evenly between their heading and the title block
    tb = 448
    notes = [n.format(commits=f['commits'], month=f['commits_month']) for n in NOTES]
    note_cap, note_lh, note_gap, note_cond = 13.5, 19, 8, .72
    note_x = X0 + 34
    note_lines = [wrap(n, note_cap, X1 - note_x - 10, note_cond) for n in notes]
    head_y = rev_bot + 25
    block = note_cap + note_lh * (sum(map(len, note_lines)) - 1) + note_gap * (len(notes) - 1)
    pad = (tb - head_y - block) / 2.0
    if pad < 8:
        raise ValueError('general notes overrun the title block by %.0f units' % (8 - pad))
    S.text('GENERAL NOTES', X0 + 12, head_y, 14, pen=1.6)
    y = head_y + pad + note_cap
    note_pos = []
    for lines in note_lines:
        note_pos.append(y)
        y += note_lh * len(lines) + note_gap

    # ---- title block
    office = tb + 32
    name_y = (office + 46, office + 90)
    role_y = office + 114
    rows_y = [606, 652, B]  # 46 units a row: 4 above the field name, cap 12, 8, the value, 7 below
    S.path(M((X0, tb), (X1, tb)), w='w4', layer='dt')
    S.path(M((X0, office), (X1, office)) + M((X0 + 76, tb), (X0 + 76, office)), w='w1', layer='dt')
    px, py = X0 + 38, tb + 16  # first-angle projection symbol (ISO 5456-2)
    S.path('M%s %sL%s %sL%s %sL%s %sZ' % (fmt(px - 28), fmt(py - 6), fmt(px - 8), fmt(py - 10), fmt(px - 8),
                                          fmt(py + 10), fmt(px - 28), fmt(py + 6))
           + circle_d(px + 13, py, 10) + circle_d(px + 13, py, 4), w='w1', layer='dt')
    S.path(M((X0, rows_y[0]), (X1, rows_y[0])), w='w3', layer='dt')
    S.path(M((X0, rows_y[1]), (X1, rows_y[1])), w='w1', layer='dt')
    cw = X1 - X0
    cells = [
        [('DRAWN', 'N. SCHAUFELBERGER', .38), ('CHECKED', 'BYTE FOR BYTE', .31), ('SCALE', '1:1', .13),
         ('LANG', 'IT·EN·DE', .18)],
        [('DATE', f['date'], .27), ('LOCATION', 'LOCARNO CH', .29), ('REV', REVISIONS[0][0], .12),
         ('SHEET', '01 / 02', .32)],
    ]
    cell_vals = []
    for ri, row in enumerate(cells):
        y0, y1 = rows_y[ri], rows_y[ri + 1]
        x = X0
        v = ''
        for i, (lab, val, frac) in enumerate(row):
            if i:
                v += M((x, y0), (x, y1))
            cell_vals.append((lab, val, x, y0, y1, cw * frac))
            x += cw * frac
        S.path(v, w='w1', layer='dt')

    # ============================================================ the plot
    # ---- the name first, so even a late start shows whose sheet this is (desktop and mid share it)
    S.text('NOAH', X0 + 12, name_y[0], 36, face='rowmand', cond=.8, pen=4.4, t=0, dur=.3, layer='dm')
    S.text('SCHAUFELBERGER', X0 + 12, name_y[1], 36, face='rowmand', cond=fit('SCHAUFELBERGER', 36, cw - 22, .8,
                                                                               'rowmand'), pen=4.4, t=.15, dur=.55,
           layer='dm')
    S.text('NETSOURCE SAGL · TICINO', X0 + 88, tb + 22, 14, pen=1.6, t=.25, dur=.4)
    S.text('PARTNER · DEVELOPMENT & AI', X0 + 12, role_y, 15, pen=1.7, t=.5, dur=.45)
    for i, (lab, val, x, y0, y1, room) in enumerate(cell_vals):
        S.text(lab, x + 7, y0 + 17, 12, op=.85, cond=fit(lab, 12, room - 14))
        big = lab == 'SHEET'
        cap = 15 if big else 13
        S.text(val, x + 7, y1 - 7, cap, cond=fit(val, cap, room - 14), pen=1.9 if big else 1.4, t=.8 + i * .07, dur=.3)

    # ---- revision rows, A first so the timeline builds upward; each row brings its own rule
    rev_cond = min(fit(desc, 13, cols[3] - cols[2] - 16) for _, _, desc, _ in REVISIONS)
    S.path(M((cols[1], rev_bot), (cols[1], col_head)) + M((cols[2], rev_bot), (cols[2], col_head)), w='w1', t=.3,
           dur=.95, layer='dt', op=.85)
    for i, (rv, date, desc, _) in enumerate(REVISIONS):
        y = col_head + (i + 1) * RH - 6.5
        t0 = .3 + (len(REVISIONS) - 1 - i) * .12
        if i:
            S.path(M((X0, col_head + i * RH), (X1, col_head + i * RH)), w='w1', t=t0 + .08, dur=.25, layer='dt', op=.85)
        S.text(rv, (cols[0] + cols[1]) / 2.0, y, 13, anchor='middle', t=t0, dur=.12, color=mark if rv == CLOUDED else None,
               pen=1.6)
        S.text(date, cols[1] + 8, y, 13, t=t0 + .04, dur=.2, cond=fit(date, 13, cols[2] - cols[1] - 16, .76))
        S.text(desc, cols[2] + 8, y, 13, t=t0 + .08, dur=.4, cond=rev_cond)

    # ---- general notes
    for i, (lines, y) in enumerate(zip(note_lines, note_pos)):
        t0 = 1.1 + i * .2
        S.text('%d.' % (i + 1), note_x - 6, y, note_cap, anchor='end', t=t0, dur=.1, op=.85)
        for k, ln in enumerate(lines):
            S.text(ln, note_x, y + k * note_lh, note_cap, cond=note_cond, t=t0 + .05 + k * .15, dur=.3)

    # ---- section A-A through a machine shop
    S.raw('<g class="sx">')
    FL = 520            # finished floor, ±0.00, flush with the yard outside: a shop floor takes forklifts
    GR = FL             # outside ground
    SB = 534            # underside of slab
    FB = 594            # underside of footings
    WLo, WLi, WRi, WRo = 130, 146, 594, 610
    EAVE, RIDGE = 284, 238
    RAIL = 370
    xb0, xb1 = 58, 704
    brk = lambda x: [(x, 562), (x - 6, 568), (x + 6, 576), (x, 582)]
    # the ground runs under the whole building; slab, footings and walls are drawn over it on their own paper
    earth = M(*([(xb0, GR), (WLo, GR), (WLo, SB), (WRo, SB), (WRo, GR), (xb1, GR)]
                + brk(xb1) + [(xb1, 612), (640, 606), (560, 615), (470, 608), (380, 616), (290, 609), (200, 617),
                              (120, 608), (xb0, 613)] + brk(xb0)[::-1]), close=True)
    slab = rect_d(WLi, FL, 372 - WLi, SB - FL) + rect_d(566, FL, WRo - 566, SB - FL)  # it runs out through the door
    mfound = rect_d(376, FL, 562 - 376, 584 - FL)
    foot = rect_d(WLo - 16, SB, 48, FB - SB) + rect_d(WRi - 16, SB, 48, FB - SB)
    lintel_l = rect_d(WLo, 318, 16, 14)
    lintel_r = rect_d(WRi, 416, 16, 16)
    walls = rect_d(WLo, 382, 16, SB - 382) + rect_d(WLo, EAVE, 16, 318 - EAVE) + rect_d(WRi, EAVE, 16, 416 - EAVE)
    xs = [WLo + k * 160 for k in range(4)]
    top = []
    for k in range(3):
        top += [(xs[k], EAVE), (xs[k + 1], RIDGE), (xs[k + 1], EAVE)]
    # Pens after ISO 128: what the plane cuts in w3, what is seen beyond it in w2, detail, hatching, dimensions and
    # leaders in w1. The hatches go down first and are painted on paper, so an outline laid under one would lose
    # the inner half of its line: every outline goes on top.
    S.fill(earth, 'url(#_he)', t=.6, dur=.45)
    S.fill(rect_d(WLi + 16, SB, 376 - WLi - 16, 9) + rect_d(562, SB, 578 - 562, 9), 'url(#_hg)', t=.65, dur=.35)
    S.fill(slab + mfound + foot + lintel_l + lintel_r, 'url(#_hc)', t=.7, dur=.4)
    S.fill(walls, 'url(#_hm)', t=.75, dur=.35)
    # the cut, plotted first: ground and walls carry the drawing in the first half second, then the roof with its
    # eaves stub, the footings and the machine foundation, whose isolation joints are the 4-unit gaps either side
    # of it, and the slab
    S.path(M((44, GR), (WLo, GR)) + M((WRo, GR), (xb1 + 10, GR)), w='w4', t=0, dur=.35)
    S.path(walls + lintel_l + lintel_r, w='w3', t=.05, dur=.45)
    S.path(M(*top) + M((WLo - 10, EAVE), (WLo, EAVE)), w='w3', t=.15, dur=.5)
    S.path(foot + mfound, w='w3', t=.3, dur=.4)
    S.path(slab, w='w3', t=.35, dur=.3)
    S.path(M(*([(xb0, 552)] + brk(xb0) + [(xb0, 620)])) + M(*([(xb1, 552)] + brk(xb1) + [(xb1, 620)])), w='w1',
           t=.4, dur=.3)
    # beyond the cut: the jambs of the door under the right lintel; the window in the left wall
    S.path(M((WRi, 432), (WRi, FL)) + M((WRo, 432), (WRo, FL)), w='w2', t=.45, dur=.3)
    S.path(M((WLo, 332), (WLi, 332)) + M((WLo, 382), (WLi, 382)) + M((WLo + 6, 332), (WLo + 6, 382))
           + M((WLo + 10, 332), (WLo + 10, 382)), w='w1', t=.9, dur=.25)
    # roof deck (its underside is cut too), glazing in the vertical faces, trusses under each tooth
    inner = mullion = glaze = truss = ''
    for k in range(3):
        a, b = xs[k], xs[k + 1]
        inner += M((a + 2, EAVE + 7), (b - 8, RIDGE + 9))
        mullion += M((b - 8, RIDGE + 9), (b - 8, EAVE + 7))
        glaze += M((b - 3, RIDGE + 12), (b - 3, EAVE - 4)) + M((b - 6, RIDGE + 14), (b - 6, EAVE - 4))
        us = (.25, .5, .75)
        pt = [(a + 2 + (b - 10 - a) * u, EAVE + 7 - (EAVE - RIDGE - 2) * u) for u in us]
        pb = [(a + 2 + (b - 10 - a) * u, EAVE + 7) for u in us]
        truss += M((a + 2, EAVE + 7), (b - 8, EAVE + 7))
        truss += M((a + 2, EAVE + 7), pt[0], pb[0], pt[1], pb[1], pt[2], pb[2], (b - 8, RIDGE + 9))
        truss += ''.join(M(u, v) for u, v in zip(pt, pb))
    S.path(inner, w='w3', t=.55, dur=.4)
    S.path(mullion, w='w2', t=.6, dur=.2)
    S.path(glaze, w='w1', t=.9, dur=.3)
    S.path(truss, w='w1', t=.85, dur=.5)
    # crane runway beyond the cut: corbels, rails, bridge girder. The trolley and its hook stay off the phone plot,
    # where they would sit right after SERVICES and read as one more letter.
    S.path(M((WLi, RAIL + 6), (WLi + 20, RAIL + 6), (WLi + 20, RAIL + 14), (WLi, RAIL + 30))
           + M((WRi, RAIL + 6), (WRi - 20, RAIL + 6), (WRi - 20, RAIL + 14), (WRi, RAIL + 30)), w='w2', t=.8, dur=.3)
    S.path(rect_d(WLi + 6, RAIL - 12, WRi - WLi - 12, 14) + rect_d(WLi + 8, RAIL + 2, 14, 4)
           + rect_d(WRi - 22, RAIL + 2, 14, 4), w='w2', t=.9, dur=.4)
    hx = 462
    S.path(rect_d(hx - 22, RAIL - 22, 44, 10) + rect_d(hx - 9, 398, 18, 12) + M((hx, 410), (hx, 416))
           + 'M%s 416a6 6 0 1 1-6 6' % fmt(hx), w='w2', t=1.1, dur=.35, layer='dm')
    S.path(M((hx - 4, RAIL + 2), (hx - 4, 398)) + M((hx + 4, RAIL + 2), (hx + 4, 398)), w='w1', t=1.15, dur=.2,
           layer='dm')
    # the machine: a generic machining centre on its own foundation, seen beyond the cut; door, window and base in w1
    mx0, mx1, mtop = 392, 540, 438
    S.path(M((mx0, FL), (mx0, mtop + 12), (mx0 + 12, mtop), (mx1, mtop), (mx1, FL)), w='w2', t=1.0, dur=.5)
    S.path(rect_d(mx0 + 30, mtop + 16, 70, 40) + M((mx0 + 65, mtop + 16), (mx0 + 65, mtop + 56))
           + M((mx0 + 108, mtop + 24), (mx0 + 108, mtop + 48)) + M((mx0 + 4, 506), (mx1 - 4, 506))
           + rect_d(mx0 + 2, FL - 4, 10, 4) + rect_d(mx1 - 12, FL - 4, 10, 4), w='w1', t=1.3, dur=.3)
    S.path(M((mx1, mtop + 8), (mx1 + 14, mtop + 8), (mx1 + 14, mtop + 14)) + rect_d(mx1 + 6, mtop + 14, 24, 34),
           w='w2', t=1.3, dur=.25)
    S.path(''.join(M((mx1 + 11 + 5 * k, mtop + 38), (mx1 + 11 + 5 * k, mtop + 42)) for k in range(3))
           + rect_d(mx1 + 10, mtop + 19, 16, 12), w='w1', t=1.45, dur=.15)
    # its chip conveyor: a hinged-belt casing out of the machine base, rising 35 degrees from the tail pulley to the
    # head pulley, where the chips drop through a chute into a bin; one leg under it. Casing, chute, leg and bin w2,
    # pulleys and belt plates w1.
    (tx0, ty0), run, hw = (385, 506), 95, 7
    ux, uy = -math.cos(math.radians(35)), -math.sin(math.radians(35))
    nx, ny = -uy, ux                                    # across the casing, towards its top side
    hx1, hy1 = tx0 + run * ux, ty0 + run * uy
    under = lambda x: hy1 - hw * ny + (x - (hx1 - hw * nx)) * uy / ux   # the casing's underside at x
    casing = (M((tx0 + hw * nx, ty0 + hw * ny), (hx1 + hw * nx, hy1 + hw * ny))
              + 'A%d %d 0 0 0 %s %s' % (hw, hw, fmt(hx1 - hw * nx), fmt(hy1 - hw * ny))
              + 'L%s %sA%d %d 0 0 0 %s %sZ' % (fmt(tx0 - hw * nx), fmt(ty0 - hw * ny), hw, hw, fmt(tx0 + hw * nx),
                                               fmt(ty0 + hw * ny)))
    cx_l, cx_r, bin_top = hx1 - 6, hx1 + 6, 486
    chute = M((cx_l, under(cx_l) - 1), (cx_l, bin_top - 9)) + M((cx_r, under(cx_r)), (cx_r, bin_top - 9))
    chip_bin = M((hx1 - 22, bin_top), (hx1 - 18, FL), (hx1 + 18, FL), (hx1 + 22, bin_top)) + M((hx1 - 25, bin_top),
                                                                                                (hx1 + 25, bin_top))
    S.path(casing + chute + M((350, under(350)), (350, FL)) + chip_bin, w='w2', t=1.2, dur=.35)
    plates = ''.join(M((tx0 + d * ux + hw * nx, ty0 + d * uy + hw * ny),
                       (tx0 + d * ux - hw * nx, ty0 + d * uy - hw * ny)) for d in range(14, run - 10, 9))
    S.path(circle_d(tx0, ty0, 4) + circle_d(hx1, hy1, 4) + plates, w='w1', t=1.4, dur=.25)
    # server rack against the left wall, its shelves in w1
    S.path(rect_d(156, 438, 34, FL - 438), w='w2', t=1.15, dur=.35)
    S.path(''.join(M((160, 448 + 12 * k), (186, 448 + 12 * k)) for k in range(6)), w='w1', t=1.3, dur=.3)
    S.path(''.join('M182 %dh.01' % (442 + 12 * k) for k in range(6)), w='w2', t=1.5, dur=.15, color=mark)
    S.raw('</g>')

    # ---- view title (the title and its rules also serve the mid layer)
    vx, vy = 84, 66
    S.path(circle_d(vx, vy - 2, 22), w='w2', t=.1, dur=.35, layer='dm')
    S.path('M%s %sh44' % (fmt(vx - 22), fmt(vy - 2)), w='w2', t=.2, dur=.2, layer='dt')
    S.text('A', vx, vy - 8, 13, anchor='middle', t=.3, dur=.12, pen=1.6)
    S.text('01', vx, vy + 15, 12, anchor='middle', t=.35, dur=.12, pen=1.4)
    S.text('A', vx, vy + 9, 22, anchor='middle', t=.3, dur=.12, pen=2.4, layer='md')
    tw = S.text('SECTION A–A', vx + 36, vy - 7, 22, t=.2, dur=.4, pen=2.4, layer='dm')
    sub = ('THROUGH THE STACK,', 'AS A MACHINE SHOP')
    sw = max(tw, max(measure(s, 13, cond=.78) for s in sub))
    S.path(M((vx + 34, vy + 1), (vx + 38 + sw, vy + 1)), w='w3', t=.45, dur=.3, layer='dm')
    S.path(M((vx + 34, vy + 6), (vx + 38 + sw, vy + 6)), w='w1', t=.5, dur=.3, layer='dm')
    for k, s in enumerate(sub):
        S.text(s, vx + 36, vy + 26 + k * 18, 13, cond=.78, t=.6 + k * .2, dur=.35)

    # ---- structural axes and the per-coding-day dimension between them
    S.raw('<g class="sx">')
    AX = [WLo + 8, WRi + 8]
    AY = 200
    S.path(''.join(M((x, AY + 11), (x, FB + 16)) for x in AX), w='w1', kind='wp', t=1.2, dur=.5, layer='dt', op=.6,
           extra=' stroke-dasharray="18 4 3 4"')
    S.path(''.join(circle_d(x, AY, 11) for x in AX), w='w1', t=1.25, dur=.3, layer='dt')
    S.row([(str(i + 1), x) for i, x in enumerate(AX)], AY + 6, 12, t=1.4, dur=.2)
    DY = 226
    S.path(M((AX[0] - 6, DY), (AX[1] + 6, DY)), w='w1', t=1.9, dur=.35, layer='dt')
    S.path(M((AX[0] - 5, DY + 5), (AX[0] + 5, DY - 5)) + M((AX[1] - 5, DY + 5), (AX[1] + 5, DY - 5)), w='w2', t=2.2,
           dur=.12, layer='dt')
    day_txt = '%s PER CODING DAY' % f['per_day']
    day_x = (AX[0] + AX[1]) / 2 - 70
    day_w = S.text(day_txt, day_x, DY - 6, 13, anchor='middle', t=2.2, dur=.45, cond=.78)

    # ---- level datums, left; the floor's sits on the ground line, which is its level outside
    for i, (y, lab) in enumerate(((RIDGE, 'RIDGE'), (EAVE, 'EAVES'), (RAIL, 'RAIL'), (FL, '±0.00'))):
        t0 = 1.6 + i * .08
        if y != GR:
            S.path(M((46, y), (xs[1] - 6 if i == 0 else WLo - 12, y)), w='w1', t=t0, dur=.3, layer='dt', op=.8)
        S.raw('<g class="dt %s"><path class="w1" d="%s"/><path fill="%s" stroke="none" d="%s"/></g>' % (
            S.motion.cls('fd', t0 + .2, .2), M((48, y - 12), (62, y - 12), (55, y), close=True), p['ink'],
            M((48, y - 12), (55, y - 12), (55, y), close=True)))
        S.text(lab, 66, y - (7 if y == GR else 4), 12, t=t0 + .22, dur=.15, cond=.76)

    # ---- the stack, lettered into the building's zones
    def zone(cx, y, name, sub, t0, sub_cond=.78, knock=False):
        wn = S.text(name, cx, y, 15, anchor='middle', t=t0, dur=.35, pen=1.8, knock=knock)
        ws = measure(sub, 12.5, cond=sub_cond)
        S.path(M((cx - max(wn, ws) / 2 - 4, y + 6), (cx + max(wn, ws) / 2 + 4, y + 6)), w='w1', t=t0 + .15, dur=.3,
               layer='dt')
        S.text(sub, cx, y + 23, 12.5, anchor='middle', t=t0 + .3, dur=.5, cond=sub_cond, knock=knock)
    zone(368, 324, ZONES[0][0], ZONES[0][1], 1.5)
    zone(270, 404, ZONES[1][0], ZONES[1][1], 1.65, sub_cond=.74)
    # between the footings, on the ground under the slab; Gradle is general note 2
    zone((WLo + 32 + 376) / 2.0, 564, ZONES[2][0], ZONES[2][1], 1.8, sub_cond=.76, knock=True)

    # ---- one overall dimension right of the section: the hours, all time. SHEET 02 cuts them by language and by
    # editor, so this sheet draws no chain of shares and the ground right of the section stays open.
    DX = 662
    S.path(M((xs[3] + 6, RIDGE), (DX + 10, RIDGE)) + M((WRo + 20, FB), (DX + 10, FB)), w='w1', t=1.9, dur=.3,
           layer='dm', op=.85)
    S.path(M((DX, RIDGE - 8), (DX, FB + 8)), w='w1', t=2.0, dur=.4, layer='dm')
    S.path(M((DX - 5, RIDGE + 5), (DX + 5, RIDGE - 5)) + M((DX - 5, FB + 5), (DX + 5, FB - 5)), w='w2', t=2.35, dur=.12,
           layer='dm')
    hours = '%s h' % thousands(f['total_h'])
    S.text(hours, DX - 6, (RIDGE + GR) / 2, 22, anchor='middle', rot=-90, t=2.4, dur=.4, pen=2.3, layer='dm',
           cond=fit(hours, 22, GR - RIDGE - 24))
    S.text('TRACKED, ALL TIME', DX + 18, (RIDGE + GR) / 2, 12, anchor='middle', rot=-90, t=2.5, dur=.4, op=.85)
    S.raw('</g>')

    # ---- DETAIL B, scale 10:1: what ERGANE sends to a control, and what it reads back
    bx0, by0, bx1, by1 = 350, 46, 562, 183
    S.path(rect_d(bx0, by0, bx1 - bx0, by1 - by0), w='w2', t=2.5, dur=.35, layer='dt')
    ref_bubble(S, bx0 + 26, by0 + 26, 'B', '01', 2.55)
    S.text('DETAIL B · SCALE 10:1', bx0 + 54, by0 + 31, 13, t=2.6, dur=.35, pen=1.5,
           cond=fit('DETAIL B · SCALE 10:1', 13, bx1 - bx0 - 66))
    sent = ['25', '0A', '4F', '31', '32']  # '%', LF, 'O12…': the head of an ISO NC program, broken off
    cx0, cwid = bx0 + 54, 27
    rows = (('SENT', by0 + 56), ('READ', by0 + 93))
    end = cx0 + len(sent) * cwid
    for ri, (lab, yy) in enumerate(rows):
        t0 = 2.75 + ri * .2
        S.text(lab, bx0 + 12, yy + 6, 13, t=t0, dur=.15, cond=fit(lab, 13, cx0 - bx0 - 18, .76))
        # the cells, and a break line where the program goes on
        S.path(''.join(rect_d(cx0 + k * cwid, yy - 12, cwid, 24) for k in range(len(sent)))
               + M((end, yy - 12), (end + 8, yy - 12)) + M((end, yy + 12), (end + 8, yy + 12))
               + M((end + 8, yy - 16), (end + 8, yy - 4), (end + 13, yy - 1), (end + 3, yy + 3), (end + 8, yy + 6),
                   (end + 8, yy + 16)), w='w1', t=t0, dur=.25, layer='dt')
        S.row([(byte, cx0 + k * cwid + cwid / 2) for k, byte in enumerate(sent)], yy + 6.5, 13, cond=.72, t=t0 + .05,
              dur=.15)
    S.path(''.join(M((cx0 + k * cwid + cwid / 2, rows[0][1] + 15), (cx0 + k * cwid + cwid / 2, rows[1][1] - 15))
                   for k in range(len(sent))), w='w2', t=3.15, dur=.15, layer='dt', color=mark)
    S.text('✓', bx0 + 12, by1 - 10, 14, t=3.2, dur=.1, color=mark, pen=2.2)
    S.text('READ BACK = SENT', bx0 + 38, by1 - 10, 13, t=3.2, dur=.35, cond=.78)
    # the detail boundary on the machine's control, a short leader and its reference bubble
    cxm, cym = mx1 + 18, mtop + 31
    S.raw('<g class="sx">')
    S.path(circle_d(cxm, cym, 24), w='w1', kind='fd', t=2.55, dur=.3, layer='dm', extra=' stroke-dasharray="6 4"')
    S.path(M((cxm, cym - 24), (cxm, cym - 34)), w='w1', t=2.8, dur=.1, layer='dt')
    ref_bubble(S, cxm, cym - 53, 'B', '01', 2.85)
    S.raw('</g>')

    # ---- the revision cloud around DETAIL B, and its delta
    cloud_d, cloud_box = cloud(bx0 - 8, by0 - 5, bx1 + 7, by1 + 6)
    S.path(cloud_d, w='w2', t=3.35, dur=.5, color=mark, layer='dt')
    tx, ty = bx1 + 38, by0 + 22
    S.path(M((tx - 14, ty + 10), (tx + 14, ty + 10), (tx, ty - 14), close=True), w='w2', kind='fd', t=3.75, dur=.15,
           color=mark, layer='dt')
    S.text(CLOUDED, tx, ty + 6, 12, anchor='middle', t=3.8, dur=.12, color=mark, pen=1.5)
    # the most colourful thing on the sheet gets room to breathe: 10 units to the frame, the axis bubble and
    # the dimension under it (both lowered by DROP on the detail plot)
    ink = grow(cloud_box, PENS['w2'] / 2)
    keep_clear('DETAIL B cloud / drawing frame', ink, (L, T - 99, R, T + PENS['w4'] / 2), 10)
    keep_clear('DETAIL B cloud / axis bubble 2', ink,
               grow((AX[1], AY + DROP, AX[1], AY + DROP), 11 + PENS['w1'] / 2), 10)
    keep_clear('DETAIL B cloud / per-coding-day dimension', ink,
               (day_x - day_w / 2, DY + DROP - 6 - 13, day_x + day_w / 2, DY + DROP - 6), 10)
    keep_clear('DETAIL B cloud / its delta', ink, (tx - 15, ty - 15, tx + 15, ty + 11), 8)

    # ============================================================ mid layer: section, detail B, short title block
    mid_layer(S, f, dict(X0=X0, X1=X1, T=T, B=B, COL=COL, tb=tb, name_y=name_y, RIDGE=RIDGE, cxm=cxm, cym=cym))

    # ============================================================ phone layer: coarser plot, heavier pens
    S.text('NOAH SCHAUFELBERGER', 64, 116, 60, face='rowmand', cond=.8, pen=6, layer='mb', t=0, dur=.8)
    S.text('PARTNER · DEVELOPMENT & AI', 66, 182, 44, cond=.8, pen=4.4, layer='mb', t=.6, dur=.6)
    # zone names on clean ground: between the truss chords and the girder, clear of the corbel and the hook;
    # the halo stops any line that runs close from touching a letter
    S.text('LOCAL AI', 300, 346, 44, anchor='middle', cond=.72, pen=4.6, layer='mb', t=1.5, dur=.4, halo=8)
    S.text('SERVICES', 300, 427, 44, anchor='middle', cond=.72, pen=4.6, layer='mb', t=1.7, dur=.4, halo=8)
    lx = (WLo + WRo) / 2
    S.text('LINUX · JAVA', lx, 676, 44, anchor='middle', cond=.72, pen=4.6, layer='mb', t=1.9, dur=.5)
    S.path(M((469, 624), (469, 574)) + 'M469 572h.01', w='w2', layer='mb', t=2.3, dur=.3)
    RX, RW = 736, 1160 - 736
    hours_mb = thousands(f['total_h'])
    # the comma of the big number hangs about 24 units below its baseline: the next line keeps clear of it
    S.text(hours_mb, RX, 355, 100, face='rowmand', cond=fit(hours_mb, 100, RW, .8, 'rowmand'), pen=9, layer='mb',
           t=2.2, dur=.7)
    S.text('HOURS TRACKED', RX + 4, 441, 44, cond=fit('HOURS TRACKED', 44, RW - 4, .76), pen=4.4, layer='mb', t=2.6,
           dur=.45)
    # under the rule, the title block: office and sheet
    S.path(M((RX, 514), (1160, 514)), w='w2', layer='mb', t=3.0, dur=.3)
    S.text('NETSOURCE SAGL', RX + 4, 580, 44, cond=fit('NETSOURCE SAGL', 44, RW - 4, .76), pen=4.4, layer='mb', t=3.2,
           dur=.4)
    S.text('SHEET 01 / 02', RX + 4, 644, 44, cond=.8, pen=4.4, layer='mb', t=3.4, dur=.4)

    title = 'Sheet 01: Noah Schaufelberger, Partner · Development & AI, NetSource Sagl, Ticino'
    desc = ('A technical drawing in single-stroke lettering. Section A-A through a machine shop with a sawtooth roof and '
            'a crane, the stack drawn as the building: foundation Linux and Java 21/25; services Spring Boot, n8n and '
            'MariaDB; Ollama for local-first AI under the roof. Detail B shows an NC program sent to a control and '
            'read back byte for byte. Two dimensions: %s hours tracked all time, and %s per coding day. General '
            'notes: build tool Gradle Kotlin DSL; %s commits in 12 months, almost all private (%s). Revision table '
            'from a first computer at 11 to ERGANE. Title block dated %s.'
            % (thousands(f['total_h']), f['per_day'], f['commits'], f['commits_month'].title(), f['date']))
    return S.svg(title, desc, extra_css=DROP_CSS % (DROP, MID_MAX))


def mid_layer(S, f, g):
    """The plot for a 521-799 px image: the section with its title and overall dimension (shared with the
    detail layer), DETAIL B and the stack keyed by item balloons, the latest revisions and a short title block.
    Nothing lettered below cap 22."""
    mark = S.p['mark']
    X0, X1, T, B, COL, tb = g['X0'], g['X1'], g['T'], g['B'], g['COL'], g['tb']

    # ---- the latest three revisions
    S.text('REVISIONS', X0 + 12, 58, 22, cond=.76, pen=2.6, layer='md', t=.25, dur=.3)
    S.path(M((X0, 72), (X1, 72)), w='w2', layer='md')
    cols = [X0, X0 + 44, X0 + 174, X1]
    latest = REVISIONS[:3]
    rh = 38
    bot = 72 + rh * len(latest)
    S.path(''.join(M((X0, 72 + rh * i), (X1, 72 + rh * i)) for i in range(1, len(latest)))
           + M((cols[1], 72), (cols[1], bot)) + M((cols[2], 72), (cols[2], bot)), w='w1', layer='md')
    S.path(M((X0, bot), (X1, bot)), w='w3', layer='md')
    cond = min(fit(short, 22, cols[3] - cols[2] - 18, .76) for _, _, _, short in latest)
    for i, (rv, date, _, short) in enumerate(latest):
        y = 72 + rh * (i + 1) - 10
        t0 = .35 + (len(latest) - 1 - i) * .15
        S.text(rv, (cols[0] + cols[1]) / 2.0, y, 22, anchor='middle', cond=.76, pen=2.6, layer='md', t=t0, dur=.1,
               color=mark if rv == CLOUDED else None)
        S.text(date, cols[1] + 8, y, 22, cond=fit(date, 22, cols[2] - cols[1] - 16, .76), layer='md', t=t0 + .05,
               dur=.2)
        S.text(short, cols[2] + 8, y, 22, cond=cond, layer='md', t=t0 + .1, dur=.3)

    # ---- the key to the section's item balloons
    item_h, lh = 50, 28
    step = (tb - 8 - bot - item_h * len(ZONES)) / float(len(ZONES) + 1)
    for i, (zone_name, what) in enumerate(ZONES):
        y = bot + step * (i + 1) + item_h * i + 22
        t0 = 1.5 + i * .25
        item_balloon(S, X0 + 28, y - 11, str(i + 1), t0)
        room = X1 - (X0 + 54) - 10
        S.text(zone_name, X0 + 54, y, 22, cond=fit(zone_name, 22, room, .76), pen=2.6, layer='md', t=t0 + .1, dur=.3)
        S.text(what, X0 + 54, y + lh, 22, cond=fit(what, 22, room, .76), layer='md', t=t0 + .2, dur=.4)
    for i, (cx, cy) in enumerate(((370, 325), (292, 412), (269, 572))):
        item_balloon(S, cx, cy, str(i + 1), 1.4 + i * .25)

    # ---- title block: office, the shared name, role, date / revision / sheet
    top = tb - 8
    S.path(M((X0, top), (X1, top)), w='w4', layer='md')
    S.text('NETSOURCE SAGL · TICINO', X0 + 12, top + 34, 22, cond=fit('NETSOURCE SAGL · TICINO', 22, X1 - X0 - 24, .76),
           pen=2.4, layer='md', t=.25, dur=.4)
    role = 'PARTNER · DEVELOPMENT & AI'
    S.text(role, X0 + 12, g['name_y'][1] + 38, 22, cond=fit(role, 22, X1 - X0 - 24, .76), pen=2.4, layer='md', t=.5,
           dur=.45)
    ry = g['name_y'][1] + 52
    S.path(M((X0, ry), (X1, ry)), w='w3', layer='md')
    cells = [(f['date'], X0, X0 + 168, 2.2), ('REV %s' % CLOUDED, X0 + 168, X0 + 266, 2.2),
             ('01 / 02', X0 + 266, X1, 2.8)]
    S.path(''.join(M((xa, ry), (xa, B)) for _, xa, _, _ in cells[1:]), w='w1', layer='md')
    base = (ry + B) / 2.0 + 11
    for i, (val, xa, xb, pen) in enumerate(cells):
        S.text(val, xa + 10, base, 22, cond=fit(val, 22, xb - xa - 20, .76), pen=pen, layer='md', t=.8 + i * .1, dur=.3)

    # ---- DETAIL B at the mid scale: sent, read back, ticked
    bx0, by0, bx1, by1 = 324, 48, 684, 194
    S.path(rect_d(bx0, by0, bx1 - bx0, by1 - by0), w='w2', layer='md', t=2.5, dur=.35)
    S.path(circle_d(bx0 + 30, by0 + 30, 20), w='w1', layer='md', t=2.55, dur=.25)
    S.text('B', bx0 + 30, by0 + 41, 22, anchor='middle', cond=.76, pen=2.4, layer='md', t=2.65, dur=.1)
    head = 'DETAIL B · READ BACK'
    S.text(head, bx0 + 62, by0 + 40, 22, cond=fit(head, 22, bx1 - bx0 - 74, .76), pen=2.4, layer='md', t=2.6, dur=.35)
    sent = ['25', '0A', '4F', '31', '32']
    cx0, cwid = bx0 + 96, 42
    end = cx0 + len(sent) * cwid
    rows = (('SENT', by0 + 70), ('READ', by0 + 116))
    for ri, (lab, yy) in enumerate(rows):
        t0 = 2.75 + ri * .2
        S.text(lab, bx0 + 14, yy + 11, 22, cond=fit(lab, 22, cx0 - bx0 - 26, .76), layer='md', t=t0, dur=.15)
        S.path(''.join(rect_d(cx0 + k * cwid, yy - 16, cwid, 32) for k in range(len(sent)))
               + M((end, yy - 16), (end + 8, yy - 16)) + M((end, yy + 16), (end + 8, yy + 16))
               + M((end + 8, yy - 20), (end + 8, yy - 5), (end + 14, yy - 1), (end + 2, yy + 3), (end + 8, yy + 7),
                   (end + 8, yy + 20)), w='w1', layer='md', t=t0, dur=.25)
        S.row([(byte, cx0 + k * cwid + cwid / 2) for k, byte in enumerate(sent)], yy + 11, 22, cond=.72, layer='md',
              t=t0 + .05, dur=.15)
    S.path(''.join(M((cx0 + k * cwid + cwid / 2, rows[0][1] + 20), (cx0 + k * cwid + cwid / 2, rows[1][1] - 20))
                   for k in range(len(sent))), w='w2', layer='md', t=3.15, dur=.15, color=mark)
    S.text('✓', end + 26, rows[1][1] + 11, 22, cond=.8, pen=3, color=mark, layer='md', t=3.2, dur=.1)
    cloud_d, cloud_box = cloud(bx0 - 8, by0 - 5, bx1 + 7, by1 + 6)
    S.path(cloud_d, w='w2', layer='md', t=3.35, dur=.5, color=mark)
    tx, ty = 734, 66
    S.path(M((tx - 22, ty + 20), (tx + 22, ty + 20), (tx, ty - 28), close=True), w='w2', kind='fd', layer='md', t=3.75,
           dur=.15, color=mark)
    S.text(CLOUDED, tx, ty + 15, 22, anchor='middle', cond=.76, pen=2.4, color=mark, layer='md', t=3.8, dur=.12)
    ink = grow(cloud_box, MID_PENS['w2'] / 2)
    keep_clear('mid DETAIL B cloud / drawing frame', ink, (0, 0, W, T + MID_PENS['w4'] / 2), 10)
    keep_clear('mid DETAIL B cloud / ridge', ink, (0, g['RIDGE'], W, H), 10)
    keep_clear('mid DETAIL B cloud / its delta', ink, (tx - 23, ty - 29, tx + 23, ty + 21), 10)
    keep_clear('mid delta / right strip', (tx - 23, ty - 29, tx + 23, ty + 21), (COL - MID_PENS['w4'] / 2, 0, W, H), 10)
    # its reference bubble over the machine's control
    S.path(circle_d(566, 408, 21) + M((g['cxm'], g['cym'] - 24), (563, 429)), w='w1', layer='md', t=2.85, dur=.25)
    S.text('B', 566, 419, 22, anchor='middle', cond=.76, pen=2.4, layer='md', t=3.0, dur=.1)

    # ---- the width dimension, which the mid plot keeps as one line under the section
    line = '%s PER CODING DAY' % f['per_day']
    txt, c = clip(line, 22, COL - 24 - 62, .76)
    S.text(txt, 62, 668, 22, cond=c, layer='md', t=2.5, dur=.6)


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else TOOLS.parent / 'assets'
    out.mkdir(parents=True, exist_ok=True)
    state, commits = load()
    import draw02
    import tags
    written = [('sheet-01-%s.svg' % theme, build(theme, state, commits)) for theme in ('dark', 'light')]
    written += [('sheet-02-%s.svg' % theme, draw02.build(theme, state, commits)) for theme in ('dark', 'light')]
    written += tags.build_all()
    for name, svg in written:
        raw, gz = validate(name, svg, *budget(name))
        (out / name).write_text(svg)
        print('%-28s %6d bytes  %5d gzip' % (name, raw, gz))


if __name__ == '__main__':
    main()
