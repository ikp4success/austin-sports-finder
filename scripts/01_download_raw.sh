#!/usr/bin/env bash
set -euo pipefail

# Downloads raw Overture Places and Land Use data for the central-Austin
# bounding box this app covers. Requires `pip install overturemaps` and
# network access to Overture's S3/STAC host.
#
# Output: data/raw/place.geojson, data/raw/land_use.geojson
# (large, gitignored — scripts/02_filter_and_build.py reduces these to the
# one small file the app actually ships: data/austin_sports.geojson)

BBOX="-97.85,30.20,-97.65,30.35"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="$SCRIPT_DIR/../data/raw"
mkdir -p "$OUT_DIR"

echo "Downloading Overture Places for bbox $BBOX ..."
overturemaps download --bbox="$BBOX" -f geojson -t place -o "$OUT_DIR/place.geojson"

echo "Downloading Overture Land Use for bbox $BBOX ..."
overturemaps download --bbox="$BBOX" -f geojson -t land_use -o "$OUT_DIR/land_use.geojson"

echo "Done. Raw files in $OUT_DIR"
