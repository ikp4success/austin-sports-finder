"""
Turns a free-text search ("somewhere quiet to play basketball near
downtown") into structured filters against the app's existing category
groups and haversine radius search, see app.py's /api/search.

A small, fixed landmark table stands in for real geocoding: the app only
covers one bounding box (central Austin), so resolving "downtown" or
"zilker" to a lat/lon is enough without pulling in a geocoding service or
API key. It intentionally only recognizes the same well-known-to-locals
areas already cited in this project's own product write-up.
"""

from llm_providers import extract_structured

LANDMARKS = {
    "downtown": (30.2672, -97.7431),
    "university of texas": (30.2849, -97.7341),
    "zilker": (30.2669, -97.7734),
    "south congress": (30.2500, -97.7500),
    "hyde park": (30.3070, -97.7280),
    "east austin": (30.2650, -97.7150),
    "travis heights": (30.2480, -97.7430),
    "barton springs": (30.2639, -97.7712),
    "mueller": (30.2989, -97.7050),
    "south lamar": (30.2550, -97.7650),
}

DEFAULT_RADIUS_MILES = 2


def _schema(valid_groups):
    return {
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "items": {"type": "string", "enum": valid_groups},
                "description": (
                    "Activity/category groups the user is asking about. "
                    "Empty array if the request isn't about a specific activity."
                ),
            },
            "landmark": {
                "type": ["string", "null"],
                "enum": [*LANDMARKS.keys(), None],
                "description": (
                    "The single closest-matching landmark from the list if the "
                    "user named a location, else null. Do not guess one that "
                    "isn't a clear match."
                ),
            },
            "radius_miles": {
                "type": "number",
                "description": (
                    f"Search radius in miles around the landmark. Use "
                    f"{DEFAULT_RADIUS_MILES} when a landmark is given but no "
                    "distance is stated. Ignored if landmark is null."
                ),
            },
        },
        "required": ["groups", "landmark", "radius_miles"],
        "additionalProperties": False,
    }


def parse_nl_query(query_text, valid_groups, provider=None):
    system = (
        "You convert a free-text request into search filters for a map of "
        "free/public sport and recreation spots in Austin, Texas. Valid "
        f"category groups are: {', '.join(valid_groups)}. Use only names "
        "from that exact list, and leave groups empty if the request "
        "doesn't name a specific activity. Valid landmarks are: "
        f"{', '.join(LANDMARKS)}. Only set one if the user's wording "
        "clearly matches it, otherwise use null."
    )
    parsed = extract_structured(
        system=system,
        user_message=query_text,
        schema=_schema(valid_groups),
        provider=provider,
    )

    groups = [g for g in (parsed.get("groups") or []) if g in valid_groups]
    landmark = parsed.get("landmark")
    lat = lon = None
    if landmark in LANDMARKS:
        lat, lon = LANDMARKS[landmark]
    radius = parsed.get("radius_miles") or DEFAULT_RADIUS_MILES

    return {
        "groups": groups,
        "landmark": landmark if landmark in LANDMARKS else None,
        "lat": lat,
        "lon": lon,
        "radius": radius,
    }
