"""Snapshot writer: one immutable copy per PokéAPI resource.

Each resource is stored twice on purpose: canonical JSON file under data/raw/pokeapi/
(gitignored) for eyeballing and reprocessing, and a raw_snapshots row (JSONB + sha256 +
source URL + fetch time) as the queryable audit record. Saving is idempotent — an
already-snapshotted resource is never fetched or written again.
"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pokedex_db.models import RawSnapshot

logger = logging.getLogger(__name__)


class SnapshotStore:
    def __init__(self, session_factory: sessionmaker[Session], data_dir: Path | str) -> None:
        self._session_factory = session_factory
        self._raw_dir = Path(data_dir) / "raw" / "pokeapi"

    def exists(self, resource_type: str, resource_id: str) -> bool:
        with self._session_factory() as session:
            return self._get(session, resource_type, resource_id) is not None

    def get_payload(self, resource_type: str, resource_id: str) -> dict[str, Any] | None:
        with self._session_factory() as session:
            snapshot = self._get(session, resource_type, resource_id)
            return None if snapshot is None else snapshot.payload

    def save(
        self,
        resource_type: str,
        resource_id: str,
        source_url: str,
        payload: dict[str, Any],
    ) -> tuple[RawSnapshot, bool]:
        """Persist file + row; returns (snapshot, created). Existing resources are kept
        untouched — snapshots are immutable."""
        with self._session_factory() as session:
            existing = self._get(session, resource_type, resource_id)
            if existing is not None:
                return existing, False

            body = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            file_path = self._raw_dir / resource_type / f"{resource_id}.json"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(body)

            snapshot = RawSnapshot(
                resource_type=resource_type,
                resource_id=resource_id,
                source_url=source_url,
                payload=payload,
                sha256=hashlib.sha256(body).hexdigest(),
            )
            session.add(snapshot)
            session.commit()
            session.refresh(snapshot)
            logger.info(
                "snapshot saved",
                extra={
                    "resource_type": resource_type,
                    "resource_id": resource_id,
                    "file": str(file_path),
                },
            )
            return snapshot, True

    @staticmethod
    def _get(session: Session, resource_type: str, resource_id: str) -> RawSnapshot | None:
        return session.scalar(
            select(RawSnapshot).where(
                RawSnapshot.resource_type == resource_type,
                RawSnapshot.resource_id == resource_id,
            )
        )
