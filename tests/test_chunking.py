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


@pytest.mark.parametrize("preamble_size", [0, 80, 160])
@pytest.mark.parametrize("overlap", [0, 20, 99])
def test_small_table_stays_whole_without_losing_content(preamble_size, overlap):
    table = "Priority | Target\nP1 | 15 minutes\nP2 | 1 business hour"
    preamble = " ".join(f"intro-{number}" for number in range(preamble_size // 8))
    ending = " ".join(f"ending-{number}" for number in range(20))
    text = preamble + "\n" + table + "\n" + ending
    chunks = split_text(text, max_chars=100, overlap=overlap)

    assert any(table in chunk for chunk in chunks)
    assert all(0 < len(chunk) <= 100 for chunk in chunks)
    assert set(text.split()) <= set(" ".join(chunks).split())


def test_oversized_table_respects_chunk_limit_and_preserves_rows():
    rows = [f"P{number} | target-{number}" for number in range(40)]
    chunks = split_text("\n".join(rows), max_chars=100, overlap=20)

    assert len(chunks) > 1
    assert all(0 < len(chunk) <= 100 for chunk in chunks)
    assert all(any(row in chunk for chunk in chunks) for row in rows)


@pytest.mark.parametrize(
    ("max_chars", "overlap"),
    [(0, 0), (100, -1), (100, 100)],
)
def test_invalid_settings_are_rejected(max_chars, overlap) -> None:
    with pytest.raises(ValueError):
        split_text("sample", max_chars=max_chars, overlap=overlap)
