from app.pii import scrub_text


def test_scrub_email() -> None:
    email_addresses = ("student@vinuni.edu.vn", "first.last+lab@example.com")

    for email_address in email_addresses:
        out = scrub_text(f"Email me at {email_address}")
        assert email_address not in out
        assert "REDACTED_EMAIL" in out


def test_scrub_common_vietnamese_phone_formats() -> None:
    phone_numbers = (
        "0901234567",
        "090 123 4567",
        "090.123.4567",
        "090-123-4567",
        "+84 90 123 4567",
        "+84901234567",
        "84901234567",
    )

    for phone_number in phone_numbers:
        out = scrub_text(f"Contact: {phone_number}")
        assert phone_number not in out
        assert "REDACTED_PHONE_VN" in out


def test_scrub_cccd() -> None:
    identifiers = ("001203012345", "001 203 012 345", "001-203-012-345")

    for identifier in identifiers:
        out = scrub_text(f"CCCD: {identifier}")
        assert identifier not in out
        assert "REDACTED_CCCD" in out


def test_scrub_credit_card() -> None:
    card_numbers = (
        "4111111111111111",
        "4111 1111 1111 1111",
        "4111-1111-1111-1111",
    )

    for card_number in card_numbers:
        out = scrub_text(f"Card: {card_number}")
        assert card_number not in out
        assert "REDACTED_CREDIT_CARD" in out
