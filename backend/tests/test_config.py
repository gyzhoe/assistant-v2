"""Tests for Settings validators in app.config."""

import warnings

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_cors_wildcard_with_api_token_raises() -> None:
    """CORS_ORIGIN=* combined with a non-empty API_TOKEN must raise ValueError."""
    with pytest.raises(ValidationError) as exc_info:
        Settings(cors_origin="*", api_token="secret-token")
    assert "CORS_ORIGIN='*' is not allowed when API_TOKEN is set" in str(exc_info.value)


def test_cors_wildcard_without_api_token_warns() -> None:
    """CORS_ORIGIN=* with no API_TOKEN (dev mode) should issue a UserWarning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Settings(cors_origin="*", api_token="")
    assert any(
        "CORS_ORIGIN='*' is set with no API_TOKEN" in str(w.message) for w in caught
    ), "Expected a warning about wildcard CORS in dev mode"


def test_specific_cors_origin_with_api_token_ok() -> None:
    """A specific extension origin with API_TOKEN must not raise or warn."""
    origin = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        s = Settings(cors_origin=origin, api_token="secret-token")
    assert s.cors_origin == origin
    wildcard_warnings = [w for w in caught if "CORS_ORIGIN" in str(w.message)]
    assert wildcard_warnings == [], "No CORS warning expected for a specific origin"


def test_specific_cors_origin_without_api_token_ok() -> None:
    """A specific extension origin with no API_TOKEN must not raise or warn."""
    origin = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        s = Settings(cors_origin=origin, api_token="")
    assert s.cors_origin == origin
    wildcard_warnings = [w for w in caught if "CORS_ORIGIN" in str(w.message)]
    assert wildcard_warnings == [], "No CORS warning expected for a specific origin"


def test_session_cookie_secure_defaults_false() -> None:
    """session_cookie_secure should default to False (localhost HTTP)."""
    s = Settings()
    assert s.session_cookie_secure is False


def test_session_cookie_secure_can_be_enabled() -> None:
    """session_cookie_secure=True should be accepted."""
    s = Settings(session_cookie_secure=True)
    assert s.session_cookie_secure is True
