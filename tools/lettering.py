"""Single-stroke lettering for SVG, after ISO 3098 type B.

The glyphs are the Hershey vector fonts (1967), the lettering pen plotters drew
with; tools/hershey.json holds the two faces used here. Every letter is a pen
stroke, so the SVG needs no font. A glyph is defined once per sheet in <defs>
and placed with <use>, which keeps a sheet full of lettering small.

Units: glyphs are 21 units from cap line to baseline, so a run is scaled by
cap / 21. Pen width follows ISO 3098 (d = h / 10) unless a run asks for more.
"""
import json
import math
import unicodedata
from pathlib import Path

_DATA = json.loads(Path(__file__).with_name('hershey.json').read_text())

# Glyphs the Hershey ASCII set lacks, in the same units: cap line y=-12,
# baseline y=9, x from the left side bearing. Value: (advance, strokes).
# ISO 3098 punctuation for the single-stroke face: Hershey futural sets the full stop a quarter of the
# letter height up, where it reads as a middle dot ('62·6'), and its hyphen is longer than a dash.
# Here the stop and the comma sit on the baseline, and hyphen < en dash < em dash.
FUTURAL = {
    '.': (8, [[(4, 7), (3, 8), (4, 9), (5, 8), (4, 7)]]),
    ',': (8, [[(5, 7), (4, 8), (3, 7), (4, 6), (5, 7), (5, 9), (3, 11)]]),
    '-': (15, [[(3, -2), (12, -2)]]),
}
CUSTOM = {
    '·': (8, [[(4, -3), (3, -2), (4, -1), (5, -2), (4, -3)]]),
    '±': (22, [[(11, -10), (11, 4)], [(4, -3), (18, -3)], [(4, 9), (18, 9)]]),
    '–': (20, [[(3, -2), (17, -2)]]),
    '—': (30, [[(2, -2), (28, -2)]]),
    '×': (20, [[(5, -7), (15, 3)], [(15, -7), (5, 3)]]),
    '→': (24, [[(3, -2), (21, -2)], [(15, -7), (21, -2), (15, 3)]]),
    '↗': (20, [[(4, 8), (16, -8)], [(8, -8), (16, -8), (16, 0)]]),
    '▽': (22, [[(2, -12), (20, -12), (11, 4), (2, -12)]]),
    '°': (11, [[(5, -12), (3, -11), (2, -9), (3, -7), (5, -6), (7, -7), (8, -9), (7, -11), (5, -12)]]),
    '✓': (24, [[(3, 0), (9, 8), (21, -12)]]),
}


def glyph(face, ch):
    if face == 'futural' and ch in FUTURAL:
        return FUTURAL[ch]
    if ch in CUSTOM:
        return CUSTOM[ch]
    g = _DATA[face].get(ch)
    if g is None:
        raise KeyError('no glyph for %r in %s' % (ch, face))
    return g[0], g[1]


def plain(s, face='futural'):
    """s with accents dropped and anything the pen has no glyph for replaced by '?'. For names from data."""
    out = ''
    for ch in unicodedata.normalize('NFKD', s):
        if ch in CUSTOM or ch in _DATA[face]:
            out += ch
        elif not unicodedata.combining(ch):
            out += '?'
    return out


def fmt(v, nd=1):
    """Shortest decimal for v at nd places: 0.5 -> .5, -0.5 -> -.5, 3.0 -> 3."""
    v = round(v, nd)
    if v == int(v):
        return str(int(v))
    s = ('%.*f' % (nd, v)).rstrip('0')
    if s.startswith('0.'):
        s = s[1:]
    elif s.startswith('-0.'):
        s = '-' + s[2:]
    return s


def _join(nums):
    out = ''
    for n in nums:
        if out and not n.startswith('-'):
            out += ' '
        out += n
    return out


