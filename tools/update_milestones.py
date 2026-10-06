"""Refresh the public-safe candidate status from local verification receipts."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path


def run() -> None:
    root = Path(__file__).resolve().parents[1]

    def read(name: str) -> dict[str, object]:
        path = root / "evidence" / name
        return json.loads(path.read_text()) if path.is_file() else {}

    native = read("daily-use-verification.json")
    launcher = read("mac-launcher-verification.json")
    startup = read("startup-benchmark.json")
    model = read("readiness-local-inference.json")
    checks = read("readiness-checks.json")
    report = {
        "schema_version": 1,
        "app_version": "0.1.1",
        "updated_at_utc": datetime.now(UTC).isoformat(),
        "checkpoint": "Daily-use foundation candidate; review before public push",
        "branch": "readiness/daily-use-foundation",
        "checks": checks,
        "implemented": [
            "version-safe atomic migrations",
            "WAL-aware private writing backups",
            "bounded recent chat context",
            "coalesced streaming saves",
            "atomic failed/stopped job transitions",
            "visible storage errors",
            "source-backed ad-hoc signed Mac launcher",
        ],
        "native": {
            key: native.get(key)
            for key in [
                "platform",
                "viewports",
                "stop_runs",
                "saved_draft_preserved",
                "failure_retry",
                "backup_control",
                "document_import_search_citation_confirmed_removal_runs",
                "original_document_unchanged",
                "qml_warnings",
            ]
        },
        "launcher": {
            key: launcher.get(key)
            for key in ["platform", "launch_services", "signature", "limitations"]
        },
        "startup": startup,
        "local_model": {
            "hardware": model.get("hardware"),
            "runtime": model.get("runtime"),
            "results": [
                {
                    key: row.get(key)
                    for key in ["operation", "load_state", "first_text_seconds", "elapsed_seconds"]
                }
                for row in model.get("results", [])
            ],
            "cancellation": model.get("cancellation"),
            "memory": {
                key: value
                for key, value in model.get("runtime_memory_followup", {}).items()
                if key != "resident_after"
            },
        },
        "remaining_gates": [
            "standalone packaging and fresh-machine/upgrade/soak checks",
            "Developer ID signing/notarization and manual Dock verification",
            "owner-triggered microphone and audible playback",
            "explicitly budgeted real cloud compatibility",
            "consented real-face accuracy/spoofing evaluation",
            "EmbeddingGemma terms review; no embedding installed",
            "branch review and authorization before public pushing",
        ],
        "privacy": {
            "test_data": "Fictional temporary workspaces only",
            "real_sensors_opened": 0,
            "real_face_enrollments": 0,
            "paid_cloud_calls": 0,
            "user_workspaces_modified": False,
            "new_credentials_created": False,
            "models_downloaded": False,
        },
    }
    (root / "milestones.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(root / "milestones.json")


if __name__ == "__main__":
    run()
