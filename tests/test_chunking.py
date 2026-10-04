from itertools import pairwise

import pytest

from app.chunking import split_text


def test_long_text_preserves_content_and_overlap() -> None:
    text = "0123456789" * 500

    chunks = split_text(text, max_chars=1800, overlap=200)

    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 1800 for chunk in chunks)

    restored = chunks[0]
    for previous, current in pairwise(chunks):
        assert previous[-200:] == current[:200]
        restored += current[200:]

    assert restored == text


def test_paragraph_boundaries_preserve_words() -> None:
    text = "\n\n".join(
        f"Paragraph {number}: contains unique information." for number in range(100)
    )

    chunks = split_text(text)

    assert len(chunks) > 1
    assert all(len(chunk) <= 1800 for chunk in chunks)
    assert set(text.split()) <= set(" ".join(chunks).split())


def test_empty_text_returns_no_chunks() -> None:
    assert split_text(" \n ") == []


@pytest.mark.parametrize(
    ("max_chars", "overlap"),
    [(0, 0), (100, -1), (100, 100)],
)
def test_invalid_settings_are_rejected(max_chars, overlap) -> None:
    with pytest.raises(ValueError):
        split_text("sample", max_chars=max_chars, overlap=overlap)
