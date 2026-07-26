from collections import defaultdict
from pathlib import Path
import json
import math
import re

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle


GROUND_NAMES = {"0", "gnd"}
SUPPLY_PATTERN = re.compile(r"^(vdd|vcc|vss|vee|vp|vn)$", re.IGNORECASE)


def natural_key(value):
    return [int(part) if part.isdigit() else part.lower()
            for part in re.split(r"(\d+)", value)]


def infer_ranks(elements):
    ranks = {"0": 0, "gnd": 0}
    mosfets = [element for element in elements if element["kind"] == "M"]
    for _ in range(max(4, len(mosfets) + 1)):
        changed = False
        for element in mosfets:
            drain, _, source, _ = element["nodes"][:4]
            source_rank = ranks.get(source.lower())
            if source_rank is not None:
                candidate = source_rank + 1
                if candidate > ranks.get(drain.lower(), -1):
                    ranks[drain.lower()] = candidate
                    changed = True
        if not changed:
            break
    max_signal_rank = max(ranks.values(), default=0)
    for element in elements:
        for node in element["nodes"]:
            if SUPPLY_PATTERN.match(node) and node.lower() not in GROUND_NAMES:
                ranks[node.lower()] = max_signal_rank + 1
    return ranks


def spaced_positions(count, left, right):
    if count == 1:
        return [(left + right) / 2]
    return [left + index * (right - left) / (count - 1) for index in range(count)]


def build_layout(parsed):
    elements = parsed["elements"]
    ranks = infer_ranks(elements)
    stage_height = 145
    ground_y = 125
    node_y = {node: ground_y + rank * stage_height for node, rank in ranks.items()}
    nodes_by_rank = defaultdict(list)
    for node, rank in ranks.items():
        if node not in GROUND_NAMES and not SUPPLY_PATTERN.match(node):
            nodes_by_rank[rank].append(node)
    for rank, nodes in nodes_by_rank.items():
        nodes.sort()
        offsets = spaced_positions(len(nodes), -18, 18) if len(nodes) > 1 else [0]
        for node, offset in zip(nodes, offsets):
            node_y[node] += offset
    placements = {}
    node_points = defaultdict(list)

    stage_groups = defaultdict(list)
    for element in elements:
        if element["kind"] != "M":
            continue
        drain, _, source, _ = element["nodes"][:4]
        stage_groups[(ranks.get(source.lower(), 0), ranks.get(drain.lower(), 1))].append(element)

    for stage, group in sorted(stage_groups.items()):
        group.sort(key=lambda element: natural_key(element["name"]))
        count = len(group)
        if count == 1:
            xs = [650]
        elif count == 2:
            xs = [505, 795]
        else:
            xs = spaced_positions(count, 420, 880)
        for element, x in zip(group, xs):
            drain, gate, source, bulk = element["nodes"][:4]
            drain_y = node_y.get(drain.lower(), ground_y + stage[1] * stage_height)
            source_y = node_y.get(source.lower(), ground_y + stage[0] * stage_height)
            placements[element["name"]] = {
                "kind": "M", "x": x, "drain_y": drain_y, "source_y": source_y,
                "drain": drain, "gate": gate, "source": source, "bulk": bulk,
            }
            node_points[drain.lower()].append((x, drain_y))
            node_points[source.lower()].append((x, source_y))

    resistors = [element for element in elements if element["kind"] == "R"]
    for index, element in enumerate(sorted(resistors, key=lambda item: natural_key(item["name"]))):
        node_a, node_b = element["nodes"][:2]
        rank_a = ranks.get(node_a.lower(), 0)
        rank_b = ranks.get(node_b.lower(), 0)
        high, low = (node_a, node_b) if rank_a >= rank_b else (node_b, node_a)
        low_points = node_points.get(low.lower(), [])
        x = sum(point[0] for point in low_points) / len(low_points) if low_points else 520 + index * 260
        high_y = node_y.get(high.lower(), ground_y + max(rank_a, rank_b) * stage_height)
        low_y = node_y.get(low.lower(), ground_y + min(rank_a, rank_b) * stage_height)
        placements[element["name"]] = {
            "kind": "R", "x": x, "high_y": high_y, "low_y": low_y,
            "high": high, "low": low,
        }
        node_points[high.lower()].append((x, high_y))
        node_points[low.lower()].append((x, low_y))

    voltage_sources = sorted(
        [element for element in elements if element["kind"] == "V"],
        key=lambda item: natural_key(item["name"]),
    )
    for element, x in zip(voltage_sources, spaced_positions(len(voltage_sources), 125, 1175)):
        placements[element["name"]] = {
            "kind": "V", "x": x, "y": 48,
            "positive": element["nodes"][0], "negative": element["nodes"][1],
        }

    return {
        "canvas": {"width": 1300, "height": 850},
        "ranks": ranks,
        "node_y": node_y,
        "placements": placements,
        "node_points": {node: points for node, points in node_points.items()},
    }


def draw_resistor(ax, x, low_y, high_y, name, value):
    margin = 35
    y0, y1 = low_y + margin, high_y - margin
    ax.plot([x, x], [low_y, y0], color="#17212b", lw=1.7)
    ax.plot([x, x], [y1, high_y], color="#17212b", lw=1.7)
    ys = [y0 + index * (y1 - y0) / 8 for index in range(9)]
    xs = [x, x - 13, x + 13, x - 13, x + 13, x - 13, x + 13, x - 13, x]
    ax.plot(xs, ys, color="#17212b", lw=1.7)
    ax.text(x + 22, (low_y + high_y) / 2 + 10, name, fontsize=10, va="center")
    ax.text(x + 22, (low_y + high_y) / 2 - 12, value, fontsize=9, va="center", color="#4a5560")


