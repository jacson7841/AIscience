from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pyspice_runtime import configure_pyspice

configure_pyspice()

from PySpice.Spice.Netlist import Circuit
from PySpice.Unit import u_kOhm, u_V


circuit = Circuit("RC Smoke Test")
circuit.V("in", "vin", circuit.gnd, 5 @ u_V)
circuit.R("top", "vin", "vout", 1 @ u_kOhm)
circuit.R("bottom", "vout", circuit.gnd, 1 @ u_kOhm)

simulator = circuit.simulator()
analysis = simulator.operating_point()
vout = float(analysis["vout"][0])
print(f"vout={vout:.6f} V")

if abs(vout - 2.5) > 1e-6:
    raise SystemExit(f"Unexpected divider output: {vout}")
