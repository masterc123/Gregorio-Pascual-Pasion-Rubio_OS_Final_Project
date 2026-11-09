"""Small helpers shared by several MiniShell modules."""


def format_table(headers, rows):
    """Return a plain-text table (header, separator line, rows) as one string."""
    str_rows = [[str(c) for c in r] for r in rows]
    widths = [len(h) for h in headers]
    for r in str_rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))

    def fmt(row):
        return "  ".join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip()

    lines = [fmt(headers), "  ".join("-" * w for w in widths)]
    lines += [fmt(r) for r in str_rows]
    return "\n".join(lines)


def parse_int(text):
    """int(text), or None when text is not a valid integer."""
    try:
        return int(text)
    except (TypeError, ValueError):
        return None


def read_text_file(path):
    """Read a whole text file (UTF-8, bad bytes replaced)."""
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def os_error_text(err):
    """Short human-readable text for an OSError ('No such file or directory')."""
    return err.strerror or str(err)
