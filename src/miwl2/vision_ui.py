from __future__ import annotations

import time
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, cast

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from miwl2.camera_ui import CameraBridge
from miwl2.gallery import Gallery, GalleryError
from miwl2.vision import MatchSettings, VisionRuntime, match


class VisionBridge(QObject):
    changed = Signal()
    profilesChanged = Signal()
    _completed = Signal(object)

    def __init__(self, gallery: Gallery, runtime: VisionRuntime, cameras: CameraBridge) -> None:
        super().__init__()
        self.gallery, self.runtime, self.cameras = gallery, runtime, cameras
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="miwl2-local-vision")
        self._future: Future[dict[str, Any]] | None = None
        self._token = 0
        self._closed = False
        self._busy = False
        self._error = ""
        self._status = "Create or unlock a passphrase-protected local gallery."
        self._enabled = [False, False]
        self._generation = [cast(int, row["generation"]) for row in cameras.manager.snapshot()]
        self._last_run = [0.0, 0.0]
        self._next_source = 0
        self._results = ["Recognition off", "Recognition off"]
        self._last_active = time.monotonic()
        self.settings = MatchSettings()
        self._completed.connect(self._finish)
        cameras.sourcesChanged.connect(self._sources_changed)
        self._timer = QTimer(self)
        self._timer.setInterval(250)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    @Property(bool, notify=changed)
    def available(self) -> bool:
        return self.runtime.paths.available

    @Property(bool, notify=changed)
    def exists(self) -> bool:
        return self.gallery.exists

    @Property(bool, notify=changed)
    def unlocked(self) -> bool:
        return self.gallery.unlocked

    @Property(bool, notify=changed)
    def busy(self) -> bool:
        return self._busy

    @Property(str, notify=changed)
    def error(self) -> str:
        return self._error

    @Property(str, notify=changed)
    def statusText(self) -> str:
        return self._status

    @Property(list, notify=profilesChanged)
    def profiles(self) -> list[dict[str, str]]:
        try:
            return [
                {"id": profile.identifier, "name": profile.name}
                for profile in self.gallery.profiles()
            ]
        except GalleryError:
            # Never include encrypted contents, names or descriptors in an error/log.
            return []

    @Property(list, notify=changed)
    def sources(self) -> list[dict[str, Any]]:
        return [
            {"enabled": self._enabled[index], "result": self._results[index]} for index in (0, 1)
        ]

    def _submit(self, work: Any, metadata: dict[str, Any]) -> None:
        self._busy = True
        self._error = ""
        token = self._token
        generation = self.gallery.generation

        def run() -> dict[str, Any]:
            try:
                return {**metadata, "token": token, "generation": generation, "value": work()}
            except GalleryError as error:
                return {**metadata, "token": token, "generation": generation, "error": str(error)}
            except Exception:
                return {
                    **metadata,
                    "token": token,
                    "generation": generation,
                    "error": "Local vision could not complete. Check the gallery and model files.",
                }

        self._future = self._executor.submit(run)
        self._future.add_done_callback(
            lambda future: self._completed.emit(future.result()) if not future.cancelled() else None
        )
        self.changed.emit()

    @Slot(str, bool)
    def unlock(self, passphrase: str, create: bool) -> None:
        if self._busy:
            return
        generation = self.gallery.generation
        self._status = "Deriving your local gallery key…"
        self._submit(
            lambda: self.gallery.unlock(passphrase, create, generation), {"kind": "unlock"}
        )

    @Slot()
    def lock(self) -> None:
        self._token += 1
        self.gallery.lock()
        self.profilesChanged.emit()
        self._enabled = [False, False]
        self._results = ["Recognition off · gallery locked", "Recognition off · gallery locked"]
        self._status = "Gallery locked. Passphrase and key are not saved."
        self._error = ""
        self.changed.emit()

    @Slot(int, bool)
    def enableSource(self, index: int, consent: bool) -> None:
        if index not in (0, 1):
            return
        self._last_active = time.monotonic()
        if consent and (not self.unlocked or not self.available):
            self._error = "Unlock the gallery and install the pinned local models first."
            self.changed.emit()
            return
        self._token += 1
        self._enabled[index] = consent
        self._results[index] = (
            "Waiting for a fresh connected frame" if consent else "Recognition off"
        )
        self.changed.emit()

    @Slot(float, float, float)
    def configure(self, threshold: float, band: float, margin: float) -> None:
        try:
            self.settings = MatchSettings(threshold, band, margin).validated()
            self._token += 1
            self._results = [
                "Thresholds changed · waiting for frame" if enabled else "Recognition off"
                for enabled in self._enabled
            ]
            self._status = "Session thresholds updated. Similarity is not a probability."
            self._error = ""
            self._last_active = time.monotonic()
        except GalleryError as error:
            self._error = str(error)
        self.changed.emit()

    @Slot(int, str, bool)
    def enroll(self, index: int, name: str, consent: bool) -> None:
        if index not in (0, 1) or self._busy:
            return
        if not consent or not self.unlocked:
            self._error = "Unlock the gallery and confirm this person's enrollment permission."
            self.changed.emit()
            return
        image, source_generation, _, state, received_at = self.cameras.manager.vision_frame(index)
        if state != "streaming" or image.isNull() or time.monotonic() - received_at > 2:
            self._error = (
                "Connect an authorized source and wait for a fresh frame before enrolling."
            )
            self.changed.emit()
            return
        self._last_active = time.monotonic()
        self._status = "Checking a single, sufficiently large face locally…"
        self._submit(
            lambda: self.runtime.samples(image, enrollment=True),
            {
                "kind": "enroll",
                "index": index,
                "source_generation": source_generation,
                "name": name,
                "consent": consent,
            },
        )

    @Slot(str)
    def deleteProfile(self, identifier: str) -> None:
        try:
            self.gallery.delete(identifier)
            self.profilesChanged.emit()
            self._token += 1
            self._results = [
                "Gallery changed · waiting for frame" if enabled else "Recognition off"
                for enabled in self._enabled
            ]
            self._status = (
                "Enrollment deleted from the active gallery. "
                "Backups and filesystem copies are separate."
            )
            self._error = ""
            self._last_active = time.monotonic()
        except GalleryError as error:
            self._error = str(error)
        self.changed.emit()

    @Slot()
    def _sources_changed(self) -> None:
        changed = False
        for index, row in enumerate(self.cameras.manager.snapshot()):
            generation = cast(int, row["generation"])
            if generation != self._generation[index]:
                changed = True
                self._generation[index] = generation
                self._enabled[index] = False
                self._token += 1
                self._results[index] = "Recognition off · source changed or stopped"
        if changed:
            self.changed.emit()

    @Slot()
    def _tick(self) -> None:
        now = time.monotonic()
        if self.unlocked and now - self._last_active > 600:
            self.lock()
        if self._busy or not self.unlocked or self._closed:
            return
        for offset in (0, 1):
            index = (self._next_source + offset) % 2
            if not self._enabled[index] or now - self._last_run[index] < 1:
                continue
            image, source_generation, _, state, received_at = self.cameras.manager.vision_frame(
                index
            )
            if state != "streaming" or image.isNull() or now - received_at > 2:
                self._results[index] = "Waiting for a fresh connected frame"
                self.changed.emit()
                continue
            self._last_run[index] = now
            self._next_source = 1 - index
            settings = self.settings

            def recognize(image: Any = image, settings: MatchSettings = settings) -> list[str]:
                profiles = self.gallery.profiles()
                results = []
                for sample in self.runtime.samples(image):
                    result = match(sample.embedding, profiles, settings)
                    similarity = (
                        f" · cosine {result['similarity']:.3f}" if "similarity" in result else ""
                    )
                    results.append(result["label"] + similarity)
                return results

            self._submit(
                recognize,
                {"kind": "recognize", "index": index, "source_generation": source_generation},
            )
            break

    @Slot(object)
    def _finish(self, outcome: dict[str, Any]) -> None:
        self._busy = False
        if self._closed:
            return
        kind = outcome["kind"]
        if kind == "unlock":
            # A camera lifecycle change does not cancel a valid gallery unlock.
            # Gallery Lock itself invalidates the key operation's generation.
            completed_generation = outcome["generation"] + (0 if "error" in outcome else 1)
            if self.gallery.generation != completed_generation or (
                "error" not in outcome and not self.unlocked
            ):
                self.changed.emit()
                return
        elif outcome["token"] != self._token or outcome["generation"] != self.gallery.generation:
            self.changed.emit()
            return
        if kind in ("enroll", "recognize"):
            row = self.cameras.manager.snapshot()[outcome["index"]]
            if row["generation"] != outcome["source_generation"] or row["state"] != "streaming":
                self.changed.emit()
                return
        if "error" in outcome:
            self._error = outcome["error"]
            if kind == "recognize":
                self._enabled[outcome["index"]] = False
                self._results[outcome["index"]] = "Recognition stopped · local error"
        elif kind == "unlock":
            self.profilesChanged.emit()
            self._last_active = time.monotonic()
            self._status = (
                "Gallery unlocked · names and descriptors encrypted on disk · "
                "locks after 10 minutes"
            )
        elif kind == "enroll":
            samples = outcome["value"]
            if len(samples) != 1:
                self._error = (
                    "Enrollment needs exactly one usable face of at least 48 pixels "
                    "in the resized frame."
                )
            else:
                try:
                    self.gallery.add(
                        outcome["name"],
                        samples[0].embedding,
                        outcome["consent"],
                        outcome["generation"],
                    )
                    self.profilesChanged.emit()
                    self._token += 1
                    self._results = [
                        "Gallery changed · waiting for frame" if enabled else "Recognition off"
                        for enabled in self._enabled
                    ]
                    self._status = "Consenting enrollment saved. No photograph was stored."
                except GalleryError as error:
                    self._error = str(error)
        elif kind == "recognize":
            self._results[outcome["index"]] = (
                "\n".join(outcome["value"]) or "No usable face detected"
            )
        self.changed.emit()

    def shutdown(self) -> None:
        self._closed = True
        self._timer.stop()
        self.lock()
        self._executor.shutdown(wait=True, cancel_futures=True)
