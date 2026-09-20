"""Deterministic, template-based certification notes.

Not the LLM-backed Part 5 generator the brief describes — that (prompt
templates, an LLM client, the general IS-number hallucination guard) was
never built in this engagement. This is a narrow, template-only stand-in
scoped to exactly what's needed to exercise
`certification_guard.assert_no_fabricated_evidence` against real output —
useful on its own (deterministic text has no hallucination risk to guard
against by construction), and a template an eventual LLM-backed generator
must produce equivalent output to, not something it replaces.
"""

from __future__ import annotations

from contracts.cluster import CertificationRequirement


def generate_certification_note(is_number: str, certification: CertificationRequirement) -> str:
    if certification.scheme == "UNKNOWN":
        return (
            f"{is_number}: certification requirement could not be determined "
            f"from available data."
        )
    if certification.scheme == "NONE":
        return f"{is_number} does not attract a mandatory certification scheme."

    mandatory_clause = "mandatory" if certification.mandatory else "not mandatory"
    lines = [f"{is_number} falls under the {certification.scheme} scheme, {mandatory_clause}."]

    if certification.traceable:
        if certification.required_evidence:
            lines.append("Evidence required: " + "; ".join(certification.required_evidence) + ".")
        if certification.notification_reference:
            lines.append(f"Per notification {certification.notification_reference}.")
    else:
        lines.append(
            "Specific evidence requirements are not recorded in our data and "
            "must be verified against the applicable BIS notification before "
            "citing them in a tender."
        )

    return " ".join(lines)
