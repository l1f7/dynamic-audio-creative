"""Base feed interface."""

from abc import ABC, abstractmethod


class BaseFeed(ABC):
    @abstractmethod
    def fetch(self, campaign) -> dict:
        """Fetch live data, return a dict of template variables."""
        ...

    @abstractmethod
    def default_prompt_template(self) -> str:
        """Return the default prompt template for this feed type."""
        ...
