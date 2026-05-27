"""Feed registry — maps feed_type strings to feed classes."""

from app.pipeline.feeds.concerts import ConcertsFeed
from app.pipeline.feeds.generic import GenericFeed
from app.pipeline.feeds.weather import WeatherFeed
from app.pipeline.feeds.world_cup import WorldCupFeed

# Register known feed types here. Unknown types fall back to
# GenericFeed, which uses Claude to extract structured data from
# any URL — JSON, HTML, or XML.
FEED_REGISTRY = {
    "weather": WeatherFeed,
    "concerts": ConcertsFeed,
    "world_cup": WorldCupFeed,
}


def get_feed(feed_type: str):
    """Return a feed instance for the given type.

    Falls back to GenericFeed for unknown types — it uses Claude to
    intelligently extract data from any feed format and includes
    sport-specific tone guidance when applicable.
    """
    feed_class = FEED_REGISTRY.get(feed_type, GenericFeed)
    return feed_class()
