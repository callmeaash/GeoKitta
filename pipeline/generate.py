"""Synthetic parcels, owners and history for the prepared OSM data."""
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely import affinity
from shapely.geometry import MultiPoint, MultiPolygon, Polygon, box
from shapely.strtree import STRtree

from pipeline import names, settings
from pipeline.transform import Prepared, assign_ward

TODAY = date(2026, 11, 12)
GRID = 0.001  # overlay precision in metres; robust snapping and identical shared edges
OUTLINE_SAMPLE_M = 2.0  # spacing of points along building outlines for the Voronoi split
SIMPLIFY_M = 1.5  # coverage simplification tolerance (square root of the smallest kept triangle area)
COMMERCIAL = {"commercial", "retail", "mixed_use", "office", "hotel", "supermarket", "shop"}
INSTITUTIONAL = {"school", "college", "university", "hospital", "government", "public", "civic", "kindergarten",
                 "dormitory", "barracks", "military"}
RELIGIOUS = {"temple", "church", "mosque", "monastery", "religious", "shrine", "stupa"}
DEED_TYPES = ["rajinama", "namasari", "hal_ko_bakaspatra", "ansha_banda", "danpatra"]
DEED_WEIGHTS = [0.60, 0.20, 0.10, 0.07, 0.03]
DEED_PREFIX = {"rajinama": "RJ", "namasari": "NS", "hal_ko_bakaspatra": "HB", "ansha_banda": "AB", "danpatra": "DP",
               "split": "KK", "boundary_update": "BU", "rokka": "RK", "fukuwa": "FK"}


@dataclass
class Generated:
    parcels: gpd.GeoDataFrame      # UTM
    owners: pd.DataFrame
    ownership: pd.DataFrame
    transactions: pd.DataFrame
    lineage: pd.DataFrame
    history: gpd.GeoDataFrame      # UTM
    rokka: pd.DataFrame
    defects: list[dict]
    survey: dict[str, list[tuple]]
    stats: dict


# ---------- geometry helpers ----------
def polygon_parts(geom) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if not geom.is_valid:
        geom = shapely.make_valid(geom)
    return [g for g in shapely.get_parts(geom) if g.geom_type == "Polygon" and g.area > 0]


def largest(geom) -> Polygon | None:
    parts = polygon_parts(geom)
    return max(parts, key=lambda p: p.area) if parts else None


def bisect(poly: Polygon) -> list[Polygon]:
    """Cut a polygon in two across the long side of its minimum rotated rectangle."""
    rect = shapely.minimum_rotated_rectangle(poly)
    if rect.geom_type != "Polygon":
        return [poly]
    c = list(rect.exterior.coords)[:4]
    mid = lambda a, b: ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)  # noqa: E731
    if math.dist(c[0], c[1]) >= math.dist(c[1], c[2]):
        a, b = mid(c[0], c[1]), mid(c[2], c[3])
        halves = [Polygon([c[0], a, b, c[3]]), Polygon([a, c[1], c[2], b])]
    else:
        a, b = mid(c[1], c[2]), mid(c[3], c[0])
        halves = [Polygon([c[0], c[1], a, b]), Polygon([b, a, c[2], c[3]])]
    pieces = [largest(shapely.intersection(poly, h, grid_size=GRID)) for h in halves]
    return [p for p in pieces if p is not None] or [poly]


def split_to_size(poly: Polygon, max_area: float) -> list[Polygon]:
    out, stack = [], [poly]
    while stack:
        p = stack.pop()
        if p.area <= max_area:
            out.append(p)
            continue
        pieces = bisect(p)
        if len(pieces) < 2:
            out.append(p)
        else:
            stack.extend(pieces)
    return out


def ring_coords(poly: Polygon) -> list[tuple[float, float]]:
    return list(poly.exterior.coords)[:-1]


