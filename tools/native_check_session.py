"""Launch the current app with isolated synthetic notes and two loopback fixtures.

All interaction is performed with native CUA controls. This harness only prepares
synthetic test data and fixtures, invokes the ordinary application entry point,
and captures its own viewport when asked through a marker file.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from benchmark_local import SOURCE
from PySide6.QtCore import QTimer
from PySide6.QtQuick import QQuickWindow

from miwl2.app import main
from miwl2.cameras import CameraManager, CameraSource
from miwl2.configuration import ProviderConfiguration
from miwl2.storage import Store


def run() -> int:
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / "tests"))
    from test_cameras import StreamFixture, stream_fixture

    directory = root / ".native-check-data"
    store = Store(directory / "workspace.sqlite3")
    store.save_provider_configuration(ProviderConfiguration("ollama"))
    if "--reuse" not in sys.argv or not store.list_sessions():
        session = store.create_session()
        store.rename(session, "Cedar Library · native check")
        store.update_source(session, SOURCE)
    first = StreamFixture(label="LOCAL SYNTHETIC FIXTURE 1", continuous=True)
    second = StreamFixture(color="#795530", label="LOCAL SYNTHETIC FIXTURE 2", continuous=True)
    with stream_fixture(first) as url1, stream_fixture(second) as url2:
        manager = CameraManager(store)
        manager.configure(0, CameraSource("Synthetic blue source", url1, True))
        manager.configure(1, CameraSource("Synthetic amber source", url2, True))
        manager.shutdown()
        sys.argv = ["miwl2", "--data-dir", str(directory)]

        def ready(window: QQuickWindow) -> None:
            timer = QTimer(window)

            def capture() -> None:
                marker = directory / "capture-request.json"
                if not marker.is_file():
                    return
                request = json.loads(marker.read_text())
                name = request["name"]
                if not name.startswith("Miwl-2-native-") or Path(name).name != name:
                    raise ValueError("Use a QA viewport filename, not an arbitrary path.")
                marker.unlink()
                image = window.grabWindow()
                assert image.save(str(root / "evidence" / name))
                print(
                    json.dumps(
                        {
                            "capture": name,
                            "viewport": [window.width(), window.height()],
                            "pixels": [image.width(), image.height()],
                        }
                    ),
                    flush=True,
                )

            timer.timeout.connect(capture)
            timer.start(250)

        return main(ready)


if __name__ == "__main__":
    raise SystemExit(run())
