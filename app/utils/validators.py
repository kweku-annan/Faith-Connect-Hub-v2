import re
from pydantic import field_validator

PHONE_REGEX = re.compile(r"^\+[1-9]\d{7,14}$")


def validate_ghana_phone(phone: str | None) -> str | None:
    """Validate phone number is +233XXXXXXXXX format"""
    if phone is None:
        return None
    if not PHONE_REGEX.match(phone):
        raise ValueError(
            "Phone number must be in the format +XXXXXXXXXXXXXXX"
        )
    return phone
