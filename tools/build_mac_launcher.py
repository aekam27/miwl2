"""Build an ad-hoc signed, source-backed local Mac launcher. No downloads or installs."""

from __future__ import annotations

import argparse
import json
import platform
import plistlib
import shutil
import subprocess
from pathlib import Path


def run() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=root / ".venv/bin/python")
    parser.add_argument(
        "--data-dir", type=Path, help="Optional isolated workspace; otherwise normal app data"
    )
    parser.add_argument("--output", type=Path, default=root / ".build/Miwl 2.app")
    args = parser.parse_args()
    python = args.python.absolute()
    if not python.is_file():
        parser.error("Prepare the virtual environment first, or supply --python.")
    subprocess.run([str(python), "-c", "import PySide6, cv2, cryptography, certifi"], check=True)
    bundle = args.output.absolute()
    if bundle.exists():
        parser.error(
            "Output already exists. Choose a fresh output or remove your generated launcher."
        )
    macos = bundle / "Contents/MacOS"
    resources = bundle / "Contents/Resources"
    macos.mkdir(parents=True)
    resources.mkdir()
    (resources / "launcher.json").write_text(
        json.dumps(
            {
                "projectRoot": str(root),
                "python": str(python),
                "dataDirectory": str(args.data_dir.absolute()) if args.data_dir else None,
            },
            indent=2,
        )
        + "\n"
    )
    shutil.copy2(root / "src/miwl2/assets/Miwl-2-app-icon.icns", resources / "Miwl.icns")
    with (bundle / "Contents/Info.plist").open("wb") as stream:
        plistlib.dump(
            {
                "CFBundleExecutable": "MiwlLauncher",
                "CFBundleIdentifier": "org.aekam.miwl2.local",
                "CFBundleName": "Miwl 2",
                "CFBundleDisplayName": "Miwl 2",
                "CFBundlePackageType": "APPL",
                "CFBundleShortVersionString": "0.1.1",
                "CFBundleVersion": "2",
                "CFBundleIconFile": "Miwl.icns",
                "NSHighResolutionCapable": True,
                "LSMinimumSystemVersion": "13.0",
            },
            stream,
        )
    cache = root / ".build/swift-cache"
    subprocess.run(
        [
            "swiftc",
            "-target",
            f"{platform.machine()}-apple-macosx13.0",
            "-module-cache-path",
            str(cache),
            str(root / "native/MiwlLauncher.swift"),
            "-o",
            str(macos / "MiwlLauncher"),
        ],
        check=True,
    )
    subprocess.run(["codesign", "--force", "--sign", "-", str(bundle)], check=True)
    subprocess.run(["codesign", "--verify", "--strict", str(bundle)], check=True)
    print(bundle)


if __name__ == "__main__":
    run()
