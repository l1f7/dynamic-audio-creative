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
    "or any special characters. Just plain spoken-word text. "
    "CRITICAL: respect the word limit given in the prompt — going over it "
    "will cause the ad to be cut off on air."
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

    target_words = int(template_vars.get("target_words", 75))
    # Allow 1.5× headroom in tokens so Claude isn't cut mid-sentence by the
    # API limit, then we hard-truncate below.
    max_tokens = max(100, int(target_words * 2))

    logger.info("Generating script via Claude (target_words=%d, max_tokens=%d)...",
                target_words, max_tokens)
    client = anthropic.Anthropic(
        api_key=current_app.config["ANTHROPIC_API_KEY"]
    )

    try:
        response = client.messages.create(
            model=current_app.config["CLAUDE_MODEL"],
            max_tokens=max_tokens,
            system=SYSTEM_MESSAGE,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as exc:
        raise ScriptGenerationError(f"Claude API call failed: {exc}") from exc

    script = response.content[0].text.strip()
    script = _clean_script(script)
    ad_tag = template_vars.get("ad_tag", "").strip()
    script = _truncate_to_word_limit(script, target_words, ad_tag)
    logger.info("Script generated (%d words, %d chars)",
                len(script.split()), len(script))
    return script


def _truncate_to_word_limit(text: str, max_words: int, protected_tag: str = "") -> str:
    """Hard-truncate script to max_words, always preserving the ad tag at the end.

    If the script doesn't already end with the tag, the body is truncated to
    make room and the tag is appended. This guarantees the tag is never cut.
    """
    tag_words = len(protected_tag.split()) if protected_tag else 0
    body_limit = max_words - tag_words

    # Strip the tag from the end of the script if Claude already included it,
    # so we can truncate the body independently.
    if protected_tag and text.endswith(protected_tag):
        body = text[: -len(protected_tag)].strip()
    else:
        body = text

    body_word_list = body.split()
    if len(body_word_list) > body_limit:
        truncated_body = " ".join(body_word_list[:body_limit])
        for punct in (".", "!", "?"):
            pos = truncated_body.rfind(punct)
            if pos != -1:
                truncated_body = truncated_body[: pos + 1]
                break
        logger.warning(
            "Script body truncated from %d to %d words to enforce word limit.",
            len(body_word_list),
            len(truncated_body.split()),
        )
        body = truncated_body

    if protected_tag:
        return f"{body.strip()} {protected_tag}".strip()
    return body.strip()


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
