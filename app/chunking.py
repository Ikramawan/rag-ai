def split_text(
    text: str,
    max_chars: int = 1800,
    overlap: int = 200,
) -> list[str]:
    if max_chars < 1 or not 0 <= overlap < max_chars:
        raise ValueError("Require max_chars > 0 and 0 <= overlap < max_chars.")

    text = text.strip()
    chunks = []
    start = 0

    while start < len(text):
        end = min(start + max_chars, len(text))

        # Prefer a paragraph, line or word boundary in the latter half.
        if end < len(text):
            midpoint = start + max_chars // 2

            for separator in ("\n\n", "\n", " "):
                boundary = text.rfind(separator, midpoint, end)
                if boundary != -1:
                    end = boundary + len(separator)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end == len(text):
            break

        start = max(start + 1, end - overlap)

    return chunks
