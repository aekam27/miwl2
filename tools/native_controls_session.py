"""Prepare one fictional file, launch the ordinary app; native UI actions use CUA."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtQuick import QQuickWindow
from verify_documents import SOURCE

from miwl2.app import main
from miwl2.configuration import ProviderConfiguration
from miwl2.documents import DocumentIndex
from miwl2.gallery import Gallery
from miwl2.storage import Store


def run() -> int:
    root = Path(__file__).resolve().parents[1]
    directory = root / ".controls-regression-data"
    directory.mkdir(exist_ok=True)
    source = Path("/tmp/Miwl-2-grounding-synthetic.md")
    source.write_text(SOURCE)
    DocumentIndex(directory / "documents.sqlite3").import_file(source)
    gallery = Gallery(directory / "gallery.sqlite3")
    if not gallery.exists:
        gallery.unlock("synthetic-public-native-layout-check", True, gallery.generation)
        gallery.lock()
    store = Store(directory / "workspace.sqlite3")
    store.save_provider_configuration(ProviderConfiguration("ollama"))
    if not store.list_sessions():
        session = store.create_session()
        store.rename(session, "Cedar Library · native layout audit")
        store.update_source(session, SOURCE)
        store.update_result(
            session,
            (
                "Fictional evaluation: 21 of 28 survey respondents reported saving time; "
                "7 did not. "
                "The survey was self-selected, without a randomized comparison group. "
                "These reports do not establish a causal improvement."
            ),
        )
    sys.argv = ["miwl2", "--data-dir", str(directory)]

    def ready(window: QQuickWindow) -> None:
        if os.environ.get("MIWL_QA_COMPACT") == "1":
            window.resize(960, 720)
        timer = QTimer(window)

        def capture() -> None:
            marker = directory / "capture-request.json"
            if not marker.is_file():
                return
            request = json.loads(marker.read_text())
            name = request["name"]
            if not name.startswith("Miwl-2-native-regression-") or Path(name).name != name:
                raise ValueError("Use a QA viewport filename.")
            marker.unlink()
            assert window.grabWindow().save(str(root / "evidence" / name))
            print(
                json.dumps(
                    {
                        "capture": name,
                        "viewport": [window.width(), window.height()],
                        "window_position": [window.x(), window.y()],
                    }
                ),
                flush=True,
            )

        timer.timeout.connect(capture)
        timer.start(250)

    return main(ready)


if __name__ == "__main__":
    raise SystemExit(run())
