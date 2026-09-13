#!/usr/bin/env python3
"""Refresh tools/commits.json from local git history. Runs on my machine, never in CI.

Almost all of my commits live in private repositories, so GitHub cannot count them.
This walks local clones, keeps the commits authored by my identities in the last
365 days, counts each commit hash once (clones and mirrors of the same repository
do not double-count), and writes coarse aggregates only:

    the count rounded down to a hundred, the share of commits in each hour of the day
    in per mille (on the author's own clock), the busiest hour, and the as-of date.

No exact count, no dates of activity, no repository names, paths, messages or e-mail
addresses are written. The exact figures are printed to the terminal and go nowhere else.

    python3 tools/commit_scan.py ~/IdeaProjects ~/WebstormProjects ~/Documents --exclude ~/IdeaProjects/some-archived-repo
    python3 tools/commit_scan.py --email me@example.org --exclude ~/IdeaProjects/old-thing ~

Identities default to `git config --global user.email` plus the GitHub no-reply
address of --github-login. Commit the refreshed tools/commits.json by hand; the push
re-plots both sheets. README.md carries the same month in three places the plot cannot
reach; edit them in the same commit:
    the count and its month in prose ("5,500+ commits in the last 12 months (Sep 2026)"),
    the Sheet 02 alt text ("over the 12 months to September 2026"),
    the heading "On the board · September 2026", if what is on the board has changed.
"""
import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {'node_modules', '.cache', '.npm', '.gradle', '.m2', '.cargo', '.rustup', 'venv', '.venv',
             'build', 'target', 'dist', 'snap', '.local', '.idea', '__pycache__'}


def find_repos(root, max_depth):
    root = Path(root).expanduser().resolve()
    base = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        depth = len(Path(dirpath).parts) - base
        if '.git' in dirnames or '.git' in filenames:
            yield Path(dirpath)
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and d != '.git' and depth < max_depth]


def git_config_email():
    try:
        return subprocess.run(['git', 'config', '--global', 'user.email'], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ''


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('roots', nargs='*', default=['~'], help='directories to search for git clones')
    ap.add_argument('--email', action='append', default=[], help='author e-mail to count (repeatable)')
    ap.add_argument('--github-login', default='schufi73', help='also count <id>+LOGIN@users.noreply.github.com')
    ap.add_argument('--exclude', action='append', default=[], help='skip repositories under this path (repeatable)')
    ap.add_argument('--days', type=int, default=365)
    ap.add_argument('--as-of', default=dt.date.today().isoformat(), help='YYYY-MM-DD, end of the window (inclusive)')
    ap.add_argument('--max-depth', type=int, default=6)
    ap.add_argument('--out', default=str(Path(__file__).with_name('commits.json')))
    a = ap.parse_args()

    emails = {e.lower() for e in (a.email or [git_config_email()]) if e}
    noreply = ('+%s@users.noreply.github.com' % a.github_login).lower()
    if not emails and not a.github_login:
        sys.exit('no identity: pass --email')
    excludes = [Path(p).expanduser().resolve() for p in a.exclude]

    end = dt.datetime.combine(dt.date.fromisoformat(a.as_of) + dt.timedelta(days=1), dt.time(), dt.timezone.utc)
    start = end - dt.timedelta(days=a.days)

    seen = {}
    repos = set()
    for root in a.roots:
        for repo in find_repos(root, a.max_depth):
            if any(repo == x or x in repo.parents for x in excludes):
                continue
            repos.add(repo)
    for repo in sorted(repos):
        try:
            out = subprocess.run(
                ['git', '-C', str(repo), 'log', '--all', '--since=%s' % (start - dt.timedelta(days=2)).isoformat(),
                 '--format=%H %at %ae %ad', '--date=format:%H %Y-%m-%d'],
                capture_output=True, text=True, check=True).stdout
        except subprocess.CalledProcessError:
            continue
        for line in out.splitlines():
            parts = line.split(' ')
            if len(parts) != 5:
                continue
            sha, at, email, hour, day = parts
            email = email.lower()
            if email not in emails and not email.endswith(noreply) and email != noreply.lstrip('+'):
                continue
            when = dt.datetime.fromtimestamp(int(at), dt.timezone.utc)
            if not (start <= when < end):
                continue
            seen[sha] = (int(hour), day)

    per_hour = [0] * 24
    for hour, _ in seen.values():
        per_hour[hour] += 1
    total = len(seen)
    # per mille, largest remainder first, so the 24 shares add up to exactly 1000
    raw = [1000.0 * c / total if total else 0.0 for c in per_hour]
    permille = [int(v) for v in raw]
    for h in sorted(range(24), key=lambda h: (-(raw[h] - permille[h]), h))[:(1000 - sum(permille)) if total else 0]:
        permille[h] += 1
    peak = max(range(24), key=lambda h: (per_hour[h], -h))
    result = {
        'as_of': a.as_of,
        'window_days': a.days,
        'commits_floor': total // 100 * 100,
        'busiest_hour': peak,
        'per_hour_permille': permille,
        'clock': "author's local time",
    }
    Path(a.out).write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print('%d commits (written as %d+), busiest hour %02d:00 -> %s' % (total, result['commits_floor'], peak, a.out))

if __name__ == '__main__':
    main()
