#!/usr/bin/env python3
"""plot.py: re-plot every sheet into assets/, or leave assets/ alone.

    python3 tools/plot.py            plot from tools/state.json and tools/commits.json
    python3 tools/plot.py --check    plot and compare with assets/, write nothing (exit 1 on a difference)

This is what CI runs after tools/wakatime.py has, or has not, refreshed state.json:

1. draw.py plots everything twice, into two scratch directories, and the two runs must be
   byte-identical: nothing in a sheet may depend on the clock, the network or dict order;
2. the full set must be there: SHEET 01 and SHEET 02 and the four link tags, dark and light;
3. every file must parse as XML with unique ids, stay inside its byte budget (raw and gzipped;
   raw.githubusercontent.com serves gzip) and stay self-contained: no scripts, no external
   references, no animation that never ends;
4. the layout self-test plots both sheets from made-up numbers well outside today's (Java at
   0-100 %, breakdowns adding up to more than 100 %, 1 h to 99,999 h, one editor or eight, long
   and accented names, no commits ...) and every one of them must plot inside its budget; the
   title blocks must carry the later of the two input dates. The guard self-test feeds
   tools/wakatime.py made-up responses (shares over 100 %, a total far too low and the correct one
   the day after, spikes, drops) and every one must be accepted or refused as it should. Neither
   uses real data, so they can only fail on the push that changed the code, never on a scheduled
   run months later;
5. only then are the files that changed copied into assets/.

Any failure in 1-4 exits non-zero and leaves assets/ untouched, so a broken generator never
replaces a good sheet. Plotting from unchanged inputs writes the same bytes, which is how a day
without new WakaTime numbers ends without a commit.
"""
import argparse
import copy
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

sys.dont_write_bytecode = True  # the self-test imports the generators: no __pycache__ in tools/
TOOLS = Path(__file__).resolve().parent
ASSETS = TOOLS.parent / 'assets'
sys.path.insert(0, str(TOOLS))

from sheet import budget, validate  # noqa: E402
import tags  # noqa: E402
import wakatime  # noqa: E402

THEMES = ('dark', 'light')
PAGE_BUDGET = (190000, 60000)  # everything one theme of the README loads
FORBIDDEN = [  # what an SVG shown through <img> must not carry
    (re.compile(r'<script|<foreignObject|@import', re.I), 'script, foreignObject or @import'),
    (re.compile(r'(?:href|src)\s*=\s*"(?!#)', re.I), 'an external href/src'),
    (re.compile(r'url\((?!#)', re.I), 'an external url()'),
    (re.compile(r'\binfinite\b', re.I), 'an animation that never ends'),
]


def expected():
    names = ['sheet-%s-%s.svg' % (n, t) for n in ('01', '02') for t in THEMES]
    return sorted(names + [name for name, _ in tags.build_all()])


def plot_into(directory):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    run = subprocess.run([sys.executable, '-B', str(TOOLS / 'draw.py'), str(directory)], env=env,
                         capture_output=True, text=True)
    if run.returncode:
        sys.stderr.write(run.stdout + run.stderr)
        raise SystemExit('draw.py failed (exit %d)' % run.returncode)
    return {p.name: p.read_bytes() for p in sorted(Path(directory).glob('*.svg'))}


# ---------------------------------------------------------------------- layout self-test
H_ = 3600
BASE_STATE = {
    'changed': '2099-01-31',  # far ahead, so no revision a later push adds is dated after it
    'numbers': {
        'total_seconds': 1000 * H_, 'coding_days': 400, 'daily_average_seconds': 9000, 'since': '2023-10-23',
        'language_count': 40, 'ai_coding_seconds': 200 * H_,
        'languages': [['Java', 600 * H_], ['Markdown', 150 * H_], ['HTML', 30 * H_], ['Other', 25 * H_],
                      ['CSS', 25 * H_], ['SQL', 24 * H_], ['Kotlin', 20 * H_], ['TypeScript', 16 * H_],
                      ['Protocol Buffer', 12 * H_], ['JavaScript', 10 * H_], ['protobuf', 8 * H_], ['JSON', 6 * H_]],
        'editors': [['IntelliJ IDEA', 700 * H_], ['Claude Code', 200 * H_], ['WebStorm', 60 * H_],
                    ['VS Code', 25 * H_], ['CLion', 10 * H_], ['Unknown Editor', 5 * H_]],
        'operating_systems': [['Linux', 550 * H_], ['Windows', 450 * H_]],
    },
}
BASE_COMMITS = {'as_of': '2099-01-31', 'window_days': 365, 'commits_floor': 5500, 'busiest_hour': 22,
                'per_hour_permille': [50, 35, 13, 8, 8, 3, 0, 1, 3, 20, 43, 50, 41, 84, 81, 70, 80, 47, 25, 30,
                                      49, 90, 97, 72], 'clock': "author's local time"}


