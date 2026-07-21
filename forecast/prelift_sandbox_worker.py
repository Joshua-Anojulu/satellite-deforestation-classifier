"""Private wrapper that applies the common pre-lift capability policy."""

from __future__ import annotations

import json
import os
import runpy
import sys
from pathlib import Path

ROLES = ("frame_selection", "precheck", "tuning", "calibration", "freezing")


class SandboxDenied(PermissionError):
    def __init__(self, category: str) -> None:
        super().__init__("sandbox capability denied")
        self.category = category


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _guard(denied_roots: tuple[Path, ...], writable_roots: tuple[Path, ...]) -> None:
    def audit(event: str, args: tuple[object, ...]) -> None:
        if event.startswith("socket."):
            raise SandboxDenied("network")
        if event in {"subprocess.Popen", "os.system", "os.posix_spawn", "os.spawn"}:
            raise SandboxDenied("process")
        if event != "open" or not args or isinstance(args[0], int):
            return
        try:
            path = Path(os.fspath(args[0])).resolve()
        except (TypeError, ValueError, OSError):
            raise SandboxDenied("filesystem") from None
        mode = str(args[1]) if len(args) > 1 else "r"
        writing = any(flag in mode for flag in ("w", "a", "x", "+"))
        if any(_inside(path, root) for root in denied_roots):
            raise SandboxDenied("raw")
        if writing and not any(_inside(path, root) for root in writable_roots):
            raise SandboxDenied("filesystem")

    sys.addaudithook(audit)


def main() -> None:
    if len(sys.argv) != 2:
        os._exit(78)
    try:
        request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        role = request["role"]
        if role not in ROLES:
            os._exit(78)
        denied = tuple(Path(path).resolve() for path in request["denied_roots"])
        writable = tuple(Path(path).resolve() for path in request["writable_roots"])
        target = Path(request["target"]).resolve()
        import_root = Path(request["import_root"]).resolve()
        arguments = [str(value) for value in request["arguments"]]
        sys.path.insert(0, str(import_root))
        _guard(denied, writable)
        sys.argv = [str(target), *arguments]
        try:
            relative = target.relative_to(import_root).with_suffix("")
            module = ".".join(relative.parts)
        except ValueError:
            module = ""
        if module and all(part.isidentifier() for part in module.split(".")):
            runpy.run_module(module, run_name="__main__")
        else:
            runpy.run_path(str(target), run_name="__main__")
    except SandboxDenied as error:
        os._exit({"raw": 71, "network": 72, "process": 73, "filesystem": 74}.get(
            error.category, 75
        ))
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 78
        os._exit(code)
    except BaseException:
        # Deliberately collapse every role failure to the same non-data-bearing
        # denial status.  A distinct exception-dependent code would itself be an
        # observable side channel.
        os._exit(76)


if __name__ == "__main__":
    main()
