"""Feed registry — maps feed_type strings to feed classes."""

from app.pipeline.feeds.weather import WeatherFeed
from app.pipeline.feeds.concerts import ConcertsFeed

# Register known feed types here. Unknown types will use a generic
# "custom" approach (just fetches the URL and passes to Claude).
FEED_REGISTRY = {
    "weather": WeatherFeed,
    "concerts": ConcertsFeed,
}


def get_feed(feed_type: str):
    """Return a feed instance for the given type.

    Falls back to ConcertsFeed for unknown types (it handles both
    JSON and HTML scraping, which is a reasonable default).
    """
    feed_class = FEED_REGISTRY.get(feed_type, ConcertsFeed)
    return feed_class()
