from __future__ import annotations

from dataclasses import replace

from miwl2.domain import Operation, ProviderRequest, Turn

TASK_INSTRUCTIONS = {
    Operation.CHAT: "Answer the user's message. Use the source and draft when relevant.",
    Operation.SUMMARIZE: (
        "Summarize only the supplied source in concise bullet points. Preserve key facts, "
        "qualifications and uncertainty. Do not add unsupported information."
    ),
    Operation.ARTICLE: (
        "Write a useful, coherent article about the user's topic. Use supplied source notes "
        "when present. Do not invent citations or present uncertain facts as verified."
    ),
    Operation.PARAPHRASE: (
        "Rewrite the supplied source in clear, natural language. Preserve its meaning, facts, "
        "names and qualifications. Return the rewritten text without adding new claims."
    ),
}


def prepare_request(request: ProviderRequest, prefix: str, byte_limit: int) -> ProviderRequest:
    """Keep current text intact; include the newest contiguous complete chat exchanges."""
    system = prefix + TASK_INSTRUCTIONS[request.operation]
    current = current_content(request)
    remaining = byte_limit - len(system.encode("utf-8")) - len(current.encode("utf-8"))
    if remaining < 0:
        raise ValueError(
            "The source, draft and current request exceed the text limit. "
            "Shorten the source or draft before sending. No text was sent."
        )
    if request.operation != Operation.CHAT:
        return replace(request, history=())
    pairs: list[tuple[Turn, Turn]] = []
    for index in range(0, len(request.history) - 1, 2):
        user, assistant = request.history[index : index + 2]
        if user.role == "user" and assistant.role == "assistant":
            pairs.append((user, assistant))
    kept: list[tuple[Turn, Turn]] = []
    for pair in reversed(pairs):
        cost = sum(len(turn.body.encode("utf-8")) for turn in pair)
        if cost > remaining:
            break
        kept.append(pair)
        remaining -= cost
    history = tuple(turn for pair in reversed(kept) for turn in pair)
    return replace(
        request,
        history=history,
        omitted_history_turns=request.omitted_history_turns + len(request.history) - len(history),
    )


def current_content(request: ProviderRequest) -> str:
    content = f"Task: {request.operation.value}\n"
    if request.source.strip():
        content += f"\n<source>\n{request.source}\n</source>\n"
    if request.operation == Operation.CHAT and request.previous_result.strip():
        content += f"\n<draft>\n{request.previous_result}\n</draft>\n"
    return content + f"\nUser request: {request.prompt or TASK_INSTRUCTIONS[request.operation]}"


def messages(request: ProviderRequest, prefix: str, byte_limit: int) -> list[dict[str, str]]:
    bounded = prepare_request(request, prefix, byte_limit)
    return (
        [{"role": "system", "content": prefix + TASK_INSTRUCTIONS[bounded.operation]}]
        + [{"role": turn.role, "content": turn.body} for turn in bounded.history]
        + [{"role": "user", "content": current_content(bounded)}]
    )
