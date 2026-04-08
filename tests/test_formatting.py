from __future__ import annotations

from bot.formatting import DISCORD_MAX_LENGTH
from bot.formatting import split_message


class TestSplitMessage:
    def test_short_message_returned_as_single_chunk(self):
        msg = "hello world"
        chunks = split_message(msg)
        assert chunks == ["hello world"]

    def test_message_at_limit_returned_as_single_chunk(self):
        msg = "x" * DISCORD_MAX_LENGTH
        chunks = split_message(msg)
        assert len(chunks) == 1
        assert len(chunks[0]) == DISCORD_MAX_LENGTH

    def test_long_message_split_into_multiple_chunks(self):
        msg = "x" * (DISCORD_MAX_LENGTH + 1)
        chunks = split_message(msg)
        assert len(chunks) == 2
        assert all(len(c) <= DISCORD_MAX_LENGTH for c in chunks)

    def test_split_prefers_newline_boundaries(self):
        # Build a message with a natural newline split point
        part1 = "a" * (DISCORD_MAX_LENGTH - 10)
        part2 = "b" * 50
        msg = part1 + "\n" + part2
        chunks = split_message(msg)
        assert len(chunks) == 2
        # First chunk should end at the newline, not mid-word
        assert not chunks[0].endswith("b")

    def test_all_content_preserved_after_split(self):
        msg = "word " * 1000  # ~5000 chars
        chunks = split_message(msg)
        assert "".join(chunks).replace(" ", "") == "word" * 1000

    def test_empty_string_returns_single_empty_chunk(self):
        assert split_message("") == [""]
