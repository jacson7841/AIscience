import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))

from PySpice.Unit import *
from pyspice_runtime import configure_pyspice
from deliverables.task19_success.design import build_circuit


configure_pyspice()
circuit = build_circuit()
checker = (ROOT / "problem_check" / "Mixer.py").read_text(encoding="utf-8")
checker = checker.replace("[FIGURE_PATH]", (HERE / "official_verification_waveform").as_posix())
exec(compile(checker, "problem_check/Mixer.py", "exec"), globals(), globals())
