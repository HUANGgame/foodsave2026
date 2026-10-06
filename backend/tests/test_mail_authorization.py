"""Authorization only: no credentials, provider calls or real messages."""
from datetime import datetime, timezone
import pytest
import foodsave.account_mail as mail


@pytest.fixture(autouse=True)
def fixed_time(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 10, 6, 20, 30, tzinfo=timezone.utc)
    monkeypatch.setattr(mail, 'datetime', Clock)
    monkeypatch.delenv('FOODSAVE_MAIL_AUTHORIZATION_MODE', raising=False)
    monkeypatch.delenv('FOODSAVE_MAIL_AUTHORIZED_UNTIL', raising=False)
    monkeypatch.setenv('FOODSAVE_MAIL_APPROVED', 'true')


@pytest.mark.parametrize('until', [None, '', 'invalid', '2026-10-04T17:51:58Z', '2026-10-10T00:00:00Z'])
def test_continuous_ignores_legacy_expiry(monkeypatch, until):
    monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZATION_MODE', 'continuous')
    if until is not None:
        monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZED_UNTIL', until)
    mail.authorization()


@pytest.mark.parametrize('mode', [None, 'timed', 'continuous'])
@pytest.mark.parametrize('approved', [None, 'false', '', 'TRUE'])
def test_every_mode_requires_exact_approval(monkeypatch, mode, approved):
    if mode is not None:
        monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZATION_MODE', mode)
    if approved is None:
        monkeypatch.delenv('FOODSAVE_MAIL_APPROVED')
    else:
        monkeypatch.setenv('FOODSAVE_MAIL_APPROVED', approved)
    monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZED_UNTIL', '2026-10-06T21:30:00Z')
    with pytest.raises(mail.MailUnavailable):
        mail.authorization()


@pytest.mark.parametrize('mode', ['', 'unknown', 'Continuous', ' continuous', 'unlimited'])
def test_unknown_mode_fails_closed_even_with_valid_expiry(monkeypatch, mode):
    monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZATION_MODE', mode)
    monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZED_UNTIL', '2026-10-06T21:30:00Z')
    with pytest.raises(mail.MailUnavailable):
        mail.authorization()


@pytest.mark.parametrize('mode', [None, 'timed'])
@pytest.mark.parametrize('until,allowed', [
    (None, False), ('invalid', False), ('2026-10-06T21:30:00', False),
    ('2026-10-04T17:51:58Z', False), ('2026-10-06T20:30:00Z', False),
    ('2026-10-06T21:30:00Z', True), ('2026-10-07T20:30:00Z', True),
    ('2026-10-07T20:30:01Z', False),
])
def test_timed_and_legacy_default_keep_expiry_bounds(monkeypatch, mode, until, allowed):
    if mode is not None:
        monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZATION_MODE', mode)
    if until is not None:
        monkeypatch.setenv('FOODSAVE_MAIL_AUTHORIZED_UNTIL', until)
    if allowed:
        mail.authorization()
    else:
        with pytest.raises(mail.MailUnavailable):
            mail.authorization()
