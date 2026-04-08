"""Discord message utilities."""

from __future__ import annotations

DISCORD_MAX_LENGTH = 2000


def split_message(text: str) -> list[str]:
    """Split a message into chunks that fit within Discord's message length limit.

    Prefers splitting at newline boundaries to avoid cutting in the middle
    of a paragraph or sentence.
    """
    if len(text) <= DISCORD_MAX_LENGTH:
        return [text]

    chunks: list[str] = []
    while len(text) > DISCORD_MAX_LENGTH:
        # Look for the last newline within the allowed window.
        split_at = text.rfind("\n", 0, DISCORD_MAX_LENGTH)
        if split_at == -1:
            # No newline found — hard split at the limit.
            split_at = DISCORD_MAX_LENGTH
        else:
            # Include the newline in the first chunk, skip it in the next.
            split_at += 1
        chunks.append(text[:split_at])
        text = text[split_at:]

    chunks.append(text)
    return chunks
