#!/usr/bin/env python3
"""
generate_stats.py — draws the profile's stat cards from the GitHub
GraphQL API. Python standard library only, so nothing can break in CI.

Determinism, learned the hard way (per the self-generating-profile guide):
  * the contribution window is pinned to whole UTC days, so two runs on
    the same day are byte-identical;
  * repositories are filtered to PUBLIC only, so the workflow's token and
    a personal token agree on the numbers.

Cards (HYPERSHAPE instrument style — near-black, hairline, amber, mono):
  stats.svg   total contributions + honest weekly columns (not lines)
  streak.svg  current and longest streak with date ranges
  langs.svg   top languages by bytes across public non-fork repos
  year.svg    the year at one character per day, on the ASCII ramp
"""

import datetime as dt
import json
import os
import urllib.request

TOKEN = os.environ["GITHUB_TOKEN"]
LOGIN = os.environ.get("GH_LOGIN", "MowkE")

BG, LINE, TEXT, DIM, AMBER = "#0b0b09", "#2a2a24", "#d6d2c4", "#7a766a", "#ffb000"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
RAMP = " .`:-=+*cs#%@"
W = 820


def gql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql", data=body,
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        out = json.loads(r.read())
    if "errors" in out:
        raise SystemExit(out["errors"])
    return out["data"]


