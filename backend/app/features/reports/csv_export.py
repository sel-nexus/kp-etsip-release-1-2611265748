"""Encode report rows as safely quoted spreadsheet-compatible CSV."""
import csv
import io
from typing import Any


def safe_cell(value: Any) -> str:
    """Neutralize formulas and leading control characters in untrusted values."""
    text = "" if value is None else str(value)
    leading = text.lstrip(' ')
    if text and (any(ord(char) < 32 or ord(char) == 127 for char in text[:len(text) - len(leading) + 1]) or leading.startswith(("=", "+", "-", "@"))):
        return "'" + text
    return text


def csv_line(values: tuple[Any, ...] | list[Any]) -> str:
    """Quote a single record and return it without retaining prior rows."""
    output = io.StringIO(newline="")
    csv.writer(output, quoting=csv.QUOTE_ALL).writerow([safe_cell(value) for value in values])
    return output.getvalue()
