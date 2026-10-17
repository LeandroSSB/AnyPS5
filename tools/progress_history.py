import argparse
import io
import json
import subprocess
import tarfile
import tempfile
from datetime import date
from html import escape
from pathlib import Path

import progress

SERIES = (("libraries", "Library functions", "#2f81f7"), ("shaders", "Shader instructions", "#2ea043"))
LINES = (("libraries", "done", "Library functions implemented", "#2f81f7", ""),
         ("libraries", "total", "Library functions declared", "#8b949e", "6 4"),
         ("shaders", "done", "Shader instructions implemented", "#2ea043", ""),
         ("shaders", "total", "Shader instructions declared", "#66d18f", "6 4"))
WIDTH, HEIGHT, LEFT, RIGHT, TOP, BOTTOM = 900, 380, 50, 70, 20, 64
MAX_DOTS = 45
BACKGROUND, GRID, TEXT = "#0d1117", "#30363d", "#c9d1d9"


def git(*args):
    return subprocess.run(["git", "-C", str(progress.ROOT), *args], check=True, capture_output=True).stdout


def daily_commits(ref):
    seen = {}
    for line in git("log", "--first-parent", "--format=%H %cs", ref).decode().splitlines():
        sha, day = line.split()
        seen.setdefault(day, sha)
    return sorted(seen.items())


def measure(sha):
    paths = [progress.PRX.relative_to(progress.ROOT).as_posix(), progress.OPCODES.relative_to(progress.ROOT).as_posix()]
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        try:
            archive = tarfile.open(fileobj=io.BytesIO(git("archive", sha, "--", *paths)))
            if hasattr(tarfile, "data_filter"):
                archive.extractall(root, filter="data")
            else:
                archive.extractall(root)
        except subprocess.CalledProcessError:
            return None
        saved = progress.PRX, progress.OPCODES
        progress.PRX, progress.OPCODES = root / paths[0], root / paths[1]
        try:
            libraries, shaders = progress.collect_libraries(), progress.collect_shaders()
        except (OSError, AttributeError):
            return None
        finally:
            progress.PRX, progress.OPCODES = saved
    return {name: {key: data[key] for key in ("done", "total", "percent")}
            for name, data in (("libraries", libraries), ("shaders", shaders))}


def collect(ref):
    points = []
    for day, sha in daily_commits(ref):
        counts = measure(sha)
        if counts:
            points.append({"date": day, "commit": sha, **counts})
    return points


def labelled(day, span):
    if span <= 31:
        return day.strftime("%m-%d")
    if span <= 150:
        return day.strftime("%m-%d") if day.weekday() == 0 else ""
    return day.strftime("%Y-%m") if day.day <= 7 and day.weekday() == 0 else ""


def chart(points):
    days = [date.fromisoformat(p["date"]).toordinal() for p in points]
    first, span = days[0], max(days[-1] - days[0], 1)
    tops = {}
    for name, _, _ in SERIES:
        peak = max(p[name][key] for p in points for key in ("done", "total"))
        step = next(s for s in (10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000) if peak <= s * 4)
        tops[name] = max(step, -(-peak // step) * step)
    px = lambda d: LEFT + (d - first) / span * (WIDTH - LEFT - RIGHT)
    py = lambda name, v: TOP + (1 - v / tops[name]) * (HEIGHT - TOP - BOTTOM)
    base = py("libraries", 0)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" '
           f'aria-label="Progress over time" font-family="sans-serif" font-size="12" fill="{TEXT}">',
           f'<rect width="{WIDTH}" height="{HEIGHT}" rx="6" fill="{BACKGROUND}"/>']
    for name, label, _ in SERIES:
        anchor, x = ("end", LEFT - 6) if name == "libraries" else ("start", WIDTH - RIGHT + 6)
        for tick in range(0, tops[name] + 1, max(tops[name] // 4, 1)):
            out.append(f'<text x="{x}" y="{py(name, tick) + 4:.1f}" text-anchor="{anchor}" fill="{label}">{tick}</text>')
    last_date_x = -100.0
    for d, p in zip(days, points):
        x = px(d)
        label = labelled(date.fromordinal(d), span)
        if label and x - last_date_x >= 46:
            last_date_x = x
            out.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{TOP}" y2="{base:.1f}" stroke="{GRID}" stroke-width="0.5"/>'
                       f'<text transform="translate({x - 14:.1f} {base + 14:.1f})" font-size="10">{label}</text>')
    for name, key, label, color, dash in LINES:
        coords = [(px(d), py(name, p[name][key])) for d, p in zip(days, points)]
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in coords)
        out.append(f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2"' + (f' stroke-dasharray="{dash}"' if dash else '') + '/>')
        for (x, y), p in zip(coords, points) if len(points) <= MAX_DOTS and not dash else ():
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{color}"><title>{p["date"]}: {label} '
                       f'{p[name][key]} ({p[name]["percent"]}%)</title></circle>')
    legend_y = HEIGHT - BOTTOM + 30
    for name, series, color in SERIES:
        done, total, percent = points[-1][name]["done"], points[-1][name]["total"], points[-1][name]["percent"]
        out.append(f'<line x1="{LEFT}" x2="{LEFT + 18}" y1="{legend_y + 4:.1f}" y2="{legend_y + 4:.1f}" stroke="{color}" stroke-width="2"/>'
                   f'<text x="{LEFT + 24}" y="{legend_y + 8:.1f}">{series}: implemented <tspan font-weight="bold" fill="{color}">{done}</tspan>'
                   f' / declared {total} ({percent}%)</text>')
        legend_y += 16
    out.append("</svg>")
    return "\n".join(out)


def page(points):
    rows = "\n".join(f'<tr><td>{p["date"]}</td>' + "".join(
        f'<td>{p[name]["done"]}/{p[name]["total"]}</td><td>{p[name]["percent"]}%</td>' for name, _, _ in SERIES) + "</tr>"
        for p in reversed(points))
    return "\n".join([
        '<!DOCTYPE html>',
        '<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
        '<title>AnyPS5 progress history</title>',
        '<style>body{font-family:sans-serif;max-width:1000px;margin:auto;padding:16px}svg{max-width:100%;height:auto}'
        'table{border-collapse:collapse}th,td{border:1px solid #ccc;padding:2px 8px}td+td,th+th{text-align:right}</style>',
        '</head><body>',
        '<h1>Progress history</h1>',
        chart(points),
        f'<p>One point per day with commits on <code>main</code>, taken at the last commit of the day. Every point is measured '
        f'with the current <a href="{progress.SOURCE}/tools/progress.py">tools/progress.py</a> rules and instruction list, '
        'so the series is comparable across days. Hover a point for the exact numbers. Raw numbers: <a href="history.json">history.json</a>. '
        '<a href="progress.html">Back to the current progress</a>.</p>',
        '<table><tr><th>Date</th>' + "".join(f'<th>{escape(label)}</th><th>%</th>' for _, label, _ in SERIES) + '</tr>',
        rows,
        '</table>',
        '</body></html>',
    ]) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--ref", default="HEAD", help="branch or commit whose first-parent history is measured")
    args = parser.parse_args()
    points = collect(args.ref)
    if not points:
        parser.error("no commit with a measurable tree")
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "history.json").write_text(json.dumps(points, indent=2))
    (args.output / "history.svg").write_text(chart(points) + "\n")
    (args.output / "history.html").write_text(page(points))
    print(f"{len(points)} days, {points[0]['date']} .. {points[-1]['date']}")