def encode(strokes, nd=1):
    """Polylines -> relative path data, on a half-unit grid (a glyph is 21 units tall, so half a unit is
    2.4 % of the letter: invisible). Rounds absolute points first, so errors never add up."""
    parts = []
    cx = cy = None
    q = 10 ** nd
    for st in strokes:
        pts = [(round(x * 2) * q // 2, round(y * 2) * q // 2) for x, y in st]
        x0, y0 = pts[0]
        if cx is None:
            parts.append('M' + _join([fmt(x0 / q, nd), fmt(y0 / q, nd)]))
        else:
            parts.append('m' + _join([fmt((x0 - cx) / q, nd), fmt((y0 - cy) / q, nd)]))
        cx, cy = x0, y0
        nums = []
        for x, y in pts[1:]:
            nums += [fmt((x - cx) / q, nd), fmt((y - cy) / q, nd)]
            cx, cy = x, y
        parts.append('l' + _join(nums or ['0', '0']))
    return ''.join(parts)


COND_STEPS = (.76, .68, .6, .52)


def snap(cond):
    """Condensation, floored to one of COND_STEPS (.8 -> .76, .72 -> .68). Every glyph is defined once per
    face and step, so a sheet with dozens of fitted runs carries only three copies of the alphabet.
    Flooring only ever makes a run narrower, so anything measured to fit still fits."""
    for step in COND_STEPS:
        if cond >= step - 1e-9:
            return step
    return COND_STEPS[-1]


def measure(s, cap, face='futural', cond=.8, track=0):
    """Advance width of s in user units."""
    return sum(glyph(face, ch)[0] + track for ch in s) * cap / 21.0 * snap(cond)


def _ident(n):
    letters = 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'
    s = letters[n % 52]
    n //= 52
    while n:
        s += letters[n % 52]
        n //= 52
    return s


class Pen:
    """Letters runs of text as <use> references to glyphs defined once."""

    def __init__(self):
        self._ids = {}
        self._defs = []

    def _glyph_id(self, face, cond, ch):
        key = (face, cond, ch)
        if key not in self._ids:
            gid = _ident(len(self._ids))
            _, strokes = glyph(face, ch)
            d = encode([[(x * cond, y - 9) for x, y in st] for st in strokes])
            self._defs.append('<path id="%s" d="%s"/>' % (gid, d))
            self._ids[key] = gid
        return self._ids[key]

    def defs(self):
        return ''.join(self._defs)

    def run(self, s, x, y, cap, face='futural', anchor='start', cond=.8, track=0, rot=0, pen=None, attrs=''):
        """One run of lettering, baseline at y. rot is 0 or -90 (reads upward). Returns (svg, width)."""
        scale = cap / 21.0
        cond = snap(cond)
        w = measure(s, cap, face, cond, track)
        shift = {'start': 0, 'middle': w / 2, 'end': w}[anchor]
        uses = []
        cur = 0
        for ch in s:
            adv, strokes = glyph(face, ch)
            if strokes:
                # a whole glyph unit is 5 % of the cap height, so rounding moves a letter 2.5 % at most:
                # invisible, and it keeps the <use> short (the first letter needs no x at all)
                gx = fmt(round(cur * cond))
                uses.append('<use href="#%s"%s/>' % (self._glyph_id(face, cond, ch), ' x="%s"' % gx if gx != '0' else ''))
            cur += adv + track
        sc = fmt(scale, 3)
        if rot == 0:
            tr = 'matrix(%s 0 0 %s %s %s)' % (sc, sc, fmt(x - shift), fmt(y))
        elif rot == -90:
            tr = 'matrix(0 -%s %s 0 %s %s)' % (sc, sc, fmt(x), fmt(y + shift))
        else:
            raise ValueError('rot must be 0 or -90')
        stroke = (pen if pen is not None else cap / 10.0) / scale
        return '<g transform="%s" stroke-width="%s"%s>%s</g>' % (tr, fmt(stroke, 1), attrs, ''.join(uses)), w

    def row(self, pieces, y, cap, face='futural', anchor='middle', cond=.8, pen=None, attrs=''):
        """Several short runs on one baseline, at one size, under one transform: [(text, x)] or
        [(text, x, anchor)], each placed at x by its anchor. A row of table cells or axis numbers costs one
        group instead of one per cell."""
        scale = cap / 21.0
        cond = snap(cond)
        starts = []
        for piece in pieces:
            s, x = piece[0], piece[1]
            w = measure(s, cap, face, cond)
            starts.append(x - {'start': 0, 'middle': w / 2, 'end': w}[piece[2] if len(piece) > 2 else anchor])
        x0 = min(starts)
        uses = []
        for (s, *_), sx in zip(pieces, starts):
            cur = (sx - x0) / scale / cond
            for ch in s:
                adv, strokes = glyph(face, ch)
                if strokes:
                    gx = fmt(round(cur * cond))
                    uses.append('<use href="#%s"%s/>' % (self._glyph_id(face, cond, ch),
                                                          ' x="%s"' % gx if gx != '0' else ''))
                cur += adv
        stroke = (pen if pen is not None else cap / 10.0) / scale
        sc = fmt(scale, 3)
        return '<g transform="matrix(%s 0 0 %s %s %s)" stroke-width="%s"%s>%s</g>' % (
            sc, sc, fmt(x0), fmt(y), fmt(stroke, 1), attrs, ''.join(uses))
