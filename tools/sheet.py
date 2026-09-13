"""What every sheet shares: paper and ink, the pen set, the plot's timing, the SVG wrapper.

Pen set, after ISO 128 (widths in viewBox units on a 1200-wide sheet):
    w1  thin          hatching boundaries, dimension, extension and leader lines, grids
    w2  medium        visible outlines, things seen beyond the cut
    w3  heavy         outlines of what the section plane cuts
    w4  extra heavy   ground line, drawing frame
Three plots of one sheet, switched by the image's own width. GitHub's README column is
846 px wide from a 1280 px window up, 766 px at 1200, 666 px at 1100, 578 px at 1012
and 398 px at 768:
    desktop  800 px and up    the detail layer (.dt): every table, note and dimension
    mid      521-799 px       the mid layer (.md): section, detail B, a short title block
    phone    520 px and less  the phone layer (.mb): the coarsest plot, the heaviest pens
Lines drawn with no layer class belong to all three; .dm is desktop and mid. Layers
switch with visibility, not display, so crossing a breakpoint does not restart the plot.

Legibility floor, as cap height on the 1200-wide sheet: 12 on the detail layer (8 px at
800 px, 8.5 px in the 846 px column), 22 on the mid layer (9.6 px at 521 px) and 44 on
the phone layer (11.3 px in a 308 px column). Sheet.text refuses anything smaller.

Motion: CSS keyframes only, inside prefers-reduced-motion: no-preference, fill-mode
backwards. The finished drawing is the static state; nothing loops. The outer sheet
form (border, zones, table frames) is pre-printed and never animates.
"""
import gzip
import re
import xml.etree.ElementTree as ET

from lettering import Pen, fmt, measure, snap

PALETTES = {
    # The blueprint copy: white lines on Prussian blue. Markup in NetSource cyan.
    'dark': dict(sheet='#0f3460', edge='#0b2a4f', ink='#eaf2ff', mark='#00ffe5', trim='#3a6699'),
    # The original: graphite on drafting film. Markup in NetSource blue.
    'light': dict(sheet='#f6f4ee', edge='#ebe6da', ink='#23262b', mark='#1a69f4', trim='#cfc9ba'),
}

MID_MAX = 799    # px of image width: the mid layer up to here
PHONE_MAX = 520  # and the phone layer up to here
BUDGETS = {  # file-name prefix -> (raw bytes, gzip bytes); plot.py and draw.py both read these
    'sheet-01': (80000, 25000),
    'sheet-02': (80000, 25000),
    'tag-': (6000, 3000),
}

PENS = {'w1': .9, 'w2': 1.5, 'w3': 2.7, 'w4': 3.6}
MID_PENS = {'w1': 1.2, 'w2': 2, 'w3': 3.4, 'w4': 4.4}
PHONE_PENS = {'w1': 2.2, 'w2': 3.2, 'w3': 4.8, 'w4': 5.8}

# kind -> (class, easing)
KINDS = {
    'dr': ('D', 'cubic-bezier(.45,.05,.35,1)'),   # a pen drawing a line
    'wp': ('P', 'linear'),                        # lettering, left to right
    'fd': ('F', 'ease-out'),                      # ink settling (fills, markers)
}

KEYFRAMES = (
    '@keyframes dr{from{stroke-dasharray:1 2;stroke-dashoffset:1.01}to{stroke-dasharray:1 2;stroke-dashoffset:0}}'
    '@keyframes wp{from{clip-path:inset(-8px 100% -8px 0)}to{clip-path:inset(-8px -8px -8px -8px)}}'
    '@keyframes fd{from{opacity:0}to{opacity:1}}'
)


def s_(v):
    """Seconds for CSS: .35s, 1.2s, 0s."""
    v = round(v, 2)
    t = ('%.2f' % v).rstrip('0').rstrip('.')
    return (t[1:] if t.startswith('0.') else t or '0') + 's'


