from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class FileArtifactRepository:

    def __init__(
        self,
        root: str = "data/runs",
    ) -> None:

        self.root = Path(root)

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

    def write_json(
        self,
        run_id: str,
        name: str,
        payload: Any,
    ) -> Path:

        destination = (
            self.root
            / run_id
            / name
        )

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=destination.parent,
            delete=False,
        ) as temporary:

            json.dump(
                payload,
                temporary,
                indent=2,
                ensure_ascii=False,
            )

            temporary.flush()
            os.fsync(
                temporary.fileno()
            )

            temporary_name = (
                temporary.name
            )

        os.replace(
            temporary_name,
            destination,
        )

        return destination