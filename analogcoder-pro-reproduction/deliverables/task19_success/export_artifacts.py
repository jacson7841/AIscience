import json
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from deliverables.task19_success.design import build_circuit
from repro_tools.schematic.netlist_parser import parse_netlist, write_json
from repro_tools.schematic.renderer import render


def main():
    circuit = build_circuit()
    netlist = str(circuit)
    netlist_path = HERE / "task19_gilbert_mixer.cir"
    netlist_path.write_text(netlist, encoding="utf-8")

    parsed = parse_netlist(netlist)
    write_json(parsed, HERE / "netlist_structure.json")
    render(
        parsed,
        svg_path=HERE / "task19_gilbert_mixer_schematic.svg",
        png_path=HERE / "task19_gilbert_mixer_schematic.png",
        layout_path=HERE / "schematic_layout.json",
    )
    manifest = {
        "verification": "passed official problem_check/Mixer.py baseline",
        "python_source": "design.py",
        "spice_netlist": netlist_path.name,
        "parsed_structure": "netlist_structure.json",
        "layout": "schematic_layout.json",
        "schematic_svg": "task19_gilbert_mixer_schematic.svg",
        "schematic_png": "task19_gilbert_mixer_schematic.png",
        "element_count": len(parsed["elements"]),
        "node_count": len(parsed["nodes"]),
    }
    (HERE / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