# ---------- blocks and parcels ----------
def make_blocks(prep: Prepared) -> list[Polygon]:
    """Land between roads and rivers, with the road and river corridors removed."""
    lines = [*prep.roads.geometry, *prep.waterways.geometry, *shapely.get_parts(prep.area.boundary)]
    noded = shapely.union_all(lines, grid_size=GRID)
    faces = shapely.get_parts(shapely.polygonize(shapely.get_parts(noded)))
    corridors = [*prep.roads.geometry.buffer(prep.roads["half_width"]),
                 *prep.waterways.geometry.buffer(prep.waterways["width_m"] / 2)]
    tree = STRtree(corridors)
    blocks = []
    for face in faces:
        if not prep.area.contains(face.representative_point()):
            continue
        hits = tree.query(face, predicate="intersects")
        if len(hits):
            face = shapely.difference(face, shapely.union_all([corridors[i] for i in hits], grid_size=GRID),
                                      grid_size=GRID)
            parts = polygon_parts(face)  # drop stray lines and points left by the overlay
            if not parts:
                continue
            face = shapely.multipolygons(parts) if len(parts) > 1 else parts[0]
        land = shapely.intersection(face, prep.area, grid_size=GRID)
        blocks += [p for p in polygon_parts(land) if p.area >= 2 * settings.MIN_PARCEL_M2]
    return blocks


def footprint_cells(block: Polygon, footprints: list, points: list) -> list:
    """Voronoi cells around building outlines, merged per building, so boundaries never cut a building."""
    seeds, owner, seen = [], [], set()
    for n, (fp, pt) in enumerate(zip(footprints, points)):
        rings = [shapely.segmentize(p.exterior, OUTLINE_SAMPLE_M) for p in polygon_parts(fp)]
        coords = np.vstack([shapely.get_coordinates(pt), *(shapely.get_coordinates(r)[:-1] for r in rings)])
        for x, y in coords:
            key = (round(x, 2), round(y, 2))
            if key not in seen:  # buildings sharing a wall share outline points
                seen.add(key)
                seeds.append((x, y))
                owner.append(n)
    vor = shapely.get_parts(shapely.voronoi_polygons(MultiPoint(seeds), extend_to=block, ordered=True))
    groups = defaultdict(list)
    for cell, n in zip(vor, owner):
        groups[n].append(cell)
    cells = [MultiPolygon(polygon_parts(shapely.intersection(shapely.union_all(groups[n], grid_size=GRID), block,
                                                             grid_size=GRID))) for n in range(len(footprints))]
    # straighten the sawtooth left by offset outline points; shared edges change together, block edge is kept
    return list(shapely.coverage_simplify(cells, SIMPLIFY_M, simplify_boundary=False))


def parcels_from_blocks(blocks: list[Polygon], buildings: gpd.GeoDataFrame) -> list[dict]:
    """One parcel per building (Voronoi cell clipped to its block); blocks without buildings become open plots."""
    points = buildings.geometry.representative_point().values
    footprints = buildings.geometry.values
    pairs = STRtree(blocks).query(points, predicate="within")
    by_block = defaultdict(list)
    for b, k in zip(*pairs):
        by_block[int(k)].append(int(b))
    kinds = buildings["building"].values
    amenities = buildings["amenity"].values if "amenity" in buildings else [None] * len(buildings)

    rows = []

    def add(geom, k, b=None):
        if geom.area >= settings.MIN_PARCEL_M2:
            rows.append({"geometry": geom, "block": k, "building": kinds[b] if b is not None else None,
                         "amenity": amenities[b] if b is not None else None})

    for k, block in enumerate(blocks):
        seen, idx = set(), []
        for b in by_block.get(k, []):
            key = (round(points[b].x, 2), round(points[b].y, 2))
            if key not in seen:
                seen.add(key)
                idx.append(b)
        if not idx:
            for piece in split_to_size(block, settings.OPEN_PLOT_TARGET_M2 * 1.5):
                add(piece, k)
            continue
        cells = [block] if len(idx) == 1 else footprint_cells(block, [footprints[b] for b in idx],
                                                               [points[b] for b in idx])
        for b, cell in zip(idx, cells):
            parts = polygon_parts(cell)
            main = next((p for p in parts if p.covers(points[b])), None) or (max(parts, key=lambda p: p.area)
                                                                             if parts else None)
            if main is None:
                continue
            for p in parts:
                if p is not main and p.area >= 100:
                    add(p, k)
            for piece in split_to_size(main, settings.MAX_PARCEL_M2):
                add(piece, k, b if piece.covers(points[b]) else None)
    return rows


