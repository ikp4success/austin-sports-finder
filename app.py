"""
Austin Sports Finder: a small Flask app that serves a pre-extracted,
filtered slice of Overture Maps data (sport & recreation places/areas
in central Austin) and a Leaflet map to browse it.

Data flow (see scripts/):
  1. 01_download_raw.sh, pulls raw Overture Places/LandUse/Buildings
                          for the Austin bbox (run locally; needs
                          network access to Overture's data host)
  2. 02_filter_and_build.py, filters down to sport/rec features,
                          writes data/austin_sports.geojson

This app just loads that single small GeoJSON file into memory and
serves it. If the real extracted file isn't present yet, it falls
back to data/austin_sports.sample.geojson so the app is runnable
end-to-end during development.
"""

import json
import math
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from llm_providers import (
    PROVIDER_LABELS,
    LLMConfigError,
    available_providers,
    extraction_failure_status,
)
from nl_search import parse_nl_query

load_dotenv()

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
REAL_DATA_PATH = os.path.join(DATA_DIR, "austin_sports.geojson")
SAMPLE_DATA_PATH = os.path.join(DATA_DIR, "austin_sports.sample.geojson")

# Human-friendly labels + a rough grouping used for the UI filter buttons.
CATEGORY_GROUPS = {
    "basketball_court": "Basketball",
    "tennis_court": "Tennis",
    "soccer_field": "Soccer / Fields",
    "football_field": "Soccer / Fields",
    "baseball_field": "Soccer / Fields",
    "dog_park": "Dog Parks",
    "skate_park": "Skate Parks",
    "skatepark": "Skate Parks",
    "disc_golf": "Disc Golf",
    "golf_course": "Golf",
    "running_track": "Track & Trails",
    "track": "Track & Trails",
    "hiking_trail": "Track & Trails",
    "trail": "Track & Trails",
    "swimming_pool": "Swimming",
    "playground": "Playgrounds",
    "park": "Parks",
    "recreation_area": "Parks",
    "recreation": "Parks",
    "sports_club": "Sports Clubs",
    "stadium_arena": "Stadiums",
    "volleyball_court": "Volleyball",
    "sports_field": "Soccer / Fields",
    "pickleball_court": "Pickleball",
}


def _load_data():
    path = REAL_DATA_PATH if os.path.exists(REAL_DATA_PATH) else SAMPLE_DATA_PATH
    with open(path) as f:
        data = json.load(f)
    using_sample = path == SAMPLE_DATA_PATH
    return data, using_sample


_DATA, _USING_SAMPLE = _load_data()


def _group_for(category):
    return CATEGORY_GROUPS.get(category, "Other")


