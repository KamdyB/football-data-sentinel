import os
import json

from google import genai

_client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY", ""))

MODEL_NAME = "gemini-3.6-flash"


def suggest_ai_mapping(missing_field: str, candidate_fields: list[str], sample_record: dict) -> dict | None:
    """Ask an LLM whether any candidate field is the same underlying stat as
    missing_field under a different name. candidate_fields must already have
    blocked pairs removed by the caller, this function never sees them."""
    if not candidate_fields:
        return None

    prompt = (
        "A football player stats record is missing a required field and has "
        "some unexpected fields instead. Decide whether any unexpected field "
        f"is genuinely the same underlying statistic as {missing_field!r}, "
        "just recorded under a different name (e.g. 'appearances' vs "
        "'games'). Only say yes if they measure the same quantity, not a "
        "related or derived one.\n\n"
        f"Missing field: {missing_field}\n"
        f"Unexpected fields: {candidate_fields}\n"
        f"Sample record: {json.dumps(sample_record)}\n\n"
        'Reply with strict JSON only: {"unexpected_field": "<name or null>", "confident": true or false}'
        )

    try:
        response = _client.models.generate_content(model=MODEL_NAME, contents=prompt)
        text = response.text.strip().strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
        result = json.loads(text)
    except Exception as error:
        import sys
        print(f"[ai_healer] skipped, {type(error).__name__}: {error}", file=sys.stderr)
        return None

    if not result.get("confident") or not result.get("unexpected_field"):
        return None

    if result["unexpected_field"] not in candidate_fields:
        return None

    return {
        "unexpected_field": result["unexpected_field"],
        "missing_field": missing_field,
        "confidence": 0.85,
        "method": "ai_suggested",
        }
