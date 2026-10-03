"""Measure native first-window startup and process memory using disposable workspaces."""

from __future__ import annotations

import argparse
import json
import os
import resource
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def child(directory: str) -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QGuiApplication

    from miwl2.app import main

    sys.argv = ["miwl2", "--data-dir", directory]

    def ready(window: object) -> None:
        def painted() -> None:
            print(
                json.dumps(
                    {
                        "ready_monotonic": time.monotonic(),
                        "maximum_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        "platform": QGuiApplication.platformName(),
                    }
                ),
                flush=True,
            )
            QGuiApplication.quit()

        QTimer.singleShot(100, painted)

    raise SystemExit(main(ready))


def run() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=root / "evidence/startup-benchmark.json")
    args = parser.parse_args()
    environment = dict(os.environ, PYTHONPATH=str(root / "src"))
    environment.pop("QT_QPA_PLATFORM", None)
    environment.pop("QT_QUICK_BACKEND", None)
    results = []
    with tempfile.TemporaryDirectory(prefix="miwl2-startup-benchmark-") as directory:
        for index in range(3):
            started = time.monotonic()
            process = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--child", directory],
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if process.returncode:
                raise RuntimeError(process.stderr)
            report = json.loads(process.stdout.strip().splitlines()[-1])
            results.append(
                {
                    "case": "fresh workspace" if index == 0 else "existing workspace/new process",
                    "first_window_seconds": report["ready_monotonic"] - started,
                    "maximum_rss_bytes": report["maximum_rss_bytes"],
                    "platform": report["platform"],
                }
            )
    args.output.parent.mkdir(exist_ok=True, parents=True)
    args.output.write_text(
        json.dumps(
            {
                "runs": results,
                "conditions": (
                    "Native Cocoa, fixture provider, 100 ms paint allowance. "
                    "OS caches were not cleared; no model loaded by startup."
                ),
                "limits": (
                    "Three sequential observations; maximum RSS is process memory, "
                    "not system/model memory."
                ),
            },
            indent=2,
        )
        + "\n"
    )
    print(json.dumps(results), flush=True)


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--child":
        child(sys.argv[2])
    else:
        run()
