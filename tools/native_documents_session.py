"""Prepare one fictional file, launch the ordinary app; native UI actions use CUA."""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtQuick import QQuickWindow
from verify_documents import SOURCE

from miwl2.app import main
from miwl2.configuration import ProviderConfiguration
from miwl2.storage import Store


def run() -> int:
    root = Path(__file__).resolve().parents[1]
    directory = root / ".grounding-native-check-data"
    directory.mkdir(exist_ok=True)
    source = Path("/tmp/Miwl-2-grounding-synthetic.md")
    source.write_text(SOURCE)
    store = Store(directory / "workspace.sqlite3")
    store.save_provider_configuration(ProviderConfiguration("ollama"))
    if not store.list_sessions():
        session = store.create_session()
        store.rename(session, "Cedar Library · native document check")
    sys.argv = ["miwl2", "--data-dir", str(directory)]

    def ready(window: QQuickWindow) -> None:
        timer = QTimer(window)

        def capture() -> None:
            marker = directory / "capture-request.json"
            if not marker.is_file():
                return
            request = json.loads(marker.read_text())
            name = request["name"]
            if not name.startswith("Miwl-2-native-documents-") or Path(name).name != name:
                raise ValueError("Use a QA viewport filename.")
            marker.unlink()
            assert window.grabWindow().save(str(root / "evidence" / name))
            print(
                json.dumps({"capture": name, "viewport": [window.width(), window.height()]}),
                flush=True,
            )

        timer.timeout.connect(capture)
        timer.start(250)

    return main(ready)


if __name__ == "__main__":
    raise SystemExit(run())