def draw_mosfet(ax, placement, name, model):
    x = placement["x"]
    drain_y = placement["drain_y"]
    source_y = placement["source_y"]
    center_y = (drain_y + source_y) / 2
    channel_half = min(34, abs(drain_y - source_y) * 0.28)
    ax.plot([x, x], [drain_y, center_y + channel_half], color="#17212b", lw=1.7)
    ax.plot([x, x], [center_y - channel_half, source_y], color="#17212b", lw=1.7)
    ax.plot([x, x], [center_y - channel_half, center_y + channel_half], color="#17212b", lw=3.0)
    gate_x = x - 27
    ax.plot([gate_x, gate_x], [center_y - channel_half, center_y + channel_half], color="#17212b", lw=1.7)
    ax.plot([gate_x - 45, gate_x], [center_y, center_y], color="#17212b", lw=1.7)
    ax.annotate("", xy=(x, center_y - channel_half + 8), xytext=(x, center_y + 4),
                arrowprops={"arrowstyle": "-|>", "color": "#17212b", "lw": 1.0})
    ax.text(gate_x - 50, center_y + 7, placement["gate"], fontsize=9, ha="right", va="bottom",
            color="#145a7a")
    ax.text(x + 15, center_y, name, fontsize=10, va="center")


def draw_voltage_source(ax, placement, name, value):
    x, y = placement["x"], placement["y"]
    radius = 22
    ax.add_patch(Circle((x, y), radius, fill=False, edgecolor="#17212b", linewidth=1.6))
    ax.plot([x, x], [y + radius, 87], color="#17212b", lw=1.4)
    ax.plot([x, x], [15, y - radius], color="#17212b", lw=1.4)
    ax.text(x, y + 8, "+", ha="center", va="center", fontsize=11)
    ax.text(x, y - 9, "-", ha="center", va="center", fontsize=11)
    ax.text(x, 94, placement["positive"], fontsize=9, ha="center", color="#145a7a")
    ax.text(x + 28, y, f"{name}\n{value}", fontsize=8, ha="left", va="center", color="#4a5560")


def render(parsed, svg_path, png_path, layout_path=None):
    layout = build_layout(parsed)
    placements = layout["placements"]
    elements_by_name = {element["name"]: element for element in parsed["elements"]}
    fig, ax = plt.subplots(figsize=(13, 8.5))
    ax.set_xlim(0, 1300)
    ax.set_ylim(0, 850)
    ax.axis("off")
    ax.set_facecolor("white")
    fig.patch.set_facecolor("white")

    title = parsed.get("title") or "SPICE Circuit"
    ax.text(55, 815, title, fontsize=20, weight="bold", color="#17212b")
    ax.text(55, 789, "PySpice design | automatic netlist layout",
            fontsize=10, color="#59636e")
    ax.text(55, 766, "MOS model: nmos_model | Net labels denote electrical continuity",
            fontsize=9, color="#59636e")

    for node, points in layout["node_points"].items():
        if not points:
            continue
        y = points[0][1]
        xs = [point[0] for point in points]
        if len(xs) > 1:
            ax.plot([min(xs), max(xs)], [y, y], color="#17212b", lw=1.7)
        for x in xs:
            ax.add_patch(Circle((x, y), 3.2, color="#17212b"))
        label = next((item["name"] for item in parsed["nodes"] if item["name"].lower() == node), node)
        if node not in GROUND_NAMES:
            ax.text(max(xs) + 13, y + 5, label, fontsize=9, color="#145a7a", va="bottom")

    for name, placement in placements.items():
        element = elements_by_name[name]
        if placement["kind"] == "M":
            draw_mosfet(ax, placement, name, element["value_or_model"])
        elif placement["kind"] == "R":
            draw_resistor(ax, placement["x"], placement["low_y"], placement["high_y"],
                          name, element["value_or_model"])

    ax.plot([70, 1230], [15, 15], color="#17212b", lw=1.7)
    for name, placement in placements.items():
        if placement["kind"] == "V":
            draw_voltage_source(ax, placement, name, elements_by_name[name]["value_or_model"])
    ground_points = layout["node_points"].get("0", []) + layout["node_points"].get("gnd", [])
    if ground_points:
        ground_x, ground_node_y = ground_points[0]
        ax.plot([ground_x, ground_x], [15, ground_node_y], color="#17212b", lw=1.7)
    ax.plot([635, 665, 650, 635], [5, 5, -7, 5], color="#17212b", lw=1.5)
    ax.text(675, 4, "0 (GND)", fontsize=9, va="center")

    ax.text(1050, 812, f"{len(parsed['elements'])} elements", fontsize=10, ha="right", color="#59636e")
    ax.text(1235, 812, f"{len(parsed['nodes'])} nodes", fontsize=10, ha="right", color="#59636e")
    fig.tight_layout(pad=0.4)
    svg_path, png_path = Path(svg_path), Path(png_path)
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(svg_path, format="svg", bbox_inches="tight")
    fig.savefig(png_path, format="png", dpi=180, bbox_inches="tight")
    plt.close(fig)
    if layout_path:
        serializable = dict(layout)
        serializable["node_points"] = {
            node: [[float(x), float(y)] for x, y in points]
            for node, points in layout["node_points"].items()
        }
        Path(layout_path).write_text(json.dumps(serializable, indent=2), encoding="utf-8")
    return layout
