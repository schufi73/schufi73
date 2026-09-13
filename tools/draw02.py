#!/usr/bin/env python3
"""draw02.py: SHEET 02 of the profile set. Called by draw.py: build(theme, state, commits) -> svg.

View C, the core log: two borings through the same tracked hours, B-1 cut by
language and B-2 cut by editor, on one linear scale with an hour ruler between
them. Every stratum carries an item balloon (ISO 6433); a run of strata too thin
for leaders of their own shares one bracket and one leader. The strata table in the
right strip lists them in the order the drill meets them, with their hatch as the
key; the two borings use two hatch families, so no hatch means two things, except
the remainder of either boring, which is one key on purpose: "the rest".

View D, the commit load: the share of commits in each hour of the day over twelve
months, from tools/commits.json, drawn as a load on a beam. Linear scale in per
cent (no absolute counts), busiest hour called out.

The right strip carries the totals and the same title block rows as SHEET 01, with the
same date: the later of the WakaTime change and the commit count (draw.sheet_date).
Like SHEET 01 it is plotted three times (see sheet.py): detail, mid and phone.
"""
import math

from draw import REVISIONS, hm, month, pct, sheet_date, thousands
from lettering import fmt, measure, plain
from sheet import M, Motion, Sheet, circle_d, clip, fit, paper, rect_d

W, H = 1200, 720

L, R, T, B = 40, 1176, 22, 698
COL = 770                       # the right strip starts where it does on SHEET 01
X0, X1 = 116, 728               # core collar and bottom of hole: 0 h and the all-time total
C = .76                         # one condensation for all lettering, so the glyphs are defined once

ALIASES = {'protobuf': 'Protocol Buffer'}   # WakaTime lists the same language under two names
SHORT = {'Protocol Buffer': 'PROTOBUF'}
BUCKETS = {'Other', 'Unknown Editor'}       # unclassified time: part of the remainder, never a stratum


class Motion10(Motion):
    """Timings on a 0.1 s grid: fewer timing classes, and nobody sees the difference."""

    def cls(self, kind, t, dur):
        return Motion.cls(self, kind, round(t * 10) / 10.0, max(.1, round(dur * 10) / 10.0))


# ---------------------------------------------------------------------- data
def strata(rows, total, keep, count, noun):
    """[(label, seconds, WakaTime name)]: the `keep` largest named entries, then one remainder that closes
    the hole (its name is None). Unclassified buckets are counted in the remainder's hours, not its entries;
    when they are at least 1 % of the hours the remainder says so."""
    merged, entries = {}, {}
    for name, sec in rows:
        key = ALIASES.get(name, name)
        merged[key] = merged.get(key, 0) + sec
        entries[key] = entries.get(key, 0) + 1
    named = sorted((k for k in merged if k not in BUCKETS), key=lambda k: (-merged[k], k))[:keep]
    out = [(plain(SHORT.get(k, k.upper())), merged[k], k) for k in named]
    rest = total - sum(row[1] for row in out)
    buckets = sum(entries[k] for k in merged if k in BUCKETS)
    unsorted = sum(merged[k] for k in merged if k in BUCKETS)
    more = count - sum(entries[k] for k in named) - buckets
    if rest > 0:
        if more > 0:
            word = noun if more != 1 else noun[:-1]       # 1 MORE EDITOR, 3 MORE EDITORS
            label = '%d MORE + UNSORTED' % more if unsorted >= .01 * total else '%d MORE %s' % (more, word)
        else:
            label = 'UNSORTED' if buckets else 'THE REST'
        out.append((label, rest, None))
    return out


def hours1(sec):
    return '{:,.1f}'.format(sec / 3600.0)


def shares_of(commits):
    """Per-hour shares in per cent, and the busiest hour."""
    permille = commits['per_hour_permille']
    total = float(sum(permille)) or 1.0
    shares = [100.0 * v / total for v in permille]
    peak = commits.get('busiest_hour')
    if peak is None:
        peak = max(range(24), key=lambda h: (permille[h], -h))
    return shares, peak


