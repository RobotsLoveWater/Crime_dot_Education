# Vendored assets — pinned versions

Never hand-edit the files in this directory. To upgrade, download the exact release
artifact, replace the file, and update this manifest in the same commit.

| File | Library | Version | Source |
|---|---|---|---|
| `htmx.min.js` | htmx | 2.0.10 | https://cdn.jsdelivr.net/npm/htmx.org@2.0.10/dist/htmx.min.js |
| `chart.umd.min.js` | Chart.js | 4.5.1 | https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js |
| `chartjs-chart-treemap.min.js` | chartjs-chart-treemap | 3.1.0 | https://cdn.jsdelivr.net/npm/chartjs-chart-treemap@3.1.0/dist/chartjs-chart-treemap.min.js |
| `chartjs-chart-geo.min.js` | chartjs-chart-geo | 4.3.6 | https://cdn.jsdelivr.net/npm/chartjs-chart-geo@4.3.6/build/index.umd.min.js |

`chartjs-chart-treemap` is a Chart.js 4 plugin (the Visualize **treemap**, `VISUALIZATION_EXPANSION.md`
Phase 5). Its UMD build auto-registers `TreemapController`/`TreemapElement` when loaded **after**
`chart.umd.min.js`, so it is included only in `visualize.html`'s `{% block head %}` — never globally.

`chartjs-chart-geo` is the Chart.js 4 plugin for the Visualize **choropleth**
(`VISUALIZATION_EXPANSION.md` §6.4 / _PROMPTS.md Phases 7–11). Its UMD build exposes the `ChartGeo`
global (`ChoroplethController`, `ProjectionScale`, `ColorScale`, `GeoFeature`, plus a bundled
`ChartGeo.topojson` for feature conversion) and does **not** self-register — the Visualize JS calls
`Chart.register(...)` explicitly. Loaded only on the Visualize view (vendored in Phase 7; wired into
the map render in Phase 8), after `chart.umd.min.js`.

Related (outside this directory):

| File | Asset | Version | Source |
|---|---|---|---|
| `static/fonts/InterVariable.woff2` | Inter variable font (OFL) | 4.1 | https://rsms.me/inter/font-files/InterVariable.woff2 (release: https://github.com/rsms/inter/releases/tag/v4.1) |
| `static/geo/mn-counties-topo.json` | MN counties TopoJSON (derived) | us-atlas 3 | https://cdn.jsdelivr.net/npm/us-atlas@3/counties-10m.json (extracted) |

**`static/geo/mn-counties-topo.json` is a *derived* asset, not a straight download.** It is the 87
Minnesota county features (FIPS `27xxx`) extracted from `us-atlas@3/counties-10m.json` (public
domain, US Census cartographic boundaries) into a standalone TopoJSON: the county geometries are
kept, their arcs pruned/reindexed to just those MN needs (9,869 US arcs → 288), the quantization
`transform` preserved, and the `bbox` recomputed to Minnesota. Each feature keeps its Census `id`
(FIPS) and `properties.name` (e.g. `"Le Sueur"`, `"Lac qui Parle"`, `"St. Louis"`). To regenerate:
download the us-atlas file, filter `objects.counties.geometries` to `id` starting `"27"`, prune the
`arcs` array to the referenced arcs (remapping indices, negatives as `~i`), and keep `transform`.
`geo.py` reconciles the dataset's county spellings to these feature names; `app.py` asserts all 87
join at startup.
