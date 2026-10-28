# advibe frontend

React and TypeScript workspace for the Qloo campaign harness.

## Run locally

Start the backend from the repository root:

```sh
advibe-backend/.venv/bin/python advibe-backend/stream_harness.py --serve
```

Configure the backend's Qloo and LLM credentials in its existing `.env` file.
Secrets stay on the backend.

In a second terminal:

```sh
cd advibe-frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173.
Vite forwards `/api` requests to the backend on port 8000.

## Verify

```sh
npm run build
npm run lint
npm test
```

Enter an incomplete brief such as `I have a brand called Chaen - it's a matcha energy drink`, select two cultural seeds, a competitor, and a location, then choose **Continue with signals**.
Review the curated prompt and choose **Start Session**.
Map and audience artifacts appear when their stream patches arrive.
Select tribes and choose Sales or Traffic to generate creative bundles and stage a Meta campaign locally.
Editing the curated prompt directly starts fresh signal resolution.
Changing signals conversationally runs another Ask turn.

The entry carousel includes Chaen, Humo Santo, Nocturne Botanica, Vespera, and Salina Club.
Use the next and previous arrows, swipe, or tab through the presets to browse.
Hover or keyboard focus previews the exact preset prompt beneath the carousel; Escape dismisses it.
Clicking a preset starts Ask directly.

## Map configuration

The map uses CARTO's Voyager raster tiles over OpenStreetMap data.
Create `advibe-frontend/.env` with your CARTO Basemaps key:

```dotenv
VITE_CARTO_API_KEY=your_carto_basemaps_key
```

Restart the Vite dev server after changing this file.
For production, set the variable before running `npm run build` and rebuild when it changes.
The `.env` file is ignored by Git, but this browser-facing key is included in tile requests and the frontend build.
Use CARTO's website restrictions for your deployed domain.
No actual key belongs in source files or documentation.

Without a key, the map displays a configuration message and keeps campaign pins and venue cards available.
OpenStreetMap and CARTO attribution remains visible when basemap tiles are enabled.

No proprietary font file is included; typography uses the design's system fallback until nbInternationalPro is installed or supplied.

## Multiple target cities

Ask can add, remove, or replace cities conversationally.
For example, start with New York and send `add SF and London` to retain New York and add San Francisco and London.
Ask explains the default of three shared tribes across all selected cities and offers **3 total** or **3 per city**.
Each shared tribe contains expandable localized prompts, Qloo signals, and PAUSED Meta specifications for every city.
Choosing three per city instead produces independent, separately selectable campaigns.
Map and Audience tabs include city selectors and hydrate while each city is grounded.
Failed cities are identified in the session error while completed artifacts remain available.

The backend keeps the legacy scalar `location_query` as the first city for existing callers.
New Ask states and resolved signals also carry an ordered `locations` array with per-city neighborhood hints and `tribe_scope` (`overall` or `per_location`).
City-specific stream events carry `location_id` and `location_query`; the frontend stores these artifacts separately from campaign-wide artifacts.
The final output includes `city_outputs`, indexed by location ID, alongside the campaign-wide strategies.
Shared strategies carry `location_variants` with a local strategy, packet, and location identifiers for each city.
Independent strategies use city-qualified IDs so selections cannot collide across cities.
For compatibility, top-level demographic and taste fields retain the first city's values; city-specific consumers should use the city artifacts or `city_outputs`.
Edited briefs use fresh extraction and pass location/scope metadata through the grounding endpoint.

## Trend history

Trending uses the backend's configured Qloo host and credentials, including the hackathon host.
It tries up to two supported selected seeds, followed by up to two artists whose Qloo explainability links back to a selected seed.
Competitors are not substituted for campaign references.
Each entity gets a recent 28-day request and, only after an empty successful response, a broader history request.
The broader start defaults to `2020-01-01` and can be changed with `QLOO_TRENDING_HISTORY_START_DATE` in the backend environment.
It must precede the recent window.
This broader request is a workaround for observed hackathon date-window behavior.

The separate `trending` artifact streams independently of `audience_insights` and is also retained in the completed audience payload.
It records HTTP outcomes, entity provenance, requested and returned dates, missing values, and metrics on Qloo's reported scale.
Identical requests are cached within a session across cities; trend measurements are global.
Each attempt carries a unique `call_id` so retries and cache hits remain distinguishable in telemetry.
Optional trend failures do not interrupt campaign generation.

## Creative development and local Meta staging

Choose tribes, a campaign objective, draft currency, and daily budget per ad set in the Tribe Campaigns tab.
The displayed total includes every selected city variant.
**Generate Ad Creatives & Stage Meta Campaign** streams editorial feed concepts, three Qloo-linked hooks, a three-beat reel storyboard, and proposed local OOH direction into Ad Creatives.
No image or video generation service is called.
The original cultural grounding remains available in its existing tabs.

The backend validates word counts, packet entity IDs and names, assigned venues, reel timing, and palette contrast.
It attempts one semantic repair for invalid creative output.
Completed variants survive partial failure; retry reuses them only when grounding, selection, and settings match the original snapshot.
Every selected variant must pass before Meta assembly.

`POST /api/session/creatives` and `POST /api/session/creatives/stream` accept `grounding`, optional `selected_strategy_ids`, required `campaign_settings`, and optional `previous_result` for retries.
Settings include `objective` (`OUTCOME_SALES` or `OUTCOME_TRAFFIC`), `currency` (`USD`, `GBP`, or `EUR`), and positive integer `daily_budget_cents_per_adset` (default `5000`, in currency minor units).
Omitted selections generate all tribes; an empty selection is rejected.
Shared tribes expand into localized variants while keeping their parent selection and stable city-qualified IDs.

Meta Campaign (Staged) shows one campaign and one ad set, draft creative, and ad per city variant.
Campaign, ad-set, and ad request templates specify PAUSED; creative assets are drafts and have no unsupported PAUSED field.
Sales requests purchase conversion settings and a future pixel; Traffic requests link clicks.
Geographic overlap is reported when planned circles intersect.
Audience and geofence settings remain request templates subject to future Meta account and API validation.

This version never calls Meta or reads Meta credentials, even when credentials exist in the environment.
Live deployment, asset upload, and monitoring are deferred.
The cURL inspector is a commented review template with unresolved account, Page, asset, destination, and API-version placeholders.
Simulated landing pages use the reserved `.example` domain.
Performance metrics are proposed measurement plans with no invented targets or measured results.
Available history does not establish positive momentum, and zero movement is displayed explicitly.