def _feature_center(feature):
    """Return (lat, lon) for either a Point or a Polygon feature, for
    distance filtering. Polygon center is a simple bbox midpoint,
    good enough for 'near me' filtering, not for precise geometry."""
    geom = feature["geometry"]
    if geom["type"] == "Point":
        lon, lat = geom["coordinates"]
        return lat, lon
    if geom["type"] in ("Polygon", "MultiPolygon"):
        coords = geom["coordinates"]
        # flatten first ring of first polygon
        ring = coords[0] if geom["type"] == "Polygon" else coords[0][0]
        lons = [c[0] for c in ring]
        lats = [c[1] for c in ring]
        return (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
    return None, None


def _haversine_miles(lat1, lon1, lat2, lon2):
    R = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


VALID_GROUPS = sorted(set(CATEGORY_GROUPS.values()))


def _filter_features(groups=None, lat=None, lon=None, radius=5.0, keyword=None):
    """Shared filter used by /api/places and /api/search: optional group
    allowlist, optional near-a-point radius, optional keyword match on
    name/category/group."""
    keyword = keyword.lower() if keyword else None
    features = []
    for feat in _DATA["features"]:
        props = feat["properties"]
        feat_group = _group_for(props["category"])

        if groups and feat_group not in groups:
            continue

        if lat is not None and lon is not None:
            flat, flon = _feature_center(feat)
            if flat is None:
                continue
            if _haversine_miles(lat, lon, flat, flon) > radius:
                continue

        if keyword:
            haystack = f"{props.get('name') or ''} {feat_group} {props['category']}".lower()
            if not all(word in haystack for word in keyword.split()):
                continue

        out_feat = dict(feat)
        out_feat["properties"] = dict(props)
        out_feat["properties"]["group"] = feat_group
        features.append(out_feat)

    return features


@app.route("/")
def index():
    return render_template("index.html", groups=VALID_GROUPS, using_sample=_USING_SAMPLE)


@app.route("/api/places")
def api_places():
    """
    Query params:
      group   - filter to one UI category group (e.g. "Basketball")
      lat,lon,radius - optional 'near me' filter (radius in miles)
    """
    group = request.args.get("group")
    lat = request.args.get("lat", type=float)
    lon = request.args.get("lon", type=float)
    radius = request.args.get("radius", type=float, default=5.0)

    groups = [group] if group and group != "All" else None
    features = _filter_features(groups=groups, lat=lat, lon=lon, radius=radius)

    return jsonify({"type": "FeatureCollection", "features": features})


def _keyword_response(query_text, notice=None):
    features = _filter_features(keyword=query_text)
    return jsonify(
        {
            "type": "FeatureCollection",
            "features": features,
            "mode": "keyword_fallback" if notice else "keyword",
            "interpreted": None,
            "notice": notice,
        }
    )


@app.route("/api/llm-providers.json")
def llm_providers_json():
    """Providers with a key configured, for the search bar's picker, plus
    'auto' (tries each configured provider in turn, free ones first, see
    llm_providers.py) and an always-available 'keyword' option to search
    without AI at all."""
    configured = available_providers()
    options = []
    if configured:
        options.append({"id": "auto", "label": "Auto (tries available AI)"})
    options += [{"id": p, "label": PROVIDER_LABELS[p]} for p in configured]
    options.append({"id": "keyword", "label": "Keyword search (no AI)"})
    return jsonify(options)


@app.route("/api/search")
def api_search():
    """
    Natural-language search: ?q=somewhere quiet to play basketball near downtown
    &provider= one of PROVIDER_LABELS' keys, "auto" to chain through every
    configured provider, or "keyword" to skip AI entirely.

    "auto" (or no provider at all) tries each configured LLM provider in
    turn, free ones first, until one parses the query into category groups
    + an optional landmark/radius (see llm_providers.extract_structured). A
    specific provider is tried alone, so a deliberate choice from the
    picker is respected even if it fails. Either way, if AI parsing doesn't
    work out (unconfigured, rate limited, bad key, every provider timing
    out) this falls back to plain keyword matching over each spot's name/
    category rather than erroring, so the search bar always returns
    something.
    """
    query_text = request.args.get("q", "").strip()
    if not query_text:
        return jsonify({"error": "q is required"}), 400

    provider = request.args.get("provider") or None
    if provider == "auto":
        provider = None

    if provider == "keyword" or not available_providers():
        return _keyword_response(query_text)

    try:
        parsed = parse_nl_query(query_text, VALID_GROUPS, provider=provider)
    except LLMConfigError as ex:
        return _keyword_response(query_text, notice=f"{ex} Showing keyword matches instead.")
    except Exception as ex:
        status = extraction_failure_status(ex)
        notice = (
            f"AI provider rejected the request (HTTP {status}). Showing keyword matches instead."
            if status is not None
            else "AI search failed. Showing keyword matches instead."
        )
        return _keyword_response(query_text, notice=notice)

    features = _filter_features(
        groups=parsed["groups"] or None,
        lat=parsed["lat"],
        lon=parsed["lon"],
        radius=parsed["radius"],
    )

    return jsonify(
        {
            "type": "FeatureCollection",
            "features": features,
            "mode": "llm",
            "interpreted": parsed,
            "notice": None,
        }
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
