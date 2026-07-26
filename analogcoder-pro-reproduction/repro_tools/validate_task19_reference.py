import json
import os
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_DIR = ROOT / "run_artifacts" / "task19_reference"


def main():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    sample = (ROOT / "sample_design" / "p19" / "p19.py").read_text(encoding="utf-8")
    design = sample.split("# Gilbert Cell Mixer Functionality Test", 1)[0]
    checker = (ROOT / "problem_check" / "Mixer.py").read_text(encoding="utf-8")
    figure_base = (ARTIFACT_DIR / "task19_waveform").as_posix()
    checker = checker.replace("[FIGURE_PATH]", figure_base)
    validation_code = (
        "from pyspice_runtime import configure_pyspice\nconfigure_pyspice()\n" +
        design + "\n" + checker
    )
    code_path = ARTIFACT_DIR / "reference_with_official_checker.py"
    code_path.write_text(validation_code, encoding="utf-8")

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["MPLBACKEND"] = "Agg"
    mpl = ROOT / ".runtime" / "matplotlib"
    mpl.mkdir(parents=True, exist_ok=True)
    env["MPLCONFIGDIR"] = str(mpl)
    env["PYTHONPATH"] = str(ROOT)
    result = subprocess.run(
        [sys.executable, str(code_path)], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=120
    )
    (ARTIFACT_DIR / "stdout.txt").write_text(result.stdout, encoding="utf-8")
    (ARTIFACT_DIR / "stderr.txt").write_text(result.stderr, encoding="utf-8")

    components = []
    for frequency, magnitude in re.findall(
        r"Frequency:\s*([0-9.]+) Hz, Magnitude:\s*([0-9.]+) V", result.stdout
    ):
        components.append({"frequency_hz": float(frequency), "magnitude_volts": float(magnitude)})
    record = {
        "status": "pass" if result.returncode == 0 else "fail",
        "returncode": result.returncode,
        "checker": "problem_check/Mixer.py",
        "candidate": "sample_design/p19/p19.py",
        "required_components_hz": [200, 2200],
        "threshold_volts": 1e-3,
        "reported_components": components,
        "waveform": "task19_waveform.png",
    }
    (ARTIFACT_DIR / "result.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
