from __future__ import annotations

from typing import Iterable

import tiktoken


def _get_encoder():
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(text: str) -> int:
    encoder = _get_encoder()
    return len(encoder.encode(text))


def _split_paragraphs(text: str) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n\n")]
    return [p for p in paragraphs if p]


def chunk_text(
    text: str,
    min_tokens: int,
    max_tokens: int,
    overlap: int,
) -> Iterable[tuple[str, int]]:
    encoder = _get_encoder()
    paragraphs = _split_paragraphs(text)

    current: list[str] = []
    current_tokens = 0
    for paragraph in paragraphs:
        tokens = len(encoder.encode(paragraph))
        if current_tokens + tokens <= max_tokens or not current:
            current.append(paragraph)
            current_tokens += tokens
            continue

        chunk_text = "\n\n".join(current)
        yield chunk_text, len(encoder.encode(chunk_text))

        if overlap > 0:
            overlap_tokens = encoder.encode(chunk_text)[-overlap:]
            overlap_text = encoder.decode(overlap_tokens)
            current = [overlap_text, paragraph]
            current_tokens = len(encoder.encode(overlap_text)) + tokens
        else:
            current = [paragraph]
            current_tokens = tokens

    if current:
        chunk_text = "\n\n".join(current)
        token_count = len(encoder.encode(chunk_text))
        if token_count >= min_tokens or not paragraphs:
            yield chunk_text, token_count
