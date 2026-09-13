#!/usr/bin/env python3
"""Read my public WakaTime all-time stats into tools/state.json.

    python3 tools/wakatime.py                       fetch, validate, update state.json
    python3 tools/wakatime.py --from-file all.json  same, from a saved response
    python3 tools/wakatime.py --github-output "$GITHUB_OUTPUT"
    python3 tools/wakatime.py --accept-drop         take a total more than 10 % lower, once, after checking it is real

The all_time endpoint is public for this profile, so no key is needed. WakaTime
answers "pending_update" while it recomputes; that is retried. If the data never
becomes usable, state.json is left alone, a ::warning:: is printed, ok=false is
written to the GitHub output, and the exit code is still 0: the last good sheets stay.
Not usable means the network is down, the status is not ok, the body is malformed or
has no languages, or the numbers fail one of the guards in judge():

- a breakdown (languages, editors, operating systems or categories) whose rows add up
  to more than the total, beyond 1 % and a minute of rounding;
- a total that grew by more than 24 hours a day since the numbers last changed;
- a total more than 10 % below the last one accepted, even when WakaTime reports its
  stats complete (a real drop that large is taken with --accept-drop, once);
- any lower total while WakaTime is still recalculating.

A refused response changes nothing, so every guard compares with the last numbers
accepted and the first correct response after a glitch is plotted at once. A smaller
drop on complete stats is plotted, and state.json remembers the total from before it
("before_drop") until the total is back above it: a recovery is not a spike.
A large rise (more than 10 % or 48 h at once) is plotted, and state.json remembers the
total from before it with the date ("before_rise") for 14 days: in that window a
complete response that falls back to about that total is taken as the correction of a
bogus rise instead of being refused as a drop, so a bad high value cannot lock the sheets.

state.json keeps the numbers the sheets are plotted from and "changed", the date
those numbers last changed. The title blocks letter the later of that date and the
date of the commit count; it moves only when a number moves, so a day without new
data commits nothing.
"""
import argparse
import datetime as dt
import http.client
import json
import math
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

URL = 'https://wakatime.com/api/v1/users/018b5c7c-fde2-4105-aa96-f5c758abb0a2/stats/all_time'
STATE = Path(__file__).with_name('state.json')
TOP_LANGUAGES = 12
BREAKDOWNS = ('languages', 'editors', 'operating_systems', 'categories')  # each one splits the same total
MAX_DROP = .10  # a total further than this below the last accepted one is refused
DAY = 24 * 3600
RISE_WINDOW = 14  # days a large rise can still be undone by a fall back to the total before it


def days_between(a, b):
    """Whole days from ISO date a to ISO date b, or None when either is missing or malformed."""
    try:
        return (dt.date.fromisoformat(b) - dt.date.fromisoformat(a)).days
    except (TypeError, ValueError):
        return None


def fetch(attempts=6, wait=20):
    last = 'no attempt'
    for i in range(attempts):
        try:
            req = urllib.request.Request(URL, headers={'User-Agent': 'schufi73-profile-plotter'})
            with urllib.request.urlopen(req, timeout=30) as r:
                body = json.load(r)
            data = payload(body)
            status = data.get('status')
            if status == 'ok' and data.get('languages'):
                return data, None
            last = 'status=%s, %d languages' % (status, len(data.get('languages') or []))
        except (OSError, http.client.HTTPException, ValueError) as e:  # URLError and TimeoutError are OSErrors
            last = '%s: %s' % (type(e).__name__, e)
        if i < attempts - 1:
            time.sleep(wait)
    return None, last


def payload(body):
    """The data object of a response, or {} when the response has another shape."""
    data = body.get('data') if isinstance(body, dict) else None
    return data if isinstance(data, dict) else {}


def rows_of(value):
    """Rows with a string name and a positive number of seconds; anything else is dropped."""
    return [r for r in (value if isinstance(value, list) else [])
            if isinstance(r, dict) and isinstance(r.get('name'), str)
            and isinstance(r.get('total_seconds'), (int, float)) and not isinstance(r.get('total_seconds'), bool)
            and math.isfinite(r['total_seconds']) and r['total_seconds'] > 0 and clean(r['name'])]


