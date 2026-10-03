from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any

from PySide6.QtCore import Property, QObject, QSize, Signal, Slot
from PySide6.QtGui import QImage
from PySide6.QtQuick import QQuickImageProvider

from miwl2.cameras import CameraManager, CameraSource


class CameraImages(QQuickImageProvider):
    def __init__(self, manager: CameraManager) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self.manager = manager

    def requestImage(self, id: str, size: QSize, requestedSize: QSize) -> QImage:
        image = self.manager.image(int(id.split("/")[0]))
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


class CameraBridge(QObject):
    sourcesChanged = Signal()
    _changed = Signal()

    def __init__(self, manager: CameraManager) -> None:
        super().__init__()
        self.manager = manager
        self._errors = ["", ""]
        self._pending = [False, False]
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="miwl2-camera-control"
        )
        self._changed.connect(self.sourcesChanged)
        manager.on_change = self._changed.emit

    @Property(list, notify=sourcesChanged)
    def sources(self) -> list[dict[str, Any]]:
        return [
            {**source, "error": self._errors[index], "pending": self._pending[index]}
            for index, source in enumerate(self.manager.snapshot())
        ]

    @Slot(int, str, str, bool, result=bool)
    def configure(self, index: int, name: str, url: str, authorized: bool) -> bool:
        if index not in {0, 1}:
            return False
        try:
            self.manager.configure(index, CameraSource(name, url, authorized))
        except ValueError as exception:
            self._errors[index] = str(exception)
            self.sourcesChanged.emit()
            return False
        self._errors[index] = ""
        self.sourcesChanged.emit()
        return True

    @Slot(int)
    def connectSource(self, index: int) -> None:
        if index not in {0, 1}:
            return
        try:
            self._errors[index] = ""
            self.manager.connect(index)
        except ValueError as exception:
            self._errors[index] = str(exception)
        self.sourcesChanged.emit()

    @Slot(int)
    def reconnect(self, index: int) -> None:
        if index not in {0, 1}:
            return
        if self._pending[index]:
            return
        generation = self.manager.prepare_reconnect(index)
        self._pending[index] = True
        self.sourcesChanged.emit()

        def finish() -> None:
            try:
                self.manager.finish_reconnect(index, generation)
            except ValueError as exception:
                self._errors[index] = str(exception)
            finally:
                self._pending[index] = False
                self._changed.emit()

        self._executor.submit(finish)

    @Slot(int)
    def pause(self, index: int) -> None:
        if index not in {0, 1}:
            return
        self.manager.stop(index, paused=True)

    @Slot(int)
    def stop(self, index: int) -> None:
        if index not in {0, 1}:
            return
        self.manager.stop(index)

    def shutdown(self) -> None:
        self.manager.shutdown()
        self._executor.shutdown(wait=True, cancel_futures=True)
