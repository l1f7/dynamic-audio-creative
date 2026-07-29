"""Base feed interface."""

from abc import ABC, abstractmethod


def apply_contains_filter(items: list, filter_key: str, filter_contains: str) -> list:
    """Keep only items whose ``filter_key`` value contains ``filter_contains``.

    Case-insensitive substring match — the text can appear anywhere in the
    value. Items missing the key are dropped. Returns the list unchanged
    when either setting is blank.
    """
    if not filter_key or not filter_contains:
        return items

    needle = str(filter_contains).strip().lower()
    return [
        item
        for item in items
        if isinstance(item, dict)
        and needle in str(item.get(filter_key) or "").lower()
    ]


class BaseFeed(ABC):
    @abstractmethod
    def fetch(self, campaign) -> dict:
        """Fetch live data, return a dict of template variables."""
        ...

    @abstractmethod
    def default_prompt_template(self) -> str:
        """Return the default prompt template for this feed type."""
        ...
