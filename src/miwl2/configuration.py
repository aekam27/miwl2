from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from miwl2.domain import Provider
from miwl2.ollama import OllamaProvider
from miwl2.providers import DeterministicProvider


@dataclass(frozen=True)
class ProviderConfiguration:
    provider: str = "deterministic"
    endpoint: str = "http://127.0.0.1:11434"
    model: str = "gemma3:4b"

    def validated(self) -> ProviderConfiguration:
        if self.provider not in {"deterministic", "ollama", "cloud"}:
            raise ValueError("Choose the fixture, local Ollama or OpenAI cloud provider.")
        endpoint = self.endpoint.strip().rstrip("/")
        parsed = urlsplit(endpoint)
        model = self.model.strip()
        if self.provider == "cloud":
            if endpoint != "https://api.openai.com/v1":
                raise ValueError("Cloud text requests use https://api.openai.com/v1 only.")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model):
                raise ValueError("Enter an enabled OpenAI Chat Completions model ID.")
            return ProviderConfiguration("cloud", endpoint, model)
        try:
            port = parsed.port
        except ValueError as exception:
            raise ValueError("Use a valid local Ollama port.") from exception
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path
            or parsed.query
            or parsed.fragment
            or port is None
        ):
            raise ValueError(
                "Use a loopback HTTP address with a port, such as http://127.0.0.1:11434."
            )
        model = self.model.strip()
        if (
            not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", model)
            or "cloud" in model.lower()
        ):
            raise ValueError("Enter an installed local model name, such as gemma3:4b.")
        return ProviderConfiguration(self.provider, endpoint, model)

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def build(self) -> Provider:
        configuration = self.validated()
        if configuration.provider == "deterministic":
            return DeterministicProvider()
        if configuration.provider == "cloud":
            from miwl2.cloud import CloudProvider

            return CloudProvider(configuration.model)
        return OllamaProvider(configuration.endpoint, configuration.model)
