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

from __future__ import annotations

import json
import os
from typing import Any


MODEL_NAME = os.getenv(
    "SENTINEL_AI_MODEL",
    "gemini-3.6-flash",
)


class GeminiRecoveryAdvisor:

    def __init__(
        self,
        api_key: str | None = None,
        model: str = MODEL_NAME,
    ) -> None:

        key = (
            api_key
            or os.getenv(
                "GEMINI_API_KEY"
            )
        )

        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set"
            )

        from google import genai

        self._client = genai.Client(
            api_key=key
        )

        self._model = model

    def suggest_batch(
        self,
        requests: list[
            dict[str, Any]
        ],
    ) -> list[
        list[dict[str, Any]]
    ]:

        if not requests:
            return []

        prompt = (
            "You are a conservative "
            "schema-recovery advisor for "
            "football data. "
            "For each request, return only "
            "field mappings that measure "
            "the exact same statistic under "
            "a different name. "
            "Never map derived metrics to "
            "counting metrics. "
            "Return strict JSON: "
            "{\"results\":["
            "{\"mappings\":["
            "{\"missing_field\":\"...\","
            "\"unexpected_field\":\"...\","
            "\"confident\":true}"
            "]}]}.\n\n"
            f"Requests:\n"
            f"{json.dumps(requests, ensure_ascii=False)}"
        )

        response = (
            self._client
            .models
            .generate_content(
                model=self._model,
                contents=prompt,
            )
        )

        try:

            text = (
                response.text
                .strip()
                .strip("`")
            )

            if text.startswith("json"):
                text = text[4:].strip()

            parsed = json.loads(text)

        except (
            json.JSONDecodeError,
            AttributeError,
            TypeError,
        ):
            return [
                []
                for _ in requests
            ]

        results = (
            parsed.get(
                "results",
                [],
            )
            if isinstance(
                parsed,
                dict,
            )
            else []
        )

        output = []

        for index, request in enumerate(
            requests
        ):

            accepted = []

            raw_items = (
                results[index].get(
                    "mappings",
                    [],
                )
                if index < len(results)
                else []
            )

            for item in raw_items:

                if not item.get(
                    "confident"
                ):
                    continue

                missing = item.get(
                    "missing_field"
                )

                unexpected = item.get(
                    "unexpected_field"
                )

                if (
                    missing
                    not in request["missing"]
                ):
                    continue

                if (
                    unexpected
                    not in request["candidates"]
                ):
                    continue

                accepted.append({
                    "missing_field": missing,
                    "unexpected_field": unexpected,
                    "confidence": 0.85,
                    "method": "ai_suggested",
                })

            output.append(
                accepted
            )

        return output