def fetch():
    today = dt.datetime.now(dt.timezone.utc).date()
    frm = f"{today - dt.timedelta(days=364)}T00:00:00Z"
    to = f"{today}T23:59:59Z"
    q = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount } }
          }
        }
        repositories(first: 100, privacy: PUBLIC, isFork: false,
                     ownerAffiliations: OWNER) {
          nodes { languages(first: 10) { edges { size node { name } } } }
        }
      }
    }"""
    return gql(q, {"login": LOGIN, "from": frm, "to": to})["user"]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;")


def card(height, inner, title):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
        f'viewBox="0 0 {W} {height}" role="img" aria-label="{esc(title)}">'
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" fill="{BG}" stroke="{LINE}"/>'
        f'<text x="18" y="27" font-family="{MONO}" font-size="10" font-weight="600" '
        f'letter-spacing="3" fill="{DIM}">{esc(title)}</text>'
        f'<line x1="18" y1="36" x2="{W - 18}" y2="36" stroke="{LINE}" stroke-width="1"/>'
        + inner + "</svg>"
    )


def fmt_date(iso):
    d = dt.date.fromisoformat(iso)
    return d.strftime("%b %d").upper()


def build(user):
    days = [d for w in user["contributionsCollection"]["contributionCalendar"]["weeks"]
            for d in w["contributionDays"]]
    total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]

    # ── stats.svg: total + weekly columns ──
    weekly = []
    for i in range(0, len(days), 7):
        weekly.append(sum(d["contributionCount"] for d in days[i:i + 7]))
    peak = max(weekly) or 1
    cols = []
    cw, gap, x0, base, maxh = 8, 3, 330, 118, 62
    for i, v in enumerate(weekly):
        h = max(2, round(v / peak * maxh)) if v else 2
        fill = AMBER if v else LINE
        cols.append(f'<rect x="{x0 + i * (cw + gap)}" y="{base - h}" width="{cw}" '
                    f'height="{h}" fill="{fill}"/>')
    inner = (
        f'<text x="18" y="102" font-family="{MONO}" font-size="46" font-weight="700" '
        f'fill="{AMBER}">{total:,}</text>'
        f'<text x="18" y="122" font-family="{MONO}" font-size="10" letter-spacing="2" '
        f'fill="{DIM}">CONTRIBUTIONS</text>'
        + "".join(cols)
    )
    open("stats.svg", "w").write(card(140, inner, f"{LOGIN} · PAST 365 DAYS"))

    # ── streak.svg ──
    counts = [d["contributionCount"] for d in days]
    cur = 0
    for c in reversed(counts if counts[-1] > 0 else counts[:-1]):
        if c > 0:
            cur += 1
        else:
            break
    best, run, run_start, best_range = 0, 0, 0, ("", "")
    for i, c in enumerate(counts):
        if c > 0:
            if run == 0:
                run_start = i
            run += 1
            if run > best:
                best = run
                best_range = (days[run_start]["date"], days[i]["date"])
        else:
            run = 0
    cur_range = ""
    if cur:
        idx = len(counts) - 1 - (0 if counts[-1] > 0 else 1)
        cur_range = f'{fmt_date(days[idx - cur + 1]["date"])} — {fmt_date(days[idx]["date"])}'
    blk = []
    for bx, label, num, rng in (
        (18, "CURRENT STREAK", cur, cur_range or "—"),
        (420, "LONGEST STREAK", best,
         f'{fmt_date(best_range[0])} — {fmt_date(best_range[1])}' if best else "—"),
    ):
        blk.append(
            f'<text x="{bx}" y="86" font-family="{MONO}" font-size="38" font-weight="700" '
            f'fill="{AMBER}">{num}</text>'
            f'<text x="{bx + 96}" y="86" font-family="{MONO}" font-size="12" '
            f'fill="{TEXT}">DAYS</text>'
            f'<text x="{bx}" y="106" font-family="{MONO}" font-size="10" letter-spacing="2" '
            f'fill="{DIM}">{label} · {rng}</text>'
        )
    open("streak.svg", "w").write(card(124, "".join(blk), f"{LOGIN} · STREAKS"))

    # ── langs.svg ──
    bytes_by = {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            bytes_by[e["node"]["name"]] = bytes_by.get(e["node"]["name"], 0) + e["size"]
    top = sorted(bytes_by.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    total_b = sum(v for _, v in top) or 1
    rows = []
    for i, (name, size) in enumerate(top):
        y = 62 + i * 26
        pct = size / total_b * 100
        bar = round(size / total_b * 470)
        rows.append(
            f'<text x="18" y="{y + 11}" font-family="{MONO}" font-size="12" '
            f'fill="{TEXT}">{esc(name)}</text>'
            f'<rect x="160" y="{y}" width="470" height="13" fill="{LINE}"/>'
            f'<rect x="160" y="{y}" width="{max(bar, 2)}" height="13" fill="{AMBER}"/>'
            f'<text x="{W - 18}" y="{y + 11}" text-anchor="end" font-family="{MONO}" '
            f'font-size="11" fill="{DIM}">{pct:.1f}%</text>'
        )
    h = 62 + len(top) * 26 + 16
    open("langs.svg", "w").write(card(h, "".join(rows), f"{LOGIN} · LANGUAGES · PUBLIC BYTES"))

    # ── year.svg: one ramp character per day ──
    peak_d = max(counts) or 1
    chars = []
    x0, y0, cwd, chh = 18, 60, 15, 15
    for i, d in enumerate(days):
        week, dow = divmod(i, 7)
        v = d["contributionCount"]
        ch = RAMP[min(int(v / peak_d * (len(RAMP) - 1) + (0.999 if v else 0)),
                      len(RAMP) - 1)]
        if ch == " ":
            ch = "."
            fill, op = DIM, "0.35"
        else:
            fill, op = AMBER, f"{0.45 + 0.55 * min(v / peak_d, 1):.2f}"
        chars.append(
            f'<text x="{x0 + week * cwd}" y="{y0 + dow * chh}" font-family="{MONO}" '
            f'font-size="12" fill="{fill}" opacity="{op}">{esc(ch)}</text>'
        )
    open("year.svg", "w").write(card(178, "".join(chars), f"{LOGIN} · THE YEAR, ONE CHARACTER PER DAY"))

    print(f"total={total} cur_streak={cur} best_streak={best} langs={[n for n, _ in top]}")


if __name__ == "__main__":
    build(fetch())
