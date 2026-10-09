def split_text(
    text: str,
    max_chars: int = 1800,
    overlap: int = 200,
) -> list[str]:
    if max_chars < 1 or not 0 <= overlap < max_chars:
        raise ValueError("Require max_chars > 0 and 0 <= overlap < max_chars.")

    text = text.strip()
    # Loaders render simple tables as consecutive pipe-separated rows.
    # Protect only tables that fit within the configured chunk limit.
    tables = []
    offset = 0
    table_start = None
    for line in text.splitlines(keepends=True):
        if " | " in line:
            if table_start is None:
                table_start = offset
        elif table_start is not None:
            table_end = offset
            if table_end - table_start <= max_chars:
                tables.append((table_start, table_end))
            table_start = None
        offset += len(line)
    if table_start is not None and len(text) - table_start <= max_chars:
        tables.append((table_start, len(text)))

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

        for table_start, table_end in tables:
            if table_start < end < table_end:
                end = table_end if table_end - start <= max_chars else table_start
                break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end == len(text):
            break

        next_start = max(start + 1, end - overlap)
        for table_start, table_end in tables:
            if end == table_start:
                # Leave enough room for the whole table in the next chunk.
                next_start = max(next_start, table_end - max_chars)
            elif table_start < next_start < table_end <= end:
                # Avoid restarting partway through a table already included.
                next_start = table_end
        start = next_start

    return chunks
