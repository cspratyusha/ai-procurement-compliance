from contracts.cluster import CertificationRequirement
from knowledge_reasoning.generation.certification_guard import (
    UngroundedCertificationClaimError,
    assert_no_fabricated_evidence,
    check_certification_text,
)
from knowledge_reasoning.generation.certification_notes import generate_certification_note


def _traceable() -> CertificationRequirement:
    return CertificationRequirement(
        scheme="ISI",
        mandatory=True,
        required_evidence=["CM/L licence number"],
        notification_reference="BIS Order 2021/XYZ",
    )


def _untraceable() -> CertificationRequirement:
    return CertificationRequirement(scheme="ISI", mandatory=True)


def test_traceable_is_derived_from_notification_reference_not_settable() -> None:
    assert _traceable().traceable is True
    assert _untraceable().traceable is False
    # Passing traceable=True explicitly has no effect — it's derived.
    sneaky = CertificationRequirement(scheme="ISI", mandatory=True, traceable=True)
    assert sneaky.traceable is False


def test_evidence_language_passes_when_traceable() -> None:
    text = "You must submit the CM/L licence number and a test report."
    result = check_certification_text(text, _traceable())
    assert result.passed is True


def test_evidence_language_fails_when_untraceable() -> None:
    text = "You must submit the CM/L licence number and a test report."
    result = check_certification_text(text, _untraceable())
    assert result.passed is False
    assert "cm/l" in result.matched_terms


def test_safe_text_passes_when_untraceable() -> None:
    text = (
        "IS 2062:2011 falls under the ISI scheme, mandatory. Specific evidence "
        "requirements are not recorded in our data and must be verified "
        "against the applicable BIS notification before citing them in a "
        "tender."
    )
    # "requirements are not" contains neither "required evidence" nor
    # "evidence required" as a phrase — the safe hedge language itself
    # must not trip the guard.
    result = check_certification_text(text, _untraceable())
    assert result.passed is True


def test_assert_raises_on_fabricated_evidence() -> None:
    text = "The required evidence is a test report and certificate number."
    import pytest

    with pytest.raises(UngroundedCertificationClaimError):
        assert_no_fabricated_evidence(text, _untraceable())


def test_generator_output_passes_its_own_guard_traceable() -> None:
    note = generate_certification_note("IS 2062:2011", _traceable())
    assert_no_fabricated_evidence(note, _traceable())  # must not raise
    assert "CM/L licence number" in note


def test_generator_output_passes_its_own_guard_untraceable() -> None:
    note = generate_certification_note("IS 2062:2011", _untraceable())
    assert_no_fabricated_evidence(note, _untraceable())  # must not raise
    assert "not recorded" in note


def test_generator_never_emits_evidence_language_when_untraceable() -> None:
    # The exact assertion integration decision 6 asked for.
    note = generate_certification_note("IS 2062:2011", _untraceable())
    result = check_certification_text(note, _untraceable())
    assert result.passed is True
    assert result.matched_terms == []


def test_unknown_scheme_note_makes_no_claims() -> None:
    unknown = CertificationRequirement(scheme="UNKNOWN", mandatory=False)
    note = generate_certification_note("IS 999:2020", unknown)
    assert "could not be determined" in note
    assert_no_fabricated_evidence(note, unknown)
