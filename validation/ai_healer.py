import json
import os

from google import genai


_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])


def _extract_json(response) -> dict:
    text = response.text.strip()

    if text.startswith("```"):
        text = text.replace("```json", "", 1)
        text = text.replace("```", "", 1).strip()

    return json.loads(text)


def suggest_ai_mappings(
    missing_fields: list[str],
    candidate_fields: list[str],
    sample_record: dict,
) -> list[dict]:
    """
    Compatibility wrapper for a single drift signature.

    One Gemini request maximum.
    Returns [] on any AI/network/quota failure.
    """
    result = suggest_ai_mappings_batch(
        [{
            "missing": missing_fields,
            "candidates": candidate_fields,
            "sample": sample_record,
        }]
    )

    if not result:
        return []

    return result[0].get("mappings", [])


def suggest_ai_mappings_batch(requests: list[dict]) -> list[dict]:
    """
    Resolve all unresolved structural mappings for an entire pipeline run
    with ONE Gemini request.

    AI failure must never fail the pipeline.
    """

    if not requests:
        return []

    prompt = {
        "task": "Resolve safe field mappings in structured football player data.",
        "rules": [
            "Only map a missing field to an unexpected field when semantic meaning is equivalent.",
            "Do not guess based only on similar spelling.",
            "Do not map fields with different meanings.",
            "Return no mapping when uncertain.",
            "Return only fields explicitly present in the candidate list.",
        ],
        "requests": requests,
        "output_format": {
            "results": [
                {
                    "request_index": 0,
                    "mappings": [
                        {
                            "missing_field": "games",
                            "unexpected_field": "gp",
                            "confidence": 0.99,
                        }
                    ],
                }
            ]
        },
    }

    try:
        response = _client.models.generate_content(
            model="gemini-3.6-flash",
            contents=json.dumps(prompt),
        )

        payload = _extract_json(response)

        results = payload.get("results", [])

        if not isinstance(results, list):
            return []

        return results

    except Exception as exc:
        print(
            "[AI_SELF_HEALING_WARNING] "
            f"AI batch mapping unavailable; deterministic path preserved: {exc}"
        )
        return []