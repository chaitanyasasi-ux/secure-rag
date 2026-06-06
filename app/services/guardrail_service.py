from __future__ import annotations

import re
import structlog

log = structlog.get_logger(__name__)

# Patterns that indicate prompt injection attempts
# Each pattern is a regex that matches common attack vectors
INJECTION_PATTERNS: list[re.Pattern] = [
    # Instruction override attempts
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),
    re.compile(r"forget\s+(all\s+)?(previous|prior|above)\s+instructions?", re.IGNORECASE),

    # Role/persona hijacking
    re.compile(r"you\s+are\s+now\s+(DAN|jailbreak|unrestricted|evil)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+you\s+are\s+)?(unrestricted|jailbreak|evil|DAN)", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)\s+(unrestricted|jailbreak)", re.IGNORECASE),

    # System prompt injection
    re.compile(r"\[SYSTEM\]", re.IGNORECASE),
    re.compile(r"<\s*system\s*>", re.IGNORECASE),
    re.compile(r"system\s*:\s*override", re.IGNORECASE),

    # Data exfiltration attempts
    re.compile(r"(print|show|reveal|display|list|dump)\s+all\s+(documents?|data|files?|chunks?)", re.IGNORECASE),
    re.compile(r"(show|reveal|print)\s+(confidential|restricted|secret|private)\s+(data|documents?|information)", re.IGNORECASE),

    # Prompt leaking attempts
    re.compile(r"(show|print|reveal|repeat)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions?)", re.IGNORECASE),
    re.compile(r"what\s+(are|is)\s+your\s+(system\s+)?(prompt|instructions?)", re.IGNORECASE),

    # Security bypass attempts
    re.compile(r"(bypass|override|disable)\s+(security|restrictions?|filters?|guardrails?)", re.IGNORECASE),
    re.compile(r"no\s+restrictions?", re.IGNORECASE),
    re.compile(r"without\s+(any\s+)?(restrictions?|filters?|limits?)", re.IGNORECASE),
]

# Questions that are too short to be meaningful
MIN_QUESTION_LENGTH = 3

# Questions that are suspiciously long (possible prompt stuffing)
MAX_QUESTION_LENGTH = 1000


class GuardrailViolation(Exception):
    """Raised when a prompt injection or policy violation is detected."""
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


def check_prompt(question: str) -> None:
    """
    Check a user question for prompt injection attacks.
    Raises GuardrailViolation if an attack is detected.
    Returns None if the question is safe.

    This runs BEFORE the question reaches the vector database or LLM.
    """
    # Length checks
    if len(question.strip()) < MIN_QUESTION_LENGTH:
        raise GuardrailViolation("Question is too short.")

    if len(question) > MAX_QUESTION_LENGTH:
        raise GuardrailViolation("Question exceeds maximum allowed length.")

    # Pattern matching
    for pattern in INJECTION_PATTERNS:
        if pattern.search(question):
            log.warning(
                "guardrail.injection_detected",
                pattern=pattern.pattern,
                question_preview=question[:100],
            )
            raise GuardrailViolation(
                "Your question was flagged as a potential security violation. "
                "Please ask a genuine question about company documents."
            )

    log.info("guardrail.passed", question_preview=question[:50])