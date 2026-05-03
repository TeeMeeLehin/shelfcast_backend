import os
import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class CollectorResult:
    """
    Standardised signal result.
    Maps directly onto a row in the raw_signals table.
    """
    source: str                     # e.g. 'joyonline', 'pytrends', 'x'
    signal_type: str                # 'keyword_based' | 'general_pulse'
    score: int                      # 0–100 normalised signal strength
    keyword: str | None = None      # None for general_pulse rows
    raw_content: str | None = None  # Text content (article body, tweet, etc.)
    signal_data: dict = field(default_factory=dict)  # Raw API payload
    geo: str = "Ghana"
    collected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_db_row(self) -> dict:
        """Serialise to a dict matching the raw_signals table schema."""
        return {
            "source":       self.source,
            "signal_type":  self.signal_type,
            "keyword":      self.keyword,
            "score":        self.score,
            "raw_content":  self.raw_content,
            "signal_data":  self.signal_data,
            "geo":          self.geo,
            "collected_at": self.collected_at,
            "is_processed": False,
            "entities":     [],
            "sentiment_score": 0,
            "impact_score":    0,
        }


class BaseCollector(ABC):
    """Abstract collector. All collectors must inherit from this."""

    def __init__(self):
        self.mock_mode = os.getenv("MOCK_COLLECTION", "false").lower() == "true"

    @abstractmethod
    def collect(self, **kwargs) -> list[CollectorResult]:
        """
        Run the collection and return a list of standardised results.
        Should not raise — handle all errors internally and return an empty list.
        """
        ...

    def _safe_score(self, value: float | int | None, max_val: float = 100.0) -> int:
        """Clamp and normalise any value to an int in 0–100 range."""
        if value is None:
            return 0
        try:
            return max(0, min(100, int(round(float(value) / max_val * 100))))
        except (ValueError, TypeError):
            return 0

    def _mock_signals(self, keyword: str | None = None, source: str = "general", count: int = 3) -> list[str]:
        """Generate a list of mock signals, optionally using AI."""
        use_ai = os.getenv("USE_AI_MOCKS", "false").lower() == "true"
        if use_ai:
            from ai.mock_generator import mock_ai
            signals = mock_ai.generate_signals(keyword or "Ghana retail", source, count=count)
            if signals:
                return signals

        # Fallback to templates
        results = []
        for _ in range(count):
            results.append(self._mock_text(keyword, source))
        return results

    def _mock_text(self, keyword: str | None = None, source: str = "general") -> str:
        """Generate a random piece of Ghanaian market-related text for testing."""
        # Check if we should use AI for high-fidelity mocks
        use_ai = os.getenv("USE_AI_MOCKS", "false").lower() == "true"
        if use_ai:
            from ai.mock_generator import mock_ai
            signals = mock_ai.generate_signals(keyword or "Ghana retail", source, count=1)
            if signals:
                return signals[0]

        templates = [
            "Prices for {subject} are seeing a significant hike in Kumasi markets this week.",
            "New regulations in the {subject} sector are expected to affect supply chains by Q3.",
            "Consumer demand for {subject} is at an all-time high ahead of the festival season.",
            "Local producers of {subject} are calling for more government support to combat import competition.",
            "Shocking price drop for {subject} at Melcom branches nationwide!",
            "Why {subject} is becoming the most sought-after item in Accra's retail space.",
            "Shortage of {subject} reported in major supermarkets; distributors cite transport issues.",
            "The impact of the new Cedi exchange rate on {subject} import costs."
        ]
        subject = keyword if keyword else random.choice(["FMCG goods", "beverages", "imported cereals", "local poultry"])
        return random.choice(templates).format(subject=subject)
