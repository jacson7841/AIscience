from dataclasses import asdict, dataclass
from pathlib import Path
import json
import shlex


TERMINAL_COUNTS = {
    "R": 2,
    "C": 2,
    "L": 2,
    "V": 2,
    "I": 2,
    "D": 2,
    "E": 4,
    "G": 4,
    "M": 4,
    "Q": 3,
}


@dataclass
class SpiceElement:
    name: str
    kind: str
    nodes: list[str]
    value_or_model: str
    parameters: list[str]
    source_line: str


def logical_lines(text):
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith("*"):
            continue
        if stripped.startswith("+") and lines:
            lines[-1] += " " + stripped[1:].strip()
        else:
            lines.append(stripped)
    return lines


def parse_netlist(text):
    title = ""
    directives = []
    models = []
    elements = []
    for index, line in enumerate(logical_lines(text)):
        if line.lower().startswith(".title"):
            title = line[6:].strip()
            continue
        if index == 0 and not line.startswith(".") and line[0].upper() not in TERMINAL_COUNTS:
            title = line
            continue
        if line.lower().startswith(".model"):
            models.append(line)
            continue
        if line.startswith("."):
            directives.append(line)
            continue
        tokens = shlex.split(line, posix=False)
        if not tokens:
            continue
        kind = tokens[0][0].upper()
        terminal_count = TERMINAL_COUNTS.get(kind)
        if terminal_count is None or len(tokens) < terminal_count + 2:
            directives.append(line)
            continue
        nodes = tokens[1:1 + terminal_count]
        remainder = tokens[1 + terminal_count:]
        value_or_model = remainder[0] if remainder else ""
        elements.append(SpiceElement(
            name=tokens[0], kind=kind, nodes=nodes,
            value_or_model=value_or_model,
            parameters=remainder[1:], source_line=line,
        ))

    node_map = {}
    for element in elements:
        for terminal_index, node in enumerate(element.nodes):
            node_map.setdefault(node, []).append({
                "element": element.name,
                "terminal_index": terminal_index,
            })
    return {
        "title": title,
        "elements": [asdict(element) for element in elements],
        "nodes": [
            {"name": name, "connections": connections}
            for name, connections in sorted(node_map.items(), key=lambda item: item[0].lower())
        ],
        "models": models,
        "directives": directives,
    }


def parse_file(path):
    return parse_netlist(Path(path).read_text(encoding="utf-8"))


def write_json(parsed, path):
    Path(path).write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
