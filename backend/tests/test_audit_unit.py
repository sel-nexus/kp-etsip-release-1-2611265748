"""Exercise safe audit serialization and scoped queries against real Mongo."""
from dataclasses import replace
from datetime import UTC, datetime
import pytest
from bson import ObjectId
from app.core.errors import DomainError
from app.features.audit.service import csv_safe
from app.features.auth.schemas import LoginRequest
from conftest import PASSWORD


@pytest.mark.parametrize('value,expected', [
    ('=1+1', "'=1+1"), ('  +SUM(A1)', "'  +SUM(A1)"), ('-2', "'-2"),
    ('@formula', "'@formula"), ('\ttext', "'\ttext"), ('ordinary', 'ordinary'), (None, ''),
])
def test_csv_safe_neutralizes_formula_and_control_prefixes(value, expected):
    """Prevent spreadsheet evaluation without changing ordinary values."""
    assert csv_safe(value) == expected


@pytest.mark.parametrize('control', [chr(code) for code in (*range(32), 127)])
@pytest.mark.parametrize('prefix', ['', ' ', '  ', '\u00a0'])
@pytest.mark.parametrize('suffix', ['', 'text', '=1+1', '+SUM(A1)', '-2', '@formula'])
def test_csv_safe_neutralizes_every_leading_ascii_control(control, prefix, suffix):
    """Guard each leading control byte, even after whitespace or before formulas."""
    value = prefix + control + suffix
    assert csv_safe(value) == "'" + value


@pytest.mark.parametrize('prefix', ['', ' ', '  ', '\u00a0', '\u2003', '\t', '\n', '\r', ' \t\n'])
@pytest.mark.parametrize('formula', ['=1+1', '+SUM(A1)', '-2', '@formula'])
def test_csv_safe_neutralizes_formulas_after_whitespace(prefix, formula):
    """Protect each spreadsheet formula prefix after varied whitespace."""
    value = prefix + formula
    assert csv_safe(value) == "'" + value


@pytest.mark.parametrize('value,expected', [
    ('', ''), ('   ', '   '), ('\u00a0 ordinary', '\u00a0 ordinary'),
    ('ordinary\ttext', 'ordinary\ttext'), ('ordinary\n=1+1', 'ordinary\n=1+1'),
    ('quoted, "text"', 'quoted, "text"'), (42, '42'),
    (datetime(2025, 1, 2, tzinfo=UTC), '2025-01-02T00:00:00+00:00'),
])
def test_csv_safe_preserves_nonleading_content_and_formats_values(value, expected):
    """Retain safe content and the existing non-string conversion contract."""
    assert csv_safe(value) == expected


async def test_audit_listing_scope_and_validation(application, db):
    """Filter real persisted records, and deny invalid or unauthorized access."""
    auth = application.state.auth
    result = await auth.login(LoginRequest(email='auditor@ketsip.local', password=PASSWORD))
    actor = await auth.authenticate(result.token)
    service = auth.audit
    page = await service.listing(actor, actor.user.id, 'login', None, None, 1, 1)
    assert page.total == 1 and page.items[0].details == 'Login succeeded'
    assert PASSWORD not in str(page.model_dump())
    with pytest.raises(DomainError):
        await service.listing(actor, 'invalid', None, None, None, 1, 25)
    with pytest.raises(DomainError):
        await service.listing(actor, None, None, datetime(2025, 2, 1, tzinfo=UTC), datetime(2025, 1, 1, tzinfo=UTC), 1, 25)
    with pytest.raises(DomainError):
        await service.listing(actor, None, None, None, None, 0, 25)
    hidden = replace(actor, user=actor.user.model_copy(update={'role': 'Engineer', 'permissions': ['view', 'export']}))
    with pytest.raises(DomainError):
        await service.listing(hidden, None, None, None, None, 1, 25)
    portfolio = await db.portfolios.find_one({})
    restricted = replace(actor, user=actor.user.model_copy(update={'portfolioAccess': [str(portfolio['_id'])]}))
    page = await service.listing(restricted, None, None, None, None, 1, 25)
    assert page.total == 0
    assert ObjectId(actor.user.id) != portfolio['_id']
