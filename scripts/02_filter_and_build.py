"""
Filters raw Overture Places + Land Use (see 01_download_raw.sh) down to
sport/recreation features and writes the one small file the app actually
loads: data/austin_sports.geojson.

Two sources, on purpose:
  - Overture Places: clean points with a name/category, often address/
    phone/website too.
  - Overture Land Use: shapes tagged for a sport/rec use (a park, a
    pitch, a dog park) that frequently have no name at all. OSM's
    "pitch" class in particular is ~94% unnamed in the Austin bbox.
    We still surface these rather than dropping them; the app marks
    them "details_limited" instead of hiding them or faking detail.

Run scripts/01_download_raw.sh first.
"""

import json
import os
from collections import Counter

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
RAW_DIR = os.path.join(DATA_DIR, "raw")
PLACE_RAW = os.path.join(RAW_DIR, "place.geojson")
LANDUSE_RAW = os.path.join(RAW_DIR, "land_use.geojson")
OUT_PATH = os.path.join(DATA_DIR, "austin_sports.geojson")

# Overture Places `categories.primary` -> this app's category key.
# Deliberately excludes categories that are commercial businesses rather
# than a place to go play (gym, boxing_gym, sporting_goods, sports_bar,
# race_track, amusement_park, rv_park, etc.) even though they live under
# Overture's "sports_and_recreation" taxonomy branch.
PLACE_CATEGORY_MAP = {
    "basketball_court": "basketball_court",
    "tennis_court": "tennis_court",
    "volleyball_court": "volleyball_court",
    "soccer_field": "soccer_field",
    "baseball_field": "baseball_field",
    "baseball_stadium": "stadium_arena",
    "american_football_field": "football_field",
    "football_stadium": "stadium_arena",
    "disc_golf_course": "disc_golf",
    "dog_park": "dog_park",
    "skate_park": "skate_park",
    "hiking_trail": "hiking_trail",
    "mountain_bike_trails": "trail",
    "golf_course": "golf_course",
    "golf_club": "golf_course",
    "miniature_golf_course": "golf_course",
    "swimming_pool": "swimming_pool",
    "playground": "playground",
    "park": "park",
    "sports_and_recreation_venue": "recreation_area",
    "stadium_arena": "stadium_arena",
    "track_stadium": "running_track",
    "sports_club_and_league": "sports_club",
    "amateur_sports_league": "sports_club",
    "amateur_sports_team": "sports_club",
}

# Overture Land Use `class` -> this app's category key.
LANDUSE_CLASS_MAP = {
    "pitch": "sports_field",
    "park": "park",
    "playground": "playground",
    "track": "running_track",
    "recreation_ground": "recreation_area",
    "dog_park": "dog_park",
    "golf_course": "golf_course",
    "stadium": "stadium_arena",
    "driving_range": "golf_course",
}

# Overture has no pickleball_court category at all (as of this bbox's
# snapshot, real pickleball venues turn up with no category or a vague one
# like active_life/sports_and_recreation_venue, not a specific gap in our
# mapping above). So a name match overrides the category-based mapping,
# except for these: businesses selling or renting gear, not a place to
# play, that happen to have "pickleball" in their name too.
PICKLEBALL_EXCLUDED_CATEGORIES = {
    "sporting_goods",
    "sport_equipment_rentals",
    "sports_wear",
}

# Broader taxonomy branch used to flag Places categories that showed up in
# the bbox but aren't in PLACE_CATEGORY_MAP above, so a human can decide
# whether they belong (see the summary printed at the end of this script).
SPORT_ADJACENT_HINTS = (
    "sport",
    "court",
    "field",
    "trail",
    "golf",
    "pool",
    "swim",
    "track",
    "stadium",
    "recreation",
    "athlet",
)


def _load(path):
    if not os.path.exists(path):
        raise SystemExit(f"Missing {path}. Run scripts/01_download_raw.sh first.")
    with open(path) as f:
        return json.load(f)


def _format_address(addr):
    if not addr:
        return None
    parts = [addr.get("freeform"), addr.get("locality"), addr.get("region")]
    parts = [p for p in parts if p]
    return ", ".join(parts) if parts else None


def _build_place_feature(feat):
    props = feat["properties"]
    if props.get("operating_status") == "closed":
        return None

    name = (props.get("names") or {}).get("primary")
    if not name:
        return None

    category = (props.get("categories") or {}).get("primary")
    if "pickleball" in name.lower() and category not in PICKLEBALL_EXCLUDED_CATEGORIES:
        mapped = "pickleball_court"
    else:
        mapped = PLACE_CATEGORY_MAP.get(category)
    if not mapped:
        return None

    addresses = props.get("addresses") or [{}]
    address = _format_address(addresses[0])
    phones = props.get("phones") or []
    websites = props.get("websites") or []
    phone = phones[0] if phones else None
    website = websites[0] if websites else None

    return {
        "type": "Feature",
        "geometry": feat["geometry"],
        "properties": {
            "source": "place",
            "name": name,
            "category": mapped,
            "address": address,
            "phone": phone,
            "website": website,
            "details_limited": not (address or phone or website),
        },
    }


def _build_landuse_feature(feat):
    props = feat["properties"]
    name = (props.get("names") or {}).get("primary") or "Unnamed spot"

    cls = props.get("class")
    if "pickleball" in name.lower():
        mapped = "pickleball_court"
    else:
        mapped = LANDUSE_CLASS_MAP.get(cls)
    if not mapped:
        return None

    return {
        "type": "Feature",
        "geometry": feat["geometry"],
        "properties": {
            "source": "land_use",
            "name": name,
            "category": mapped,
            "address": None,
            "phone": None,
            "website": None,
            "details_limited": True,
        },
    }


def main():
    place_raw = _load(PLACE_RAW)
    landuse_raw = _load(LANDUSE_RAW)

    out_features = []
    unfamiliar = Counter()

    for feat in place_raw["features"]:
        category = (feat["properties"].get("categories") or {}).get("primary")
        if category and category not in PLACE_CATEGORY_MAP:
            if any(hint in category for hint in SPORT_ADJACENT_HINTS):
                unfamiliar[category] += 1
        built = _build_place_feature(feat)
        if built:
            out_features.append(built)

    for feat in landuse_raw["features"]:
        built = _build_landuse_feature(feat)
        if built:
            out_features.append(built)

    with open(OUT_PATH, "w") as f:
        json.dump({"type": "FeatureCollection", "features": out_features}, f)

    counts = Counter(f["properties"]["category"] for f in out_features)
    sources = Counter(f["properties"]["source"] for f in out_features)
    limited = sum(1 for f in out_features if f["properties"]["details_limited"])

    print(f"Wrote {len(out_features)} features to {OUT_PATH}")
    print(f"  by source: {dict(sources)}")
    print(f"  details_limited: {limited} ({limited * 100 // max(len(out_features), 1)}%)")
    print("  by category:")
    for cat, n in counts.most_common():
        print(f"    {cat}: {n}")

    if unfamiliar:
        print(
            "\nSport-adjacent Places categories seen in this bbox but NOT "
            "mapped (check whether any belong in PLACE_CATEGORY_MAP):"
        )
        for cat, n in unfamiliar.most_common():
            print(f"    {cat}: {n}")


if __name__ == "__main__":
    main()