# ---------------------------------------------------------------------- materials
PATTERNS = [  # (w, h, path, stroke width, transform, opacity)
    # B-1, by language
    (18, 10, 'M0 .5H18M0 5.5H18M4 .5V5.5M13 5.5V10.5', .8, '', .75),                  # 0 brick bond
    (10, 10, 'M2 3h.01M7 1.5h.01M4.5 7.5h.01M9 8.5h.01', 1.7, '', .75),                 # 1 stipple
    (6, 6, 'M0 0V6', .8, 'rotate(45)', .75),                                            # 2 hatch 45
    (7, 7, 'M0 0V7M0 0H7', .7, 'rotate(45)', .75),                                      # 3 cross hatch
    (6, 4, 'M0 .5H6', .8, '', .75),                                                     # 4 courses
    (6, 6, 'M0 0V6', .8, 'rotate(-45)', .75),                                           # 5 hatch 135
    (10, 10, 'M1 3a2 2 0 1 0 4 0a2 2 0 1 0-4 0M6 8a1.6 1.6 0 1 0 3.2 0a1.6 1.6 0 1 0-3.2 0', .7, '', .75),  # 6 gravel
    (4, 6, 'M.5 0V6', .8, '', .75),                                                     # 7 vertical
    # the remainder of either boring: one key for "the rest"
    (12, 8, 'M1.5 2h4M7.5 6h4', .9, '', .75),                                           # 8 dashes
    # B-2, by editor: a family of its own, four textures nobody confuses at key size
    (12, 8, 'M0 4L3 1L9 7L12 4', .8, '', .75),                                          # 9 zigzag (batts)
    (6, 6, 'M0 .5H6M.5 0V6', .6, '', .75),                                              # 10 square grid
    (10, 10, 'M5 2.5v5M2.5 5h5', .8, '', .75),                                          # 11 plus signs
    (4, 4, 'M0 1H4M0 3H4', 2.2, '', .3),                                                # 12 tone
    # view D
    (5, 5, 'M0 0V5', .7, 'rotate(60)', .75),                                            # 13 the load
]
FAMILIES = {'B-1': (0, 8, 8), 'B-2': (9, 4, 8)}   # first pattern, how many for named strata, the remainder's
LOAD = 13


def patterns(S):
    for i, (w, h, d, sw, tr, op) in enumerate(PATTERNS):
        S.defs.append('<pattern id="_p%d" width="%s" height="%s" patternUnits="userSpaceOnUse"%s>'
                      '<path d="%s" stroke-width="%s" stroke-opacity="%s"/></pattern>'
                      % (i, w, h, ' patternTransform="%s"' % tr if tr else '', d, fmt(sw, 2), fmt(op, 2)))


# ---------------------------------------------------------------------- views
def view_title(S, vx, vy, letter, title, subs, t0):
    """The view title: bubble, title and its rules serve the detail and the mid plot; the sheet number and the
    subtitles are detail only, and the mid plot letters the bubble at its own size."""
    S.path(circle_d(vx, vy - 2, 22), w='w2', t=t0, dur=.3, layer='dm')
    S.path('M%s %sh44' % (fmt(vx - 22), fmt(vy - 2)), w='w2', t=t0 + .1, dur=.2, layer='dt')
    S.text(letter, vx, vy - 8, 13, anchor='middle', cond=C, t=t0 + .1, dur=.1, pen=1.6)
    S.text('02', vx, vy + 15, 12, anchor='middle', cond=C, t=t0 + .2, dur=.1, pen=1.4)
    S.text(letter, vx, vy + 9, 22, anchor='middle', cond=C, t=t0 + .1, dur=.1, pen=2.4, layer='md')
    tw = S.text(title, vx + 36, vy - 7, 22, cond=C, t=t0 + .1, dur=.4, pen=2.4, layer='dm')
    sw = max([tw] + [measure(s, 13, cond=C) for s in subs])
    for width, layer in ((sw, 'dt'), (tw, 'md')):     # the mid plot has no subtitles to underline
        S.path(M((vx + 34, vy + 1), (vx + 38 + width, vy + 1)), w='w3', t=t0 + .3, dur=.3, layer=layer)
        S.path(M((vx + 34, vy + 6), (vx + 38 + width, vy + 6)), w='w1', t=t0 + .4, dur=.3, layer=layer)
    for k, s in enumerate(subs):
        S.text(s, vx + 36, vy + 26 + k * 18, 13, cond=C, t=t0 + .5 + k * .2, dur=.4)
    return vx + 38 + sw


