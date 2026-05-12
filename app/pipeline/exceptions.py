"""Pipeline exceptions — raised instead of sys.exit so the runner can handle them."""


class PipelineError(Exception):
    """Base class for pipeline errors."""
    pass


class FeedFetchError(PipelineError):
    """Failed to fetch data from the feed source."""
    pass


class FeedParseError(PipelineError):
    """Failed to parse feed data."""
    pass


class ScriptGenerationError(PipelineError):
    """Claude API call failed."""
    pass


class VoiceoverGenerationError(PipelineError):
    """ElevenLabs TTS call failed."""
    pass


class MixingError(PipelineError):
    """FFmpeg mixing failed."""
    pass