class Motion:
    """Timings as short shared classes: the kind class names the keyframes, the timing class sets --m."""

    def __init__(self, end=4.0):
        self.end = end
        self._cls = {}

    def cls(self, kind, t, dur):
        t = round(t * 50) / 50.0
        dur = max(.06, round(dur * 50) / 50.0)
        if t + dur > self.end + 1e-9:
            raise ValueError('%s at %.2fs + %.2fs ends after %.1fs' % (kind, t, dur, self.end))
        key = (t, dur)
        if key not in self._cls:
            self._cls[key] = 'm%d' % len(self._cls)
        return '%s %s' % (KINDS[kind][0], self._cls[key])

    def css(self):
        timings = ''.join('.%s{--m:%s %s}' % (name, s_(dur), s_(t)) for (t, dur), name in self._cls.items())
        kinds = ''.join('.%s{animation:%s var(--m) %s backwards}' % (c, k, ease) for k, (c, ease) in KINDS.items())
        return '%s@media (prefers-reduced-motion:no-preference){%s}' % (timings, kinds)


class Sheet:
    """One SVG. min_cap / mid_cap / phone_cap are the legibility floors (None switches a check off)."""

    def __init__(self, theme, width, height, end=4.0, min_cap=12, mid_cap=22, phone_cap=44):
        self.theme = theme
        self.p = PALETTES[theme]
        self.W, self.H = width, height
        self.pen = Pen()
        self.motion = Motion(end)
        self.min_cap, self.mid_cap, self.phone_cap = min_cap, mid_cap, phone_cap
        self.defs = []
        self.body = []

    # ------------------------------------------------------------------ primitives
    def _classes(self, *names):
        names = [n for n in names if n]
        return ' class="%s"' % ' '.join(names) if names else ''

    def path(self, d, w='w2', t=None, dur=.5, kind='dr', layer=None, color=None, op=None, extra=''):
        """A stroked path. t=None means pre-printed on the sheet (no motion)."""
        mc = self.motion.cls(kind, t, dur) if t is not None else None
        attrs = self._classes(w, layer, mc)
        if mc and kind == 'dr':
            attrs += ' pathLength="1"'
        if color:
            attrs += ' stroke="%s"' % color
        if op is not None:
            attrs += ' stroke-opacity="%s"' % fmt(op, 2)
        self.body.append('<path%s%s d="%s"/>' % (attrs, extra, d))

    def fill(self, d, paint, t=None, dur=.5, kind='wp', layer=None, op=None):
        """A filled area (hatch pattern or solid)."""
        mc = self.motion.cls(kind, t, dur) if t is not None else None
        o = ' fill-opacity="%s"' % fmt(op, 2) if op is not None else ''
        self.body.append('<path%s fill="%s" stroke="none"%s d="%s"/>' % (self._classes(layer, mc), paint, o, d))

    def text(self, s, x, y, cap, face='futural', anchor='start', cond=.8, track=0, rot=0, pen=None,
             t=None, dur=None, layer='dt', color=None, op=None, knock=False, kind='wp', halo=None):
        """A run of lettering, baseline at y. layer 'dt' (desktop, default), 'md' (mid), 'dm' (desktop and mid),
        'mb' (phone) or None (all). knock=True clears a box behind it; halo=n first letters the same run in paper
        colour n units wider, so a line passing close by stops short of the letters. Returns the width."""
        floor = {'mb': self.phone_cap, 'md': self.mid_cap, 'dm': self.mid_cap}.get(layer, self.min_cap)
        if floor is not None and cap < floor - 1e-9:
            raise ValueError('%r lettered at cap %s, below the %s floor of %s' % (s, cap, layer, floor))
        if dur is None:
            dur = max(.2, min(1.0, len(s) * .025))
        mc = self.motion.cls(kind, t, dur) if t is not None else None
        grouped = knock or halo
        attrs = self._classes(layer if not grouped else None, mc if not grouped else None)
        if color:
            attrs += ' stroke="%s"' % color
        if op is not None:
            attrs += ' stroke-opacity="%s"' % fmt(op, 2)
        run, width = self.pen.run(s, x, y, cap, face=face, anchor=anchor, cond=cond, track=track, rot=rot, pen=pen,
                                  attrs=attrs)
        if halo:
            under, _ = self.pen.run(s, x, y, cap, face=face, anchor=anchor, cond=cond, track=track, rot=rot,
                                    pen=(pen if pen is not None else cap / 10.0) + halo,
                                    attrs=' stroke="%s"' % self.p['sheet'])
            self.body.append('<g%s>%s%s</g>' % (self._classes(layer, mc), under, run))
        elif knock:
            off = {'start': 0, 'middle': width / 2, 'end': width}[anchor]
            pad = max(3, cap * .3)
            if rot == 0:
                box = (x - off - pad, y - cap - pad, width + 2 * pad, cap + 2 * pad)
            else:
                box = (x - cap - pad, y + off - width - pad, cap + 2 * pad, width + 2 * pad)
            rect = '<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>' % (
                fmt(box[0]), fmt(box[1]), fmt(box[2]), fmt(box[3]), self.p['sheet'])
            self.body.append('<g%s>%s%s</g>' % (self._classes(layer, mc), rect, run))
        else:
            self.body.append(run)
        return width

    def row(self, pieces, y, cap, face='futural', anchor='middle', cond=.8, pen=None, t=None, dur=.3, layer='dt',
            color=None, op=None, kind='wp'):
        """Short runs on one baseline under one transform (see Pen.row): [(text, x)]."""
        pieces = [pc for pc in pieces if pc[0]]
        if not pieces:
            return
        floor = {'mb': self.phone_cap, 'md': self.mid_cap, 'dm': self.mid_cap}.get(layer, self.min_cap)
        if floor is not None and cap < floor - 1e-9:
            raise ValueError('%r lettered at cap %s, below the %s floor of %s' % (pieces, cap, layer, floor))
        mc = self.motion.cls(kind, t, dur) if t is not None else None
        attrs = self._classes(layer, mc)
        if color:
            attrs += ' stroke="%s"' % color
        if op is not None:
            attrs += ' stroke-opacity="%s"' % fmt(op, 2)
        self.body.append(self.pen.row(pieces, y, cap, face=face, anchor=anchor, cond=cond, pen=pen, attrs=attrs))

    def raw(self, s):
        self.body.append(s)

    # ------------------------------------------------------------------ output
    def svg(self, title, desc, extra_css=''):
        p = self.p
        pens = ''.join('.%s{stroke-width:%spx}' % (k, fmt(v, 2)) for k, v in PENS.items())
        mid = ''.join('.%s{stroke-width:%spx}' % (k, fmt(v, 2)) for k, v in MID_PENS.items())
        phone = ''.join('.%s{stroke-width:%spx}' % (k, fmt(v, 2)) for k, v in PHONE_PENS.items())
        # the phone query comes second and wins below PHONE_MAX; no gap between the two at fractional widths
        css = ('svg{fill:none;stroke:%s;stroke-linecap:round;stroke-linejoin:round}rect{stroke:none}%s'
               '.mb,.md{visibility:hidden}%s%s'
               '@media (max-width:%dpx){.dt{visibility:hidden}.md{visibility:visible}%s}'
               '@media (max-width:%dpx){.md,.dm{visibility:hidden}.mb{visibility:visible}%s}%s'
               % (p['ink'], pens, KEYFRAMES, self.motion.css(), MID_MAX, mid, PHONE_MAX, phone, extra_css))
        return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" '
                'aria-labelledby="_t _d"><title id="_t">%s</title><desc id="_d">%s</desc><style>%s</style>'
                '<defs>%s%s</defs>%s</svg>\n') % (
            self.W, self.H, self.W, self.H, esc(title), esc(desc), css,
            ''.join(self.defs), self.pen.defs(), ''.join(self.body))


