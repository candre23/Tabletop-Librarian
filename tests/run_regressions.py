from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = ROOT / "tests"
GROUPS = ("regression", "system_packs", "ai", "library")


def _local_venv_python() -> Path | None:
    """Return TTL's project-local virtualenv Python, if present."""
    candidates = (
        ROOT / ".venv" / "bin" / "python",
        ROOT / ".venv" / "Scripts" / "python.exe",
        ROOT / "venv" / "bin" / "python",
        ROOT / "venv" / "Scripts" / "python.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _same_interpreter(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return str(left) == str(right)


def _ensure_project_interpreter() -> None:
    """Relaunch under the project venv when the runner was started with system Python."""
    venv_python = _local_venv_python()
    if venv_python is None or _same_interpreter(Path(sys.executable), venv_python):
        return

    print(
        f"[INFO] Relaunching regression suite with project environment: {venv_python}",
        flush=True,
    )
    result = subprocess.run([str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]], cwd=ROOT)
    raise SystemExit(result.returncode)


def _check_runtime_dependencies() -> None:
    """Fail once with a useful message instead of producing many import-error test failures."""
    required = {
        "fastapi": "FastAPI",
        "starlette": "Starlette",
        "fitz": "PyMuPDF",
        "numpy": "NumPy",
    }
    missing = [display for module, display in required.items() if importlib.util.find_spec(module) is None]
    if not missing:
        return

    venv_python = _local_venv_python()
    print("ERROR: TTL regression dependencies are not installed in the active Python environment.", file=sys.stderr)
    print(f"Missing: {', '.join(missing)}", file=sys.stderr)
    print(f"Interpreter: {sys.executable}", file=sys.stderr)
    if venv_python is None:
        print(
            "No project .venv was found. Create/install the TTL environment before running the suite.",
            file=sys.stderr,
        )
    else:
        print(
            f"Project environment detected at {venv_python}, but required packages are missing from it.",
            file=sys.stderr,
        )
    raise SystemExit(2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Tabletop Librarian regression scripts.")
    parser.add_argument(
        "--group",
        action="append",
        choices=GROUPS,
        dest="groups",
        help="Run only this test group. Repeat to select multiple groups.",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failure.")
    return parser.parse_args()


def main() -> int:
    _ensure_project_interpreter()
    _check_runtime_dependencies()

    args = parse_args()
    groups = tuple(args.groups or GROUPS)
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    failures: list[tuple[Path, int]] = []
    total = 0

    for group in groups:
        print(f"\n== {group} ==", flush=True)
        for test in sorted((TEST_ROOT / group).glob("test_*.py")):
            total += 1
            print(f"[RUN] {test.relative_to(ROOT)}", flush=True)
            result = subprocess.run([sys.executable, str(test)], cwd=ROOT, env=env)
            if result.returncode:
                failures.append((test, result.returncode))
                print(f"[FAIL] {test.name} ({result.returncode})", flush=True)
                if args.fail_fast:
                    break
            else:
                print(f"[PASS] {test.name}", flush=True)
        if failures and args.fail_fast:
            break

    print(f"\nRan {total} regression scripts; {len(failures)} failed.")
    for test, code in failures:
        print(f"  - {test.relative_to(ROOT)} (exit {code})")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
