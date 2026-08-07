"""Pokémon-name lookup for entity resolution.

Lazy + cached, matching SqlPokemonTypeLookup's policy: nothing touches the database
until the first /intent request, so startup and offline tests stay free. The roster is
151 immutable rows — caching it forever is correct, not an optimisation gamble.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pokedex_db.models import Pokemon


class SqlPokemonNameLookup:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._cache: dict[str, int] | None = None

    def known_names(self) -> dict[str, int]:
        if self._cache is None:
            with self._session_factory() as session:
                self._cache = dict(session.execute(select(Pokemon.name, Pokemon.id)).all())
        return self._cache