def core(S, rows, total, y0, hgt, label, t0, item0):
    """One boring, drilled left to right. Returns the strata with their positions."""
    first, n_named, rest = FAMILIES[label]
    # strata that add up to more than the total (a response wakatime.py refuses) still end at the bottom of the hole
    k = (X1 - X0) / float(max(total, sum(row[1] for row in rows)))
    y1, yc = y0 + hgt, y0 + hgt / 2.0
    segs, x = [], X0
    for i, (name, sec, orig) in enumerate(rows):
        w = sec * k
        segs.append(dict(name=name, orig=orig or name, rest=orig is None, sec=sec, pc=pct(sec, total), x=x, w=w,
                         item=item0 + i, pat=rest if orig is None else first + i % n_named))
        x += w
    ry = hgt / 2.0
    # the cut: core walls first, heavy, then the collar and the bottom of the hole
    S.path(M((X0, y0), (X1, y0)) + M((X0, y1), (X1, y1)), w='w3', t=t0, dur=.5)
    S.path('M%s %sa7 %s 0 1 0 0 %sa7 %s 0 1 0 0 %s' % (fmt(X0), fmt(y0), fmt(ry), fmt(hgt), fmt(ry), fmt(-hgt)),
           w='w2', t=t0, dur=.2)
    S.path('M%s %sa7 %s 0 0 1 0 %s' % (fmt(X1), fmt(y0), fmt(ry), fmt(hgt)), w='w3', t=t0 + .5, dur=.1)
    # strata, drilled in the order the hole meets them
    drill = 1.0
    at = lambda xx: t0 + .1 + drill * (xx - X0) / (X1 - X0)
    for s in segs:
        S.fill(rect_d(s['x'], y0, s['w'], hgt), 'url(#_p%d)' % s['pat'], t=at(s['x']), dur=drill * s['w'] / (X1 - X0))
    S.path(''.join(M((s['x'], y0), (s['x'], y1)) for s in segs[1:]), w='w1', t=t0 + .6, dur=.5)
    S.text(label, X0 - 14, yc + 7, 14, anchor='end', cond=C, t=t0, dur=.1, pen=1.6)
    S.text(label, X0 - 20, yc + 11, 22, anchor='end', cond=C, t=t0, dur=.1, pen=2.4, layer='md')
    # strata wide enough get their name lettered in, at the detail and at the mid size; every stratum gets a
    # balloon on the detail plot
    for cap, pad, layer in ((13, 16, 'dt'), (22, 24, 'md')):
        for s in segs:
            for txt in ('%s %.1f %%' % (s['name'], s['pc']), s['name']):
                if measure(txt, cap, cond=C) + pad <= s['w']:
                    S.text(txt, s['x'] + s['w'] / 2, yc + cap / 2.0, cap, anchor='middle', cond=C, knock=True,
                           t=at(s['x'] + s['w']), dur=.3, layer=layer, pen=None if layer == 'dt' else 2.4)
                    break
    return segs


def balloons(S, segs, edge, by, t0, r=12, gap=10):
    """Item balloons in one row, after ISO 6433. A stratum wide enough for a leader of its own gets a dot, a
    leader and a balloon. A run of two or more thinner strata gets a bracket over the run, one leader and a row
    of touching balloons in drilling order. Blocks keep the strata's order, so no two leaders can cross."""
    sgn = -1 if by < edge else 1
    lo, hi = X0, COL - 18
    blocks, i = [], 0
    while i < len(segs):
        j = i
        while j < len(segs) and segs[j]['w'] < 2 * r + 4:
            j += 1
        members = segs[i:j] if j - i >= 2 else segs[i:i + 1]
        i += len(members)
        a, b = members[0]['x'], members[-1]['x'] + members[-1]['w']
        blocks.append(dict(m=members, a=a, b=b, w=2.0 * r * len(members)))
    prev = lo - gap
    for bl in blocks:                       # centred on their strata, pushed apart left to right
        bl['l'] = max((bl['a'] + bl['b'] - bl['w']) / 2.0, prev + gap)
        prev = bl['l'] + bl['w']
    nxt = hi + gap
    for bl in reversed(blocks):             # then pulled back inside the view
        bl['l'] = min(bl['l'], nxt - gap - bl['w'])
        nxt = bl['l']
    yd, ys = edge - 6 * sgn, edge + 9 * sgn     # a dot inside the core, a stub or bracket clear of its wall
    dots = leaders = rings = ''
    labels = []
    for bl in blocks:
        cxs = [bl['l'] + r + 2 * r * n for n in range(len(bl['m']))]
        rings += ''.join(circle_d(c, by, r) for c in cxs)
        labels += [(str(s['item']), c) for s, c in zip(bl['m'], cxs)]
        x = (bl['a'] + bl['b']) / 2.0
        end = min(cxs, key=lambda c: abs(c - x))
        dx, dy = x - end, ys - by
        d = math.hypot(dx, dy) or 1
        rim = (end + dx / d * r, by + dy / d * r)
        if len(bl['m']) == 1:
            dots += 'M%s %sh.01' % (fmt(x), fmt(yd))
            leaders += M((x, yd), (x, ys), rim)
        else:
            ya = edge + 3 * sgn
            leaders += M((bl['a'] + 1, ya), (bl['a'] + 1, ys), (bl['b'] - 1, ys), (bl['b'] - 1, ya)) + M((x, ys), rim)
    S.path(leaders, w='w1', t=t0, dur=.4, layer='dt')
    if dots:
        S.path(dots, w=None, kind='fd', t=t0, dur=.2, layer='dt', extra=' stroke-width="3.4"')
    S.path(rings, w='w1', t=t0 + .2, dur=.3, layer='dt')
    S.row(labels, by + 6, 12, cond=C, t=t0 + .4, dur=.2, pen=1.3)