def clean(name):
    """A name as the sheets can letter it: no control, format, surrogate or unassigned code points, one space
    between words, at most 80 characters."""
    name = ''.join(ch for ch in name if not unicodedata.category(ch).startswith('C') or ch in ' \t\n')
    return re.sub(r'\s+', ' ', name).strip()[:80]


def numbers(data):
    """The subset of the response the sheets use, in integers so it compares exactly."""
    def secs(rows, n=None):
        rows = rows_of(rows)
        rows.sort(key=lambda r: (-r['total_seconds'], r['name']))
        return [[clean(r['name']), int(round(r['total_seconds']))] for r in (rows[:n] if n else rows)]

    since = str(data.get('human_readable_range') or '').replace('since ', '').strip()
    try:
        since = dt.datetime.strptime(since, '%b %d %Y').date().isoformat()
    except ValueError:
        since = None
    cats = {c['name']: c['total_seconds'] for c in rows_of(data.get('categories'))}
    return {
        'total_seconds': int(round(data['total_seconds_including_other_language'])),
        'coding_days': int(data.get('days_minus_holidays') or 0),
        'daily_average_seconds': int(round(data.get('daily_average_including_other_language') or 0)),
        'since': since,
        'language_count': len(rows_of(data['languages'])),
        'languages': secs(data['languages'], TOP_LANGUAGES),
        'editors': secs(data.get('editors', [])),
        'operating_systems': secs(data.get('operating_systems', [])),
        'ai_coding_seconds': int(round(cats.get('AI Coding', 0))),
    }


def overfull(data, total):
    """The first breakdown whose rows add up to more than the total, with 1 % and a minute of slack; None if none."""
    for key in BREAKDOWNS:
        rows = sum(r['total_seconds'] for r in rows_of(data.get(key)))
        if rows > total * 1.01 + 60:
            return '%s add up to %d s, %.1f %% of the %d s total' % (key.replace('_', ' '), rows, 100.0 * rows / total,
                                                                    total)
    return None


def judge(data, state, today, accept_drop=False):
    """One usable response against the last accepted state: (state, refusal, notice). state is what state.json
    should hold (the same object when nothing changed, None when refused), refusal says why it was refused, notice
    is worth printing on success. Pure: no files, no network, no clock. Raises on a malformed response."""
    new = numbers(data)
    if new['total_seconds'] <= 0 or not new['languages']:
        raise ValueError('no positive total or no languages')
    over = overfull(data, new['total_seconds'])
    if over:
        return None, 'breakdown does not add up: %s' % over, None
    old = state.get('numbers')
    if not old:
        return {'changed': today, 'numbers': new}, None, None
    if new == old:
        return state, None, None
    # A plausible total grows by at most 24 hours a day since the numbers last changed. "changed" does not move
    # while data is refused, so a real jump (a backlog synced after weeks offline) still gets through once enough
    # days have passed, and a one-off bogus spike never locks the sheets.
    try:
        days = max(1, (dt.date.fromisoformat(today) - dt.date.fromisoformat(state['changed'])).days)
    except (KeyError, TypeError, ValueError):
        days = 1
    before, after = old['total_seconds'], new['total_seconds']
    high = max(before, state.get('before_drop') or 0)   # climbing back after an accepted drop is not growth
    complete = data.get('is_up_to_date') is True and data.get('percent_calculated') == 100
    rise = state.get('before_rise')   # [total before a large rise, date of that rise]
    age = days_between(rise[1], today) if isinstance(rise, list) and len(rise) == 2 else None
    if age is None or not 0 <= age <= RISE_WINDOW:
        rise = None
    if after > high + DAY * days:
        return None, 'total grew by more than 24 h a day (%d s -> %d s in %d days)' % (before, after, days), None
    undo = (rise is not None and complete and after < high * (1 - MAX_DROP)
            and after >= rise[0] * (1 - MAX_DROP))
    if after < high * (1 - MAX_DROP) and not accept_drop and not undo:
        return None, ('total dropped by more than %d %% (%d s -> %d s); if the drop is real, run tools/wakatime.py '
                      '--accept-drop once' % (round(MAX_DROP * 100), high, after)), None
    if after < before and not complete:
        return None, 'total went down while WakaTime is still recalculating (%d s -> %d s)' % (before, after), None
    kept = {'changed': today, 'numbers': new}
    notice = None
    if undo:
        return kept, None, ('total fell back to about its level before the large rise on %s (%d s -> %d s); '
                            'plotting it as a correction' % (rise[1], before, after))
    if after < before:
        notice = 'total went down (%d s -> %d s) and WakaTime reports the stats complete; plotting it' % (before, after)
    if after < high and not accept_drop:
        kept['before_drop'] = high
    if after > before + max(2 * DAY, MAX_DROP * before):
        kept['before_rise'] = [before, today]
    elif rise is not None:
        kept['before_rise'] = rise
    return kept, None, notice


