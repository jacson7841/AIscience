import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
configured_ngspice = os.environ.get("NGSPICE_EXECUTABLE")
discovered_ngspice = shutil.which("ngspice_con.exe") or shutil.which("ngspice")
NGSPICE_EXE = Path(configured_ngspice or discovered_ngspice).resolve() \
    if configured_ngspice or discovered_ngspice else None


def package_versions():
    modules = [
        "PySpice", "openai", "numpy", "scipy", "pandas", "matplotlib", "cffi",
        "schemdraw",
    ]
    versions = {}
    for name in modules:
        module = __import__(name)
        versions[name] = getattr(module, "__version__", "unknown")
    return versions


def main():
    report = {
        "python": sys.version,
        "python_executable": sys.executable,
        "platform": platform.platform(),
        "packages": package_versions(),
        "ngspice_executable": str(NGSPICE_EXE) if NGSPICE_EXE else None,
        "ngspice_executable_exists": bool(NGSPICE_EXE and NGSPICE_EXE.is_file()),
        "ngspice_dll": str(ROOT / "vendor/ngspice-46-dll/Spice64_dll/dll-vs/ngspice.dll"),
        "dashscope_api_key_present": bool(os.environ.get("DASHSCOPE_API_KEY")),
        "bailian_base_url": os.environ.get(
            "BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
    }
    if NGSPICE_EXE and NGSPICE_EXE.is_file():
        result = subprocess.run(
            [str(NGSPICE_EXE), "--version"], capture_output=True, text=True, timeout=15
        )
        report["ngspice_version_output"] = (result.stdout + result.stderr).strip()

    from pyspice_runtime import configure_pyspice
    configure_pyspice()
    from PySpice.Spice.Netlist import Circuit
    from PySpice.Unit import u_kOhm, u_V

    circuit = Circuit("environment check")
    circuit.V("in", "vin", circuit.gnd, 5 @ u_V)
    circuit.R("top", "vin", "vout", 1 @ u_kOhm)
    circuit.R("bottom", "vout", circuit.gnd, 1 @ u_kOhm)
    vout = float(circuit.simulator().operating_point()["vout"][0])
    report["pyspice_rc_vout_volts"] = vout
    report["pyspice_rc_pass"] = abs(vout - 2.5) < 1e-6

    output = ROOT / "run_artifacts" / "environment_check.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["pyspice_rc_pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
