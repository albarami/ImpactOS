"""Canonical text tokenization and matching utilities — MVP-12.

Used by mapping library fuzzy matching. Deterministic, no LLM.

Amendment 8: Scoring guardrails:
- Filter tokens < 3 chars
- Consulting stopwords filtered
- Arabic normalization hooks (tatweel, alef, ya, diacritics)
- Minimum 2 distinct meaningful tokens for a match
"""

import re
import unicodedata

# --- Stop words (general + consulting boilerplate) ---

_GENERAL_STOP_WORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "for", "in", "to", "on",
    "with", "at", "by", "from", "is", "are", "was", "were",
})

_CONSULTING_STOP_WORDS = frozenset({
    "supply", "services", "general", "works", "other", "total",
    "various", "miscellaneous", "items", "cost", "price",
})

_ALL_STOP_WORDS = _GENERAL_STOP_WORDS | _CONSULTING_STOP_WORDS

# Minimum token length to include
_MIN_TOKEN_LENGTH = 3

# Minimum distinct tokens for a valid match
MIN_MATCH_TOKENS = 2

# --- Arabic normalization (Amendment 8) ---

# Tatweel (kashida)
_TATWEEL = "\u0640"

# Alef variants → plain alef
_ALEF_VARIANTS = re.compile("[\u0623\u0625\u0622]")  # أ إ آ

# Ya variant ى → ي
_YA_VARIANT = "\u0649"
_YA_NORMAL = "\u064a"

# Arabic diacritics range
_DIACRITICS = re.compile(
    "[\u064b-\u065f\u0670]"
)


def normalize_arabic(text: str) -> str:
    """Deterministic Arabic string normalization.

    - Strip tatweel (ـ)
    - Normalize alef variants (أ إ آ → ا)
    - Normalize ya (ى → ي)
    - Remove diacritics
    """
    text = text.replace(_TATWEEL, "")
    text = _ALEF_VARIANTS.sub("\u0627", text)  # → ا
    text = text.replace(_YA_VARIANT, _YA_NORMAL)
    text = _DIACRITICS.sub("", text)
    return text


def tokenize(text: str) -> set[str]:
    """Tokenize text into meaningful words for fuzzy matching.

    Returns lowercase alphanumeric tokens with:
    - Minimum 3 characters (Amendment 8)
    - Stop words removed (general + consulting boilerplate)
    - Arabic normalization applied
    """
    # Apply Arabic normalization first
    text = normalize_arabic(text)

    words: set[str] = set()
    for w in text.lower().split():
        # Strip non-alphanumeric (keep Unicode letters)
        cleaned = "".join(
            c for c in w
            if c.isalnum() or unicodedata.category(c).startswith("L")
        )
        if (
            cleaned
            and len(cleaned) >= _MIN_TOKEN_LENGTH
            and cleaned not in _ALL_STOP_WORDS
        ):
            words.add(cleaned)
    return words


def overlap_score(
    query_tokens: set[str],
    pattern_tokens: set[str],
) -> float:
    """Compute pattern recall score (fraction of pattern tokens matched).

    Returns 0.0 if either set has fewer than MIN_MATCH_TOKENS distinct
    meaningful tokens (Amendment 8).
    """
    if (
        len(query_tokens) < MIN_MATCH_TOKENS
        or len(pattern_tokens) < MIN_MATCH_TOKENS
    ):
        return 0.0

    matched = query_tokens & pattern_tokens
    return len(matched) / len(pattern_tokens)
