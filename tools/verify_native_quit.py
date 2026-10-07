"""Exercise the native Cocoa Cmd-Q path with fictional temporary writing.

AppKit receives queued NSEvents, not QTest input, a QML close-handler call, or
QCoreApplication.quit(). Qt foreground activation is disabled. This verifies
the native menu shortcut path; it does not claim an OS-posted key or menu click.
Run explicitly on macOS with the prepared Python environment. No models needed.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

CASES = ("clean", "dirty-both", "failed-source", "failed-draft", "repeated-quit")
SOURCE = "Fictional Cedar Library source before Quit."
DRAFT = "Fictional Cedar Library draft before Quit."


def save_report(path: Path, report: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(path)


def child(
    case: str, helper: Path, data: Path, receipt: Path, previous: dict[str, Any] | None = None
) -> int:
    from PySide6.QtCore import QEvent, QObject, QTimer
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQml import QQmlEngine
    from PySide6.QtQuick import QQuickItem, QQuickWindow

    from miwl2.app import main
    from miwl2.storage import Store

    native = ctypes.CDLL(str(helper))
    for name in ("miwl_frontmost_pid", "miwl_application_active", "miwl_command_q_events"):
        function = getattr(native, name)
        function.argtypes, function.restype = [], ctypes.c_int
    native.miwl_observe_command_q.argtypes = []
    native.miwl_observe_command_q.restype = None
    native.miwl_quit_menu_action.argtypes = []
    native.miwl_quit_menu_action.restype = ctypes.c_char_p
    native.miwl_post_command_q.argtypes = [ctypes.c_int]
    native.miwl_post_command_q.restype = ctypes.c_int

    store = Store(data / "workspace.sqlite3")
    if previous is None:
        session = store.create_session()
        store.update_source(session, SOURCE)
        store.update_result(session, DRAFT)
        expected = {"source": SOURCE, "result": DRAFT}
    else:
        session = previous["session_id"]
        assert [row["id"] for row in store.list_sessions()] == [session]
        expected = dict(previous["expected_writing"])
    report: dict[str, Any] = {
        "case": case + ("-reopen" if previous else ""),
        "session_id": session,
        "fresh_process_reopen": previous is not None,
        "frontmost_before": native.miwl_frontmost_pid(),
        "close_events": 0,
        "about_to_quit": 0,
        "writes": [],
        "maximum_write_depth": 0,
        "blocked_verified": False,
        "recovery_requested": False,
        "passed": False,
    }
    failing = previous is None and case in {"failed-source", "failed-draft", "repeated-quit"}
    field = "result" if case == "failed-draft" else "source"
    repeats = 3 if case == "repeated-quit" and previous is None else 1
    depth = 0
    probe: QObject | None = None

    def ready(window: QQuickWindow) -> None:
        nonlocal probe
        application = QGuiApplication.instance()
        assert isinstance(application, QGuiApplication)
        assert application.platformName() == "cocoa"
        report["platform"] = application.platformName()
        bridge = QQmlEngine.contextForObject(window).contextProperty("bridge")
        current_store = bridge.service.store

        def item(name: str) -> QQuickItem:
            value = window.findChild(QQuickItem, name)
            assert value is not None, name
            return value

        editors = {"source": item("sourceEditor"), "result": item("resultEditor")}

        class CloseObserver(QObject):
            def eventFilter(self, watched: QObject, event: QEvent) -> bool:
                if event.type() == QEvent.Type.Close:
                    report["close_events"] += 1
                return False

        probe = CloseObserver(application)
        window.installEventFilter(probe)
        native.miwl_observe_command_q()
        original = getattr(current_store, "update_" + field)

        def persist(session_id: str, value: str) -> None:
            nonlocal depth
            depth += 1
            report["maximum_write_depth"] = max(report["maximum_write_depth"], depth)
            report["writes"].append({"value": value, "failed": failing})
            try:
                if failing:
                    raise sqlite3.OperationalError("Fictional injected persistence failure")
                original(session_id, value)
            finally:
                depth -= 1

        setattr(current_store, "update_" + field, persist)

        def safe(work: Any) -> None:
            try:
                work()
            except Exception as error:
                report["error"] = str(error) or type(error).__name__
                save_report(receipt, report)
                application.exit(2)  # Failure cleanup only; never counted as a Quit check.

        def post_quit() -> None:
            assert native.miwl_frontmost_pid() == report["frontmost_before"]
            assert not native.miwl_application_active(), "Probe unexpectedly became foreground"
            action = native.miwl_quit_menu_action().decode()
            assert action, "No enabled native Cmd-Q menu action"
            report["native_quit_menu_action"] = action
            assert native.miwl_post_command_q(repeats) == repeats

        def verify_blocked() -> None:
            nonlocal failing
            assert window.isVisible(), "Failed save closed the window"
            assert report["about_to_quit"] == 0, "Failed save started shutdown"
            assert native.miwl_command_q_events() == repeats
            assert len(report["writes"]) == repeats, "Unexpected save retry/reentrancy"
            assert report["maximum_write_depth"] == 1
            assert current_store.session(session)["source"] == SOURCE
            assert current_store.session(session)["result"] == DRAFT
            assert editors[field].property("text") == expected[field]
            assert bridge.editorSaveFailed and "could not be saved" in bridge.errorMessage
            assert item("errorBanner").isVisible(), "Save error is not visible"
            report["blocked_verified"] = True
            report["blocked_native_events"] = native.miwl_command_q_events()
            report["blocked_error"] = bridge.errorMessage
            preview = receipt.with_suffix(".png")
            assert window.grabWindow().save(str(preview))
            report["preview"] = preview.name
            failing = False
            expected[field] = "Fictional latest edit after the save error."
            editors[field].setProperty("text", expected[field])
            report["recovery_requested"] = True
            post_quit()

        def attempt() -> None:
            started = time.monotonic()
            if previous is not None:
                for name, editor in editors.items():
                    assert editor.property("text") == expected[name], "Reopened editor differs"
                report["reopened_editors_match"] = True
            elif case == "dirty-both":
                for name, editor in editors.items():
                    expected[name] = "Fictional pending " + name + " saved by native Quit."
                    editor.setProperty("text", expected[name])
            elif failing:
                expected[field] = "Fictional unsaved " + field + " retained after native Quit."
                editors[field].setProperty("text", expected[field])
                # The error must remain visible even outside the writing views.
                window.setProperty("activeView", 5)
            post_quit()
            report["edit_to_event_post_seconds"] = time.monotonic() - started
            assert report["edit_to_event_post_seconds"] < 0.35
            if failing:
                # Wait past the 350 ms autosave delay: the rejected close must stop its timer.
                QTimer.singleShot(450, lambda: safe(verify_blocked))

        def quitting() -> None:
            report["about_to_quit"] += 1
            report["native_command_q_events"] = native.miwl_command_q_events()
            report["save_error_at_exit"] = bridge.errorMessage
            report["frontmost_at_exit"] = native.miwl_frontmost_pid()
            save_report(receipt, report)

        def timeout() -> None:
            raise RuntimeError("Native Quit did not finish within the fixture deadline")

        application.aboutToQuit.connect(quitting)
        QTimer.singleShot(350, lambda: safe(attempt))
        QTimer.singleShot(5000, lambda: safe(timeout))

    sys.argv = ["miwl2-native-quit-fixture", "--data-dir", str(data)]
    exit_code = main(ready)
    try:
        assert exit_code == 0, report.get("error", f"App exited with {exit_code}")
        assert report["about_to_quit"] == 1
        assert report["native_command_q_events"] >= 1
        assert report["close_events"] >= 1
        assert not report["save_error_at_exit"]
        assert report["frontmost_at_exit"] == report["frontmost_before"]
        if previous is None and case in {"failed-source", "failed-draft", "repeated-quit"}:
            assert report["blocked_verified"] and report["recovery_requested"]
            assert len(report["writes"]) == repeats + 1
        reopened = Store(store.path).session(session)
        assert {name: reopened[name] for name in expected} == expected
        report["expected_writing"] = expected
        report["reopened_writing_matches"] = True
        report["passed"] = True
    except Exception as error:
        report["error"] = str(error) or type(error).__name__
        exit_code = 2
    save_report(receipt, report)
    return exit_code


def run() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("evidence/native-quit"))
    parser.add_argument("--child", choices=CASES)
    parser.add_argument("--helper", type=Path)
    parser.add_argument("--data", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--verify-saved", type=Path)
    arguments = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Native Quit verification requires macOS.")
    if arguments.child:
        assert arguments.helper and arguments.data and arguments.receipt
        previous = (
            json.loads(arguments.verify_saved.read_text()) if arguments.verify_saved else None
        )
        return child(arguments.child, arguments.helper, arguments.data, arguments.receipt, previous)
    root = Path(__file__).resolve().parents[1]
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(
        os.environ,
        PYTHONPATH=str(root / "src"),
        QT_QPA_PLATFORM="cocoa",
        QT_QUICK_BACKEND="software",
        QT_MAC_DISABLE_FOREGROUND_APPLICATION_TRANSFORM="1",
    )
    results = []
    with tempfile.TemporaryDirectory(prefix="miwl-native-quit-") as directory:
        temporary = Path(directory)
        helper = temporary / "native-quit-events.dylib"
        subprocess.run(
            [
                "xcrun",
                "clang",
                "-dynamiclib",
                "-fobjc-arc",
                "-framework",
                "AppKit",
                str(root / "tools/native_quit_events.m"),
                "-o",
                str(helper),
            ],
            check=True,
            timeout=30,
        )
        for case in CASES:
            receipt = output / (case + ".json")
            receipt.unlink(missing_ok=True)
            process = subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--child",
                    case,
                    "--helper",
                    str(helper),
                    "--data",
                    str(temporary / case),
                    "--receipt",
                    str(receipt),
                ],
                env=environment,
                capture_output=True,
                text=True,
                timeout=15,
            )
            (output / (case + ".txt")).write_text(process.stdout + process.stderr)
            result = json.loads(receipt.read_text()) if receipt.exists() else {"case": case}
            result["process_exit_code"] = process.returncode
            if result.get("passed") and process.returncode == 0:
                reopened_receipt = output / (case + "-reopen.json")
                reopened_receipt.unlink(missing_ok=True)
                reopened = subprocess.run(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--child",
                        case,
                        "--helper",
                        str(helper),
                        "--data",
                        str(temporary / case),
                        "--receipt",
                        str(reopened_receipt),
                        "--verify-saved",
                        str(receipt),
                    ],
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                (output / (case + "-reopen.txt")).write_text(reopened.stdout + reopened.stderr)
                result["reopen"] = (
                    json.loads(reopened_receipt.read_text()) if reopened_receipt.exists() else {}
                )
                result["reopen"]["process_exit_code"] = reopened.returncode
            results.append(result)
            print(json.dumps({"case": case, "passed": result.get("passed", False)}), flush=True)
    report = {
        "cases": results,
        "passed": all(
            row.get("passed")
            and row["process_exit_code"] == 0
            and row.get("reopen", {}).get("passed")
            and row["reopen"]["process_exit_code"] == 0
            for row in results
        ),
        "mechanism": "Native AppKit NSEvent Cmd-Q queue and local-event observer; Cocoa Qt.",
        "limits": "No OS-posted key, physical keyboard, or menu-bar mouse/Accessibility click.",
        "data": "Fictional temporary writing; no real devices, credentials, models or user stores.",
    }
    save_report(output / "verification.json", report)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(run())
