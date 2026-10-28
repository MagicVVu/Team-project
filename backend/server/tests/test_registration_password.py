"""Registration-only policy boundaries; legacy login passwords remain valid input."""
import pytest
from pydantic import ValidationError
from app.schemas import LoginRequest, RegisterRequest


@pytest.mark.parametrize("password", ["Abcd1234", "abcd1234", "ABCD1234", "Abcdef1234567890"])
def test_registration_accepts_letters_and_digits(password):
    assert RegisterRequest(phone="13800138000", password=password, display_name="Test").password == password


@pytest.mark.parametrize("password", ["abc1234", "12345678", "abcdefgh", "Abcdef12345678901",
                                      "Abcd123!", "Abcd123 ", "中文abc123", "Abcd1234\n"])
def test_registration_rejects_invalid_password(password):
    with pytest.raises(ValidationError):
        RegisterRequest(phone="13800138000", password=password, display_name="Test")


def test_login_keeps_legacy_password_input():
    password = "Legacy-password-longer-than-16!"
    assert LoginRequest(phone="13800138000", password=password).password == password
