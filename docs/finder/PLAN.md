# Policy & Grant Finder — Implementation Plan

**Branch:** `claude/policy-grant-finder-l84zm2` ("policy and grant finder")
**Goal:** A keyword-driven finder for EU policies and Horizon Europe grants that
runs **directly from GitHub Pages** — no installation, no server, no build step.
It will live at:

> https://tobi-wan-kenob1.github.io/GreenInformationFactory_Prototype/finder/

## 1. Requirements (from the task description)

1. **Enter keywords** in a web UI.
2. **Search** EU policies (EUR-Lex) and EU Horizon grants (Funding & Tenders
   portal) matching the keywords.
3. **Analyse** all matched documents: which keywords/topics appear most often
   across the policy corpus and the grant corpus.
4. **Select topics and build scenarios** that combine policies and grants under
   specific topics.
5. **Analyse scenario metrics**: CO2 mitigation potential and potential funding
   per scenario.

Hard constraint: the finder must work from a plain GitHub Pages URL.

## 2. Architecture

A single static web app in `docs/finder/` (vanilla HTML + JS + CSS, same
zero-dependency style as the existing `docs/index.html` tour — GitHub Pages
serves `docs/` already, so nothing changes in repo configuration).

### Data access — two tiers

| Tier | Source | How |
|------|--------|-----|
| **Live** (primary) | SEDIA Search API (`api.tech.ec.europa.eu/search-api/…?apiKey=SEDIA`) for Horizon Europe calls/topics; EUR-Lex via the Publications Office CELLAR SPARQL endpoint (`publications.europa.eu/webapi/rdf/sparql`) for policies | `fetch()` directly from the browser |
| **Snapshot** (fallback) | Same sources, fetched by a scheduled **GitHub Action** (`finder-data.yml`) into compact JSON files under `docs/finder/data/` | The app loads the JSON when live calls fail (CORS, downtime, rate limits) or when the user picks "offline/cached mode" |

Rationale: both EU endpoints are public, but their CORS behavior is not
guaranteed and cannot be verified from this development sandbox (its network
policy blocks EU hosts — GitHub Actions runners and end-user browsers are not
affected). The snapshot tier guarantees the Pages app **always** works; the
live tier keeps results fresh when the APIs cooperate.

The snapshot fetcher is a small Python module (`src/gif/finder_data.py`) so it
follows the repo's existing `gif` package conventions and is unit-testable.

### Analysis — all client-side

- Tokenization of titles/abstracts/objectives, English stopword list,
  document-frequency + TF-IDF scoring, keyword co-occurrence.
- Aggregated separately for **policies** vs **grants**, then intersected to
  surface topics that bridge both.
- Charts drawn with inline SVG (no CDN dependency) matching the BioFairNet
  visual identity used in the tour pages.

### Scenarios & metrics

- User selects top topics → app proposes policy+grant bundles per topic →
  user composes named scenarios (multi-select of policies and grants).
- **Potential funding** = aggregated from the grant records' budget fields
  (SEDIA metadata: call budget / contribution ranges).
- **CO2 mitigation potential** = transparent assumption-based scoring, in the
  spirit of `metadata/sustainability_assumptions_v1.json`: a JSON file
  (`docs/finder/data/co2_assumptions.json`) mapping topics/keywords to
  mitigation-potential factors with documented sources. No EU API provides CO2
  numbers per policy/grant, so this is an explicit, editable heuristic — shown
  as such in the UI.
- Scenario comparison view: table + bar charts (funding vs CO2 score),
  export as CSV/JSON download.

## 3. Execution steps

Each step is a self-contained commit on this branch, testable from the Pages
URL (or locally by opening the HTML file).

- [x] **Step 1 — UI skeleton** (`docs/finder/index.html`): keyword input,
      five-stage layout (Keywords → Search → Topic analysis → Scenarios →
      Metrics), BioFairNet branding, link from the main tour page + README.
- [x] **Step 2 — Search integration**: SEDIA grant search + EUR-Lex SPARQL
      policy search from the browser, with graceful fallback to bundled
      sample data; result cards with title, type, date, budget, link.
- [x] **Step 3 — Snapshot pipeline**: `gif finder-data` fetcher + GitHub
      Action (scheduled + manual) writing `docs/finder/data/*.json`; app
      auto-fallback wiring; tests for the fetcher's parsing.
- [x] **Step 4 — Topic analytics**: client-side TF-IDF / frequency /
      co-occurrence across all matched documents, per-corpus and combined
      top-topic charts.
- [x] **Step 5 — Scenario builder**: topic selection, policy+grant bundling,
      named scenarios, persistence in `localStorage`.
- [x] **Step 6 — Metrics & comparison**: funding aggregation, CO2 assumption
      file + scoring, scenario comparison view, CSV/JSON export.
- [x] **Step 7 — Polish & docs**: README section, how-to entry, accessibility
      pass, CI green.

## 4. Risks & mitigations

- **CORS blocked on live APIs** → snapshot tier is the guaranteed path; live
  tier is progressive enhancement.
- **Sandbox cannot reach EU hosts during development** → develop against
  recorded sample fixtures; the GitHub Action (full internet) and the user's
  browser do the real fetching; verify live behavior from the Pages URL after
  each push.
- **EUR-Lex volume** → constrain SPARQL queries by date range, document type
  (regulations/directives/communications) and keyword match; page results.
- **CO2 metric credibility** → keep it assumption-based, visible, and
  editable; label it "indicative potential", never a measured value.
