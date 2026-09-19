"""Pydantic schemas for capturing and validating user interaction and feedback logs.

Serves as the single source of truth for logged user interactions across:
- Stage D feedback capture (API endpoints)
- Synthetic interaction data generation
- Feedback-augmented training dataset construction
- LTR model retraining and evaluation
"""
from typing import List, Optional, Literal, Dict, Any
from pydantic import BaseModel, Field, model_validator


class CandidateShown(BaseModel):
    """Metadata for a candidate standard returned by /retrieve."""
    id: str = Field(..., description="Standard unique identifier (e.g. 'IS-ELEC-001').")
    final_score: float = Field(..., description="Normalized final relevance score in [0.0, 1.0].")
    rank: int = Field(..., description="1-indexed presentation rank in the retrieval result.")


class InteractionLog(BaseModel):
    """Full interaction log entry stored in the JSONL feedback database."""
    query: str = Field(..., description="Original user procurement query.")
    candidates_shown: List[Dict[str, Any]] = Field(
        ...,
        description="All candidates presented to the official, each with id, final_score, and rank."
    )
    chosen_id: Optional[str] = Field(
        default=None,
        description="ID of standard selected by official (None if official rejected all shown)."
    )
    action: Literal["accept", "reject", "correct"] = Field(
        ...,
        description="Action performed by official: 'accept' (chose candidate), 'reject' (rejected all), or 'correct' (manual override)."
    )
    corrected_id: Optional[str] = Field(
        default=None,
        description="Target standard ID manually specified by official when action='correct'."
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 formatted timestamp of the interaction."
    )
    source: Literal["synthetic", "live"] = Field(
        ...,
        description="Origin tag distinguishing synthetic training/demo data from live operational feedback."
    )

    @model_validator(mode="after")
    def validate_action_fields(self):
        """Enforces schema consistency between action and selection fields."""
        if self.action == "correct":
            if not self.corrected_id or not str(self.corrected_id).strip():
                raise ValueError("corrected_id is required and cannot be empty when action='correct'.")
        elif self.action == "accept":
            if not self.chosen_id or not str(self.chosen_id).strip():
                raise ValueError("chosen_id is required and cannot be empty when action='accept'.")
        elif self.action == "reject":
            # For rejection, chosen_id is typically None
            pass
        return self


class FeedbackRequest(BaseModel):
    """Incoming request payload for POST /feedback (timestamp and source managed by server)."""
    query: str = Field(..., description="Original user procurement query.")
    candidates_shown: List[Dict[str, Any]] = Field(
        ...,
        description="List of candidates shown, each with id, final_score, and rank."
    )
    chosen_id: Optional[str] = Field(
        default=None,
        description="ID of standard accepted by official (None if rejected)."
    )
    action: Literal["accept", "reject", "correct"] = Field(
        ...,
        description="Official's decision: 'accept', 'reject', or 'correct'."
    )
    corrected_id: Optional[str] = Field(
        default=None,
        description="Manually specified standard ID required if action='correct'."
    )

    @model_validator(mode="after")
    def validate_action_fields(self):
        """Enforces schema consistency on the incoming API payload."""
        if self.action == "correct":
            if not self.corrected_id or not str(self.corrected_id).strip():
                raise ValueError("corrected_id is required and cannot be empty when action='correct'.")
        elif self.action == "accept":
            if not self.chosen_id or not str(self.chosen_id).strip():
                raise ValueError("chosen_id is required and cannot be empty when action='accept'.")
        return self
