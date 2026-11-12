"""Place names for the public search: places from OSM plus named roads and rivers, each with a location."""
from dataclasses import dataclass

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.search.index import Match, NameIndex
from app.spatial.features import base_name

FEATURE_ID_OFFSET = 10_000_000  # gazetteer ids for roads and rivers, kept apart from places.id
_KIND = {"highway": "road", "road": "road", "river": "river", "stream": "river"}
_RANK = {"ward": 0, "tole": 1, "landmark": 2, "park": 3, "river": 4, "road": 5}  # tie-break between equal scores


@dataclass(frozen=True)
class Place:
    id: int
    name: str
    name_ne: str | None
    kind: str
    ward: int | None
    lng: float
    lat: float


class Gazetteer:
    def __init__(self, places: list[Place]):
        self.places = {p.id: p for p in places}
        self.index = NameIndex([(p.id, p.name) for p in places])

    @classmethod
    def load(cls, db: Session | Connection) -> "Gazetteer":
        places = [Place(r[0], r[1], r[2], r[3], r[4], r[5], r[6]) for r in db.execute(text(
            "SELECT id, name, name_ne, place_type, ward_no, ST_X(location), ST_Y(location) FROM places"))]
        seen = {(base_name(p.name), p.kind) for p in places}
        # one entry per named road or river, at the middle of its longest way
        rows = db.execute(text("""
            SELECT DISTINCT ON (feature_type, name) id, name, feature_type,
                   ST_X(ST_LineInterpolatePoint(geom, 0.5)), ST_Y(ST_LineInterpolatePoint(geom, 0.5))
            FROM features WHERE name IS NOT NULL AND feature_type <> 'power_line'
            ORDER BY feature_type, name, ST_Length(geom::geography) DESC
        """))
        for fid, name, ftype, lng, lat in rows:
            key = (base_name(name), _KIND[ftype])
            if key not in seen:
                seen.add(key)
                places.append(Place(FEATURE_ID_OFFSET + fid, name, None, _KIND[ftype], None, lng, lat))
        return cls(places)

    def search(self, query: str, limit: int = 6) -> list[tuple[Place, Match]]:
        matches = self.index.search(query, limit=limit * 3)
        ranked = sorted(matches, key=lambda m: (m.score, _RANK.get(self.places[m.id].kind, 9), len(m.name)))
        return [(self.places[m.id], m) for m in ranked[:limit]]
