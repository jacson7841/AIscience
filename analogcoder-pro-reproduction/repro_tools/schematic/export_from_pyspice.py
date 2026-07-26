import argparse
import json
import runpy
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pyspice_runtime import configure_pyspice
from repro_tools.schematic.netlist_parser import parse_netlist, write_json
from repro_tools.schematic.renderer import render
from repro_tools.schematic.schemdraw_renderer import render_vcvs_frontend


def export_candidate(candidate, output_dir):
    candidate = Path(candidate).resolve()
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    configure_pyspice()
    namespace = runpy.run_path(str(candidate), run_name="pyspice_schematic_export")
    circuit = namespace.get("circuit")
    if circuit is None and callable(namespace.get("build_circuit")):
        circuit = namespace["build_circuit"]()
    if circuit is None:
        raise RuntimeError("PySpice file must expose `circuit` or `build_circuit()`")

    netlist = str(circuit)
    netlist_path = output_dir / "circuit.cir"
    netlist_path.write_text(netlist, encoding="utf-8")
    parsed = parse_netlist(netlist)
    write_json(parsed, output_dir / "netlist_structure.json")
    if any(element["kind"] == "E" for element in parsed["elements"]):
        render_vcvs_frontend(
            parsed,
            svg_path=output_dir / "schematic.svg",
            png_path=output_dir / "schematic.png",
        )
        renderer = "schemdraw-vcvs-frontend"
    else:
        render(
            parsed,
            svg_path=output_dir / "schematic.svg",
            png_path=output_dir / "schematic.png",
            layout_path=output_dir / "schematic_layout.json",
        )
        renderer = "matplotlib-mos-hierarchy"
    manifest = {
        "source": str(candidate),
        "spice_netlist": "circuit.cir",
        "parsed_structure": "netlist_structure.json",
        "schematic_svg": "schematic.svg",
        "schematic_png": "schematic.png",
        "renderer": renderer,
        "element_count": len(parsed["elements"]),
        "node_count": len(parsed["nodes"]),
    }
    (output_dir / "schematic_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_candidate(args.candidate, args.output_dir), indent=2))


if __name__ == "__main__":
    main()
