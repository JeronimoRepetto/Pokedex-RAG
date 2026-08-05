"""Sprite downloader: completes the sprites manifest by fetching each source URL once.

Files land under <data_dir>/sprites/ (gitignored — no Pokémon imagery in the repo);
rows get local_path (relative to data_dir) and sha256. Idempotent: rows whose file
already exists are skipped. Individual download failures are logged and skipped so a
re-run can pick them up — explicit, visible degradation instead of a dead run.
"""

import hashlib
import logging
import time
from collections.abc import Callable
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pokedex_db.models import Sprite

logger = logging.getLogger(__name__)


class SpriteDownloader:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        data_dir: Path | str,
        *,
        timeout_seconds: float = 30.0,
        rate_limit_per_sec: float = 3.0,
        sleep: Callable[[float], None] = time.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._session_factory = session_factory
        self._data_dir = Path(data_dir)
        self._client = httpx.Client(timeout=timeout_seconds, follow_redirects=True)
        self._min_interval = 1.0 / rate_limit_per_sec
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_request_at: float | None = None

    def close(self) -> None:
        self._client.close()

    def run(self) -> tuple[int, int, int]:
        """Returns (downloaded, skipped, failed)."""
        downloaded = skipped = failed = 0
        with self._session_factory() as session:
            rows = session.scalars(select(Sprite).order_by(Sprite.pokemon_id)).all()
            for row in rows:
                if row.local_path and (self._data_dir / row.local_path).exists() and row.sha256:
                    skipped += 1
                    continue
                try:
                    body = self._download(row.source_url)
                except httpx.HTTPError as exc:
                    failed += 1
                    logger.warning(
                        "sprite download failed; will retry on next run",
                        extra={
                            "pokemon_id": row.pokemon_id,
                            "kind": row.kind,
                            "url": row.source_url,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                    )
                    continue
                suffix = Path(httpx.URL(row.source_url).path).suffix or ".png"
                relative = Path("sprites") / f"{row.pokemon_id}-{row.kind}{suffix}"
                target = self._data_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(body)
                row.local_path = relative.as_posix()
                row.sha256 = hashlib.sha256(body).hexdigest()
                session.commit()
                downloaded += 1
        logger.info(
            "sprite run finished",
            extra={"downloaded": downloaded, "skipped": skipped, "failed": failed},
        )
        return downloaded, skipped, failed

    def _download(self, url: str) -> bytes:
        if self._last_request_at is not None:
            wait = self._min_interval - (self._monotonic() - self._last_request_at)
            if wait > 0:
                self._sleep(wait)
        self._last_request_at = self._monotonic()
        response = self._client.get(url)
        response.raise_for_status()
        return response.content
