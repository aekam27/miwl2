from __future__ import annotations

import re
from collections.abc import Iterator
from threading import Event

from miwl2.domain import Operation, ProviderInfo, ProviderRequest

TEST_LABEL = "TEST PROVIDER · NOT REAL AI"


class DeterministicProvider:
    """An extractive, scripted local provider. No model, network, or credentials."""

    def __init__(self, chunk_delay: float = 0.035, preparation_delay: float = 0.25) -> None:
        self.chunk_delay = chunk_delay
        self.preparation_delay = preparation_delay

    @property
    def info(self) -> ProviderInfo:
        return ProviderInfo("deterministic-v1", "Deterministic test provider", True, "local")

    @staticmethod
    def _sentences(source: str) -> list[str]:
        normalized = re.sub(r"\s+", " ", source).strip()
        return [part.strip() for part in re.split(r"(?<=[.!?])\s+", normalized) if part.strip()]

    def render(self, request: ProviderRequest) -> str:
        sentences = self._sentences(request.source)
        prompt = request.prompt.casefold()
        if request.operation == Operation.ARTICLE:
            return (
                f"{TEST_LABEL}\n\nArticle workflow fixture\n\nTopic: {request.prompt}\n\n"
                "Introduction → supporting points → conclusion.\n\n"
                "This is a fixed test outline, not a generated article. "
                "Select a configured local Ollama model for actual writing."
            )
        if request.operation == Operation.PARAPHRASE:
            return (
                f"{TEST_LABEL}\n\nParaphrase workflow fixture\n\n"
                f"{request.source}\n\n"
                "The fixture repeats your source unchanged; it does not paraphrase."
            )
        if request.operation == Operation.SUMMARIZE or any(
            word in prompt for word in ("summarize", "summarise", "summary", "key points")
        ):
            bullets = "\n".join(f"• {sentence}" for sentence in sentences[:3])
            if not bullets:
                raise ValueError("Paste some source text before requesting a summary.")
            return f"{TEST_LABEL}\n\nExtractive preview\n\n{bullets}"
        if any(word in prompt for word in ("shorter", "concise", "brief")):
            previous = request.previous_result
            prior_bullets = [line for line in previous.splitlines() if line.startswith("• ")]
            first = (
                prior_bullets[0] if prior_bullets else (f"• {sentences[0]}" if sentences else "")
            )
            if not first:
                first = "There is no source or prior extractive result to shorten yet."
            return f"{TEST_LABEL}\n\nShorter preview\n\n{first}"
        context = (
            f"Your source begins:\n“{sentences[0][:320]}”"
            if sentences
            else "Paste source text to try the extractive summary workflow."
        )
        return (
            f"{TEST_LABEL}\n\nYou asked: {request.prompt}\n\n"
            "This scripted provider demonstrates conversation and storage; it cannot reason "
            "or answer general questions.\n\n"
            f"{context}\n\nTry “summarize this”, “key points”, or “make it shorter”."
        )

    def stream(self, request: ProviderRequest, cancel: Event) -> Iterator[str]:
        if cancel.wait(self.preparation_delay):
            return
        text = self.render(request)
        for index, offset in enumerate(range(0, len(text), 32)):
            if cancel.wait(self.chunk_delay):
                return
            if request.simulate_error and index == 2:
                raise RuntimeError(
                    "Simulated provider interruption. Your source and saved output are safe."
                )
            yield text[offset : offset + 32]
