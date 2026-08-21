from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class FileDataSource:

    name = "local_file"

    def __init__(
        self,
        path: str = "data/raw/latest.json",
    ) -> None:

        self.path = Path(path)

    def collect(self) -> dict[str, Any]:

        if not self.path.exists():
            raise FileNotFoundError(
                f"Raw data not found: {self.path}"
            )

        with self.path.open(
            "r",
            encoding="utf-8",
        ) as file:

            payload = json.load(file)

        if not isinstance(
            payload,
            dict,
        ):
            raise ValueError(
                "Raw source must be a JSON object"
            )

        return payload