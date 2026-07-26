import argparse
import importlib.util
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pyspice_runtime import configure_pyspice


def load_design(path):
    spec = importlib.util.spec_from_file_location("candidate_design", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "build_circuit"):
        raise AttributeError("Candidate must define build_circuit(...)")
    return module.build_circuit


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    args = parser.parse_args()
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    configure_pyspice()
    build_circuit = load_design(args.candidate.resolve())

    dc_circuit = build_circuit()
    dc = dc_circuit.simulator().operating_point()
    bias = float(dc["vout"][0])

    ac_circuit = build_circuit(input_ac=1e-3)
    ac = ac_circuit.simulator().ac(
        variation="dec", number_of_points=60, start_frequency=10,
        stop_frequency=100e3,
    )
    frequencies = np.asarray(ac.frequency, dtype=float)
    gains = np.abs(np.asarray(ac["vout"], dtype=complex)) / 1e-3
    gain_100 = float(gains[np.argmin(np.abs(frequencies - 100))])
    gain_10k = float(gains[np.argmin(np.abs(frequencies - 10e3))])
    attenuation_db = float(20 * np.log10(gain_100 / gain_10k))
    cutoff_target = gain_100 / np.sqrt(2)
    cutoff = float(frequencies[np.argmin(np.abs(gains - cutoff_target))])

    tran_circuit = build_circuit(
        input_amplitude=0.1, input_frequency=100.0, transient=True
    )
    tran = tran_circuit.simulator().transient(step_time=10e-6, end_time=50e-3)
    time_values = np.asarray(tran.time, dtype=float)
    output_values = np.asarray(tran["vout"], dtype=float)
    settled = output_values[time_values >= 20e-3]
    transient_amplitude = float((np.max(settled) - np.min(settled)) / 2)
    output_min = float(np.min(settled))
    output_max = float(np.max(settled))

    checks = {
        "bias": abs(bias - 2.5) <= 0.25,
        "gain": 4.5 <= gain_100 <= 5.5,
        "cutoff": 700 <= cutoff <= 1300,
        "attenuation": attenuation_db >= 15,
        "no_clipping": (0.2 <= output_min and output_max <= 4.8 and
                         0.40 <= transient_amplitude <= 0.60),
    }
    metrics = {
        "bias_volts": bias,
        "gain_at_100_hz": gain_100,
        "cutoff_hz": cutoff,
        "attenuation_100_hz_to_10_khz_db": attenuation_db,
        "transient_output_amplitude_volts": transient_amplitude,
        "transient_output_min_volts": output_min,
        "transient_output_max_volts": output_max,
    }
    passed = all(checks.values())
    result = {"status": "pass" if passed else "fail", "checks": checks, "metrics": metrics}
    (args.artifact_dir / "result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )

    fig, axes = plt.subplots(2, 1, figsize=(8, 7))
    axes[0].semilogx(frequencies, 20 * np.log10(gains))
    axes[0].axvline(1000, color="tab:red", linestyle="--")
    axes[0].set(xlabel="Frequency (Hz)", ylabel="Gain (dB)", title="AC response")
    axes[0].grid(True, which="both")
    axes[1].plot(time_values * 1000, output_values)
    axes[1].set(xlabel="Time (ms)", ylabel="Vout (V)", title="100 Hz, 100 mV peak transient")
    axes[1].grid(True)
    fig.tight_layout()
    fig.savefig(args.artifact_dir / "response.png", dpi=150)
    plt.close(fig)
    print(json.dumps(result, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
