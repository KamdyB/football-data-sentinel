from __future__ import annotations

import os
from typing import Any

from sources.file import FileDataSource


class BrightDataSource:

    name = "brightdata"

    def __init__(
        self,
        raw_path: str | None = None,
        refresh: bool | None = None,
    ) -> None:

        self.raw_path = (
            raw_path
            or os.getenv(
                "SENTINEL_RAW_PATH",
                "data/raw/latest.json",
            )
        )

        self.refresh_enabled = (
            refresh
            if refresh is not None
            else os.getenv(
                "SENTINEL_REFRESH",
                "0",
            ).lower()
            in {
                "1",
                "true",
                "yes",
            }
        )

    def collect(
        self,
    ) -> dict[str, Any]:

        if self.refresh_enabled:

            from scraper.refresh import refresh

            refresh()

        return FileDataSource(
            self.raw_path
        ).collect()