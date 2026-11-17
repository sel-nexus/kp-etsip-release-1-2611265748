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


def test_csv_line_round_trips_quotes_newlines_and_empty_values():
    """Encode each column without allowing commas or quotes to escape."""
    assert next(csv.reader(io.StringIO(csv_line(['a,b', '"quoted"', 'a\nb', None])))) == ['a,b', '"quoted"', 'a\nb', '']
