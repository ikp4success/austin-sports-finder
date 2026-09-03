# AUSTIN PICKUP

[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![isort](https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336)](https://github.com/timothycrosley/isort)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/)
[![AI-powered search](https://img.shields.io/badge/search-AI--powered-6366f1.svg)](docs/architecture.md)
[![Built with Claude Code](https://img.shields.io/badge/Built%20with-Claude%20Code-D97757.svg)](https://claude.com/claude-code)

**About**

A map that answers "where do people actually go to play basketball, throw a frisbee, or walk a dog around here." Built on Overture Maps data for anyone new to Austin who doesn't yet have that local knowledge, with a natural-language search bar that an LLM (Gemini, Groq, Mistral, Anthropic, or OpenAI, whichever the server has a key for) turns into map filters.

**Screenshots**

| Map | List |
|---|---|
| ![Map view of central Austin with sport/rec spots plotted](docs/screenshots/map-view.png) | ![List view of the same spots as cards](docs/screenshots/list-view.png) |

Natural-language search, parsed by AI into the same category/location filters used by the sidebar:

![Search for "somewhere quiet to play basketball near downtown", showing it understood as Basketball near downtown within 2 miles](docs/screenshots/search-ai.png)

## Why this idea

Commercial-venue apps (Yelp, Google) are built around businesses, so free public infrastructure (a park's basketball hoops, an unnamed green space with a soccer pitch, a neighborhood dog park) is often missing, buried, or miscategorized. That's exactly the kind of data Overture actually has (Places and the Land Use/Base theme), and exactly the gap a newcomer to a city feels most: not "what restaurant should I try," but "is there anywhere nearby I can just go play."

I picked Austin because I know it well enough to sanity-check whether the output actually looks right. A park that's missing, or a court mislabeled as something else, is obvious to me here in a way it wouldn't be in a city I don't know.

## What it does

- A single map of central Austin, filterable by activity (basketball, tennis, soccer/fields, dog parks, skate parks, disc golf, pickleball, trails, swimming, playgrounds, general parks, and a few more)
- "Use my location" for a real near-me radius search, not just a static city-wide view
- A natural-language search bar ("somewhere quiet to play basketball near downtown") parsed by an LLM into the same category/location filters, see [Settings](#settings) below
- A map/list toggle, so results can be browsed as cards instead of pins
- Every result shows what Overture actually knows about that spot. When the data is thin (no address, no phone, just a shape with a name or no name at all), the UI says so explicitly instead of hiding the result or pretending the field exists

## The key trade-off, and why it's the interesting part

Overture's sport/rec data is genuinely uneven: some courts and fields exist as clean `place` points with a name and category, while a lot of others only exist as an unlabeled `land_use` polygon (a shape tagged "recreation" or "park" with no name, no attributes). A version of this app that only used clean Places data would look nicer in a demo but would silently miss a large share of real, usable spots, including some of the most obvious ones in Austin.

I chose to surface both, Places and Land Use polygons, and to be honest in the UI when a result is thin ("Limited details available for this spot") rather than dropping it or faking detail it doesn't have. That felt like the more honest product decision, even though it means some pins on the map have almost no information behind them.

The same judgment call showed up again with pickleball: Overture has no dedicated category for it at all, real pickleball venues turn up with no category or a vague generic one. Rather than let the search bar silently shrug at "pickleball," the extraction script now catches those by name and re-tags them, while still excluding the pickleball gear store that would otherwise slip in under the same name.

## What I deliberately cut

- **One city, one small bounding box** (central Austin), not a multi-city or nationwide tool. Keeps the extracted file small and lets me actually verify the data is right.
- **No live status.** No "open now," no real-time crowding. Overture is a static snapshot, and I didn't want to fake liveness the data can't back up.
- **No accounts, no saved favorites, no reviews.** This is a discovery tool, not a social app.
- **Polygon "center" for radius search is a bounding-box midpoint,** not a true geometric centroid or nearest-edge distance. Accurate enough for "is this roughly nearby," not for precise routing.

## How it's built

- **Data pipeline** (`scripts/`): a one-time extraction (`01_download_raw.sh`, using the `overturemaps` CLI) pulls Places and Land Use for the Austin bounding box. `02_filter_and_build.py` filters that down to sport/recreation features and writes one small `data/austin_sports.geojson`, the only file the running app depends on, matching the spirit of Overture's own example ("43k places, extracted once, shipped as one small file").
- **Backend**: Flask, loads that one GeoJSON file into memory, serves it through `/api/places` with optional category and near-me filtering.
- **Frontend**: Leaflet (no API key required, unlike Mapbox/Google) plus vanilla JS, server-rendered filter buttons from the same category set the backend uses.
- **Search** (`llm_providers.py`, `nl_search.py`): `/api/search` parses a free-text query into structured filters via whichever LLM provider is selected, five supported (Groq, Mistral, Gemini, Anthropic, OpenAI), not locked to one vendor. Left on "Auto," it chains through every configured provider, free ones first, before falling back to keyword matching over each spot's name/category.

See [docs/architecture.md](docs/architecture.md) for diagrams of both the offline data pipeline and the live request flow, including how the search fallback branches.

### Setup

```bash
$ make setup   # venv, deps, a .env copied from the template, pre-commit hooks
$ make run
```

Or by hand:

```bash
$ python3 -m venv .venv
$ .venv/bin/pip install -r requirements.txt

# One-time data extraction (needs network access to Overture's data host).
# overturemaps pulls in pyarrow/numpy (about 230MB) that the running app
# never needs, so it's kept out of requirements.txt and lives here instead:
$ .venv/bin/pip install -r requirements-dev.txt
$ bash scripts/01_download_raw.sh
$ .venv/bin/python scripts/02_filter_and_build.py

$ .venv/bin/python app.py
```

If you skip the extraction step, the app falls back to `data/austin_sports.sample.geojson`, a small hand-built sample in the same schema, so it's runnable end-to-end without a live download.

### Pre-commit

[pre-commit](https://pre-commit.com/) runs black, isort, and flake8 automatically before each commit, installed by `make setup`.

```bash
$ make lint     # flake8 + black --check + isort --check-only
$ make format   # black + isort, applied
```

#### Settings

- Copy `.env.example` to `.env` and set at least one of `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` to enable natural-language search. Without any, search still works via plain keyword matching.
- Gemini, Groq, and Mistral all have a genuine standing free tier (rate-limited, not a one-time trial credit); Anthropic and OpenAI don't.
- With more than one key set, the search bar's provider picker defaults to **Auto**, which tries each configured provider in turn, free ones first, so one provider having a bad day doesn't take the feature down when another key would work. Picking a specific provider from that same dropdown searches with only that one.
- `LLM_PROVIDER` overrides which provider "Auto" (and the server default) resolves to.
- `.env` is git-ignored to protect sensitive keys, never commit it.

##### deploys

The repository includes a Render Blueprint (`render.yaml`) for the free tier. Push the repository, choose **New > Blueprint** in Render, and select it. Render reads `render.yaml`, runs `pip install -r requirements.txt`, and starts `gunicorn app:app`. Make sure `data/austin_sports.geojson` (the real extracted file, not just the sample) is committed before deploying.

The LLM API keys are optional. Add any of `GEMINI_API_KEY`, `GROQ_API_KEY`, `MISTRAL_API_KEY`, `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` from the service's **Environment** page. `render.yaml` declares them with `sync: false` so Render prompts for each value there instead of expecting it in the repo.

**Author**

* [***Immanuel George***](https://www.linkedin.com/in/imgeorgeresume/)
