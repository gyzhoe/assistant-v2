"""Tests for text chunking utilities."""

from __future__ import annotations

from app.utils.chunker import chunk_by_markdown_headings, chunk_by_tokens


class TestChunkByMarkdownHeadings:
    def test_empty_text(self) -> None:
        assert chunk_by_markdown_headings("") == []

    def test_whitespace_only(self) -> None:
        assert chunk_by_markdown_headings("   \n  ") == []

    def test_no_headings(self) -> None:
        result = chunk_by_markdown_headings("Just some plain text content.")
        assert len(result) == 1
        assert result[0][0] == "Introduction"
        assert result[0][1] == "Just some plain text content."

    def test_single_heading(self) -> None:
        text = "## Getting Started\nThis is the getting started section."
        result = chunk_by_markdown_headings(text)
        assert len(result) == 1
        assert result[0][0] == "Getting Started"
        assert "getting started section" in result[0][1]

    def test_intro_plus_headings(self) -> None:
        text = (
            "This is the introduction.\n\n"
            "## Section One\nContent for section one.\n\n"
            "## Section Two\nContent for section two."
        )
        result = chunk_by_markdown_headings(text)
        assert len(result) == 3
        assert result[0][0] == "Introduction"
        assert "introduction" in result[0][1]
        assert result[1][0] == "Section One"
        assert result[2][0] == "Section Two"

    def test_h3_headings(self) -> None:
        text = "### Subsection\nSubsection content here."
        result = chunk_by_markdown_headings(text)
        assert len(result) == 1
        assert result[0][0] == "Subsection"

    def test_mixed_h2_h3(self) -> None:
        text = (
            "## Main Section\nMain content.\n\n"
            "### Subsection\nSub content."
        )
        result = chunk_by_markdown_headings(text)
        assert len(result) == 2
        assert result[0][0] == "Main Section"
        assert result[1][0] == "Subsection"

    def test_h1_not_split(self) -> None:
        """H1 headings (single #) should not trigger a split."""
        text = "# Title\nSome content under H1."
        result = chunk_by_markdown_headings(text)
        assert len(result) == 1
        assert result[0][0] == "Introduction"
        assert "# Title" in result[0][1]

    def test_oversized_section_sub_split(self) -> None:
        # Create a section with >10 words (using max_tokens=10 for test)
        words = " ".join(f"word{i}" for i in range(25))
        text = f"## Big Section\n{words}"
        result = chunk_by_markdown_headings(text, max_tokens=10, overlap_tokens=2)
        assert len(result) > 1
        assert all("Big Section (part" in title for title, _ in result)

    def test_empty_section_skipped(self) -> None:
        text = "## Empty\n## Non-empty\nActual content here."
        result = chunk_by_markdown_headings(text)
        assert len(result) == 1
        assert result[0][0] == "Non-empty"

    def test_heading_whitespace_stripped(self) -> None:
        text = "##   Spaced Title  \nContent."
        result = chunk_by_markdown_headings(text)
        assert result[0][0] == "Spaced Title"


class TestChunkByTokens:
    def test_empty(self) -> None:
        assert chunk_by_tokens("") == []

    def test_short_text(self) -> None:
        result = chunk_by_tokens("hello world", max_tokens=10)
        assert result == ["hello world"]

    def test_splits_with_overlap(self) -> None:
        words = " ".join(f"w{i}" for i in range(20))
        result = chunk_by_tokens(words, max_tokens=10, overlap_tokens=2)
        assert len(result) > 1
