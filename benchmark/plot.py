# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements. See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership. The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License. You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied. See the License for the
# specific language governing permissions and limitations
# under the License.

"""Chart the results of run.py as SVG and PNG files and one report.html, and tabulate them in summary.md.

Each chart answers one question for one protocol and its serialization:

- the peak throughput of each server on one core, the headline: a group of
  bars per payload, one bar per implementation, the median of the rounds
  with their range;
- the P99 latency of each server on one core at one number of calls in
  flight;
- the peak throughput of each Dubbo server on several cores;
- the peak throughput of the Dubbo Python consumer on one core.

With several runs, the charts show the first, and the table every run, the
first the baseline.

Every implementation keeps its color and place in every chart. report.html
holds every chart, with the values of each mark on hover, the environment
and the table, and needs nothing else to open.
"""

import argparse
import html
import json
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any

import altair as alt
import vl_convert

PROTOCOLS = {"tri": ("Triple + Protobuf", "triple-protobuf"), "dubbo": ("Dubbo + Hessian 2", "dubbo-hessian2")}
IMPLEMENTATIONS = {
    "python": "Dubbo Python",
    "java": "Dubbo Java",
    "go": "Dubbo Go",
    "grpcio": "grpcio",
    "grpclib": "grpclib",
}
# The categorical palette in its fixed order: each implementation keeps its color, Dubbo Python the first.
COLORS = dict(zip(IMPLEMENTATIONS, ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4"], strict=True))
INK, MUTED, GRID, AXIS = "#1f2329", "#5b6170", "#eceef2", "#c9ccd3"
# A load that used this share of the cores it may use may be what limits the throughput.
LOAD_LIMIT = 0.9


@alt.theme.register("benchmark", enable=True)
def theme() -> alt.theme.ThemeConfig:
    return {
        "config": {
            "font": "Inter, Helvetica, Arial, sans-serif",
            "background": "#ffffff",
            "view": {"stroke": None},
            "title": {"fontSize": 14, "fontWeight": 600, "anchor": "start", "color": INK, "offset": 10},
            "axis": {
                "labelFontSize": 11, "titleFontSize": 11.5, "titleFontWeight": 400, "titleColor": MUTED,
                "labelColor": MUTED, "gridColor": GRID, "domainColor": AXIS, "tickColor": AXIS,
            },
            "axisX": {"grid": False},
            "legend": {"orient": "top", "labelFontSize": 11.5, "labelColor": INK, "title": None, "symbolType": "square"},
            "header": {"labelFontSize": 11.5, "labelColor": INK, "title": None},
        }
    }  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("runs", nargs="+", type=Path, help="directories of run.py, the first the baseline")
    parser.add_argument("--concurrency", type=int, default=64, help="the calls in flight latency is compared at")
    parser.add_argument("--out", type=Path, help="where to write the charts; the first run by default")
    args = parser.parse_args()
    out = args.out or args.runs[0]
    out.mkdir(parents=True, exist_ok=True)

    runs = [run.name for run in args.runs]
    points = aggregate(
        {**json.loads(line), "run": run.name}
        for run in args.runs
        for line in (run / "results.jsonl").read_text().splitlines()
        if line
    )
    environment = json.loads((args.runs[0] / "env.json").read_text())
    charts = []
    for protocol, (name, slug) in PROTOCOLS.items():
        servers = [p for p in points if p["run"] == runs[0] and p["side"] == "server" and p["protocol"] == protocol]
        one_core = [p for p in servers if p["cores"] == 1]
        multi_core = [p for p in servers if (p["cores"] or 0) > 1]
        consumer = [p for p in points if p["run"] == runs[0] and p["side"] == "client" and p["protocol"] == protocol]
        if one_core:
            charts.append((f"{slug}-throughput-one-core", peak_chart(one_core, f"Throughput, one core · {name}")))
            charts.append((f"{slug}-latency", latency_chart(one_core, name, args.concurrency)))
        if multi_core:
            cores = max(p["cores"] for p in multi_core)
            title = f"Throughput, {cores} cores · {name}"
            charts.append((f"{slug}-throughput-multi-core", peak_chart(multi_core, title)))
        if consumer:
            charts.append((f"{slug}-consumer", peak_chart(consumer, f"Consumer throughput, one core · {name}")))

    for file, chart in charts:
        spec = chart.to_dict()
        (out / f"{file}.svg").write_text(vl_convert.vegalite_to_svg(spec))
        (out / f"{file}.png").write_bytes(vl_convert.vegalite_to_png(spec, scale=2))
    (out / "summary.md").write_text(table(points, runs))
    (out / "report.html").write_text(report(charts, environment, points, runs))
    print(f"Wrote {len(charts)} charts, report.html and summary.md to {out}")


def aggregate(rows) -> list[dict[str, Any]]:
    """Return each point once, with the median of its rounds, and the range of their throughput."""
    rounds = defaultdict(list)
    for row in rows:
        key = tuple(
            row.get(field)
            for field in (
                "run",
                "scenario",
                "side",
                "implementation",
                "protocol",
                "loop",
                "size",
                "concurrency",
                "cores",
            )
        )
        rounds[key].append(row)
    points = []
    for each in rounds.values():
        first = each[0]
        limited = any(
            row.get("load_cores") is not None
            and row.get("load_cores_available")
            and row["load_cores"] >= LOAD_LIMIT * row["load_cores_available"]
            for row in each
        )
        cpu = "server_cpu_us" if first["side"] == "server" else "client_cpu_us"
        points.append({
            **{field: first.get(field) for field in ("run", "scenario", "side", "implementation", "protocol", "loop", "size", "concurrency", "cores")},
            "rounds": len(each),
            "rps": median([row["rps"] for row in each]),
            "rps_min": min(row["rps"] for row in each),
            "rps_max": max(row["rps"] for row in each),
            "cpu_us": median([row.get(cpu) for row in each]),
            "server_cores": median([row.get("server_cores") for row in each]),
            "rss_mib": median([row.get("server_rss_mib") for row in each]),
            "p50_ms": ms(median([row["latency_us"].get("p50") for row in each])),
            "p99_ms": ms(median([row["latency_us"].get("p99") for row in each])),
            "errors": sum(sum(row["errors"].values()) for row in each),
            "pinned": all(row.get("pinned") for row in each),
            "load": first.get("load") or first.get("peer"),
            "load_limited": limited,
        })  # fmt: skip
    return points


def median(values: list[Any]) -> float | None:
    values = [each for each in values if each is not None]
    return statistics.median(values) if values else None


def ms(microseconds: float | None) -> float | None:
    return None if microseconds is None else round(microseconds / 1000, 3)


def label(point: dict[str, Any]) -> str:
    return IMPLEMENTATIONS[point["implementation"]]


def size(point: dict[str, Any]) -> str:
    return f"{point['size']:,}"


def sizes(points) -> list[str]:
    return [f"{each:,}" for each in sorted({point["size"] for point in points})]


def implementations(points) -> tuple[list[str], list[str]]:
    """Return the names of the implementations among ``points``, in their fixed order, and their colors."""
    present = [each for each in IMPLEMENTATIONS if any(point["implementation"] == each for point in points)]
    return [IMPLEMENTATIONS[each] for each in present], [COLORS[each] for each in present]


def bars(data, x_sort, names, colors, y, y_title, title, tooltip, low=None, high=None, mark_label="text"):
    """Draw a group of bars per payload, one bar per implementation, labelled, with a range when given."""
    base = alt.Chart(alt.Data(values=data)).encode(
        x=alt.X("payload:N", sort=x_sort, title="Payload (bytes)", axis=alt.Axis(labelAngle=0)),
        xOffset=alt.XOffset("implementation:N", sort=names),
    )
    layers = [
        base.mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3).encode(
            y=alt.Y(f"{y}:Q", title=y_title, axis=alt.Axis(format="~s")),
            color=alt.Color("implementation:N", sort=names, scale=alt.Scale(domain=names, range=colors)),
            tooltip=tooltip,
        )
    ]
    if low is not None:
        layers.append(base.mark_rule(color=MUTED, strokeWidth=1).encode(y=f"{low}:Q", y2=f"{high}:Q"))
    layers.append(
        base.mark_text(dy=-6, fontSize=10, color=MUTED).encode(y=alt.Y(f"{high or y}:Q"), text=f"{mark_label}:N")
    )
    # Each bar as wide in every chart: the step of the offset is that of one bar.
    width = alt.Step(40)
    return alt.layer(*layers).properties(width=width, height=280, title=title)


def peak_chart(points, title: str) -> alt.LayerChart:
    best: dict[tuple[str, int], dict[str, Any]] = {}
    for point in points:
        key = (point["implementation"], point["size"])
        # A point where calls failed is the peak only when every point of its bar has failures.
        if key not in best or (not point["errors"], point["rps"]) > (not best[key]["errors"], best[key]["rps"]):
            best[key] = point
    data = [
        {
            "implementation": label(p), "payload": size(p), "rps": p["rps"], "low": p["rps_min"], "high": p["rps_max"],
            "text": f"{p['rps'] / 1000:.3g}k" + (" †" if p["load_limited"] else ""), "concurrency": p["concurrency"],
            "cpu": p["cpu_us"], "p99": p["p99_ms"], "cores": p["server_cores"], "errors": p["errors"],
            "load": p["load"], "rounds": p["rounds"],
        }
        for p in best.values()
    ]  # fmt: skip
    names, colors = implementations(points)
    tooltip = [
        alt.Tooltip("implementation:N", title="Implementation"), alt.Tooltip("payload:N", title="Payload (bytes)"),
        alt.Tooltip("rps:Q", title="Calls / s (median)", format=",.0f"),
        alt.Tooltip("low:Q", title="Lowest round", format=",.0f"), alt.Tooltip("high:Q", title="Highest round", format=",.0f"),
        alt.Tooltip("concurrency:Q", title="Calls in flight"), alt.Tooltip("cpu:Q", title="CPU of the side measured (µs / call)", format=".1f"),
        alt.Tooltip("cores:Q", title="Server cores used", format=".2f"), alt.Tooltip("p99:Q", title="P99 (ms)", format=".2f"),
        alt.Tooltip("errors:Q", title="Errors"), alt.Tooltip("load:N", title="Load"),
    ]  # fmt: skip
    return bars(
        data, sizes(points), names, colors, "rps", "Throughput (calls / s)", title, tooltip, low="low", high="high",
    )  # fmt: skip


def latency_chart(points, protocol: str, concurrency: int) -> alt.LayerChart:
    measured = sorted({p["concurrency"] for p in points})
    concurrency = min(measured, key=lambda each: abs(each - concurrency))
    chosen = [p for p in points if p["concurrency"] == concurrency and p["p99_ms"] is not None]
    data = [
        {
            "implementation": label(p), "payload": size(p), "p99": p["p99_ms"], "p50": p["p50_ms"],
            "text": f"{p['p99_ms']:.3g}", "rps": p["rps"], "errors": p["errors"], "load": p["load"],
        }
        for p in chosen
    ]  # fmt: skip
    names, colors = implementations(chosen)
    tooltip = [
        alt.Tooltip("implementation:N", title="Implementation"), alt.Tooltip("payload:N", title="Payload (bytes)"),
        alt.Tooltip("p99:Q", title="P99 (ms)", format=".3f"), alt.Tooltip("p50:Q", title="P50 (ms)", format=".3f"),
        alt.Tooltip("rps:Q", title="Calls / s", format=",.0f"), alt.Tooltip("load:N", title="Load"),
    ]  # fmt: skip
    return bars(
        data, sizes(chosen), names, colors, "p99", "P99 latency (ms)",
        f"P99 latency, one core, {concurrency} in flight · {protocol}", tooltip,
    )  # fmt: skip


def table(points, runs: list[str]) -> str:
    columns = ["Run"] if len(runs) > 1 else []
    columns += ["Scenario", "Side", "Protocol", "Implementation", "Payload (bytes)", "In flight", "Calls/s (median)"]
    columns += [
        "Lowest",
        "Highest",
        "CPU µs/call",
        "Server cores",
        "Server RSS MiB",
        "P50 ms",
        "P99 ms",
        "Errors",
        "Load or peer",
    ]
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    order = list(IMPLEMENTATIONS)

    def key(p):
        return (
            runs.index(p["run"]),
            p["scenario"],
            p["side"],
            p["protocol"],
            p["size"],
            p["concurrency"],
            order.index(p["implementation"]),
            p["loop"] or "",
        )

    for p in sorted(points, key=key):
        name = label(p) + (f" ({p['loop']})" if p["loop"] else "")
        cells = [p["run"]] if len(runs) > 1 else []
        cells += [p["scenario"], p["side"], PROTOCOLS[p["protocol"]][0], name, size(p), p["concurrency"]]
        cells += [f"{p['rps']:,.0f}", f"{p['rps_min']:,.0f}", f"{p['rps_max']:,.0f}", p["cpu_us"], p["server_cores"]]
        cells += [
            p["rss_mib"],
            p["p50_ms"],
            p["p99_ms"],
            p["errors"],
            (p["load"] or "") + (" †" if p["load_limited"] else ""),
        ]
        lines.append("| " + " | ".join("" if cell is None else str(cell) for cell in cells) + " |")
    return "\n".join(lines) + "\n"


def report(charts, environment: dict[str, Any], points, runs: list[str]) -> str:
    """Return a page holding every chart, with the values of each mark on hover, the environment and the table."""
    specs = {f"chart-{index}": chart.to_dict() for index, (_, chart) in enumerate(charts)}
    sections = "\n".join(f'<figure id="chart-{index}"></figure>' for index in range(len(charts)))
    rows = "\n".join(
        f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(json.dumps(value) if isinstance(value, dict) else str(value))}</td></tr>"
        for key, value in environment.items()
    )
    summary = table(points, runs).splitlines()
    head = "".join(f"<th>{html.escape(cell.strip())}</th>" for cell in summary[0].strip("|").split("|"))
    body = "\n".join(
        "<tr>" + "".join(f"<td>{html.escape(cell.strip())}</td>" for cell in line.strip("|").split("|")) + "</tr>"
        for line in summary[2:]
    )
    pinning = " by taskset" if environment.get("taskset") else ", by GOMAXPROCS and ActiveProcessorCount alone"
    script = vl_convert.javascript_bundle()
    embed = f"const specs = {json.dumps(specs)};\nfor (const [id, spec] of Object.entries(specs)) vegaEmbed('#' + id, spec, {{actions: false}});"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dubbo Python benchmarks</title>
