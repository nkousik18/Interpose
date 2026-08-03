"""Unit tests for interpose.policies.redaction -- pure regex substitution, no policy
engine or gateway involved.
"""

from interpose.policies.redaction import REDACTED_PLACEHOLDER, redact_json_value, redact_text


class TestRedactText:
    def test_redacts_an_ssn(self) -> None:
        assert redact_text("SSN: 123-45-6789 on file", ["ssn"]) == (
            f"SSN: {REDACTED_PLACEHOLDER} on file"
        )

    def test_redacts_a_credit_card_number(self) -> None:
        assert redact_text("card 4111111111111111 charged", ["credit_card"]) == (
            f"card {REDACTED_PLACEHOLDER} charged"
        )

    def test_redacts_a_bank_routing_and_account_combination(self) -> None:
        assert redact_text("routing+account 021000021123456789", ["bank_account"]) == (
            f"routing+account {REDACTED_PLACEHOLDER}"
        )

    def test_leaves_text_unchanged_when_no_pattern_matches(self) -> None:
        assert redact_text("Suspect Corp, entity E001", ["ssn"]) == "Suspect Corp, entity E001"

    def test_unknown_pattern_name_is_a_no_op_not_a_crash(self) -> None:
        assert redact_text("123-45-6789", ["not_a_real_pattern"]) == "123-45-6789"

    def test_applies_multiple_patterns(self) -> None:
        text = "ssn 123-45-6789 card 4111111111111111"
        redacted = redact_text(text, ["ssn", "credit_card"])
        assert "123-45-6789" not in redacted
        assert "4111111111111111" not in redacted


class TestRedactJsonValue:
    def test_redacts_a_string_leaf(self) -> None:
        assert redact_json_value("123-45-6789", ["ssn"]) == REDACTED_PLACEHOLDER

    def test_redacts_within_a_nested_dict(self) -> None:
        value = {"note": "ssn 123-45-6789 on file", "count": 3}
        redacted = redact_json_value(value, ["ssn"])
        assert redacted == {"note": f"ssn {REDACTED_PLACEHOLDER} on file", "count": 3}

    def test_redacts_within_a_list_of_dicts(self) -> None:
        value = [{"text": "123-45-6789"}, {"text": "no pii here"}]
        redacted = redact_json_value(value, ["ssn"])
        assert redacted == [{"text": REDACTED_PLACEHOLDER}, {"text": "no pii here"}]

    def test_non_string_leaves_pass_through_unchanged(self) -> None:
        value = {"flagged": True, "count": 3, "amount": 27000.0, "note": None}
        assert redact_json_value(value, ["ssn"]) == value
