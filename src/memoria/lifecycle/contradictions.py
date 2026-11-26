"""Heuristic contradiction signals between two similar statements.

Embedding similarity cannot tell a paraphrase from a contradiction ("port 8000" vs
"port 9000" scores 0.89 with bge-small), so candidates above the similarity threshold
are checked for lexical signs of disagreement. These are *potential* conflicts for the
agent to resolve; nothing is changed automatically.
"""

import re
from enum import Enum
from typing import Protocol


class ConflictReason(str, Enum):
    NEGATION = "negation"
    DIFFERENT_NUMBERS = "different_numbers"
    ANTONYM = "antonym"
    DIFFERENT_TERMS = "different_terms"


NEGATIONS = frozenset(
    {"not", "no", "never", "cannot", "without", "none", "nothing", "neither", "nor", "nobody"}
)
ANTONYM_PAIRS = (
    ("enabled", "disabled"),
    ("enable", "disable"),
    ("true", "false"),
    ("allowed", "forbidden"),
    ("allow", "deny"),
    ("synchronous", "asynchronous"),
    ("synchronously", "asynchronously"),
    ("sync", "async"),
    ("required", "optional"),
    ("public", "private"),
    ("pass", "fail"),
    ("passes", "fails"),
    ("passed", "failed"),
    ("passing", "failing"),
    ("success", "failure"),
    ("succeeds", "fails"),
    ("valid", "invalid"),
    ("always", "never"),
    ("supported", "unsupported"),
    ("increase", "decrease"),
    ("before", "after"),
)
STOPWORDS = frozenset(
    "a an the is are was were be been being of in on at to for from by with and or as "
    "it its this that these those we our you your they their i he she uses use used using "
    "has have had do does did can will would should may might must there here".split()
)
_TOKEN = re.compile(r"[a-z0-9]+(?:['.][a-z0-9]+)*")
_NUMBER = re.compile(r"\d+(?:\.\d+)*")
# A term swap ("uses PostgreSQL" vs "uses MySQL") is a few differing content words on
# each side against a shared core. Larger differences are rewordings, not swaps.
SWAP_MAX_TERMS = 2
SWAP_MIN_OVERLAP = 1 / 3


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def _stem(token: str) -> str:
    return token[:-1] if len(token) > 3 and token.endswith("s") and not token.endswith("ss") else token


def _negated(tokens: set[str]) -> bool:
    count = sum(1 for t in tokens if t in NEGATIONS or t.endswith("n't"))
    return count % 2 == 1


class ContradictionDetector(Protocol):
    def reasons(self, a: str, b: str, check_terms: bool) -> list[ConflictReason]: ...


class HeuristicContradictionDetector:
    def reasons(self, a: str, b: str, check_terms: bool = True) -> list[ConflictReason]:
        """Signs that `a` and `b` disagree. `check_terms` enables the term-swap check,
        which also fires on loose paraphrases, so callers skip it for near-duplicates."""
        ta, tb = _tokens(a), _tokens(b)
        found: list[ConflictReason] = []
        if _negated(ta) != _negated(tb):
            found.append(ConflictReason.NEGATION)

        na = {t for t in ta if _NUMBER.fullmatch(t)}
        nb = {t for t in tb if _NUMBER.fullmatch(t)}
        if na and nb and na != nb:
            found.append(ConflictReason.DIFFERENT_NUMBERS)

        for x, y in ANTONYM_PAIRS:
            if (x in ta and y in tb and x not in tb) or (y in ta and x in tb and y not in tb):
                found.append(ConflictReason.ANTONYM)
                break

        if check_terms and not found:
            ignore = STOPWORDS | NEGATIONS
            ca = {_stem(t) for t in ta - ignore if not _NUMBER.fullmatch(t)}
            cb = {_stem(t) for t in tb - ignore if not _NUMBER.fullmatch(t)}
            only_a, only_b, union = ca - cb, cb - ca, ca | cb
            if (
                0 < len(only_a) <= SWAP_MAX_TERMS
                and 0 < len(only_b) <= SWAP_MAX_TERMS
                and len(ca & cb) / len(union) >= SWAP_MIN_OVERLAP
            ):
                found.append(ConflictReason.DIFFERENT_TERMS)
        return found