_NOT_XML = re.compile('[^\u0009\u000a\u000d\u0020-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]')


def esc(s):
    """Text for <title> and <desc>: XML-escaped, and without the code points XML 1.0 cannot hold."""
    return _NOT_XML.sub('', s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def fit(s, cap, room, cond=.8, face='futural', floor=.6):
    """The condensation at which s fits into room units (never wider than cond). Raises below floor."""
    w = measure(s, cap, face, cond)
    if w <= room:
        return cond
    c = snap(cond) * room / w   # measure letters at snap(cond): scale from there, or the run never narrows
    if c < floor:
        raise ValueError('%r needs %.0f units at cap %s, has %.0f' % (s, w, cap, room))
    return c


def clip(s, cap, room, cond=.8, face='futural', floor=.6):
    """(text, condensation) that fits room: condensed down to floor, then shortened with a full stop.
    For names that come from data; never use it on a number."""
    try:
        return s, fit(s, cap, room, cond, face, floor)
    except ValueError:
        while len(s) > 1 and measure(s + '.', cap, face, floor) > room:
            s = s[:-1].rstrip()
        return s + '.', floor


def budget(name):
    for prefix, b in BUDGETS.items():
        if name.startswith(prefix):
            return b
    raise ValueError('%s: no budget for this file' % name)


def validate(name, svg, max_raw=None, max_gzip=None):
    """Parse as XML and check the byte budgets. Returns (raw, gzip) sizes; raises ValueError on failure."""
    data = svg.encode()
    ids = [e.get('id') for e in ET.fromstring(data).iter() if e.get('id')]
    if len(ids) != len(set(ids)):
        raise ValueError('%s: duplicate ids %s' % (name, sorted({i for i in ids if ids.count(i) > 1})))
    raw, gz = len(data), len(gzip.compress(data, 9, mtime=0))
    if max_raw and raw > max_raw:
        raise ValueError('%s: %d bytes, budget %d' % (name, raw, max_raw))
    if max_gzip and gz > max_gzip:
        raise ValueError('%s: %d bytes gzipped, budget %d' % (name, gz, max_gzip))
    return raw, gz


def M(*pts, close=False):
    """Absolute polyline."""
    d = 'M%s %s' % (fmt(pts[0][0]), fmt(pts[0][1]))
    for x, y in pts[1:]:
        d += 'L%s %s' % (fmt(x), fmt(y))
    return d + ('Z' if close else '')


def rect_d(x, y, w, h):
    return 'M%s %sh%sv%sh%sZ' % (fmt(x), fmt(y), fmt(w), fmt(h), fmt(-w))


def circle_d(cx, cy, r):
    return 'M%s %sa%s %s 0 1 0 %s 0a%s %s 0 1 0 -%s 0' % (fmt(cx - r), fmt(cy), fmt(r), fmt(r), fmt(2 * r), fmt(r),
                                                          fmt(r), fmt(2 * r))


def paper(S, trim=True):
    """The drafting film / blueprint ground, a trim line and a faint tooth. Pre-printed."""
    p = S.p
    S.defs.append('<radialGradient id="_vg" cx=".45" cy=".4" r=".9"><stop offset=".6" stop-color="%s" stop-opacity="0"/>'
                  '<stop offset="1" stop-color="%s"/></radialGradient>' % (p['edge'], p['edge']))
    # paper tooth: a fixed stipple, a few bytes instead of a raster tile
    dots = ''.join('M%d %dh.01' % (x, y) for x, y in (
        (7, 11), (31, 4), (52, 23), (18, 37), (44, 49), (61, 58), (3, 55), (26, 62), (57, 8), (38, 29), (12, 21),
        (49, 38)))
    S.defs.append('<pattern id="_gr" width="64" height="64" patternUnits="userSpaceOnUse">'
                  '<path d="%s" stroke="%s" stroke-width="1.1" stroke-opacity=".16"/></pattern>' % (dots, p['ink']))
    S.raw('<rect width="%d" height="%d" fill="%s"/>' % (S.W, S.H, p['sheet']))
    S.raw('<rect width="%d" height="%d" fill="url(#_vg)"/>' % (S.W, S.H))
    S.raw('<rect width="%d" height="%d" fill="url(#_gr)"/>' % (S.W, S.H))
    if trim:
        S.raw('<path stroke="%s" stroke-width="2" d="%s"/>' % (p['trim'], rect_d(1, 1, S.W - 2, S.H - 2)))
