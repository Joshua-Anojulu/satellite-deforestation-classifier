"""Mandatory launcher for frame selection, precheck, tuning, calibration, freezing."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .sandbox_process import run_sealed_process

PRE_LIFT_ROLES = ("frame_selection", "precheck", "tuning", "calibration", "freezing")
ROLE_ENVIRONMENT = "FORECAST_PRELIFT_ROLE"


@dataclass(frozen=True)
class RoleTranscript:
    role: str
    child_exit_status: int
    supervisor_error_code: str
    stdout_bytes: int
    stderr_bytes: int

    @property
    def succeeded(self) -> bool:
        return self.supervisor_error_code == "OK"


def require_pre_lift_role(role: str) -> None:
    """Prevent direct execution of a pre-lift command outside the launcher."""

    if role not in PRE_LIFT_ROLES:
        raise ValueError(role)
    if os.environ.get(ROLE_ENVIRONMENT) != role:
        raise RuntimeError(
            f"{role} must run through forecast.prelift_sandbox; direct execution is denied."
        )


def _environment(temp_dir: Path, role: str) -> dict[str, str]:
    keep = ("SystemRoot", "WINDIR", "PATH", "PATHEXT", "COMSPEC")
    environment = {key: os.environ[key] for key in keep if key in os.environ}
    environment.update({
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "TEMP": str(temp_dir),
        "TMP": str(temp_dir),
        ROLE_ENVIRONMENT: role,
    })
    return environment


def run_pre_lift_role(
    role: str,
    target: str | Path,
    arguments: Sequence[str] = (),
    *,
    raw_denied_roots: Sequence[str | Path],
    writable_roots: Sequence[str | Path] = (),
    timeout_seconds: float = 60.0,
    temp_parent: str | Path | None = None,
) -> RoleTranscript:
    """Run one pre-lift executable with raw-GFC and network capabilities denied."""

    if role not in PRE_LIFT_ROLES:
        raise ValueError(role)
    parent = Path(temp_parent).resolve() if temp_parent is not None else None
    if parent is not None:
        parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"prelift-{role}-", dir=parent) as temporary:
        temp_dir = Path(temporary)
        request = {
            "role": role,
            "target": str(Path(target).resolve()),
            "import_root": str(Path(__file__).resolve().parents[1]),
            "arguments": list(arguments),
            "denied_roots": [str(Path(path).resolve()) for path in raw_denied_roots],
            "writable_roots": [str(temp_dir), *(str(Path(path).resolve()) for path in writable_roots)],
        }
        request_path = temp_dir / "request.json"
        request_path.write_text(
            json.dumps(request, sort_keys=True, allow_nan=False), encoding="utf-8"
        )
        worker = Path(__file__).with_name("prelift_sandbox_worker.py")
        result = run_sealed_process(
            [sys.executable, "-I", str(worker), str(request_path)],
            cwd=temp_dir,
            env=_environment(temp_dir, role),
            timeout_seconds=timeout_seconds,
        )
    if result.timed_out:
        code = "ROLE_TIMEOUT"
    elif result.returncode in {71, 72, 73, 74, 75}:
        code = "CAPABILITY_DENIED"
    elif result.returncode != 0:
        code = "ROLE_FAILED"
    elif result.stdout_bytes or result.stderr_bytes:
        code = "STREAM_POLICY_VIOLATION"
    else:
        code = "OK"
    return RoleTranscript(
        role=role,
        child_exit_status=result.returncode,
        supervisor_error_code=code,
        stdout_bytes=result.stdout_bytes,
        stderr_bytes=result.stderr_bytes,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("role", choices=PRE_LIFT_ROLES)
    parser.add_argument("target", type=Path)
    parser.add_argument("--raw-root", action="append", required=True, type=Path)
    parser.add_argument("--write-root", action="append", default=[], type=Path)
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("arguments", nargs="*")
    args = parser.parse_args()
    transcript = run_pre_lift_role(
        args.role,
        args.target,
        args.arguments,
        raw_denied_roots=args.raw_root,
        writable_roots=args.write_root,
        timeout_seconds=args.timeout,
    )
    print(json.dumps({
        "role": transcript.role,
        "child_exit_status": transcript.child_exit_status,
        "supervisor_error_code": transcript.supervisor_error_code,
        "stdout_bytes": transcript.stdout_bytes,
        "stderr_bytes": transcript.stderr_bytes,
    }, sort_keys=True))
    raise SystemExit(0 if transcript.succeeded else 1)


if __name__ == "__main__":
    main()
