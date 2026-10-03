"""Bounded local YuNet/SFace inference; similarity suggests matches, never authenticates."""

from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from PySide6.QtGui import QImage

from miwl2.gallery import GalleryError, Profile, normalized


@dataclass(frozen=True)
class VisionPaths:
    detector: Path
    recognizer: Path

    @classmethod
    def local(cls, root: Path) -> VisionPaths:
        directory = root / ".runtime/vision-models"
        return cls(
            directory / "face_detection_yunet_2023mar.onnx",
            directory / "face_recognition_sface_2021dec.onnx",
        )

    @property
    def available(self) -> bool:
        return self.detector.is_file() and self.recognizer.is_file()


@dataclass(frozen=True)
class FaceSample:
    box: tuple[int, int, int, int]
    detection_score: float
    embedding: NDArray[np.float32] = field(repr=False, compare=False)


@dataclass(frozen=True)
class MatchSettings:
    threshold: float = 0.5
    uncertain_band: float = 0.1
    margin: float = 0.08

    def validated(self) -> MatchSettings:
        if (
            not 0.35 <= self.threshold <= 0.9
            or not 0.01 <= self.uncertain_band <= 0.2
            or not 0.01 <= self.margin <= 0.3
        ):
            raise GalleryError(
                "Use threshold 0.35–0.90, uncertainty band 0.01–0.20 and margin 0.01–0.30."
            )
        return self


def match(
    vector: NDArray[np.float32], profiles: list[Profile], settings: MatchSettings
) -> dict[str, Any]:
    settings.validated()
    if not profiles:
        return {"state": "unknown", "label": "Unknown · gallery empty"}
    vector = normalized(vector)
    scores = sorted(
        ((float(np.dot(vector, profile.embedding)), profile) for profile in profiles),
        key=lambda value: value[0],
        reverse=True,
    )
    score, profile = scores[0]
    difference = score - scores[1][0] if len(scores) > 1 else 2.0
    if score >= settings.threshold and difference >= settings.margin:
        return {
            "state": "possible",
            "label": f"Possible match: {profile.name}",
            "similarity": round(score, 3),
        }
    if score >= settings.threshold - settings.uncertain_band:
        return {
            "state": "uncertain",
            "label": "Uncertain · no identity suggested",
            "similarity": round(score, 3),
        }
    return {"state": "unknown", "label": "Unknown", "similarity": round(score, 3)}


class VisionRuntime:
    DETECTOR_SHA = "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
    RECOGNIZER_SHA = "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"

    def __init__(self, paths: VisionPaths) -> None:
        self.paths = paths
        self._detector: Any = None
        self._recognizer: Any = None
        self._lock = threading.Lock()

    def _load(self) -> None:
        if self._detector is not None:
            return
        if not self.paths.available:
            raise GalleryError("Pinned local YuNet/SFace models are missing.")
        for path, expected in [
            (self.paths.detector, self.DETECTOR_SHA),
            (self.paths.recognizer, self.RECOGNIZER_SHA),
        ]:
            if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise GalleryError("A local vision model does not match its pinned hash.")
        cv2.setNumThreads(2)
        self._detector = cv2.FaceDetectorYN.create(
            str(self.paths.detector), "", (640, 480), 0.9, 0.3, 100
        )
        self._recognizer = cv2.FaceRecognizerSF.create(str(self.paths.recognizer), "")

    @staticmethod
    def _pixels(image: QImage) -> NDArray[np.uint8]:
        if image.isNull() or image.width() > 1920 or image.height() > 1080:
            raise GalleryError("Use a current frame no larger than 1920 × 1080.")
        image = image.convertToFormat(QImage.Format.Format_RGB888)
        rgb = (
            np.frombuffer(image.bits(), dtype=np.uint8)
            .reshape(image.height(), image.bytesPerLine())[:, : image.width() * 3]
            .reshape(image.height(), image.width(), 3)
        )
        return cast(NDArray[np.uint8], cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))

    def samples(self, image: QImage, enrollment: bool = False) -> list[FaceSample]:
        with self._lock:
            self._load()
            frame = self._pixels(image)
            height, width = frame.shape[:2]
            scale = min(1.0, 640 / max(height, width))
            if scale < 1:
                frame = cast(
                    NDArray[np.uint8],
                    cv2.resize(
                        frame, (max(1, round(width * scale)), max(1, round(height * scale)))
                    ),
                )
            self._detector.setInputSize((frame.shape[1], frame.shape[0]))
            _, faces = self._detector.detect(frame)
            result: list[FaceSample] = []
            if faces is None:
                return result
            if enrollment and len(faces) != 1:
                raise GalleryError("Enrollment requires exactly one detected face.")
            for face in faces[:5]:
                x, y, w, h = face[:4]
                if (
                    min(w, h) < 48
                    or x < 0
                    or y < 0
                    or x + w > frame.shape[1]
                    or y + h > frame.shape[0]
                ):
                    continue
                aligned = self._recognizer.alignCrop(frame, face)
                vector = normalized(self._recognizer.feature(aligned))
                result.append(
                    FaceSample(
                        cast(
                            tuple[int, int, int, int],
                            tuple(int(float(value) / scale) for value in face[:4]),
                        ),
                        float(face[14]),
                        vector,
                    )
                )
            return result

    def synthetic_smoke(self) -> dict[str, Any]:
        """Exercise both networks without an image of a person or exposing a descriptor."""
        with self._lock:
            self._load()
            pattern = np.zeros((112, 112, 3), dtype=np.uint8)
            pattern[24:88, 24:88] = (20, 60, 100)
            synthetic_landmarks = np.array(
                [0, 0, 112, 112, 32, 42, 80, 42, 56, 64, 38, 85, 74, 85, 1], dtype=np.float32
            )
            aligned = self._recognizer.alignCrop(pattern, synthetic_landmarks)
            descriptor = normalized(self._recognizer.feature(aligned))
            self._detector.setInputSize((112, 112))
            _, detections = self._detector.detect(pattern)
            return {
                "aligned_shape": list(aligned.shape),
                "synthetic_landmarks_only": True,
                "descriptor_dimensions": int(descriptor.size),
                "finite": bool(np.isfinite(descriptor).all()),
                "synthetic_detections": 0 if detections is None else int(len(detections)),
                "accuracy_tested": False,
            }
