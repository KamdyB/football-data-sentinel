from __future__ import annotations

import json
import os
import time

from pathlib import Path
from urllib.error import (
    HTTPError,
)
from urllib.request import (
    Request,
    urlopen,
)


API_TOKEN_ENV = (
    "BRIGHTDATA_API_TOKEN"
)

COLLECTOR_ENV = (
    "BRIGHTDATA_COLLECTOR_ID"
)

TARGET_ENV = (
    "BRIGHTDATA_TARGET_URL"
)

BASE_URL = os.getenv(
    "BRIGHTDATA_API_BASE_URL",
    "https://api.brightdata.com",
)

POLL_INTERVAL = int(
    os.getenv(
        "BRIGHTDATA_POLL_INTERVAL",
        "10",
    )
)

MAX_ATTEMPTS = int(
    os.getenv(
        "BRIGHTDATA_MAX_ATTEMPTS",
        "60",
    )
)

RAW_PATH = Path(
    os.getenv(
        "SENTINEL_RAW_PATH",
        "data/raw/latest.json",
    )
)


def _required(
    name: str,
) -> str:

    value = os.getenv(
        name
    )

    if not value:
        raise RuntimeError(
            f"{name} is not set"
        )

    return value


def trigger_collection() -> str:

    token = _required(
        API_TOKEN_ENV
    )

    collector_id = _required(
        COLLECTOR_ENV
    )

    target_url = _required(
        TARGET_ENV
    )

    request = Request(
        (
            f"{BASE_URL}"
            f"/dca/trigger"
            f"?collector={collector_id}"
            f"&queue_next=1"
        ),
        method="POST",
        headers={
            "Authorization":
                f"Bearer {token}",
            "Content-Type":
                "application/json",
        },
        data=json.dumps(
            [{"url": target_url}]
        ).encode(
            "utf-8"
        ),
    )

    with urlopen(
        request,
        timeout=60,
    ) as response:

        result = json.loads(
            response.read()
        )

    return result[
        "collection_id"
    ]


def retrieve_collection(
    collection_id: str,
) -> dict:

    token = _required(
        API_TOKEN_ENV
    )

    request = Request(
        (
            f"{BASE_URL}"
            f"/dca/dataset"
            f"?id={collection_id}"
        ),
        headers={
            "Authorization":
                f"Bearer {token}"
        },
    )

    for _ in range(
        MAX_ATTEMPTS
    ):

        try:

            with urlopen(
                request,
                timeout=60,
            ) as response:

                data = json.loads(
                    response.read()
                )

            if data.get(
                "status"
            ) in {
                "collecting",
                "building",
            }:

                time.sleep(
                    POLL_INTERVAL
                )

                continue

            return data

        except HTTPError as error:

            if error.code != 202:
                raise

            time.sleep(
                POLL_INTERVAL
            )

    raise TimeoutError(
        "Bright Data collection "
        "did not finish"
    )


def save_raw(
    data: dict,
) -> Path:

    RAW_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = (
        RAW_PATH.with_suffix(
            ".tmp"
        )
    )

    with temporary.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )

        file.flush()
        os.fsync(
            file.fileno()
        )

    temporary.replace(
        RAW_PATH
    )

    return RAW_PATH


def refresh() -> Path:

    collection_id = (
        trigger_collection()
    )

    data = (
        retrieve_collection(
            collection_id
        )
    )

    return save_raw(
        data
    )


if __name__ == "__main__":

    print(
        "Fresh Bright Data result "
        f"saved to {refresh()}"
    )