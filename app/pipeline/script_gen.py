"""Generate ad script via Claude API."""

import logging

import anthropic
from flask import current_app

from app.pipeline.exceptions import ScriptGenerationError

logger = logging.getLogger(__name__)


def generate_script(prompt_template: str, template_vars: dict) -> str:
    """Generate a radio ad script via Claude.

    Args:
        prompt_template: A format-string prompt with {placeholder} keys.
        template_vars: Dict of values to interpolate into the template.

    Returns:
        The generated script text.

    Raises:
        ScriptGenerationError: If the Claude API call fails.
    """
    user_message = prompt_template.format(**template_vars)

    logger.info("Generating script via Claude...")
    client = anthropic.Anthropic(
        api_key=current_app.config["ANTHROPIC_API_KEY"]
    )

    try:
        response = client.messages.create(
            model=current_app.config["CLAUDE_MODEL"],
            max_tokens=300,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as exc:
        raise ScriptGenerationError(f"Claude API call failed: {exc}") from exc

    script = response.content[0].text.strip()
    logger.info("Script generated (%d chars)", len(script))
    return script
