from __future__ import annotations

import pytest

from bot.formatting import DISCORD_MAX_LENGTH
from bot.formatting import split_message
from bot.formatting import to_discord_markdown


class TestToDiscordMarkdown:
    def test_plain_text_unchanged(self):
        assert to_discord_markdown("hello world") == "hello world"

    def test_h1_converted_to_bold(self):
        result = to_discord_markdown("# Title")
        assert result == "**Title**"

    def test_h2_converted_to_bold(self):
        result = to_discord_markdown("## Section")
        assert result == "**Section**"

    def test_h3_converted_to_bold(self):
        result = to_discord_markdown("### Sub")
        assert result == "**Sub**"

    def test_bold_preserved(self):
        result = to_discord_markdown("**bold text**")
        assert "**bold text**" in result

    def test_inline_code_preserved(self):
        result = to_discord_markdown("`code`")
        assert "`code`" in result

    def test_code_block_preserved(self):
        result = to_discord_markdown("```python\nprint('hi')\n```")
        assert "```" in result
        assert "print('hi')" in result

    def test_heading_inside_code_block_not_converted(self):
        text = "```\n# not a heading\n```"
        result = to_discord_markdown(text)
        assert "# not a heading" in result

    def test_heading_between_two_code_blocks_not_converted(self):
        text = "```python\nprint('hi')\n```\n\n# This is a real heading\n\n```bash\n# not a heading\n```"
        result = to_discord_markdown(text)
        assert "**This is a real heading**" in result
        assert "# not a heading" in result

    def test_multiple_headings(self):
        text = "# Title\n\nsome text\n\n## Section"
        result = to_discord_markdown(text)
        assert "**Title**" in result
        assert "**Section**" in result
        assert "# " not in result

    def test_strips_trailing_whitespace(self):
        result = to_discord_markdown("hello   \n\n")
        assert not result.endswith("\n")

    def test_empty_string(self):
        assert to_discord_markdown("") == ""


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
