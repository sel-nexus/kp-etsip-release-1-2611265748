"""Test report CSV quoting and formula-injection safety."""
import csv
import io
import pytest
from app.features.reports.csv_export import csv_line, safe_cell


@pytest.mark.parametrize('value,expected', [('', ''), (None, ''), ('ordinary', 'ordinary'), ('=1+2', "'=1+2"),
    ('  +1', "'  +1"), ('-2', "'-2"), ('@SUM(A1)', "'@SUM(A1)"), ('\ttext', "'\ttext"),
    ('\rtext', "'\rtext"), ('\x01text', "'\x01text"), ('  \x01text', "'  \x01text"), ('a,b', 'a,b')])
def test_safe_cell_neutralizes_formula_and_control_prefixes(value, expected):
    """Protect spreadsheet readers while preserving ordinary values."""
    assert safe_cell(value) == expected


@pytest.mark.parametrize('marker', ['=', '+', '-', '@'])
@pytest.mark.parametrize('prefix', ['', ' ', '\u00a0', '\u2003', ' \u2003\u00a0', '\u2003\t '])
def test_safe_cell_formula_markers_after_whitespace(prefix, marker):
    """Neutralize each marker even after mixed Unicode whitespace and controls."""
    value = prefix + marker + 'SUM(1,2)'
    assert safe_cell(value) == "'" + value


@pytest.mark.parametrize('control', [chr(code) for code in (*range(32), 127)])
@pytest.mark.parametrize('prefix', ['', ' ', '\u00a0', '\u2003', ' \u2003\u00a0'])
def test_safe_cell_control_prefixes_after_whitespace(prefix, control):
    """Neutralize all ASCII controls and DEL, including after Unicode whitespace."""
    value = prefix + control + 'ordinary'
    assert safe_cell(value) == "'" + value


@pytest.mark.parametrize('value', [' ', '\u00a0\u2003', '\u2003ordinary', '  ordinary',
                                  'ordinary=1', 'ordinary\ttext', "'already safe", 'a,b', 'a\nb', 42])
def test_safe_cell_preserves_ordinary_contents(value):
    """Keep non-dangerous whitespace, punctuation, and embedded controls intact."""
    assert safe_cell(value) == str(value)


def test_csv_line_round_trips_quotes_newlines_and_empty_values():
    """Encode each column without allowing commas or quotes to escape."""
    assert next(csv.reader(io.StringIO(csv_line(['a,b', '"quoted"', 'a\nb', None])))) == ['a,b', '"quoted"', 'a\nb', '']
