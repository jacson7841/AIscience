import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def extract_code(answer):
    matches = re.findall(r"```(?:python)?\s*\n(.*?)```", answer, flags=re.DOTALL | re.IGNORECASE)
    if not matches:
        raise ValueError("Response did not contain a fenced Python code block")
    return matches[-1].strip() + "\n"


def normalize_pyspice_imports(code):
    """Pin generated candidates to the PySpice 1.5 import surface used by this repo."""
    kept_lines = []
    for line in code.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("from PySpice") or stripped.startswith("import PySpice"):
            continue
        kept_lines.append(line)
    preamble = (
        "from PySpice.Spice.Netlist import Circuit\n"
        "from PySpice.Unit import *\n\n"
    )
    return preamble + "\n".join(kept_lines).strip() + "\n"


def complete(client, args, messages, label, events):
    last_error = None
    for attempt in range(1, args.api_max_retries + 1):
        started = time.time()
        try:
            response = client.chat.completions.create(
                model=args.model, messages=messages, temperature=args.temperature
            )
            if not response.choices or response.choices[0].message.content is None:
                raise RuntimeError("Empty model response")
            events.append({"label": label, "attempt": attempt, "status": "success",
                           "elapsed_seconds": round(time.time() - started, 3)})
            return response
        except Exception as exc:
            last_error = exc
            events.append({"label": label, "attempt": attempt, "status": "error",
                           "error_type": type(exc).__name__, "error": str(exc),
                           "elapsed_seconds": round(time.time() - started, 3)})
            if attempt < args.api_max_retries:
                time.sleep(args.api_retry_delay)
    raise RuntimeError(f"{label} failed after {args.api_max_retries} API attempts") from last_error


def checker_env():
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["MPLBACKEND"] = "Agg"
    mpl = ROOT / ".runtime" / "matplotlib"
    mpl.mkdir(parents=True, exist_ok=True)
    env["MPLCONFIGDIR"] = str(mpl)
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def add_usage(total, response):
    usage = getattr(response, "usage", None)
    if usage:
        total["prompt"] += usage.prompt_tokens or 0
        total["completion"] += usage.completion_tokens or 0
        total["total"] += usage.total_tokens or 0


def run_once(client, args, run_id):
    started = time.time()
    run_dir = args.output_dir / f"run_{run_id}"
    run_dir.mkdir(parents=True, exist_ok=True)
    task = (HERE / "task.md").read_text(encoding="utf-8")
    messages = [
        {"role": "system", "content": "You are an analog circuit design and PySpice expert."},
        {"role": "user", "content": task},
    ]
    events = []
    tokens = {"prompt": 0, "completion": 0, "total": 0}
    attempts = []
    passed = False

    for attempt in range(args.max_repairs + 1):
        label = "initial_generation" if attempt == 0 else f"repair_{attempt}"
        response = complete(client, args, messages, label, events)
        add_usage(tokens, response)
        answer = response.choices[0].message.content
        (run_dir / f"attempt_{attempt}_prompt.json").write_text(
            json.dumps(messages, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (run_dir / f"attempt_{attempt}_answer.md").write_text(answer, encoding="utf-8")
        candidate = run_dir / f"attempt_{attempt}_candidate.py"
        checker_dir = run_dir / f"attempt_{attempt}_evaluation"
        try:
            raw_code = extract_code(answer)
            candidate.write_text(normalize_pyspice_imports(raw_code), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(HERE / "checker.py"), str(candidate),
                 "--artifact-dir", str(checker_dir)],
                cwd=ROOT, env=checker_env(), capture_output=True, text=True, timeout=120
            )
            stdout, stderr, returncode = result.stdout, result.stderr, result.returncode
        except Exception as exc:
            stdout, stderr, returncode = "", f"{type(exc).__name__}: {exc}", 2
        (run_dir / f"attempt_{attempt}_stdout.txt").write_text(stdout, encoding="utf-8")
        (run_dir / f"attempt_{attempt}_stderr.txt").write_text(stderr, encoding="utf-8")
        attempts.append({"attempt": attempt, "returncode": returncode,
                         "candidate": candidate.name, "evaluation": checker_dir.name,
                         "pyspice_imports_normalized": True})
        messages.append({"role": "assistant", "content": answer})
        if returncode == 0:
            schematic_dir = run_dir / f"attempt_{attempt}_schematic"
            schematic_dir.mkdir(parents=True, exist_ok=True)
            try:
                export = subprocess.run(
                    [sys.executable, str(ROOT / "repro_tools" / "schematic" /
                                         "export_from_pyspice.py"), str(candidate),
                     "--output-dir", str(schematic_dir)],
                    cwd=ROOT, env=checker_env(), capture_output=True, text=True,
                    timeout=120,
                )
                export_stdout = export.stdout
                export_stderr = export.stderr
                export_returncode = export.returncode
            except Exception as exc:
                export_stdout = ""
                export_stderr = f"{type(exc).__name__}: {exc}"
                export_returncode = 2
            (schematic_dir / "export_stdout.txt").write_text(
                export_stdout, encoding="utf-8"
            )
            (schematic_dir / "export_stderr.txt").write_text(
                export_stderr, encoding="utf-8"
            )
            attempts[-1]["schematic"] = schematic_dir.name
            attempts[-1]["schematic_export_returncode"] = export_returncode
            passed = True
            break
        if attempt < args.max_repairs:
            feedback = (
                "The deterministic testbench rejected the design. Rewrite the complete code.\n\n"
                f"Checker stdout:\n{stdout[-6000:]}\n\nChecker stderr:\n{stderr[-6000:]}"
            )
            messages.append({"role": "user", "content": feedback})

    record = {
        "schema_version": 1, "run_id": run_id,
        "status": "success" if passed else "failed", "model": args.model,
        "base_url": args.base_url, "max_repairs": args.max_repairs,
        "tokens": tokens, "api_events": events, "attempts": attempts,
        "python": sys.version, "python_executable": sys.executable,
        "started_at_utc": datetime.fromtimestamp(started, timezone.utc).isoformat(),
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": round(time.time() - started, 3),
    }
    (run_dir / "run_record.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(json.dumps({
        "run_id": run_id, "status": record["status"], "tokens": tokens,
        "attempts": attempts,
    }, indent=2))
    return passed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default=os.environ.get("BAILIAN_CODE_MODEL", "qwen3-coder-plus"))
    parser.add_argument("--base-url", default=os.environ.get(
        "BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"))
    parser.add_argument("--api-key", default=os.environ.get("DASHSCOPE_API_KEY"))
    parser.add_argument("--temperature", type=float, default=0.5)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--max-repairs", type=int, default=3)
    parser.add_argument("--api-max-retries", type=int, default=3)
    parser.add_argument("--api-retry-delay", type=float, default=5)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "run_artifacts" / "lm358_agent")
    args = parser.parse_args()
    if not args.api_key:
        parser.error("Set DASHSCOPE_API_KEY before running the LM358 task")
    client = OpenAI(
        api_key=args.api_key, base_url=args.base_url, max_retries=0, timeout=60.0
    )
    start_run = 0
    while (args.output_dir / f"run_{start_run}" / "run_record.json").is_file():
        start_run += 1
    results = [
        run_once(client, args, run_id)
        for run_id in range(start_run, start_run + args.runs)
    ]
    return 0 if all(results) else 2


if __name__ == "__main__":
    raise SystemExit(main())
