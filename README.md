# Austin Pickup

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)

**One-sentence pitch:** a map that answers "where do people actually go to play basketball, throw a frisbee, or walk a dog around here." Built for anyone new to Austin who doesn't yet have that local knowledge.

## Screenshots

| Map | List |
|---|---|
| ![Map view of central Austin with sport/rec spots plotted](docs/screenshots/map-view.png) | ![List view of the same spots as cards](docs/screenshots/list-view.png) |

**Natural-language search**, parsed by AI into the same category/location filters used by the sidebar:

![Search for "somewhere quiet to play basketball near downtown", showing it understood as Basketball near downtown within 2 miles](docs/screenshots/search-ai.png)

## Why this idea

Commercial-venue apps (Yelp, Google) are built around businesses, so free public infrastructure (a park's basketball hoops, an unnamed green space with a soccer pitch, a neighborhood dog park) is often missing, buried, or miscategorized. That's exactly the kind of data Overture actually has (Places and the Land Use/Base theme), and exactly the gap a newcomer to a city feels most: not "what restaurant should I try," but "is there anywhere nearby I can just go play."

I picked Austin because I know it well enough to sanity-check whether the output actually looks right. A park that's missing, or a court mislabeled as something else, is obvious to me here in a way it wouldn't be in a city I don't know.

## What it does

- A single map of central Austin, filterable by activity (basketball, tennis, soccer/fields, dog parks, skate parks, disc golf, trails, swimming, playgrounds, general parks, and a few more)
- "Use my location" for a real near-me radius search, not just a static city-wide view
- A natural-language search bar ("somewhere quiet to play basketball near downtown") parsed by an LLM into the same category/location filters. A provider picker shows which AI keys are configured and lets you choose one, or search by plain keyword instead. Any AI failure falls back to keyword search automatically rather than erroring out. See [API keys](#api-keys-optional-natural-language-search) below.
- A map/list toggle, so results can be browsed as cards instead of pins
- Every result shows what Overture actually knows about that spot. When the data is thin (no address, no phone, just a shape with a name or no name at all), the UI says so explicitly instead of hiding the result or pretending the field exists

## The key trade-off, and why it's the interesting part

Overture's sport/rec data is genuinely uneven: some courts and fields exist as clean `place` points with a name and category, while a lot of others only exist as an unlabeled `land_use` polygon (a shape tagged "recreation" or "park" with no name, no attributes). A version of this app that only used clean Places data would look nicer in a demo but would silently miss a large share of real, usable spots, including some of the most obvious ones in Austin.

I chose to surface both, Places and Land Use polygons, and to be honest in the UI when a result is thin ("Limited details available for this spot") rather than dropping it or faking detail it doesn't have. That felt like the more honest product decision, even though it means some pins on the map have almost no information behind them.

## What I deliberately cut

- **One city, one small bounding box** (central Austin), not a multi-city or nationwide tool. Keeps the extracted file small and lets me actually verify the data is right.
- **No live status.** No "open now," no real-time crowding. Overture is a static snapshot, and I didn't want to fake liveness the data can't back up.
- **No accounts, no saved favorites, no reviews.** This is a discovery tool, not a social app.
- **Polygon "center" for radius search is a bounding-box midpoint,** not a true geometric centroid or nearest-edge distance. Accurate enough for "is this roughly nearby," not for precise routing.

## How it's built

- **Data pipeline** (`scripts/`): a one-time extraction (`01_download_raw.sh`, using the `overturemaps` CLI) pulls Places and Land Use for the Austin bounding box. `02_filter_and_build.py` filters that down to sport/recreation features and writes one small `data/austin_sports.geojson`, the only file the running app depends on, matching the spirit of Overture's own example ("43k places, extracted once, shipped as one small file").
- **Backend**: Flask, loads that one GeoJSON file into memory, serves it through `/api/places` with optional category and near-me filtering.
- **Frontend**: Leaflet (no API key required, unlike Mapbox/Google) plus vanilla JS, server-rendered filter buttons from the same category set the backend uses.
- **Search** (`llm_providers.py`, `nl_search.py`): `/api/search` parses a free-text query into structured filters via whichever LLM provider is selected, five supported (Gemini, Groq, Mistral, Anthropic, OpenAI), auto-detected from `.env`, not locked to one vendor. Left on "Auto," it chains through every configured provider, free ones first, before falling back to keyword matching over each spot's name/category.

See [docs/architecture.md](docs/architecture.md) for diagrams of both the offline data pipeline and the live request flow, including how the search fallback branches.

## Running it locally

Fast path, using the included [Makefile](Makefile):

```bash
make setup   # venv, deps, a .env copied from the template, pre-commit hooks
make run
```

Or by hand:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# One-time data extraction (needs network access to Overture's data host).
# overturemaps pulls in pyarrow/numpy (about 230MB) that the running app
# never needs, so it's kept out of requirements.txt and lives here instead:
.venv/bin/pip install -r requirements-dev.txt
bash scripts/01_download_raw.sh
.venv/bin/python scripts/02_filter_and_build.py

# Run the app
.venv/bin/python app.py
```

If you skip the extraction step, the app falls back to `data/austin_sports.sample.geojson`, a small hand-built sample in the same schema, so it's runnable end-to-end without a live download.

### API keys (optional, natural-language search)

The search bar works with zero setup, via plain keyword matching. To enable the LLM-parsed version, copy `.env.example` to `.env` and set **one or more** keys:

```bash
cp .env.example .env
# then edit .env and uncomment/fill in any of:
#   GEMINI_API_KEY=...
#   GROQ_API_KEY=gsk_...
#   MISTRAL_API_KEY=...
#   ANTHROPIC_API_KEY=sk-ant-...
#   OPENAI_API_KEY=sk-...
```

Gemini, Groq, and Mistral all have a genuine standing free tier (rate-limited, not a one-time trial credit); Anthropic and OpenAI don't. `app.py` loads `.env` automatically (via `python-dotenv`). With more than one key set, the search bar's provider picker defaults to **Auto**, which tries each configured provider in turn, free ones first, so one provider having a bad day (a 503, an outage) doesn't take the feature down when another key would work; picking a specific provider from that same dropdown searches with only that one. `LLM_PROVIDER` overrides which provider "Auto" (and the server default) resolves to. `.env` is gitignored and should never be committed.

## Deploying (Render, free tier)

This repo includes `render.yaml`. Connect the repo in Render, and it will use `pip install -r requirements.txt` to build and `gunicorn app:app` to run. Make sure `data/austin_sports.geojson` (the real extracted file, not just the sample) is committed before deploying.

To enable natural-language search on the deployed app, set any of `GEMINI_API_KEY` / `GROQ_API_KEY` / `MISTRAL_API_KEY` / `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` in Render's dashboard, under the service's **Environment** tab. `render.yaml` declares them with `sync: false`, so Render prompts for each value there instead of expecting it in the repo. This is optional; the deployed app works without any of them.

## Development

```bash
make lint     # flake8 + black --check + isort --check-only
make format   # black + isort, applied
```

Pre-commit hooks (installed by `make setup`) run the same checks automatically before each commit. See `.pre-commit-config.yaml`.

## What I'd do next with more time

- Extend the bounding box to cover greater Austin, not just the central core
- A real point-in-polygon / nearest-edge distance for polygon features, instead of a bbox midpoint
- Cross-reference Buildings to flag indoor vs. outdoor facilities explicitly
- A "report an issue" affordance, since Overture data will sometimes just be wrong. Better to give users a way to flag it than to imply it's authoritative.
- Deduplicate near-identical Places results. The same park can show up several times under slightly different names in crowd-sourced data.

**Author**

* [***Immanuel George***](https://www.linkedin.com/in/imgeorgeresume/)
