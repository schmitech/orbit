"""
Shared validation for System One decision-model questions.

Used by both DecisionModelStep (decision_model.py) and ModelSelectionStep
(model_selection.py) so both build/validate question definitions identically.
"""

from typing import Any, Optional

QUESTION_TYPES = ("choice", "noul", "score")


def validate_questions(questions: Any) -> Optional[str]:
    """Return an error message if the question definitions are invalid, else None."""
    if not isinstance(questions, dict) or not questions:
        return "Decision questions must be a non-empty mapping of question name to definition."
    for name, spec in questions.items():
        if not isinstance(name, str) or not name.strip():
            return "Decision question names must be non-empty strings."
        if not isinstance(spec, dict):
            return f"Decision question '{name}' must be an object."
        qtype = spec.get("type")
        if qtype not in QUESTION_TYPES:
            return f"Decision question '{name}' has invalid type {qtype!r}; expected one of {', '.join(QUESTION_TYPES)}."
        instructions = spec.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            return f"Decision question '{name}' requires non-empty 'instructions'."
        criteria = spec.get("criteria")
        if qtype == "choice" and (not isinstance(criteria, dict) or not criteria):
            return f"Choice question '{name}' requires a non-empty 'criteria' mapping of option to description."
        if qtype == "score" and (not isinstance(criteria, list) or len(criteria) < 2):
            return f"Score question '{name}' requires a 'criteria' list of at least 2 ordered levels."
    return None
