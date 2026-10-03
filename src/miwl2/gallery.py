"""Consent-controlled encrypted gallery. No photographs or persistent keys."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from numpy.typing import NDArray


class GalleryError(ValueError):
    pass


def normalized(vector: NDArray[np.float32]) -> NDArray[np.float32]:
    result = np.asarray(vector, dtype=np.float32).reshape(-1)
    if result.shape != (128,) or not np.isfinite(result).all():
        raise GalleryError("The local model returned an invalid face descriptor.")
    norm = float(np.linalg.norm(result))
    if not np.isfinite(norm) or norm < 1e-8:
        raise GalleryError("The local model returned an empty face descriptor.")
    return result / norm


@dataclass(frozen=True)
class Profile:
    identifier: str
    name: str
    embedding: NDArray[np.float32] = field(repr=False, compare=False)


class Gallery:
    MAX_PROFILES = 100

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.RLock()
        self._key: bytes | None = None
        self._generation = 0

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def unlocked(self) -> bool:
        with self._lock:
            return self._key is not None

    @property
    def generation(self) -> int:
        with self._lock:
            return self._generation

    def lock(self) -> None:
        with self._lock:
            self._key = None
            self._generation += 1

    @staticmethod
    def _derive(passphrase: str, salt: bytes) -> bytes:
        if not 12 <= len(passphrase) <= 256:
            raise GalleryError("Use a passphrase of 12–256 characters. It cannot be recovered.")
        return Scrypt(salt=salt, length=32, n=32768, r=8, p=1).derive(passphrase.encode("utf-8"))

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        if self.exists and self.path.stat().st_size > 2_000_000:
            raise GalleryError("The gallery exceeds its 2 MB safety limit.")
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("PRAGMA secure_delete=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @staticmethod
    def _seal(key: bytes, data: bytes, identifier: str) -> bytes:
        nonce = os.urandom(12)
        return nonce + AESGCM(key).encrypt(nonce, data, ("miwl-gallery-v1:" + identifier).encode())

    @staticmethod
    def _open(key: bytes, data: bytes, identifier: str) -> bytes:
        if len(data) < 28 or len(data) > 16_384:
            raise GalleryError(
                "Gallery authentication failed. Lock the gallery and check its file."
            )
        try:
            return AESGCM(key).decrypt(
                data[:12], data[12:], ("miwl-gallery-v1:" + identifier).encode()
            )
        except InvalidTag as error:
            raise GalleryError(
                "Incorrect passphrase or damaged gallery. Nothing was decrypted."
            ) from error

    def unlock(self, passphrase: str, create: bool, generation: int) -> None:
        # Expensive KDF occurs outside the lock; Lock can invalidate an in-flight unlock.
        with self._lock:
            if generation != self._generation:
                raise GalleryError("Gallery operation was cancelled.")
            if create:
                if self.exists:
                    raise GalleryError("A gallery already exists. Unlock it with its passphrase.")
                salt = os.urandom(16)
                check = None
            else:
                if not self.exists:
                    raise GalleryError("Create your local gallery first.")
                try:
                    with self._connection() as connection:
                        rows = dict(connection.execute("SELECT key,value FROM metadata"))
                    salt, check = bytes(rows["salt"]), bytes(rows["check"])
                    if len(salt) != 16:
                        raise ValueError("salt")
                except (sqlite3.Error, KeyError, ValueError) as error:
                    raise GalleryError("This gallery file is damaged or unsupported.") from error
        key = self._derive(passphrase, salt)
        if check is not None and self._open(key, check, "check") != b"miwl-gallery-v1":
            raise GalleryError("This gallery version is unsupported.")
        with self._lock:
            if generation != self._generation:
                raise GalleryError("Gallery operation was cancelled.")
            if create:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation prevents replacing a gallery that appeared during the KDF.
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.close(fd)
                with self._connection() as connection:
                    connection.execute("CREATE TABLE metadata(key TEXT PRIMARY KEY,value BLOB)")
                    connection.execute(
                        "CREATE TABLE profiles(id TEXT PRIMARY KEY,sealed BLOB NOT NULL)"
                    )
                    connection.executemany(
                        "INSERT INTO metadata VALUES(?,?)",
                        [("salt", salt), ("check", self._seal(key, b"miwl-gallery-v1", "check"))],
                    )
            os.chmod(self.path, 0o600)
            self._key = key
            self._generation += 1

    def profiles(self) -> list[Profile]:
        with self._lock:
            if self._key is None:
                return []
            try:
                with self._connection() as connection:
                    rows = connection.execute("SELECT id,sealed FROM profiles LIMIT 101").fetchall()
                if len(rows) > self.MAX_PROFILES:
                    raise GalleryError("Gallery capacity exceeded.")
                profiles = []
                for identifier, sealed in rows:
                    payload = json.loads(self._open(self._key, bytes(sealed), identifier))
                    name = payload["name"]
                    if not isinstance(name, str) or not 1 <= len(name) <= 80:
                        raise GalleryError("Gallery record is invalid.")
                    profiles.append(
                        Profile(
                            identifier,
                            name,
                            normalized(np.array(payload["vector"], dtype=np.float32)),
                        )
                    )
                return profiles
            except (sqlite3.Error, KeyError, TypeError, json.JSONDecodeError) as error:
                raise GalleryError("Gallery data could not be read safely.") from error

    def add(self, name: str, vector: NDArray[np.float32], consent: bool, generation: int) -> str:
        name = name.strip()
        if not consent:
            raise GalleryError("Explicit permission from the person is required for enrollment.")
        if not 1 <= len(name) <= 80 or any(ord(char) < 32 for char in name):
            raise GalleryError("Enter a name of 1–80 characters without control characters.")
        vector = normalized(vector)
        with self._lock:
            if self._key is None or generation != self._generation:
                raise GalleryError("Unlock the gallery and retry enrollment.")
            profiles = self.profiles()
            if len(profiles) >= self.MAX_PROFILES:
                raise GalleryError("The gallery holds at most 100 consenting people.")
            if any(profile.name.casefold() == name.casefold() for profile in profiles):
                raise GalleryError(
                    "That name already exists. Delete its old enrollment before replacing it."
                )
            identifier = str(uuid.uuid4())
            payload = json.dumps(
                {"name": name, "vector": vector.tolist()}, separators=(",", ":")
            ).encode()
            with self._connection() as connection:
                connection.execute(
                    "INSERT INTO profiles VALUES(?,?)",
                    (identifier, self._seal(self._key, payload, identifier)),
                )
            self._generation += 1
            return identifier

    def delete(self, identifier: str) -> None:
        with self._lock:
            if self._key is None:
                raise GalleryError("Unlock the gallery before deleting an enrollment.")
            with self._connection() as connection:
                connection.execute("DELETE FROM profiles WHERE id=?", (identifier,))
            self._generation += 1
