"""Build a Claude prompt from a template and generate the ad script."""

import sys

import anthropic

from config import CLAUDE_MODEL


def generate_script(prompt_template: str, template_vars: dict) -> str:
    """Generate a radio ad script via Claude.

    Args:
        prompt_template: A format-string prompt with {placeholder} keys.
        template_vars: Dict of values to interpolate into the template.

    Returns:
        The generated script text.
    """
    user_message = prompt_template.format(**template_vars)

    print("Generating script via Claude...")
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            messages=[{"role": "user", "content": user_message}],
        )
    except anthropic.APIError as exc:
        print(f"ERROR: Claude API call failed: {exc}", file=sys.stderr)
        sys.exit(1)

    script = response.content[0].text.strip()

    print("--- SCRIPT ---")
    print(script)
    print("--------------")

    return script
