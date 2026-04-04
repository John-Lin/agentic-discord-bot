"""Convert standard Markdown to Discord-compatible Markdown."""

from __future__ import annotations

import re

DISCORD_MAX_LENGTH = 2000

# Matches fenced code blocks (``` ... ```) so we can skip heading conversion inside them.
_CODE_BLOCK_RE = re.compile(r"```.*?```", re.DOTALL)

# Matches ATX headings: optional leading whitespace, 1-6 # signs, space, then text.
_HEADING_RE = re.compile(r"^#{1,6} (.+)$", re.MULTILINE)


def to_discord_markdown(text: str) -> str:
    """Convert standard Markdown to Discord-compatible Markdown.

    The main transformation is converting headings to bold text, since
    Discord does not render heading syntax.  Everything inside fenced
    code blocks is left untouched.
    """
    if not text:
        return text

    # Split on code blocks, process non-code segments only.
    parts = _CODE_BLOCK_RE.split(text)
    code_blocks = _CODE_BLOCK_RE.findall(text)

    processed_parts = [_HEADING_RE.sub(r"**\1**", part) for part in parts]

    # Interleave processed text and original code blocks.
    result_parts: list[str] = []
    for i, part in enumerate(processed_parts):
        result_parts.append(part)
        if i < len(code_blocks):
            result_parts.append(code_blocks[i])

    return "".join(result_parts).strip()


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
