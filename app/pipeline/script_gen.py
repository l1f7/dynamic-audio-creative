"""Generate ad script via Claude API."""

import logging
import re

import anthropic
from flask import current_app

from app.pipeline.exceptions import ScriptGenerationError

logger = logging.getLogger(__name__)

SYSTEM_MESSAGE = (
    "You are a radio ad script writer. Output ONLY the script text that "
    "will be read aloud — nothing else. Never include introductions, "
    "commentary, questions, sign-offs, or offers to revise. Never use "
    "markdown, bullet points, headers, bold, italics, horizontal rules, "
    "or any special characters. Just plain spoken-word text."
)


def generate_script(prompt_template: str, template_vars: dict) -> str:
    """Generate a radio ad script via Claude.

    Args:
        prompt_template: A format-string prompt with {placeholder} keys.
        template_vars: Dict of values to interpolate into the template.

    Returns:
        The generated script text, cleaned of any markdown or preamble.

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
            system=SYSTEM_MESSAGE,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as exc:
        raise ScriptGenerationError(f"Claude API call failed: {exc}") from exc

    script = response.content[0].text.strip()
    script = _clean_script(script)
    logger.info("Script generated (%d chars)", len(script))
    return script


def _clean_script(text: str) -> str:
    """Strip markdown artefacts and conversational wrapping from the script.

    Even with strong prompting, models occasionally add markdown formatting
    or preamble like "Here is the script:" — this function removes it so the
    text-to-speech engine receives clean spoken-word text.
    """
    # Strip markdown code fences
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    # Strip markdown bold / italic markers
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}(.+?)_{1,3}", r"\1", text)

    # Strip markdown headers (# Header)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)

    # Strip horizontal rules (---, ***, ___)
    text = re.sub(r"^[\s]*[-*_]{3,}[\s]*$", "", text, flags=re.MULTILINE)

    # Strip bullet point markers (- item, * item)
    text = re.sub(r"^[\s]*[-*]\s+", "", text, flags=re.MULTILINE)

    # Strip numbered list markers (1. item)
    text = re.sub(r"^[\s]*\d+\.\s+", "", text, flags=re.MULTILINE)

    # Remove common preamble / postamble lines
    preamble_patterns = [
        r"^Here(?:'s| is) (?:the|your|a) .*?(?:script|update|ad|read).*?:\s*",
        r"^Sure[!,.].*?:\s*",
        r"^(?:Would|Do|Let|Shall|I) (?:you|me).*\?\s*$",
        r"^---+\s*$",
    ]
    for pattern in preamble_patterns:
        text = re.sub(pattern, "", text, flags=re.MULTILINE | re.IGNORECASE)

    # Collapse multiple blank lines into one
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