def selftest():
    """Every guard on made-up responses, in the order a bad week would bring them. Returns (cases, errors).
    No network and no files."""
    hour = 3600
    errors, cases = [], [0]

    def response(hours, complete=True, **breakdowns):
        t = hours * hour
        body = {'status': 'ok', 'is_up_to_date': complete, 'percent_calculated': 100 if complete else 87,
                'total_seconds_including_other_language': t, 'daily_average_including_other_language': 9000,
                'human_readable_range': 'since Oct 23 2023', 'days_minus_holidays': 400,
                'languages': [{'name': 'Java', 'total_seconds': t * .6}, {'name': 'Markdown', 'total_seconds': t * .4}],
                'editors': [{'name': 'IntelliJ IDEA', 'total_seconds': t * .8},
                            {'name': 'Claude Code', 'total_seconds': t * .2}],
                'operating_systems': [{'name': 'Linux', 'total_seconds': t}],
                'categories': [{'name': 'Coding', 'total_seconds': t * .7},
                               {'name': 'AI Coding', 'total_seconds': t * .3}]}
        for key, shares in breakdowns.items():
            body[key] = [{'name': 'Row %d' % i, 'total_seconds': t * share} for i, share in enumerate(shares)]
        return body

    def expect(label, state, today, body, accepted, accept_drop=False):
        cases[0] += 1
        try:
            kept, refused, _ = judge(body, state, today, accept_drop)
        except Exception as e:  # noqa: BLE001 - a guard that raises on a well-formed response is a failure too
            errors.append('%s: %s: %s' % (label, type(e).__name__, e))
            return state
        if accepted and refused:
            errors.append('%s: refused (%s)' % (label, refused))
        elif not accepted and not refused:
            errors.append('%s: accepted' % label)
        return kept if kept is not None else state

    def check(label, ok):
        cases[0] += 1
        if not ok:
            errors.append(label)

    base = expect('first response', {'changed': None, 'numbers': None}, '2026-01-01', response(1000), True)
    check('first response: dated the day it came', base.get('changed') == '2026-01-01')
    check('the same numbers again: nothing changes', expect('same numbers', base, '2026-01-09', response(1000), True)
          is base)
    for key in BREAKDOWNS:
        expect('%s adding up to 130 %%' % key, base, '2026-01-02', response(1001, **{key: [.8, .5]}), False)
    expect('languages adding up to 100.9 %', base, '2026-01-02', response(1001, languages=[.6, .409]), True)
    # a complete-looking response with a total far too low, and the correct one the day after
    glitch = expect('complete stats, total 90 % low', base, '2026-01-02', response(100), False)
    check('a refused glitch leaves the state alone', glitch is base)
    after = expect('the correct total the day after the glitch', glitch, '2026-01-03', response(1010), True)
    check('the correct total is plotted at once', after.get('numbers', {}).get('total_seconds') == 1010 * hour
          and after.get('changed') == '2026-01-03')
    expect('complete stats, total 11 % low', base, '2026-01-02', response(890), False)
    expect('recalculating, total 1 % low', base, '2026-01-02', response(990, complete=False), False)
    # a small drop on complete stats is plotted, a second one past 10 % of the old total is not, the way back is
    dropped = expect('complete stats, total 8 % low', base, '2026-01-02', response(920), True)
    check('an accepted drop remembers the total before it', dropped.get('before_drop') == 1000 * hour)
    expect('a second drop, 12 % below the total before the first', dropped, '2026-01-03', response(880), False)
    back = expect('climbing back 84 h the day after a drop', dropped, '2026-01-03', response(1004), True)
    check('back above the old total, the drop is forgotten', 'before_drop' not in back)
    # spikes, and the growth a long offline stretch brings
    expect('500 h more in one day', base, '2026-01-02', response(1500), False)
    expect('the correct total the day after the spike', base, '2026-01-03', response(1020), True)
    expect('200 h more after 30 days offline', base, '2026-01-31', response(1200), True)
    taken = expect('a real 50 % drop with --accept-drop', base, '2026-01-02', response(500), True, accept_drop=True)
    check('--accept-drop keeps no old total', 'before_drop' not in taken)
    expect('recalculating, 50 % drop with --accept-drop', base, '2026-01-02', response(500, complete=False), False,
           accept_drop=True)
    # a bogus rise that passes the growth guard, and the correction that follows it
    small = expect('20 h more in a day', base, '2026-01-02', response(1020), True)
    check('a small rise remembers nothing', 'before_rise' not in small)
    risen = expect('200 h more after 10 days', base, '2026-01-11', response(1200), True)
    check('a large rise remembers the total before it', risen.get('before_rise') == [1000 * hour, '2026-01-11'])
    grown = expect('normal growth after the rise', risen, '2026-01-12', response(1205), True)
    check('normal growth keeps the rise in memory', grown.get('before_rise') == [1000 * hour, '2026-01-11'])
    expect('recalculating, back to the old total', grown, '2026-01-13', response(1010, complete=False), False)
    fixed = expect('complete stats back to the old total within 14 days', grown, '2026-01-13', response(1010), True)
    check('the correction forgets the rise and remembers no drop',
          'before_rise' not in fixed and 'before_drop' not in fixed)
    expect('complete stats back to the old total after 14 days', grown, '2026-01-30', response(1010), False)
    expect('complete stats 30 % below the total before the rise', grown, '2026-01-13', response(700), False)
    return cases[0], errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--from-file')
    ap.add_argument('--today', default=dt.datetime.now(dt.timezone.utc).date().isoformat())
    ap.add_argument('--github-output')
    ap.add_argument('--accept-drop', action='store_true',
                    help='take a total more than 10 %% below the last one accepted (check it is real first)')
    a = ap.parse_args()

    def out(ok, changed=False):
        if a.github_output:
            with open(a.github_output, 'a') as f:
                f.write('ok=%s\nchanged=%s\n' % (str(ok).lower(), str(changed).lower()))

    if a.from_file:
        try:
            data = payload(json.loads(Path(a.from_file).read_text()))
        except (OSError, ValueError):
            data = {}
        err = None if data.get('status') == 'ok' and data.get('languages') else 'status=%s' % data.get('status')
    else:
        data, err = fetch()
    if err:
        print('::warning::WakaTime all-time stats not usable (%s); keeping the last good sheets.' % err)
        out(False)
        return 0

    state = json.loads(STATE.read_text()) if STATE.exists() else {'changed': None, 'numbers': None}
    try:
        kept, refused, notice = judge(data, state, a.today, a.accept_drop)
    except (KeyError, TypeError, ValueError, AttributeError, OverflowError) as e:
        print('::warning::WakaTime all-time stats malformed (%s: %s); keeping the last good sheets.'
              % (type(e).__name__, e))
        out(False)
        return 0
    if refused:
        print('::warning::WakaTime all-time stats refused, %s; keeping the last good sheets.' % refused)
        out(False)
        return 0
    if notice:
        print('::notice::WakaTime all-time %s.' % notice)
    changed = kept != state
    if changed:
        STATE.write_text(json.dumps(kept, indent=2, sort_keys=True) + '\n')
    print('WakaTime: %.1f h all time, numbers %s (changed %s)'
          % (kept['numbers']['total_seconds'] / 3600.0, 'changed' if changed else 'unchanged', kept['changed']))
    out(True, changed)
    return 0


if __name__ == '__main__':
    sys.exit(main())