# ---------------------------------------------------------------------- the sheet
def build(theme, state, commits):
    n = state['numbers']
    total = n['total_seconds']
    S = Sheet(theme, W, H, end=4.0)
    S.motion = Motion10(4.0)
    p = S.p
    mark = p['mark']
    paper(S)
    patterns(S)

    langs = strata(n['languages'], total, 8, n['language_count'], 'LANGUAGES')
    eds = strata(n['editors'], total, 4, len(n['editors']), 'EDITORS')
    shares, peak = shares_of(commits)
    as_of = month(commits['as_of'])
    date = sheet_date(state, commits)
    total_h = thousands(total / 3600.0)
    ai_pc = pct(n['ai_coding_seconds'], total)
    per_day = hm(n['daily_average_seconds'])
    oss = n['operating_systems']
    os_total = sum(s for _, s in oss) or 1
    os_txt = ' · '.join('%s %.0f %%' % (plain(name.upper()), pct(s, os_total)) for name, s in oss[:2]) or '—'

    # ============================================================ pre-printed sheet form
    S.path(rect_d(10, 10, W - 20, H - 20), w='w1', op=.5)
    S.path(rect_d(L, T, R - L, B - T), w='w4')
    zx, zy = (R - L) / 6.0, (B - T) / 4.0
    ticks = ''.join('M%s 10V%sM%s %sV%s' % (fmt(L + i * zx), T, fmt(L + i * zx), B, H - 10) for i in range(1, 6))
    ticks += ''.join('M10 %sH%sM%s %sH%s' % (fmt(T + i * zy), L, R, fmt(T + i * zy), W - 10) for i in range(1, 4))
    S.path(ticks, w='w1', layer='dt', op=.7)
    S.path(M((COL, T), (COL, B)), w='w4', layer='dm')

    # ---- strata table frame: header pre-printed, rows ruled as they are plotted
    RH = 21
    head = T + 32
    body = head + 20
    cols = [COL, COL + 40, COL + 82, 1054, 1122, R]
    table = [('B-1 · BY LANGUAGE', None)] + [(None, s) for s in range(len(langs))] + \
            [('B-2 · BY EDITOR', None)] + [(None, s) for s in range(len(eds))]
    tbot = body + RH * len(table)
    S.path(M((COL, head), (R, head)) + M((COL, body), (R, body)), w='w2', layer='dt')
    S.path(''.join(M((c, head), (c, body)) for c in cols[1:-1]), w='w1', layer='dt', op=.85)

    # ---- totals and title block grid: 4 units above each field name, cap 12, the value, 6-7 below
    tb = tbot
    rows_y = [tb, tb + 66, tb + 108, tb + 150, 606, 652, B]
    cw = R - COL
    S.path(M((COL, tb), (R, tb)), w='w3', layer='dt')
    S.path(''.join(M((COL, y), (R, y)) for y in rows_y[1:3] + rows_y[5:6]), w='w1', layer='dt')
    S.path(M((COL, rows_y[3]), (R, rows_y[3])), w='w3', layer='dt')
    S.path(M((COL, rows_y[4]), (R, rows_y[4])), w='w3', layer='dm')
    totals = [
        [('TOTAL DEPTH', '%s h' % total_h, .56), ('LOGGED SINCE', n['since'] or '—', .44)],
        [('AI CODING, ALL TOOLS', '%s h · %.1f %%' % (thousands(n['ai_coding_seconds'] / 3600.0), ai_pc), .5),
         ('PER CODING DAY', per_day, .5)],
        [('OPERATING SYSTEM', os_txt, 1.0)],
    ]
    block = [
        [('DRAWN', 'N. SCHAUFELBERGER', .42), ('SOURCE', 'WAKATIME · GIT', .31), ('SCALE', 'LINEAR', .27)],
        [('DATE', date, .29), ('LOCATION', 'LOCARNO CH', .27), ('REV', REVISIONS[0][0], .12),
         ('SHEET', '02 / 02', .32)],
    ]
    cells = []
    for grid_rows, ys in ((totals, rows_y[0:4]), (block, rows_y[4:7])):
        for ri, row in enumerate(grid_rows):
            y0, y1 = ys[ri], ys[ri + 1]
            x, v = COL, ''
            for i, (lab, val, frac) in enumerate(row):
                if i:
                    v += M((x, y0), (x, y1))
                cells.append((lab, val, x, y0, y1, cw * frac))
                x += cw * frac
            if v:
                S.path(v, w='w1', layer='dt')

    # ============================================================ the plot
    # ---- the sheet's identity first: the total depth and the name in the title block
    for lab, val, x, y0, y1, room in cells:
        S.text(lab, x + 7, y0 + 17, 12, op=.85, cond=fit(lab, 12, room - 14, C))
    lab, val, x, y0, y1, room = cells[0]
    S.text(val, x + 10, y1 - 8, 34, face='rowmand', cond=fit(val, 34, room - 20, C, 'rowmand'), pen=4, t=0, dur=.5)
    name = 'NOAH SCHAUFELBERGER'
    S.text(name, COL + 12, rows_y[4] - 12, 26, face='rowmand', cond=fit(name, 26, cw - 24, C, 'rowmand'), pen=3,
           t=.1, dur=.6, layer='dm')
    for i, (lab, val, x, y0, y1, room) in enumerate(cells[1:]):
        big = lab in ('SHEET', 'LOGGED SINCE')
        cap = 15 if big else 13
        tall = y1 - y0 >= 46
        txt, c = clip(val, cap, room - 14, C) if lab == 'OPERATING SYSTEM' else (val, fit(val, cap, room - 14, C))
        S.text(txt, x + 7, y1 - (7 if tall else 6), cap, cond=c, pen=1.9 if big else 1.4, t=1.7 + i * .08, dur=.3)

    # ---- view C: the core log
    view_title(S, 84, 66, 'C', 'CORE LOG', ('TWO BORINGS THROUGH THE SAME HOURS,', 'ONE LINEAR SCALE, DEPTH IN HOURS'),
               .1)
    Y1, Y2, HG = 180, 302, 40
    seg1 = core(S, langs, total, Y1, HG, 'B-1', .2, 1)
    seg2 = core(S, eds, total, Y2, HG, 'B-2', .4, len(langs) + 1)
    balloons(S, seg1, Y1, 148, 1.4)
    balloons(S, seg2, Y2 + HG, 374, 1.7)

    # hour ruler between the cores: a label every 250 h while labels stay 64 units apart (130 on the mid plot),
    # then every 500, 1,000 ...
    RY = 262
    top_h = int(total / 3600.0)
    k = (X1 - X0) / max(total / 3600.0, 1e-9)
    steps = (250, 500, 1000, 2500, 5000, 10000, 25000, 50000, 100000)
    step = next(s for s in steps if s * k >= 64 or s == 100000)
    tk = ''.join(M((X0 + h * k, RY), (X0 + h * k, RY - (10 if h % step == 0 else 4)))
                 for h in range(0, top_h + 1, step // 5))
    S.path(M((X0, RY), (X1, RY)) + M((X1, RY - 8), (X1, RY + 8)), w='w2', t=1.0, dur=.5, layer='dm')
    if tk:
        S.path(tk, w='w1', kind='wp', t=1.0, dur=.5, layer='dm')
    for s_, cap, dy, gap_end, layer in ((step, 12, 19, 26, 'dt'),
                                        (next(s for s in steps if s * k >= 130 or s == 100000), 22, 30, 38, 'md')):
        S.row([('{:,}'.format(h), X0 + h * k) for h in range(0, top_h + 1, s_) if not h or X1 - (X0 + h * k) >= gap_end],
              RY + dy, cap, cond=C, t=1.1, dur=.4, layer=layer, pen=None if layer == 'dt' else 2.2)
    S.text('HOURS', X0 - 14, RY + 5, 12, anchor='end', cond=C, t=1.0, dur=.1, op=.85)
    S.text('%s h' % total_h, X1 - 2, RY - 17, 13, anchor='end', cond=C, t=1.5, dur=.2, pen=1.6)

    # ---- the strata table, row by row with its rules, cells and swatch
    S.text('STRATA', COL + 12, T + 22, 14, cond=C, pen=1.6)
    S.text('DRILLING ORDER', R - 12, T + 22, 12, anchor='end', cond=C, op=.8)
    S.row([(lab, {'middle': (x0 + x1) / 2.0, 'start': x0 + 8, 'end': x1 - 8}[anchor], anchor)
           for lab, x0, x1, anchor in (('ITEM', cols[0], cols[1], 'middle'), ('KEY', cols[1], cols[2], 'middle'),
                                       ('DESCRIPTION', cols[2], cols[3], 'start'), ('HOURS', cols[3], cols[4], 'end'),
                                       ('%', cols[4], cols[5], 'end'))], head + 16, 12, cond=C, op=.85)
    it = iter(seg1 + seg2)
    for i, (sub, _) in enumerate(table):
        y0 = body + i * RH
        t0 = .5 + i * .08
        rule = M((COL, y0 + RH), (R, y0 + RH)) if i < len(table) - 1 else ''
        if sub:
            S.path(rule, w='w1', t=t0, dur=.2, layer='dt', op=.85)
            S.text(sub, COL + 12, y0 + 16.5, 12, cond=C, t=t0, dur=.3, pen=1.5, op=.9)
            continue
        s = next(it)
        yb = y0 + 17
        sw = rect_d(cols[1] + 7, y0 + 5, cols[2] - cols[1] - 14, RH - 10)
        S.path(rule + ''.join(M((c, y0), (c, y0 + RH)) for c in cols[1:-1]), w='w1', t=t0, dur=.2, layer='dt', op=.85)
        S.fill(sw, 'url(#_p%d)' % s['pat'], t=t0 + .05, dur=.2, kind='wp', layer='dt')
        S.path(sw, w='w1', t=t0 + .05, dur=.2, kind='fd', layer='dt')
        nm, nc = clip(s['name'], 13, cols[3] - cols[2] - 14, C)
        hrs = hours1(s['sec'])
        if measure(hrs, 13, cond=.6) > cols[4] - cols[3] - 12:
            hrs = thousands(s['sec'] / 3600.0)      # a total too large for its decimal loses it, never the column
        rc = min(nc, fit(hrs, 13, cols[4] - cols[3] - 12, C))
        S.row([(str(s['item']), (cols[0] + cols[1]) / 2.0, 'middle'), (nm, cols[2] + 8, 'start'),
               (hrs, cols[4] - 8, 'end'), ('%.1f' % s['pc'], cols[5] - 8, 'end')], yb, 13, cond=rc, t=t0, dur=.3)

    # ---- view D: the commit load, in per cent of the year's commits
    title_end = view_title(S, 84, 440, 'D', 'COMMIT LOAD', ('SHARE OF COMMITS PER HOUR OF THE DAY,',
                                                            '12 MONTHS TO %s' % as_of), 1.9)
    BASE, QH = 636, 136             # the tallest bar stays 15 units below the view title
    step = (X1 - X0) / 24.0
    qmax = max(shares) or 1.0
    q = QH / qmax
    grid = next(g for g in (1, 2, 5, 10, 20, 25, 50) if qmax / g <= 5)
    marks = [v for v in range(grid, int(qmax) + 1, grid)]
    SX = X0 - 30
    grid_top = marks[-1] if marks else 0
    S.path(M((SX, BASE), (SX, BASE - max(grid_top * q, 20) - 6)) + ''.join(M((SX - 5, BASE - v * q), (SX, BASE - v * q))
                                                                           for v in marks), w='w1', t=2.2, dur=.3,
           layer='dt')
    if marks:
        S.path(''.join(M((SX + 6, BASE - v * q), (X1, BASE - v * q)) for v in marks), w='w1', t=2.3, dur=.5, kind='wp',
               layer='dt', op=.4, extra=' stroke-dasharray="2 5"')
    for v in marks:
        S.text(str(v), SX - 8, BASE - v * q + 6, 12, anchor='end', cond=C, t=2.3, dur=.2, op=.85)
    S.text('%', SX, BASE - max(grid_top * q, 20) - 14, 12, anchor='middle', cond=C, t=2.3, dur=.1, op=.85)
    # the beam, a pin and a roller
    S.path(M((X0 - 20, BASE), (X1 + 20, BASE)), w='w3', t=2.1, dur=.4)
    px, rx = X0 - 14, X1 + 12
    sup = M((px, BASE), (px - 8, BASE + 13), (px + 8, BASE + 13), close=True)
    sup += M((rx, BASE), (rx - 8, BASE + 10), (rx + 8, BASE + 10), close=True) + circle_d(rx - 4, BASE + 13, 3) + \
        circle_d(rx + 4, BASE + 13, 3)
    sup += M((px - 12, BASE + 13), (px + 12, BASE + 13)) + M((rx - 12, BASE + 16), (rx + 12, BASE + 16))
    sup += ''.join(M((x + 5, BASE + 13), (x, BASE + 19)) for x in (px - 12, px - 6, px, px + 6))
    sup += ''.join(M((x + 5, BASE + 16), (x, BASE + 22)) for x in (rx - 12, rx - 6, rx, rx + 6))
    S.path(sup, w='w1', t=2.3, dur=.3)
    # the load, hour by hour, plotted left to right
    bars, fills, peak_d = '', '', ''
    for h, c in enumerate(shares):
        if not c:
            continue
        x, bw, bh = X0 + h * step + 3, step - 6, max(1.0, c * q)
        fills += rect_d(x, BASE - bh, bw, bh)
        d = 'M%s %sV%sH%sV%s' % (fmt(x), BASE, fmt(BASE - bh), fmt(x + bw), BASE)
        if h == peak:
            peak_d = d
        else:
            bars += d
    if fills:
        S.fill(fills, 'url(#_p%d)' % LOAD, t=2.5, dur=.9)
    if bars:
        S.path(bars, w='w2', t=2.4, dur=.9, kind='wp')
    if peak_d:
        S.path(peak_d, w='w2', t=2.4 + .9 * peak / 24.0, dur=.2, color=mark)
    S.row([('%02d' % h, X0 + (h + .5) * step) for h in range(0, 24, 3)], BASE + 24, 12, cond=C, t=2.5, dur=.3)
    # the mid plot keeps three hour marks, clear of the pin and the roller
    S.row([('%02d' % h, X0 + (h + .5) * step) for h in (6, 12, 18)], BASE + 32, 22, cond=C, t=2.5, dur=.3,
          layer='md', pen=2.2)
    S.text("AUTHOR'S LOCAL TIME", X0, B - 14, 12, cond=C, t=3.0, dur=.4, op=.85)
    # the busiest hour: the callout opens to the left of its bar unless that would run into the view title
    none = not any(shares)
    cx, top = X0 + (peak + .5) * step, BASE - shares[peak] * q
    lab = '%02d:00' % peak if not none else '--:--'
    if none:
        S.text('NO COMMITS IN THESE 12 MONTHS', X0 + 12, BASE - 40, 13, cond=C, t=3.3, dur=.4)
        S.text('NO COMMITS', X0 + 12, BASE - 40, 22, cond=C, t=3.3, dur=.4, layer='md')
    for cap_l, cap_s, drop, layer in ((20, 12, 30, 'dt'), (30, 22, 34, 'md')):
        if none:
            break
        sw_ = max(measure(lab, cap_l, cond=C), measure('BUSIEST HOUR', cap_s, cond=C))
        pen_l, pen_s = (2.3, None) if layer == 'dt' else (3.2, 2.2)
        shelf_y = top - drop
        if cx - 36 - sw_ - 6 >= title_end + 12:
            shelf_x = cx - 36
            S.path(M((cx - 2, top - 3), (shelf_x, shelf_y), (shelf_x - sw_ - 6, shelf_y)), w='w1', t=3.3, dur=.3,
                   layer=layer)
            S.text(lab, shelf_x - 4, shelf_y - 6 - (cap_l - 20) / 5.0, cap_l, anchor='end', cond=C, t=3.4, dur=.3,
                   pen=pen_l, layer=layer)
            S.text('BUSIEST HOUR', shelf_x - 4, shelf_y + 5 + cap_s, cap_s, anchor='end', cond=C, t=3.4, dur=.3,
                   pen=pen_s, layer=layer)
        else:                               # under the title: a shelf just above the tallest bar, lettering on it
            shelf_y = BASE - QH - 8
            wl, ws = measure(lab, cap_l, cond=C), measure('BUSIEST HOUR', cap_s, cond=C)
            shelf_x = min(max(cx + 20, title_end + 12), X1 + 30 - wl - ws - 18)
            S.path(M((cx, top - 3), (cx, shelf_y), (shelf_x + wl + ws + 18, shelf_y)), w='w1', t=3.3, dur=.3,
                   layer=layer)
            S.text(lab, shelf_x + 4, shelf_y - 6, cap_l, cond=C, t=3.4, dur=.3, pen=pen_l, layer=layer)
            S.text('BUSIEST HOUR', shelf_x + wl + 14, shelf_y - 6, cap_s, cond=C, t=3.4, dur=.3, pen=pen_s,
                   layer=layer)

    # ============================================================ mid layer: key, totals, short title block
    ky = 58
    for group, segs in (('B-1 · BY LANGUAGE', seg1), ('B-2 · BY EDITOR', seg2)):
        S.text(group, COL + 12, ky, 22, cond=fit(group, 22, cw - 24, C), pen=2.6, layer='md', t=.5, dur=.3)
        ky += 34
        for s in [s for s in segs if not s['rest']][:3]:
            sw = rect_d(COL + 12, ky - 19, 38, 22)
            S.fill(sw, 'url(#_p%d)' % s['pat'], t=.7, dur=.2, kind='fd', layer='md')
            S.path(sw, w='w1', t=.7, dur=.2, kind='fd', layer='md')
            pc_txt = '%.1f %%' % s['pc']
            wp = measure(pc_txt, 22, cond=C)
            nm, nc = clip(s['name'], 22, R - 12 - wp - 16 - (COL + 62), C)
            S.row([(nm, COL + 62, 'start'), (pc_txt, R - 12, 'end')], ky, 22, cond=nc, t=.8, dur=.3, layer='md',
                  pen=2.2)
            ky += 32
        ky += 12
    S.path(M((COL, 322), (R, 322)), w='w2', layer='md')
    S.text('%s h' % total_h, COL + 12, 376, 40, face='rowmand', cond=fit('%s h' % total_h, 40, cw - 24, C, 'rowmand'),
           pen=4.2, layer='md', t=0, dur=.5)
    for i, line in enumerate(('LOGGED SINCE %s' % (n['since'] or '—'), 'AI CODING, ALL TOOLS %.1f %%' % ai_pc,
                              '%s PER CODING DAY' % per_day, os_txt)):
        txt, c = clip(line, 22, cw - 24, C)
        S.text(txt, COL + 12, 416 + 38 * i, 22, cond=c, layer='md', t=1.7 + i * .1, dur=.3, pen=2.2)
    mcells = [(date, COL, COL + 168, 2.2), ('REV %s' % REVISIONS[0][0], COL + 168, COL + 266, 2.2),
              ('02 / 02', COL + 266, R, 2.8)]
    S.path(''.join(M((xa, rows_y[4]), (xa, B)) for _, xa, _, _ in mcells[1:]), w='w1', layer='md')
    S.row([(val, xa + 10, 'start') for val, xa, _, _ in mcells[:2]], (rows_y[4] + B) / 2.0 + 11, 22,
          cond=min(fit(val, 22, xb - xa - 20, C) for val, xa, xb, _ in mcells[:2]), layer='md', t=.8, dur=.3, pen=2.2)
    S.text(mcells[2][0], mcells[2][1] + 10, (rows_y[4] + B) / 2.0 + 11, 22, cond=C, pen=2.8, layer='md', t=1.0, dur=.2)

    # ============================================================ phone layer: coarser plot, heavier pens
    S.text('CORE LOG', 64, 90, 52, face='rowmand', cond=C, pen=5.4, layer='mb', t=0, dur=.6)
    for s, y, t0 in ((seg1[0], Y1 - 12, .9), (seg2[0], Y2 - 12, 1.2)):   # both labels above their cores
        txt, c = clip('%s %.0f %%' % (s['name'].split()[0], s['pc']), 44, X1 - X0, C)
        S.text(txt, X0, y, 44, cond=c, pen=4.4, layer='mb', t=t0, dur=.4)
    commits_w = S.text('COMMITS / HOUR', X0, 488, 44, cond=C, pen=4.4, layer='mb', t=2.2, dur=.5)
    S.row([('%02d' % h, X0 + (h + .5) * step) for h in (6, 12, 18)], 690, 44, cond=C, t=2.6, dur=.4, layer='mb',
          pen=4.4)
    RX, RW = 756, 1164 - 756
    # a phone reader has just seen the hours on SHEET 01: this sheet opens with the share of them that was AI
    ai_big = '%.0f %%' % ai_pc
    S.text(ai_big, RX, 140, 100, face='rowmand', cond=fit(ai_big, 100, RW, C, 'rowmand'), pen=9, layer='mb', t=.3,
           dur=.6)
    for kk, s in enumerate(('AI CODING', 'OF %s %s' % (total_h, 'HOUR' if total_h == '1' else 'HOURS'))):
        S.text(s, RX + 4, 220 + 62 * kk, 44, cond=fit(s, 44, RW - 4, C), pen=4.4, layer='mb', t=.8 + .2 * kk, dur=.4)
    S.path(M((RX, 308), (1160, 308)), w='w2', layer='mb', t=1.3, dur=.3)
    S.text(lab, RX, 424, 100, face='rowmand', cond=fit(lab, 100, RW, C, 'rowmand'), pen=9, layer='mb', t=3.0, dur=.5)
    for kk, s in enumerate(('BUSIEST HOUR', as_of)):
        S.text(s, RX + 4, 488 + 64 * kk, 44, cond=fit(s, 44, RW - 4, C), pen=4.4, layer='mb', t=3.3 + .2 * kk, dur=.3)
    if not none and cx > X0 + commits_w + 20:      # an early busiest hour would run its leader through that label
        S.path(M((cx + 3, top - 4), (RX - 10, 400)), w='w2', layer='mb', t=3.2, dur=.3)
    S.path(M((RX, 576), (1160, 576)), w='w2', layer='mb', t=3.5, dur=.2)
    S.text('SHEET 02 / 02', RX + 4, 642, 44, cond=fit('SHEET 02 / 02', 44, RW - 8, C), pen=4.4, layer='mb', t=3.5,
           dur=.4)

    title = 'Sheet 02: core log and commit load, Noah Schaufelberger'
    desc = ('A technical drawing in single-stroke lettering. View C, a core log: two borings through the same %s '
            'tracked hours on one linear scale, B-1 cut by language (%s), B-2 by editor (%s), with a strata table. '
            'View D, a commit load diagram: the share of commits in each hour of the day over the 12 months to %s, '
            'busiest at %s. AI coding, all tools, %.1f %%, %s per coding day, %s, logged since %s. Dated %s.'
            % (total_h, ', '.join('%s %.1f %%' % (s['orig'], s['pc']) for s in seg1[:2]),
               ', '.join('%s %.1f %%' % (s['orig'], s['pc']) for s in seg2[:2]),
               as_of.title(), lab, ai_pc, per_day, os_txt.title(), n['since'] or 'unknown',
               date))
    return S.svg(title, desc)
