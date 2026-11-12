"""Roads, rivers and power lines in UTM metres, indexed with the in-memory quadtree; setback zones around them."""
import math
from dataclasses import dataclass

from sqlalchemy import Connection, text
from sqlalchemy.orm import Session

from app.spatial.geometry import (Box, Point, Polygon, box_of, boxes_touch, chunk_line, expand, line_distance,
                                  point_segment_distance, within_distance)
from app.spatial.memory import MemoryQuadtree
from app.spatial.projection import line_from_geojson

PIECE_M = 100.0  # long lines are indexed in pieces of about this length
_SUFFIXES = {"river", "khola", "nadi", "stream", "road", "marg", "sadak", "highway"}


def base_name(name: str | None) -> str | None:
    """Name without case or a trailing kind word, so OSM's "Bagmati" and "Bagmati River" match."""
    if not name:
        return None
    words = name.lower().split()
    while len(words) > 1 and words[-1] in _SUFFIXES:
        words.pop()
    return " ".join(words)


@dataclass(frozen=True)
class Feature:
    id: int
    name: str | None
    type: str
    width: float | None
    line: list[Point]


@dataclass(frozen=True)
class Rule:
    id: int
    feature_type: str
    distance: float
    measured_from: str
    source: str
    note: str | None

    def zone(self, feature: Feature) -> float:
        """Distance from the centre line that the rule protects (bank rules add half the river's width)."""
        return self.distance + ((feature.width or 0) / 2 if self.measured_from == "bank" else 0)


def load_rules(db: Session | Connection) -> list[Rule]:
    rows = db.execute(text("SELECT id, feature_type, distance_m, measured_from, source, note FROM setback_rules "
                           "ORDER BY feature_type, distance_m DESC")).all()
    return [Rule(r[0], r[1], float(r[2]), r[3], r[4], r[5]) for r in rows]


def strictest(rules: list[Rule]) -> dict[str, Rule]:
    """The widest rule per feature type (e.g. the national highway rule over the municipal one)."""
    out: dict[str, Rule] = {}
    for r in rules:
        if r.feature_type not in out or r.distance > out[r.feature_type].distance:
            out[r.feature_type] = r
    return out


class FeatureIndex:
    def __init__(self, features: list[Feature]):
        self.features = {f.id: f for f in features}
        self._pieces: list[tuple[int, list[Point], Box]] = []
        for f in features:
            for part in chunk_line(f.line, PIECE_M):
                self._pieces.append((f.id, part, box_of(part)))
        self._tree = MemoryQuadtree([(i, p[2]) for i, p in enumerate(self._pieces)])
        self._max_half_width = max(((f.width or 0) / 2 for f in features), default=0.0)

    @classmethod
    def load(cls, db: Session | Connection) -> "FeatureIndex":
        rows = db.execute(text("SELECT id, name, feature_type, width_m, ST_AsGeoJSON(geom) FROM features")).all()
        return cls([Feature(r[0], r[1], r[2], float(r[3]) if r[3] is not None else None, line_from_geojson(r[4]))
                    for r in rows])

    def __len__(self) -> int:
        return len(self.features)

    def nearest(self, p: Point, types: set[str] | None, max_distance: float) -> tuple[Feature, float] | None:
        """Closest feature (of the given types) to a point, within max_distance of its centre line."""
        best = None
        for i in self._tree.search(expand((p[0], p[1], p[0], p[1]), max_distance)):
            fid, part, _ = self._pieces[i]
            feature = self.features[fid]
            if types and feature.type not in types:
                continue
            d = min((point_segment_distance(p, a, b) for a, b in zip(part, part[1:])),
                    default=math.hypot(p[0] - part[0][0], p[1] - part[0][1]))
            if d <= max_distance and (best is None or d < best[1]):
                best = (feature, d)
        return best

    def group(self, feature: Feature) -> list[Feature]:
        """All ways of the same named road or river (OSM splits them); an unnamed one stands alone."""
        key = base_name(feature.name)
        if key is None:
            return [feature]
        return [f for f in self.features.values() if f.type == feature.type and base_name(f.name) == key]

    def setbacks(self, polygon: Polygon, rules: list[Rule]) -> list[dict]:
        """Setback zones a parcel lies in: one entry per named feature, with the distance to its line or bank."""
        governing = strictest(rules)
        if not governing:
            return []
        pbox = box_of(polygon[0])
        reach = max(r.distance for r in governing.values()) + self._max_half_width
        closest: dict[int, float] = {}
        for i in self._tree.search(expand(pbox, reach)):
            fid, part, box = self._pieces[i]
            feature = self.features[fid]
            rule = governing.get(feature.type)
            if rule is None or not boxes_touch(expand(box, rule.zone(feature)), pbox):
                continue
            if within_distance(polygon, part, rule.zone(feature)):
                closest[fid] = min(line_distance(polygon, part), closest.get(fid, math.inf))
        out: dict[tuple, dict] = {}
        for fid, d in closest.items():
            f = self.features[fid]
            rule = governing[f.type]
            from_edge = max(0.0, d - (f.width or 0) / 2) if rule.measured_from == "bank" else d
            key = (f.type, base_name(f.name) or fid)
            if key not in out or from_edge < out[key]["distance_m"]:
                out[key] = {"feature_id": f.id, "name": f.name, "feature_type": f.type,
                            "distance_m": round(from_edge, 1), "rule_id": rule.id, "rule_distance_m": rule.distance,
                            "measured_from": rule.measured_from, "source": rule.source, "note": rule.note}
        return sorted(out.values(), key=lambda s: s["distance_m"])