def _scaled(state, factor):
    n = state['numbers']
    for key in ('total_seconds', 'ai_coding_seconds'):
        n[key] = int(n[key] * factor)
    for key in ('languages', 'editors', 'operating_systems'):
        n[key] = [[name, max(1, int(sec * factor))] for name, sec in n[key]]
    return state


def variants():
    """(label, state, commits): made-up inputs that a layout has to survive."""
    def v(label, change_state=None, change_commits=None):
        st, cm = copy.deepcopy(BASE_STATE), copy.deepcopy(BASE_COMMITS)
        if change_state:
            st = change_state(st) or st
        if change_commits:
            cm = change_commits(cm) or cm
        return label, st, cm

    out = [v('base')]
    for java in (0, 1, 3, 6, 10, 20, 30, 40, 45, 50, 60, 70, 75, 80, 90, 95, 99, 100):
        def ch(st, java=java):
            n = st['numbers']
            tot = n['total_seconds']
            j = int(tot * java / 100.0)
            others = [row for row in n['languages'] if row[0] != 'Java']
            left = sum(s for _, s in others) or 1
            n['languages'] = [['Java', j]] + [[name, int((tot - j) * s / left)] for name, s in others]
        out.append(v('java %d %%' % java, ch))
    for hours in (1, 10, 100, 999, 1000, 2750, 5000, 12000, 99999):
        out.append(v('%d h' % hours, lambda st, hours=hours: _scaled(st, hours / 1000.0)))
    for top in (13, 20, 50, 72, 90, 99, 100):
        def ch(st, top=top):
            n = st['numbers']
            tot = n['total_seconds']
            first = int(tot * top / 100.0)
            rest = tot - first
            n['editors'] = [['IntelliJ IDEA', first]] + ([['Claude Code', int(rest * .7)], ['VS Code', rest - int(rest * .7)]]
                                                         if rest else [])
        out.append(v('top editor %d %%' % top, ch))
    out.append(v('one editor', lambda st: st['numbers'].update(editors=[['Vim', st['numbers']['total_seconds']]])))
    out.append(v('no editors', lambda st: st['numbers'].update(editors=[])))
    out.append(v('eight tiny editors', lambda st: st['numbers'].update(
        editors=[['Editor %d' % i, st['numbers']['total_seconds'] // 8] for i in range(8)])))
    out.append(v('long names', lambda st: st['numbers'].update(
        languages=[['Windows Registry Entries Protocol Buffer Text Format', 400 * H_]] + st['numbers']['languages'][1:],
        editors=[['IntelliJ IDEA Ultimate Early Access Program Edition', 700 * H_]] + st['numbers']['editors'][1:])))
    out.append(v('accented names', lambda st: st['numbers'].update(
        languages=[['Ünïcødé Läng 日本語', 400 * H_]] + st['numbers']['languages'][1:],
        editors=[['Café Editor', 700 * H_]] + st['numbers']['editors'][1:],
        operating_systems=[['Système Ωmega', 600 * H_], ['Linux', 400 * H_]])))
    out.append(v('many thin languages', lambda st: st['numbers'].update(
        languages=[['Java', 900 * H_]] + [['Lang %d' % i, 8 * H_] for i in range(11)], language_count=150)))
    out.append(v('no os, no since, no average', lambda st: st['numbers'].update(
        operating_systems=[], since=None, daily_average_seconds=0, ai_coding_seconds=0)))
    out.append(v('huge average', lambda st: st['numbers'].update(daily_average_seconds=99 * H_ + 59 * 60)))
    out.append(v('no commits', None, lambda cm: cm.update(commits_floor=0, per_hour_permille=[0] * 24, busiest_hour=0)))
    out.append(v('one hour of commits', None, lambda cm: cm.update(
        per_hour_permille=[0] * 3 + [1000] + [0] * 20, busiest_hour=3)))
    out.append(v('busiest at midnight', None, lambda cm: cm.update(busiest_hour=0, per_hour_permille=[200] + [35] * 23)))
    out.append(v('busiest at 23:00', None, lambda cm: cm.update(busiest_hour=23, per_hour_permille=[35] * 23 + [195])))
    out.append(v('flat commits', None, lambda cm: cm.update(per_hour_permille=[42] * 23 + [34], busiest_hour=0)))
    out.append(v('99,900 commits in December', None, lambda cm: cm.update(commits_floor=99900, as_of='2099-12-31')))
    # breakdowns that add up to more than the total: wakatime.py refuses them, the sheets must still plot
    out.append(v('languages adding up to 130 %', lambda st: st['numbers'].update(
        languages=[['Java', 900 * H_], ['Markdown', 400 * H_]], language_count=2)))
    out.append(v('one language at 120 %', lambda st: st['numbers'].update(languages=[['Java', 1200 * H_]],
                                                                          language_count=1)))
    out.append(v('editors adding up to 150 %', lambda st: st['numbers'].update(
        editors=[['IntelliJ IDEA', 1200 * H_], ['Claude Code', 300 * H_]])))
    out.append(v('operating systems and AI coding over 100 %', lambda st: st['numbers'].update(
        operating_systems=[['Linux', 900 * H_], ['Windows', 800 * H_]], ai_coding_seconds=1400 * H_)))
    out.append(v('commits counted after the numbers changed', None, lambda cm: cm.update(as_of='2099-06-30')))
    return out


def selftest():
    import draw
    import draw02
    errors = []
    sheets = (('sheet-01', draw.build), ('sheet-02', draw02.build))
    for label, st, cm in variants():
        for name, build in sheets:
            try:
                validate(name, build('dark', st, cm), *budget(name))
            except Exception as e:  # noqa: BLE001 - any exception is a layout that breaks on data
                errors.append('self-test %s, %s: %s: %s' % (name, label, type(e).__name__, e))
    # both title blocks carry the later of the two input dates, whichever that is
    st, cm = copy.deepcopy(BASE_STATE), copy.deepcopy(BASE_COMMITS)
    for changed, as_of in (('2099-02-01', '2099-03-01'), ('2099-03-01', '2099-02-01')):
        st['changed'], cm['as_of'] = changed, as_of
        for name, build in sheets:
            if 'dated 2099-03-01.' not in build('dark', st, cm).lower():
                errors.append('self-test %s: numbers of %s and commits of %s not dated 2099-03-01'
                              % (name, changed, as_of))
    # and a revision newer than both is refused rather than plotted under an older date
    st['changed'] = cm['as_of'] = '2026-01-31'
    for name, build in sheets:
        try:
            build('dark', st, cm)
            errors.append('self-test %s: plotted revision %s under a sheet dated 2026-01-31'
                          % (name, draw.REVISIONS[0][0]))
        except ValueError:
            pass
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--check', action='store_true', help='compare with assets/ and write nothing')
    a = ap.parse_args()

    with tempfile.TemporaryDirectory() as one, tempfile.TemporaryDirectory() as two:
        first, second = plot_into(one), plot_into(two)
    errors = []
    if first != second:
        diff = sorted(n for n in set(first) | set(second) if first.get(n) != second.get(n))
        errors.append('two runs differ: %s' % ', '.join(diff))
    missing = sorted(set(expected()) - set(first))
    if missing:
        errors.append('not plotted: %s' % ', '.join(missing))

    page = {t: [0, 0] for t in THEMES}
    for name, data in sorted(first.items()):
        try:
            raw, gz = validate(name, data.decode(), *budget(name))
        except (ValueError, ET.ParseError) as e:
            errors.append('%s: %s' % (name, e) if isinstance(e, ET.ParseError) else str(e))
            continue
        text = data.decode()
        errors += ['%s: %s' % (name, why) for rx, why in FORBIDDEN if rx.search(text)]
        theme = name.rsplit('-', 1)[1][:-4]
        if theme in page:
            page[theme][0] += raw
            page[theme][1] += gz
        print('%-26s %6d bytes %6d gzip' % (name, raw, gz))
    for theme, (raw, gz) in page.items():
        print('%-26s %6d bytes %6d gzip' % ('README, %s' % theme, raw, gz))
        if raw > PAGE_BUDGET[0] or gz > PAGE_BUDGET[1]:
            errors.append('README %s images: %d bytes / %d gzip, budget %d / %d' % ((theme, raw, gz) + PAGE_BUDGET))
    tested = selftest()
    print('layout self-test: %d made-up inputs, %s' % (len(variants()), '%d failures' % len(tested) if tested else 'all plot'))
    errors += tested
    cases, guarded = wakatime.selftest()
    print('guard self-test: %d checks on made-up WakaTime responses, %s'
          % (cases, '%d failures' % len(guarded) if guarded else 'all decide as they should'))
    errors += ['guard self-test, %s' % e for e in guarded]

    if errors:
        for e in errors:
            print('::error::%s' % e)
        print('assets/ left untouched.')
        return 1

    changed = [n for n, data in first.items() if not (ASSETS / n).is_file() or (ASSETS / n).read_bytes() != data]
    if a.check:
        print('assets/ %s' % ('differs: ' + ', '.join(changed) if changed else 'is up to date'))
        return 1 if changed else 0
    ASSETS.mkdir(exist_ok=True)
    for n in changed:
        (ASSETS / n).write_bytes(first[n])
    print('%d of %d files changed%s' % (len(changed), len(first), ': ' + ', '.join(changed) if changed else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
