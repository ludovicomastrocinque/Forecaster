"""Anthropic Claude API wrapper with retry logic."""

import os
import json
import re
import time
import streamlit as st
import anthropic


def _get_api_key():
    """Retrieve API key from Streamlit secrets or environment."""
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except (KeyError, FileNotFoundError):
        key = os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise ValueError(
                "ANTHROPIC_API_KEY not found. Set it in .streamlit/secrets.toml "
                "or as an environment variable."
            )
        return key


def _get_client():
    return anthropic.Anthropic(api_key=_get_api_key())


def call_claude(system_prompt, user_message, max_tokens=4096, model="claude-sonnet-4-20250514"):
    """Call Claude and return the text response."""
    client = _get_client()
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
            else:
                raise
        except anthropic.APIError as e:
            raise RuntimeError(f"Claude API error: {e}")


def call_claude_conversation(system_prompt, messages, max_tokens=4096, model="claude-sonnet-4-20250514"):
    """Call Claude with a full conversation history."""
    client = _get_client()
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=messages,
            )
            return response.content[0].text
        except anthropic.RateLimitError:
            if attempt < 2:
                time.sleep(2 ** (attempt + 1))
            else:
                raise
        except anthropic.APIError as e:
            raise RuntimeError(f"Claude API error: {e}")


def parse_json_response(text):
    """Extract and parse JSON from Claude's response, stripping markdown fences."""
    # Strip markdown code fences if present
    cleaned = re.sub(r"^```(?:json)?\s*\n?", "", text.strip())
    cleaned = re.sub(r"\n?```\s*$", "", cleaned)
    return json.loads(cleaned)
