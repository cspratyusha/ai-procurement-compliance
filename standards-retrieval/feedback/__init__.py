"""Feedback loop module for user click/acceptance logs and safe ranker retraining."""
from feedback.schema import InteractionLog, FeedbackRequest, CandidateShown
from feedback.logger import append_log, read_logs
from feedback.retrain_and_promote import promotion_decision, should_promote
from feedback.build_training_set import (
    load_logs,
    logs_to_training_data,
    compute_historical_acceptance_rate,
)

__all__ = [
    "InteractionLog",
    "FeedbackRequest",
    "CandidateShown",
    "append_log",
    "read_logs",
    "promotion_decision",
    "should_promote",
    "load_logs",
    "logs_to_training_data",
    "compute_historical_acceptance_rate",
]
