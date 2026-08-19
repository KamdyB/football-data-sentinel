import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


API_TOKEN = os.environ.get("BRIGHTDATA_API_TOKEN")
COLLECTOR_ID = "c_msx0vnthdbenf0tf7"
TARGET_URL = (
    "https://fbref.com/en/comps/9/2025-2026/stats/"
    "2025-2026-Premier-League-Stats"
)

BASE_URL = "https://api.brightdata.com"
POLL_INTERVAL = 30
MAX_ATTEMPTS = 60


def trigger_collection() -> str:
    if not API_TOKEN:
        raise RuntimeError("BRIGHTDATA_API_TOKEN is not set")

    url = (
        f"{BASE_URL}/dca/trigger"
        f"?collector={COLLECTOR_ID}&queue_next=1"
    )

    body = json.dumps([{"url": TARGET_URL}]).encode("utf-8")

    request = Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {API_TOKEN}",
            "Content-Type": "application/json",
        },
        data=body,
    )

    with urlopen(request) as response:
        result = json.loads(response.read())

    return result["collection_id"]


def retrieve_collection(collection_id: str) -> dict:
    url = f"{BASE_URL}/dca/dataset?id={collection_id}"

    for _ in range(MAX_ATTEMPTS):
        request = Request(
            url,
            headers={"Authorization": f"Bearer {API_TOKEN}"},
        )

        try:
            with urlopen(request) as response:
                data = json.loads(response.read())

            if data.get("status") in {"collecting", "building"}:
                time.sleep(POLL_INTERVAL)
                continue

            return data

        except HTTPError as error:
            if error.code != 202:
                raise
            time.sleep(POLL_INTERVAL)

    raise TimeoutError("Bright Data collection did not finish")


def save_raw(data: dict) -> Path:
    path = Path("data/raw/latest.json")
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)

    return path


def refresh() -> Path:
    collection_id = trigger_collection()
    data = retrieve_collection(collection_id)
    return save_raw(data)


if __name__ == "__main__":
    path = refresh()
    print(f"Fresh Bright Data result saved to {path}")