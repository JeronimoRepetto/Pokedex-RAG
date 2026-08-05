"""Generation ingest orchestrator: fetch-once → snapshot → normalize, in dependency
order. Fully resumable: resources already snapshotted are read back from the database
instead of the network, and normalization is idempotent."""

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pipeline.normalize import (
    extract_id,
    normalize_ability,
    normalize_evolution_chain,
    normalize_move,
    normalize_pokemon,
    normalize_species,
    normalize_type,
)
from pipeline.snapshots import SnapshotStore
from pokedex_db.models import PokemonAbility, PokemonMove, PokemonType, Species

logger = logging.getLogger(__name__)


class ResourceClient(Protocol):
    def get_json(self, path: str) -> tuple[dict[str, Any], str]: ...


@dataclass
class IngestReport:
    fetched: int = 0
    reused: int = 0
    normalized: dict[str, int] = field(default_factory=dict)

    def bump(self, resource_type: str) -> None:
        self.normalized[resource_type] = self.normalized.get(resource_type, 0) + 1


def ingest_generation(
    client: ResourceClient,
    store: SnapshotStore,
    session_factory: sessionmaker[Session],
    generation: int = 1,
) -> IngestReport:
    report = IngestReport()

    def fetch_once(resource_type: str, resource_id: str, path: str) -> dict[str, Any]:
        payload = store.get_payload(resource_type, resource_id)
        if payload is not None:
            report.reused += 1
            return payload
        payload, url = client.get_json(path)
        store.save(resource_type, resource_id, url, payload)
        report.fetched += 1
        return payload

    gen_payload = fetch_once("generation", str(generation), f"/generation/{generation}")
    species_ids = sorted(extract_id(ref["url"]) for ref in gen_payload["pokemon_species"])
    logger.info(
        "ingest starting",
        extra={"generation": generation, "species_count": len(species_ids)},
    )

    default_pokemon_ids: list[int] = []
    for species_id in species_ids:
        payload = fetch_once("pokemon-species", str(species_id), f"/pokemon-species/{species_id}")
        with session_factory() as session:
            normalize_species(session, payload)
            session.commit()
        report.bump("pokemon-species")
        for variety in payload.get("varieties", []):
            if variety.get("is_default"):
                default_pokemon_ids.append(extract_id(variety["pokemon"]["url"]))

    for pokemon_id in sorted(default_pokemon_ids):
        payload = fetch_once("pokemon", str(pokemon_id), f"/pokemon/{pokemon_id}")
        with session_factory() as session:
            normalize_pokemon(session, payload)
            session.commit()
        report.bump("pokemon")

    with session_factory() as session:
        chain_ids = sorted(
            session.scalars(
                select(Species.evolution_chain_id)
                .where(Species.id.in_(species_ids), Species.evolution_chain_id.is_not(None))
                .distinct()
            ).all()
        )
    for chain_id in chain_ids:
        payload = fetch_once("evolution-chain", str(chain_id), f"/evolution-chain/{chain_id}")
        with session_factory() as session:
            normalize_evolution_chain(session, payload)
            session.commit()
        report.bump("evolution-chain")

    backfills = (
        ("type", select(PokemonType.type_id).distinct(), normalize_type),
        ("ability", select(PokemonAbility.ability_id).distinct(), normalize_ability),
        ("move", select(PokemonMove.move_id).distinct(), normalize_move),
    )
    for resource_type, id_query, normalizer in backfills:
        with session_factory() as session:
            ids = sorted(session.scalars(id_query).all())
        logger.info("backfill starting", extra={"resource_type": resource_type, "count": len(ids)})
        for index, resource_id in enumerate(ids, start=1):
            payload = fetch_once(resource_type, str(resource_id), f"/{resource_type}/{resource_id}")
            with session_factory() as session:
                normalizer(session, payload)
                session.commit()
            report.bump(resource_type)
            if index % 100 == 0:
                logger.info(
                    "backfill progress",
                    extra={"resource_type": resource_type, "done": index, "total": len(ids)},
                )

    logger.info(
        "ingest finished",
        extra={
            "generation": generation,
            "fetched": report.fetched,
            "reused": report.reused,
            "normalized": report.normalized,
        },
    )
    return report
