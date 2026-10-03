from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path

import numpy as np
import pytest
from PySide6.QtGui import QImage

from miwl2.gallery import Gallery, GalleryError, Profile, normalized
from miwl2.vision import MatchSettings, VisionPaths, VisionRuntime, match

PASSPHRASE = "synthetic test passphrase only"


def vector(axis: int = 0) -> np.ndarray:
    result = np.zeros(128, dtype=np.float32)
    result[axis] = 1
    return result


def opened(tmp_path: Path) -> Gallery:
    gallery = Gallery(tmp_path / "gallery.sqlite3")
    gallery.unlock(PASSPHRASE, True, gallery.generation)
    return gallery


def test_encrypted_gallery_restart_wrong_passphrase_and_deletion(tmp_path: Path) -> None:
    gallery = opened(tmp_path)
    identifier = gallery.add("Synthetic example person", vector(), True, gallery.generation)
    disk = gallery.path.read_bytes()
    assert b"Synthetic example person" not in disk
    assert PASSPHRASE.encode() not in disk
    assert os.stat(gallery.path).st_mode & 0o777 == 0o600
    with sqlite3.connect(gallery.path) as connection:
        ciphertext = connection.execute("SELECT sealed FROM profiles").fetchone()[0]
    assert ciphertext in disk
    assert "embedding" not in repr(gallery.profiles()[0])
    gallery.lock()
    assert not gallery.unlocked and gallery.profiles() == []
    restarted = Gallery(gallery.path)
    with pytest.raises(GalleryError, match="Incorrect passphrase"):
        restarted.unlock("different synthetic password", False, restarted.generation)
    assert not restarted.unlocked
    restarted.unlock(PASSPHRASE, False, restarted.generation)
    assert restarted.profiles()[0].name == "Synthetic example person"
    restarted.delete(identifier)
    assert restarted.profiles() == []
    assert ciphertext not in gallery.path.read_bytes()
    assert not list(tmp_path.glob("*.sqlite3-*"))


def test_gallery_authentication_rejects_record_tampering_and_cross_record_swap(
    tmp_path: Path,
) -> None:
    gallery = opened(tmp_path)
    first = gallery.add("Synthetic Alpha", vector(), True, gallery.generation)
    second = gallery.add("Synthetic Beta", vector(1), True, gallery.generation)
    with sqlite3.connect(gallery.path) as connection:
        sealed = connection.execute("SELECT sealed FROM profiles WHERE id=?", (first,)).fetchone()[
            0
        ]
        connection.execute("UPDATE profiles SET sealed=? WHERE id=?", (sealed, second))
    with pytest.raises(GalleryError, match="damaged gallery"):
        gallery.profiles()


def test_gallery_consent_shape_names_capacity_and_stale_generation(tmp_path: Path) -> None:
    gallery = opened(tmp_path)
    with pytest.raises(GalleryError, match="permission"):
        gallery.add("Synthetic", vector(), False, gallery.generation)
    with pytest.raises(GalleryError, match="invalid"):
        normalized(np.ones(127, dtype=np.float32))
    with pytest.raises(GalleryError, match="invalid"):
        normalized(np.full(128, np.nan, dtype=np.float32))
    with pytest.raises(GalleryError, match="name"):
        gallery.add("bad\nname", vector(), True, gallery.generation)
    previous = gallery.generation
    gallery.add("Synthetic", vector(), True, previous)
    with pytest.raises(GalleryError, match="retry"):
        gallery.add("Late", vector(), True, previous)
    with pytest.raises(GalleryError, match="already exists"):
        gallery.add("synthetic", vector(), True, gallery.generation)
    gallery.MAX_PROFILES = 1
    with pytest.raises(GalleryError, match="at most"):
        gallery.add("Full", vector(), True, gallery.generation)
    gallery.lock()
    with pytest.raises(GalleryError, match="Unlock"):
        gallery.delete("missing")


def test_lock_invalidates_unlock_in_flight(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    gallery = Gallery(tmp_path / "gallery.sqlite3")
    entered, release = threading.Event(), threading.Event()
    original = gallery._derive
    failures = []

    def delayed(passphrase: str, salt: bytes) -> bytes:
        entered.set()
        assert release.wait(3)
        return original(passphrase, salt)

    monkeypatch.setattr(gallery, "_derive", delayed)

    def unlock() -> None:
        try:
            gallery.unlock(PASSPHRASE, True, gallery.generation)
        except GalleryError as error:
            failures.append(str(error))

    worker = threading.Thread(target=unlock)
    worker.start()
    assert entered.wait(2)
    gallery.lock()
    release.set()
    worker.join(3)
    assert failures == ["Gallery operation was cancelled."]
    assert not gallery.exists and not gallery.unlocked


def test_match_distinguishes_possible_uncertain_unknown_and_ambiguous() -> None:
    settings = MatchSettings()
    profiles = [Profile("1", "Synthetic Alpha", vector())]
    assert match(vector(), profiles, settings)["state"] == "possible"
    assert match(vector(1), profiles, settings)["state"] == "unknown"
    mid = vector() * 0.45 + vector(1) * (1 - 0.45**2) ** 0.5
    assert match(mid, profiles, settings)["state"] == "uncertain"
    profiles.append(Profile("2", "Synthetic Beta", normalized(vector() + vector(1) * 0.05)))
    result = match(vector(), profiles, settings)
    assert result["state"] == "uncertain"
    assert "Synthetic" not in result["label"]
    assert match(vector(), [], settings)["state"] == "unknown"
    with pytest.raises(GalleryError, match="threshold"):
        MatchSettings(0.1).validated()


def test_missing_or_modified_models_fail_before_inference(tmp_path: Path) -> None:
    paths = VisionPaths(tmp_path / "detector", tmp_path / "recognizer")
    runtime = VisionRuntime(paths)
    with pytest.raises(GalleryError, match="missing"):
        runtime.synthetic_smoke()
    paths.detector.write_bytes(b"synthetic corrupted model")
    paths.recognizer.write_bytes(b"synthetic corrupted model")
    with pytest.raises(GalleryError, match="pinned hash"):
        runtime.synthetic_smoke()


def test_qimage_padding_and_max_dimensions() -> None:
    image = QImage(113, 111, QImage.Format.Format_RGB888)
    image.fill(0x112233)
    pixels = VisionRuntime._pixels(image)
    assert pixels.shape == (111, 113, 3)
    assert pixels[0, 0].tolist() == [0x33, 0x22, 0x11]
    with pytest.raises(GalleryError, match="1920"):
        VisionRuntime._pixels(QImage(1921, 10, QImage.Format.Format_RGB888))
