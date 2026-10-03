"""Verify LaunchServices opens the real app through a temporary auto-quit QA wrapper."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def run() -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="miwl2-launcher-qa-") as directory:
        data = Path(directory)
        wrapper = data / "qa-python"
        receipt = data / "ready.json"
        preview = root / "evidence/Miwl-2-daily-use-launcher.png"
        wrapper.write_text(f"""#!{sys.executable}
import os,sys,json
if '-c' in sys.argv:
    os.execv({sys.executable!r}, [{sys.executable!r},*sys.argv[1:]])
from PySide6.QtCore import QTimer
from PySide6.QtGui import QGuiApplication
from miwl2.app import main
sys.argv=['miwl2',*sys.argv[3:]]
def ready(window):
    def finish():
        window.grabWindow().save({str(preview)!r})
        from pathlib import Path
        value={{'platform':QGuiApplication.platformName(), 'launcher_pid':os.getppid(),
               'viewport':[window.width(),window.height()]}}
        Path({str(receipt)!r}).write_text(json.dumps(value))
        QGuiApplication.quit()
    QTimer.singleShot(150,finish)
raise SystemExit(main(ready))
""")
        wrapper.chmod(0o700)
        bundle = data / "Miwl QA.app"
        subprocess.run(
            [
                sys.executable,
                str(root / "tools/build_mac_launcher.py"),
                "--python",
                str(wrapper),
                "--data-dir",
                str(data / "workspace"),
                "--output",
                str(bundle),
            ],
            check=True,
        )
        environment = dict(os.environ)
        environment.pop("QT_QPA_PLATFORM", None)
        environment.pop("QT_QUICK_BACKEND", None)
        subprocess.run(
            ["/usr/bin/open", "-n", str(bundle)], env=environment, check=True, timeout=10
        )
        deadline = time.monotonic() + 20
        while not receipt.is_file() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not receipt.is_file():
            raise RuntimeError("LaunchServices returned without the real app ready receipt.")
        report = json.loads(receipt.read_text())
        launcher_pid = report.pop("launcher_pid")
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.kill(launcher_pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.05)
        else:
            raise RuntimeError("The QA launcher stayed alive after the app closed.")
        assert report["platform"] == "cocoa"
        report.update(
            {
                "launch_services": True,
                "signature": "ad-hoc verified",
                "workspace": "temporary fictional QA workspace",
                "limitations": (
                    "Source-backed launcher and prepared environment; not standalone, "
                    "Developer ID signed or notarized. Dock identity and permission "
                    "attribution need manual verification."
                ),
            }
        )
        (root / "evidence/mac-launcher-verification.json").write_text(
            json.dumps(report, indent=2) + "\n"
        )
        print(json.dumps(report), flush=True)


if __name__ == "__main__":
    run()