<style>
body {{ font-family: Inter, Helvetica, Arial, sans-serif; color: {INK}; background: #fff; margin: 32px auto; max-width: 1100px; padding: 0 16px; }}
h1 {{ font-size: 26px; }} h2 {{ font-size: 19px; margin-top: 40px; }}
figure {{ margin: 28px 0; overflow-x: auto; }}
table {{ border-collapse: collapse; font-size: 12.5px; }} th, td {{ border-bottom: 1px solid {GRID}; padding: 4px 8px; text-align: left; }}
.wide {{ overflow-x: auto; }}
</style></head><body>
<h1>Dubbo Python benchmarks</h1>
<ul>
<li>A unary echo of bytes. Each bar is the median of the rounds; the thin line on it spans them.</li>
<li><b>One core</b>: every server held to one core{pinning}; the Python ones run one event loop.
<b>Multi-core</b>: each Dubbo server held to several cores in the same way; a Python process serves on one.</li>
<li>Throughput is the best over the numbers of calls in flight; † marks a load that used most of its cores.</li>
<li>Hover a bar for all its numbers.</li>
</ul>
{sections}
<h2>Environment</h2><table>{rows}</table>
<h2>Every point</h2><div class="wide"><table><tr>{head}</tr>{body}</table></div>
<script>{script}</script>
<script>{embed}</script>
</body></html>
"""


if __name__ == "__main__":
    main()