def classify(building, amenity, rng) -> tuple[str, str]:
    """(land_use, parcel_type) from the OSM building and amenity tags."""
    tags = {str(building or "").lower(), str(amenity or "").lower()}
    if tags & RELIGIOUS or "place_of_worship" in tags:
        return "institutional", "guthi"
    if tags & INSTITUTIONAL:
        return "institutional", "government" if rng.random() < 0.6 else "public"
    if tags & COMMERCIAL:
        return "commercial", "private"
    if building is None:
        return ("agricultural" if rng.random() < 0.6 else "other"), "private"
    return "residential", "private"


# ---------- generator ----------
class Generator:
    def __init__(self, prep: Prepared, seed: int):
        self.prep = prep
        self.rng = np.random.default_rng(seed)
        self.defects: list[dict] = []
        self.survey: dict[str, list[tuple]] = {}
        self.owners: list[dict] = []
        self.persons: list[int] = []
        self.singletons: dict[str, int] = {}
        self.ownership: list[dict] = []
        self.txns: list[dict] = []

    # ----- dates -----
    def rand_date(self, start: date, end: date) -> date | None:
        if end <= start:
            return None
        return start + timedelta(days=int(self.rng.integers(0, (end - start).days + 1)))

    # ----- parcels -----
    def build_parcels(self) -> gpd.GeoDataFrame:
        blocks = make_blocks(self.prep)
        rows = parcels_from_blocks(blocks, self.prep.buildings)
        df = gpd.GeoDataFrame(rows, geometry="geometry", crs=settings.UTM)
        uses = [classify(b, a, self.rng) for b, a in zip(df["building"], df["amenity"])]
        df["land_use"] = [u for u, _ in uses]
        df["parcel_type"] = [t for _, t in uses]
        df["status"] = "active"
        df["child"] = False
        df["defect"] = False
        self.stats = {"blocks": len(blocks), "buildings_used": int(df["building"].notna().sum())}
        return df

    def neighbours(self, df: gpd.GeoDataFrame, tree: STRtree, i: int, min_shared: float) -> list[int]:
        geom = df.geometry.iat[i]
        out = []
        for j in tree.query(geom, predicate="intersects"):
            j = int(j)
            if j != i and geom.boundary.intersection(df.geometry.iat[j].boundary).length >= min_shared:
                out.append(j)
        return out

    def add_splits(self, df: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, list[tuple[int, int, int]]]:
        """Merge some neighbouring pairs into a retired parent, as if they came from a kitta kaat."""
        tree = STRtree(df.geometry.values)
        target = int(settings.SPLIT_SHARE * len(df))
        ok = (df["land_use"] == "residential") & df.area.between(80, 1500)
        used, pairs = set(), []
        for i in self.rng.permutation(np.flatnonzero(ok.values)):
            if len(pairs) >= target:
                break
            if i in used:
                continue
            for j in self.neighbours(df, tree, int(i), 3):
                if j in used or not ok.iat[j] or df["block"].iat[j] != df["block"].iat[i]:
                    continue
                union = shapely.union_all([df.geometry.iat[i], df.geometry.iat[j]], grid_size=GRID)
                if union.geom_type == "Polygon":
                    pairs.append((int(i), j, union))
                    used |= {int(i), j}
                    break
        parents = []
        for i, j, union in pairs:
            df.loc[df.index[[i, j]], "child"] = True
            row = df.iloc[i].to_dict()
            row.update(geometry=union, status="retired", child=False, building=None)
            parents.append(row)
        start = len(df)
        df = pd.concat([df, gpd.GeoDataFrame(parents, geometry="geometry", crs=settings.UTM)], ignore_index=True)
        return gpd.GeoDataFrame(df, geometry="geometry", crs=settings.UTM), [
            (start + n, i, j) for n, (i, j, _) in enumerate(pairs)]

    def plant_defects(self, df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Overlaps, a plus-sign crossing and slivers; area mismatches are set later."""
        tree = STRtree(df.geometry.values)
        free = lambda i: df["status"].iat[i] == "active" and not df["child"].iat[i] and not df["defect"].iat[i]  # noqa
        order = self.rng.permutation(len(df))
        extra = []

        overlaps = 0
        for i in order:
            if overlaps >= settings.DEFECT_OVERLAPS or not free(i):
                continue
            nb = [j for j in self.neighbours(df, tree, int(i), 3) if free(j)]
            if not nb:
                continue
            j = nb[0]
            a, b = df.geometry.iat[i], df.geometry.iat[j]
            dx, dy = b.centroid.x - a.centroid.x, b.centroid.y - a.centroid.y
            d = math.hypot(dx, dy) or 1
            shift = float(self.rng.uniform(0.4, 1.2))
            moved = affinity.translate(a, dx / d * shift, dy / d * shift)
            df.loc[df.index[i], "geometry"] = moved
            df.loc[df.index[[i, j]], "defect"] = True
            side = [int(k) for k in tree.query(moved, predicate="overlaps") if k not in (i, j)]
            self.defects.append({"type": "overlap", "rows": [int(i), j], "also_overlaps": side,
                                 "shift_m": round(shift, 2)})
            overlaps += 1

        slivers = 0
        for i in order:
            if slivers >= settings.DEFECT_SLIVERS or not free(i):
                continue
            nb = [j for j in self.neighbours(df, tree, int(i), 8) if free(j)]
            if not nb:
                continue
            j = nb[0]
            a, b = df.geometry.iat[i], df.geometry.iat[j]
            shared = a.boundary.intersection(b.boundary)
            strip = largest(shapely.intersection(shared.buffer(0.35, cap_style="flat"), a, grid_size=GRID))
            rest = largest(shapely.difference(a, strip, grid_size=GRID)) if strip is not None else None
            if strip is None or rest is None or strip.area < 1 or rest.area < settings.MIN_PARCEL_M2:
                continue
            df.loc[df.index[i], "geometry"] = rest
            df.loc[df.index[[i, j]], "defect"] = True
            extra.append({"geometry": strip, "block": df["block"].iat[i], "building": None, "amenity": None,
                          "land_use": "other", "parcel_type": "private", "status": "active", "child": False,
                          "defect": True})
            self.defects.append({"type": "sliver", "rows": [len(df) + len(extra) - 1], "between": [int(i), j],
                                 "width_m": 0.35})
            slivers += 1

        for i in order:
            if not free(i) or pd.notna(df["building"].iat[i]) or df.geometry.iat[i].area < 600:
                continue
            c = df.geometry.iat[i].representative_point()
            arm = min(20.0, math.sqrt(df.geometry.iat[i].area) * 0.4)  # half-length of each bar
            h = box(c.x - arm, c.y - arm / 5, c.x + arm, c.y + arm / 5)
            v = box(c.x - arm / 5, c.y - arm, c.x + arm / 5, c.y + arm)
            if h.within(df.geometry.iat[i]) and v.within(df.geometry.iat[i]):
                df.loc[df.index[i], "geometry"] = h
                df.loc[df.index[i], "defect"] = True
                extra.append({"geometry": v, "block": df["block"].iat[i], "building": None, "amenity": None,
                              "land_use": "other", "parcel_type": "private", "status": "active", "child": False,
                              "defect": True})
                self.defects.append({"type": "overlap_cross", "rows": [int(i), len(df) + len(extra) - 1],
                                     "note": "plus-sign crossing: no corner of either parcel is inside the other"})
                break

        if extra:
            df = pd.concat([df, gpd.GeoDataFrame(extra, geometry="geometry", crs=settings.UTM)], ignore_index=True)
        return gpd.GeoDataFrame(df, geometry="geometry", crs=settings.UTM)

    def take_vacant_plot(self, df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Remove one open plot so it can be registered in the officer demo; keep its survey coordinates."""
        ok = ((df["status"] == "active") & df["building"].isna() & ~df["defect"] & ~df["child"]
              & df.area.between(150, 600))
        idx = np.flatnonzero(ok.values)
        if len(idx):
            i = int(self.rng.choice(idx))
            self.survey["register_vacant_plot.csv"] = ring_coords(df.geometry.iat[i])
            df = df.drop(df.index[i]).reset_index(drop=True)
        return df

    def assign_ids(self, df: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """Ward, map sheet, kitta number and PIN; split children are numbered after the older parcels."""
        df["ward_no"] = assign_ward(df.geometry, self.prep.wards).astype(int)
        x0, _, _, y1 = self.prep.wards.total_bounds
        rp = df.geometry.representative_point()
        df["cell"] = list(zip(((y1 - rp.y) // settings.SHEET_SIZE_M).astype(int),
                              ((rp.x - x0) // settings.SHEET_SIZE_M).astype(int)))
        df["sheet"] = 0
        for ward, group in df.groupby("ward_no"):
            numbers = {cell: n + 1 for n, cell in enumerate(sorted(set(group["cell"])))}
            df.loc[group.index, "sheet"] = group["cell"].map(numbers)
        df["_y"], df["_x"] = -rp.y, rp.x
        df = df.sort_values(["ward_no", "sheet", "child", "_y", "_x"])
        df["parcel_no"] = df.groupby(["ward_no", "sheet"]).cumcount() + 1
        df["map_sheet_code"] = [f"{settings.DISTRICT_CODE:02d}{settings.SHEET_SCALE_DIGIT}{w:02d}{s:03d}0"
                                for w, s in zip(df["ward_no"], df["sheet"])]
        df["pin"] = [f"KTM-{w:02d}-{s:03d}-{k:04d}" for w, s, k in zip(df["ward_no"], df["sheet"], df["parcel_no"])]
        df = df.sort_index()
        df["id"] = np.arange(1, len(df) + 1)
        return df.drop(columns=["cell", "_y", "_x"])

    # ----- owners -----
    def _person(self, gender: str | None = None, surname=None, born=(1940, 2000)) -> int:
        gender = gender or ("male" if self.rng.random() < 0.55 else "female")
        first = names.MALE if gender == "male" else names.FEMALE
        middle = names.MALE_MIDDLE if gender == "male" else names.FEMALE_MIDDLE
        parts = [first[self.rng.integers(len(first))]]
        if self.rng.random() < 0.6:
            parts.append(middle[self.rng.integers(len(middle))])
        parts.append(surname or names.SURNAMES[self.rng.integers(len(names.SURNAMES))])
        home = self.rng.random() < 0.85
        district = settings.DISTRICT_CODE if home else int(self.rng.integers(1, 78))
        dob = self.rand_date(date(*born[:1], 1, 1), date(born[1], 12, 31))
        oid = self._add_owner(
            owner_type="individual", full_name=" ".join(p[0] for p in parts),
            full_name_ne=" ".join(p[1] for p in parts), gender=gender, date_of_birth=dob,
            citizenship_no=f"{district:02d}-{int(self.rng.integers(1, 100)):02d}-{dob.year % 100:02d}-"
                           f"{int(self.rng.integers(1, 100000)):05d}",
            district_code=district, address="Kathmandu" if home else None, suffix="M" if gender == "male" else "F")
        self.owners[-1]["_surname"] = parts[-1]
        self.persons.append(oid)
        return oid

    def _add_owner(self, suffix: str, **fields) -> int:
        oid = len(self.owners) + 1
        row = {"id": oid, "lin": f"{settings.DISTRICT_CODE:02d}-{oid:06d}-{suffix}", "full_name_ne": None,
               "gender": None, "date_of_birth": None, "citizenship_no": None,
               "district_code": settings.DISTRICT_CODE, "address": "Kathmandu"}
        row.update(fields)
        self.owners.append(row)
        return oid

    def _singleton(self, name: str, owner_type: str, suffix: str) -> int:
        if name not in self.singletons:
            self.singletons[name] = self._add_owner(owner_type=owner_type, full_name=name, suffix=suffix)
        return self.singletons[name]

    def owner_set(self, parcel_type: str, land_use: str) -> list[tuple[int, int, int]]:
        """[(owner_id, share_num, share_den)] for a new set of current owners."""
        if parcel_type == "government":
            return [(self._singleton("Government of Nepal", "government", "G"), 1, 1)]
        if parcel_type == "public":
            return [(self._singleton("Kathmandu Metropolitan City", "government", "G"), 1, 1)]
        if parcel_type == "guthi":
            s = names.SURNAMES[self.rng.integers(len(names.SURNAMES))][0]
            return [(self._singleton(f"{s} Guthi", "communal", "C"), 1, 1)]
        if land_use == "commercial" and self.rng.random() < 0.3:
            words = names.COMPANY_WORDS[self.rng.integers(len(names.COMPANY_WORDS))]
            kind = names.COMPANY_KINDS[self.rng.integers(len(names.COMPANY_KINDS))]
            return [(self._singleton(f"{words} {kind} Pvt. Ltd. (demo)", "organisation", "O"), 1, 1)]
        r = self.rng.random()
        if r < settings.TRIPLE_SHARE:
            s = names.SURNAMES[self.rng.integers(len(names.SURNAMES))]
            return [(self._person(surname=s, born=(1960, 2000)), 1, 3) for _ in range(3)]
        if r < settings.TRIPLE_SHARE + settings.JOINT_SHARE:
            s = names.SURNAMES[self.rng.integers(len(names.SURNAMES))]
            return [(self._person("male", s, (1945, 1995)), 1, 2), (self._person("female", s, (1950, 1998)), 1, 2)]
        if self.persons and self.rng.random() < 0.45:  # many people own more than one parcel
            return [(int(self.persons[self.rng.integers(len(self.persons))]), 1, 1)]
        return [(self._person(), 1, 1)]

    def heirs(self, previous: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
        surname_latin = self.owners[previous[0][0] - 1].get("_surname")
        surname = next((s for s in names.SURNAMES if s == surname_latin), None)
        n = int(self.rng.integers(1, 4))
        return [(self._person(surname=surname, born=(1965, 2002)), 1, n) for _ in range(n)]

    # ----- transactions -----
    def txn(self, txn_type: str, parcel_id: int, when: date) -> int:
        tid = len(self.txns) + 1
        office = "Survey Office (demo)" if txn_type in ("split", "boundary_update") else "Land Revenue Office (demo)"
        self.txns.append({"id": tid, "txn_type": txn_type, "parcel_id": parcel_id, "status": "approved",
                          "deed_date": when, "office": office})
        return tid

    def own(self, parcel_id, owners, start, end=None, acquired=None, ended=None):
        for oid, num, den in owners:
            self.ownership.append({"parcel_id": parcel_id, "owner_id": oid, "share_num": num, "share_den": den,
                                   "valid_from": start, "valid_to": end, "acquired_txn_id": acquired,
                                   "ended_txn_id": ended})

    def history_and_owners(self, df: gpd.GeoDataFrame, splits: list[tuple[int, int, int]]):
        """Ownership chains, transfers, splits, boundary updates and rokka."""
        rid = df["id"].values
        start_of, owners_of, parent_of = {}, {}, {}
        lineage, history, rokka = [], [], []

        for p, a, b in splits:
            reg = self.rand_date(date(1985, 1, 1), date(2010, 12, 31))
            when = self.rand_date(reg + timedelta(days=365), date(2021, 12, 31))
            initial = self.owner_set(df["parcel_type"].iat[p], df["land_use"].iat[p])
            t = self.txn("split", int(rid[p]), when)
            self.own(int(rid[p]), initial, reg, when, None, t)
            for c in (a, b):
                parent_of[c] = p
                start_of[c], owners_of[c] = when, (initial, t)
                lineage.append({"parent_id": int(rid[p]), "child_id": int(rid[c]), "transaction_id": t})

        active = np.flatnonzero((df["status"] == "active").values)
        for i in active:
            pid = int(rid[i])
            if i in start_of:
                start, (initial, acquired) = start_of[i], owners_of[i]
            else:
                start = self.rand_date(date(1985, 1, 1), date(2012, 12, 31))
                initial, acquired = self.owner_set(df["parcel_type"].iat[i], df["land_use"].iat[i]), None
            last_change = start
            if df["parcel_type"].iat[i] == "private" and self.rng.random() < settings.TRANSFER_SHARE:
                when = self.rand_date(start + timedelta(days=365), TODAY - timedelta(days=60))
                if when:
                    kind = str(self.rng.choice(DEED_TYPES, p=DEED_WEIGHTS))
                    new = self.heirs(initial) if kind in ("namasari", "ansha_banda") else self.owner_set(
                        "private", df["land_use"].iat[i])
                    t = self.txn(kind, pid, when)
                    self.own(pid, initial, start, when, acquired, t)
                    self.own(pid, new, when, None, t, None)
                    last_change = when
                else:
                    self.own(pid, initial, start, None, acquired, None)
            else:
                self.own(pid, initial, start, None, acquired, None)

            plain = not df["child"].iat[i] and not df["defect"].iat[i]
            if plain and self.rng.random() < settings.BOUNDARY_UPDATE_SHARE:
                when = self.rand_date(start + timedelta(days=365), TODAY - timedelta(days=30))
                if when:
                    t = self.txn("boundary_update", pid, when)
                    old = affinity.scale(df.geometry.iat[i], *(2 * [1 + float(self.rng.uniform(0.01, 0.03))]))
                    history.append({"parcel_id": pid, "geometry": old, "area_m2": round(old.area, 2),
                                    "valid_from": datetime.combine(start, time(10), timezone.utc),
                                    "valid_to": datetime.combine(when, time(10), timezone.utc), "transaction_id": t})

            if df["parcel_type"].iat[i] == "private" and self.rng.random() < settings.ROKKA_SHARE:
                earliest = max(last_change, date(2018, 1, 1)) + timedelta(days=30)
                begin = self.rand_date(earliest, TODAY - timedelta(days=30))
                if begin:
                    kind = str(self.rng.choice(["bank", "court", "ciaa", "government"], p=[0.7, 0.2, 0.05, 0.05]))
                    who = {"bank": names.BANKS[self.rng.integers(len(names.BANKS))], "court": "District Court (demo)",
                           "ciaa": "CIAA (demo)", "government": "Government of Nepal (demo)"}[kind]
                    placed = self.txn("rokka", pid, begin)
                    end = begin + timedelta(days=int(self.rng.integers(180, 900))) if self.rng.random() < 0.4 else None
                    released = self.txn("fukuwa", pid, end) if end and end < TODAY else None
                    rokka.append({"parcel_id": pid, "requested_by_type": kind, "requested_by_name": who,
                                  "reason": "loan security" if kind == "bank" else "case under review",
                                  "start_date": begin, "fukuwa_date": end if released else None,
                                  "placed_txn_id": placed, "released_txn_id": released})
        return lineage, history, rokka

    def plant_duplicate_owners(self):
        """Near-duplicate owners: one spelling change, same date of birth and district, owning another parcel."""
        current_single = [k for k, o in enumerate(self.ownership)
                          if o["valid_to"] is None and o["share_den"] == 1
                          and self.owners[o["owner_id"] - 1]["owner_type"] == "individual"]
        candidates = [o for o in self.owners if o["owner_type"] == "individual"
                      and any(w in names.VARIANTS for w in o["full_name"].split())]
        n = min(settings.NEAR_DUPLICATE_OWNERS, len(candidates), len(current_single))
        picks = self.rng.choice(len(candidates), n, replace=False)
        targets = self.rng.choice(len(current_single), n, replace=False)
        for c, t in zip(picks, targets):
            orig = candidates[int(c)]
            words = orig["full_name"].split()
            k = next(i for i, w in enumerate(words) if w in names.VARIANTS)
            words[k] = names.VARIANTS[words[k]]
            oid = self._add_owner(owner_type="individual", full_name=" ".join(words), gender=orig["gender"],
                                  date_of_birth=orig["date_of_birth"], district_code=orig["district_code"],
                                  address=orig["address"], suffix="M" if orig["gender"] == "male" else "F")
            self.ownership[current_single[int(t)]]["owner_id"] = oid
            self.defects.append({"type": "duplicate_owner", "original_lin": orig["lin"],
                                 "duplicate_lin": self.owners[oid - 1]["lin"], "original": orig["full_name"],
                                 "duplicate": self.owners[oid - 1]["full_name"]})

    def survey_samples(self, df: gpd.GeoDataFrame):
        """Coordinate files for the boundary-update and split demos."""
        ok = (df["status"] == "active") & (df["land_use"] == "residential") & ~df["defect"] & ~df["child"]
        idx = self.rng.permutation(np.flatnonzero((ok & df.area.between(250, 900)).values))
        if len(idx) >= 2:
            a, b = int(idx[0]), int(idx[1])
            poly = df.geometry.iat[a]
            pts = ring_coords(poly)
            cx, cy = poly.centroid.x, poly.centroid.y
            x, y = pts[0]
            d = math.hypot(cx - x, cy - y) or 1
            pts[0] = (x + (cx - x) / d * 0.5, y + (cy - y) / d * 0.5)
            self.survey[f"update_{df['pin'].iat[a]}.csv"] = pts
            for n, piece in enumerate(bisect(df.geometry.iat[b])):
                self.survey[f"split_{df['pin'].iat[b]}_{'AB'[n]}.csv"] = ring_coords(piece)

    def run(self) -> Generated:
        df = self.build_parcels()
        df = self.take_vacant_plot(df)  # before anything records row positions
        df, splits = self.add_splits(df)
        df = self.plant_defects(df)
        df = self.assign_ids(df)

        area = df.area
        df["registered_area"] = (area * (1 + self.rng.normal(0, 0.004, len(df)))).round(2)
        ok = np.flatnonzero(((df["status"] == "active") & ~df["defect"] & ~df["child"]).values)
        for i in self.rng.choice(ok, min(settings.DEFECT_AREA_MISMATCH, len(ok)), replace=False):
            factor = 1 + float(self.rng.choice([-1, 1])) * float(self.rng.uniform(0.08, 0.2))
            df.loc[df.index[i], "registered_area"] = round(area.iat[i] * factor, 2)
            df.loc[df.index[i], "defect"] = True
            self.defects.append({"type": "area_mismatch", "rows": [int(i)],
                                 "calculated_m2": round(area.iat[i], 2),
                                 "registered_m2": float(df["registered_area"].iat[i])})

        lineage, history, rokka = self.history_and_owners(df, splits)
        self.plant_duplicate_owners()
        self.survey_samples(df)

        pins = df["pin"].values
        for d in self.defects:
            for key in ("rows", "between", "also_overlaps"):
                if key in d:
                    d["pins" if key == "rows" else key] = [str(pins[r]) for r in d.pop(key)]

        txns = pd.DataFrame(self.txns).sort_values(["deed_date", "id"])
        txns["case_id"] = [str(2_000_001 + n) for n in range(len(txns))]
        txns["deed_ref"] = [f"{DEED_PREFIX[t]}-{d.year}-{n:05d}" for n, (t, d) in
                            enumerate(zip(txns["txn_type"], txns["deed_date"]), start=1)]
        txns = txns.sort_values("id")

        owners = pd.DataFrame(self.owners).drop(columns=["_surname"], errors="ignore")
        stats = {**self.stats, "parcels": len(df), "active": int((df["status"] == "active").sum()),
                 "retired": int((df["status"] == "retired").sum()), "owners": len(owners),
                 "ownership_rows": len(self.ownership), "transactions": len(txns), "splits": len(splits),
                 "boundary_updates": len(history), "rokka": len(rokka),
                 "defects": pd.Series([d["type"] for d in self.defects]).value_counts().to_dict()}
        return Generated(
            parcels=df, owners=owners, ownership=pd.DataFrame(self.ownership), transactions=txns,
            lineage=pd.DataFrame(lineage, columns=["parent_id", "child_id", "transaction_id"]),
            history=gpd.GeoDataFrame(history, geometry="geometry", crs=settings.UTM) if history else
            gpd.GeoDataFrame({"parcel_id": [], "area_m2": [], "valid_from": [], "valid_to": [], "transaction_id": []},
                             geometry=[], crs=settings.UTM),
            rokka=pd.DataFrame(rokka), defects=self.defects, survey=self.survey, stats=stats)


def generate(prep: Prepared, seed: int = settings.DEFAULT_SEED) -> Generated:
    return Generator(prep, seed).run()
