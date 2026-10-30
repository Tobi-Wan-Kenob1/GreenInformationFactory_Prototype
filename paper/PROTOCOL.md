# Validation study — protocol

**Status:** draft for co-author review · **Version:** 0.1 · **Date:** 2026-10-30
**Branch:** `claude/validation-paper` · **Tool under study:** Policy & Grant Finder
(`docs/finder/`), part of the GreenInformationFactory prototype
**Pre-registration:** not yet filed. Nothing in §6 (outcome data) may be
retrieved before §8 is filed and this file is tagged. See §8.

---

## 1. Purpose

The Policy & Grant Finder produces, from a keyword query, a ranked set of
topics bridging EU policy and EU research funding, plus scenarios combining
them and indicative metrics. The narrative and the method are in place; what
is missing is evidence that the tool's output has merit — that its rankings
carry signal rather than restating keyword frequency.

This protocol specifies how that is tested, what is deliberately **not**
claimed, and in what order the work happens so the result is credible rather
than merely favourable.

## 2. What is under test

The tool's claims, separated so each can be tested or explicitly set aside:

| # | Claim | Tested here |
|---|-------|-------------|
| C1 | Retrieval: returned documents are topically relevant to the query | Yes (§5.3) |
| C2 | Topic extraction: extracted topics match what domain sources treat as central | Yes (§5.3) |
| C3 | **Prospective signal: topics ranked highly at time *T* are disproportionately those that attracted policy and funding attention after *T*** | **Yes — the core test (§5.1)** |
| C4 | Gap detection: codes flagged as blind spots were genuinely under-addressed | Yes (§5.1, H4) |
| C5 | The CO₂ and cost-saving figures estimate real quantities | **No — see §9.1** |

C3 is the claim the tool actually makes, and the only one that supports a
merit argument. It is deliberately **not** a claim about firm performance: the
tool does not predict whether an organisation prospers, so testing it against
company trajectories would be a construct mismatch.

## 3. Research questions

- **RQ1** Does the tool's topic ranking, computed from a corpus frozen at *T*,
  predict where EU policy and funding subsequently went?
- **RQ2** Does the bridging construct (topics present in *both* the policy and
  the funding corpus) outperform single-corpus topics? This tests the tool's
  central conceptual move rather than the tool as a whole.
- **RQ3** Does the pipeline beat naive keyword frequency? If not, the analytics
  add nothing and the paper should say so.
- **RQ4** What did organisations that took up the highly-ranked topics actually
  do, and how did they fare? (Illustrative — see §5.2 and §9.2.)

## 4. Design in brief

Two tiers. The validation claim rests entirely on Tier A; Tier B is
illustrative and is labelled as such throughout the paper.

- **Tier A — back-test (quantitative).** Freeze the corpus at *T*, run the tool
  blind, record its ranked output, *then* measure subsequent uptake. Unit of
  analysis is the **topic** (expected n ≈ 50–150), not the organisation, which
  is where the statistical power comes from.
- **Tier B — case studies (qualitative).** From a complete register of
  organisations funded under the top-ranked topics, sample by a stated rule and
  trace what they did. Mechanism evidence, not validation evidence.

### 4.1 Two freeze points

| Arm | *T* | Input corpus at *T* | Outcome window |
|-----|-----|---------------------|----------------|
| **A1** | 2009-12-31 | EU policies ≤ 2009 (CELLAR reaches 2004; the current snapshot holds 50 pre-2010 acts) **plus** FP6 and FP7 projects started ≤ 2009 | 2010–2026 (FP7 remainder, H2020, Horizon Europe) |
| **A2** | 2013-12-31 | Policies ≤ 2013 **plus** FP6 and FP7 projects started ≤ 2013 | 2014–2026 (H2020, Horizon Europe) |

Two freeze points give an internal replication. A1 is the stronger test — a
sixteen-year outcome window against A2's thirteen — and A2 is nearly free once
the CORDIS adapter exists.

**A1 was specified as policy-only until WP0 corrected it.** The reasoning was
that the Funding & Tenders API indexes Horizon 2020 onward, so no pre-2010 call
topics are retrievable, and substituting CORDIS projects would leak (§4.2).
What that overlooked is that CORDIS publishes every framework programme back to
FP1: FP6 ran 2002–2006 and FP7 from 2007, so by the end of 2009 those awards
were long public. Projects already funded are legitimate available-at-*T*
information — exactly the "what is already being financed in this area"
signal the tool is meant to surface. A1 therefore runs on both corpora, which
removes the asymmetry between the arms and makes the replication a genuine one.
Running A1 policy-only as well is cheap and is retained as a robustness check,
reported alongside.

**What "the frozen corpus" means.** The corpus must not be defined by the study
queries, or query selection (§5.1 step 2) would be circular. It is instead
built from the **scope keywords already committed** in
`docs/finder/data/snapshot_config.json` — agriculture, mining, bioeconomy,
biomass, soil, circular economy, carbon farming, raw materials, land use, just
transition — which predate this study and define the tool's declared sector
scope, with the arm's upper date bound applied:

```bash
gif finder-data --since 1990-01-01 --until 2009-12-31 --out paper/data/frozen-A1
```

Query selection then measures document frequency *within* that fixed corpus,
and the selected queries are run against the same corpus. Corpus first,
queries second, outcomes last.

**Tooling defect that would breach this (found while drafting).** In
`gif finder-data`, `--since`/`--until` bound the **policy** fetch only;
`fetch_grants()` receives no date arguments. So the command above writes a
`grants.json` containing 2014+ call topics regardless of `--until`. The app is
unaffected (it filters by window client-side), but a frozen corpus directory
would contain post-*T* documents — leakage introduced by tooling rather than
design.

Two consequences:

- **WP1 must fix it** by bounding the grant fetch to the window inside
  `build_snapshot`, with tests. This also fixes the benchmark feature for
  ordinary users, whose historical snapshots currently carry an
  entirely out-of-window grants file.
- **Until it is fixed, WP2 must verify** each frozen corpus before use: assert
  that no document in `policies.json` or `grants.json` carries a date after the
  arm's *T*, and record the assertion output in §8. For A1 the SEDIA-sourced
  `grants.json` is expected to be **empty** after filtering, since that API
  indexes Horizon 2020 onward; A1's grant corpus comes from the CORDIS adapter
  instead, and is asserted against *T* the same way.

Note that tool fixes belong on `main`, not on this branch; this branch carries
the study, not the instrument.

### 4.2 Leakage — the trap to design out

It is tempting to feed CORDIS **projects** into the tool as the historical
"grant" corpus. That would invalidate the back-test: projects are awarded
*after* the call, so a corpus of projects started after *T* contains outcome
information the tool could not have had at *T*. The ranking would then partly
restate the answer.

The rule that follows is a single one, applied identically in both arms:

> A CORDIS project may enter the input corpus if and only if it **started on or
> before *T***. Projects starting after *T* are outcome data and are excluded
> from the input by the adapter, in code, not by hand.

**Why `startDate` and not the signature date.** The obvious field is
`ecSignatureDate` — a project is knowable once its grant agreement is signed —
and the column exists in both programmes' `project.csv`. WP0 measured it as
**0.0 % populated** in FP6 and FP7 alike (§6.1): present but empty, a trap that
would have turned the rule into a silent no-op had the adapter trusted the
column's existence. `startDate` is populated for 99.1 % of FP6 and 99.6 % of
FP7 projects and is strictly **conservative** for this purpose: signature
always precedes start, so a project starting on or before *T* was certainly
awarded by *T*, while a project signed before *T* but starting after it is
excluded. The filter can therefore drop information the tool could have had,
but it can never admit information the tool could not. Erring that way is the
correct direction for a back-test. Projects with no `startDate` at all —
0.9 % of FP6, 0.4 % of FP7 — are excluded, and the count is reported.

The leak the design must still avoid is the subtler one: measuring outcomes on
the same projects that were fed in. Outcome uptake is therefore computed
**only over projects starting after *T***, so the input and outcome sets are
disjoint by construction.

Note that `startDate` reaching 2018-06-18 in FP7 (§6.1) is not an anomaly —
late FP7 grants and extensions genuinely ran that long — and it means the
filter does real work rather than merely restating the programme's dates.

## 5. Methods

### 5.1 Tier A — back-test

**Query selection (pre-specified).** The ten query sets are derived by rule,
not chosen ad hoc, so that neither the tool's author nor the analyst picks
queries that flatter the result.

The codebook of the BioFairNet WP1/D1.2 literature review supplies the
candidate pool — it is machine-readable at
`docs/finder/data/wp1_codebook.json` and, importantly, was produced
independently of this tool. Its codes are ranked by the number of reviewed
papers in which they appear.

Ranking by paper count alone does not work, and this was tested during
drafting rather than discovered after freezing: the top codes are bare generic
words — `land` (99 papers), `water` (90), `demand` (43), `efficiency` (24) —
and a term like *water* matches EU acts across drinking water, bathing water,
maritime policy and much else. Nor can the query be narrowed by adding
`agriculture`/`mining` as anchors: the tool's multi-keyword semantics are a
**union**, so extra keywords widen the corpus rather than focus it.

The rule is therefore:

1. Take every code in the barriers and drivers dimensions of the codebook.
2. Compute each code's document frequency in the **frozen input corpus** for
   that arm (defined in §4.1 — built from the committed scope keywords, not
   from these codes). Discard any code matching more than **20 %** of the
   corpus — a term that broad is not a topic. This filter uses input data
   only, so it introduces no leakage.
3. Of those remaining, take the **ten with the highest codebook paper count**.
   Each becomes a single-keyword query set.
4. Ties broken alphabetically. The resulting ten queries, the thresholds and
   the computed document frequencies are recorded verbatim in §8.

**Circularity caveat.** These codes also drive the tool's own codebook-coverage
panel, so H4 tests that panel against the vocabulary it is built from — which
is intended (H4 asks whether the blind-spot flag tracks reality) but must be
stated. For the query-selection use the shared provenance is a strength: the
queries are what a BioFairNet researcher would plausibly search for, taken
from the project's own review rather than invented for the study. The keyword
thesaurus (`keyword_thesaurus.json`) is **not** used for selection, since it
was written as part of the tool and would make the test self-referential.

**Procedure.**
1. Generate the frozen corpus: `gif finder-data --since … --until …` for each
   arm; archive the exact JSON with a checksum.
2. Run the tool; record ranked topics, bridge/single-corpus labels, scenarios
   and the codebook coverage panel's blind-spot flags.
3. Commit and tag. Only then retrieve §6 outcome data.

**Outcome measures.** Per topic, within the arm's window:
- *Primary:* EC contribution (€) to projects whose title/objective/euroSciVoc
  classification matches the topic, **as a share of total programme
  contribution in that window** — absolute euros are not comparable across
  FP7/H2020/HE, whose budgets differ by multiples.
- *Secondary:* project count; distinct participating organisations; count of
  subsequent EUR-Lex acts matching the topic.

**Hypotheses and baselines.** Each tested against a pre-specified comparator:

| | Hypothesis | Comparator |
|---|---|---|
| H1 | Tool ranking predicts subsequent uptake | Random topic rankings (permutation test, 10 000 draws) |
| H2 | The pipeline beats naive counting | Raw keyword document-frequency ranking |
| H3 | Bridge topics outperform single-corpus topics | Within-run comparison of the two topic classes |
| H4 | Blind-spot codes show lower subsequent uptake than covered codes | Within-run comparison |

**Analysis (pre-specified).** Spearman rank correlation between tool rank and
subsequent-uptake rank, with bootstrap CIs; top-decile vs median uptake ratio
as the effect size reported in the abstract; permutation tests for H1–H2;
Mann–Whitney for H3–H4. Significance is secondary to effect size — with n in
the low hundreds, a small-but-significant correlation would not support a merit
claim, and the paper should not present one as if it did.

### 5.2 Tier B — case studies

**Sampling frame.** All organisations participating in projects funded under
the top-*k* ranked topics in the arm's first three years. This is a **complete
register**, which is the point: searching the web for "who acted on this"
returns survivors with communications departments and silently drops every firm
that tried the same thing and failed. The register includes the failures.

**The frame is FP7 onward, not FP6.** WP0 found FP6's organisation register
largely unpopulated — `organisationID` 1.5 %, `activityType` 3.7 %,
`ecContribution` 4.3 %, `nutsCode` 0.7 % — against 99.7 %, 99.2 %, 94.1 % and
78.3 % for FP7 (§6.1). FP6 participants are, in practice, a name and a country.
That is enough for FP6 to serve as **input** corpus in A1, where only titles,
objectives and money matter, and not enough to stratify or trace a sample from.
Tier B therefore draws on projects funded under FP7 onward in both arms, and
says so rather than reporting a sample silently biased toward the programmes
whose metadata happens to be complete.

**Sampling rule (stated before sampling).** Stratify by CORDIS `activityType`
(PRC private for-profit / HES higher education / REC research organisation /
PUB public body / OTH) and by country; take *n* ≈ 10; **include every sampled
entity that has since dissolved or exited**, up to a third of the sample, and
report attrition as a finding rather than a gap.

Stratification deliberately does **not** use the `SME` flag, although the
design would prefer it and the column exists: WP0 measured it at 0.0 % in both
programmes. Enterprise size therefore cannot be a stratum, and the paper must
not imply the sample is balanced on it. Where size matters for a given case it
is established from the organisation's own filings during the case work and
reported per case, not as a sampling property.

**Assessment.** Per organisation, past (*T*) vs present, across the three
dimensions — within the limits in §9.2.

### 5.3 Retrieval and topic validity (C1, C2)

Secondary, and cheap: a domain expert rates a stratified sample of ~100
returned documents for topical relevance (precision), and the extracted topics
are compared against independently-derived topic lists — ex-post Commission
programme evaluations and euroSciVoc classifications. Inter-rater agreement on
a 20 % overlap subsample.

## 6. Data sources

Retrieved **only after** §8 is filed.

| Source | Use | Access | Status |
|--------|-----|--------|--------|
| EUR-Lex / CELLAR SPARQL | Policy corpus at *T*; subsequent acts | Open | Working (in tool) |
| EU Funding & Tenders (SEDIA) | Grant corpus, 2014+ | Open | Working (in tool) |
| **CORDIS** project + organisation datasets (FP1–FP7, H2020, Horizon Europe) | Outcome uptake; input corpus at *T*; Tier B sampling frame | Open, data.europa.eu | Confirmed (§6.1); **adapter to build (§7, WP1)** |
| EU ETS / EUTL | Verified installation CO₂, 2005–2025 | Open, EEA public share | Confirmed (§6.1) |
| Eurostat (SBS, agricultural accounts, NUTS-2 employment, GVA) | Sector/region economic and social context | Open | Confirmed, with caveats (§6.1) |
| GLEIF LEI records | Entity status — survival/dissolution for Tier B attrition | Open | Confirmed (§6.1) |

### 6.1 WP0 — data availability, as measured on 2026-10-30

Verified by `paper/analysis/wp0_probe.py`, run on a GitHub Actions runner
because the development sandbox's egress policy denies every EU host. The
probe only reads; it discovers datasets through the `data.europa.eu` catalogue
API rather than assuming URLs, and checks each file column by column. Figures
below are measured, not quoted from documentation.

**CORDIS.** All archives answer HTTP 200 as CSV zips: FP5 13.1 MB, FP6 12.0 MB,
FP7 33.0 MB, H2020 55.2 MB, Horizon Europe 37.5 MB. The catalogue in fact lists
every framework programme back to FP1 (1984). FP6 and FP7 were read in full and
share one 20-column `project.csv` schema; FP6 nests its files under `csv/`,
FP7 does not, which the adapter must handle.

| | FP6 `project.csv` | FP7 `project.csv` |
|---|---|---|
| Rows (well-formed / ragged) | 9 763 / 330 | 25 022 / 763 |
| `ecMaxContribution`, `objective`, `frameworkProgramme` | 99.4 / 98.3 / 100 % | 100 / 100 / 100 % |
| `startDate` | 99.1 %, 2002-05-22 → 2010-07-12 | 99.6 %, 2007-05-01 → 2018-06-18 |
| `ecSignatureDate` | **0.0 %** | **0.0 %** |
| euroSciVoc classification | present, 30 015 rows | present, 66 986 rows |

Organisation registers, the Tier B sampling frame, differ sharply:

| Field | FP6 `organization.csv` (75 213 rows) | FP7 `organization.csv` (140 064 rows) |
|---|---|---|
| `organisationID` | 1.5 % | 99.7 % |
| `activityType` | 3.7 % | 99.2 % |
| `ecContribution` | 4.3 % | 94.1 % |
| `nutsCode` | 0.7 % | 78.3 % |
| `vatNumber` | 0.7 % | 72.1 % |
| `SME` | 0.0 % | 0.0 % |
| `country` | 99.2 % | 99.6 % |

**Eurostat.** Regional GVA (`nama_10r_3gva`) and regional employment
(`nama_10r_3empers`) answer as JSON-stat, but their NACE dimension carries only
15 aggregates — agriculture is `A`, while mining is buried inside `B-E`, so
mining cannot be isolated regionally from these. Structural business statistics
under the current code `sbs_ovw_act` hold **2022 onward only** and are therefore
useless for a 2009 or 2013 baseline; the discontinued `sbs_na_sca_r2` and
`sbs_na_ind_r2` do answer for mining at NACE B08 and span **2005–2020**. The
regional series `sbs_r_nuts06_r2` offers 101 NACE codes including B05–B09 but
only five indicators (`V11210`, `V13320`, `V16110`, `V91290`, `V94310`) and
ends in 2020. Agriculture is excluded from SBS altogether, so the agricultural
half of the scope uses the economic accounts `aact_eaa01` (dimensions `am_item`,
`indic_agr`, `unit`) and farm labour `aact_ali01` (`THS_AWU`), both answering
for 2009.

**GLEIF.** The LEI API returns `entity.status` (ACTIVE/INACTIVE) and
`registration.status` with no credentials, and its fulltext filter searches by
name, which is how CORDIS organisations will be matched in the absence of a
shared identifier.

**EU ETS.** The dataset is *European Union Emissions Trading System (EU ETS)
data from the Union Registry*, EEA, covering 2005–2025. Its advertised
`access_url` is not a file but a Nextcloud share page whose listing is drawn by
JavaScript; the file is reachable without a browser by PROPFIND against
`https://sdi.eea.europa.eu/datashare/public.php/webdav/<folder>/` using the
sharing token embedded in that page. The installation-level table is
`CITL_cube_final_version83_*.xlsx` (3.7 MB), beside an activity-code
translation table and the EEA's own data-quality note. The EEA's GeoNetwork
record API returns HTTP 500 and the old data-viewer URL is dead, so the
WebDAV route is the one the adapter should use — and because the token can
rotate, it must be re-read from the share page rather than hard-coded.

**Consequences for the design** — each worked into the sections named:

1. **Arm A1 is no longer policy-only** (§4.1, §4.2). FP6 and early FP7 awards
   were public knowledge at the end of 2009, so A1 gains a real grant corpus.
2. **The available-at-*T* rule uses `startDate`, not `ecSignatureDate`** (§4.2),
   because the signature column is empty for both old programmes.
3. **Tier B draws on FP7, not FP6** (§5.2), and stratifies by `activityType`
   rather than the SME flag, which is empty everywhere.
4. **Mining cannot be tracked regionally** through the national-accounts series
   (§9.2); it is tracked nationally via `sbs_na_sca_r2`.

## 7. Work packages

- **WP0 — feasibility. Done, 2026-10-30.** All four outcome sources confirmed
  reachable without credentials and checked field by field; findings and the
  four design changes they forced are recorded in §6.1. Probe:
  `paper/analysis/wp0_probe.py`, run by `.github/workflows/wp0-probe.yml`.
- **WP1 — tool work (on `main`, not this branch).**
  (a) Fix the date-window defect in `build_snapshot` (§4.1) so a frozen corpus
  cannot contain post-*T* documents, with tests.
  (b) `gif cordis`: ingest FP6/FP7/H2020/HE projects and organisations into the
  finder's document shape, enforcing the available-at-*T* restriction of §4.2
  in code, with tests. Permanently extends the tool's coverage below 2014 — a
  contribution in its own right. WP0 fixes three details in advance: FP6 nests
  its CSVs under `csv/` while FP7 does not; the date filter must key on
  `startDate`, since `ecSignatureDate` is empty; and the loader must tolerate
  ragged rows (330 of 10 093 in FP6, 763 of 25 785 in FP7) rather than assume a
  clean CSV.
- **WP2 — freeze and pre-register.** Generate both corpora, run the tool, commit
  outputs with checksums, file §8, tag the repository.
- **WP3 — outcomes.** Retrieve and link outcome data; compute §5.1.
- **WP4 — Tier B.** Sample and trace case studies.
- **WP5 — write-up.** Paper, figures, FAIR data release (Zenodo, consistent with
  the repo's existing release workflow).

## 8. Pre-registration

Filed on OSF before WP3, and generated from this file so the two cannot drift.
Frozen content: research questions and hypotheses (§3, §5.1); the query
selection rule and the resulting queries; the tool version and commit hash;
the frozen corpora checksums; outcome measures and their normalisation;
comparators; the analysis plan including tests and effect sizes; the Tier B
sampling rule.

**Deviation policy.** Any departure from the frozen plan is recorded in a
dated appendix to this file with its reason, and reported in the paper as a
deviation. Analyses not pre-specified are reported as exploratory.

## 9. Limitations — what this study cannot claim

### 9.1 The tool's own metrics are not validated
The indicative CO₂ abatement and cost-saving figures are assumption-based
heuristics with declared parameters (`docs/finder/data/co2_assumptions.json`),
not estimators fitted to data. This study does not validate them and the paper
must not present them as validated. At most their plausibility is bounded
against published ex-post evaluations for a handful of completed projects — a
sanity check, reported as such.

### 9.2 The economic dimension is not firm-level
No ORBIS/Amadeus licence is available, so firm financial accounts are out of
reach. The substitution, and its cost:

| Dimension | What we can measure | What we cannot |
|-----------|--------------------|----------------|
| Economic | Entity survival/status (GLEIF `entity.status`); subsequent EU funding received (CORDIS `ecContribution`); national sector turnover and enterprise counts for mining, NACE B08, 2005–2020 (`sbs_na_sca_r2`); agricultural output (`aact_eaa01`) | Firm revenue, margin, productivity |
| Social | Regional employment by NACE aggregate (`nama_10r_3empers`, NUTS-2); farm labour in annual work units (`aact_ali01`); project-reported social outcomes | Firm-level employment quality, wages |
| Environmental | Verified installation CO₂ 2005–2025 (EEA Union Registry extract) — but only for ETS-covered installations, which excludes most agricultural SMEs | Firm-level footprint for non-ETS entities |

Two further boundaries were established by WP0 rather than assumed:

- **Mining has no regional economic series.** The NUTS-2 national-accounts
  tables resolve NACE only to 15 aggregates, in which mining is absorbed into
  `B-E` alongside all manufacturing, energy and water. Mining is therefore
  reported **nationally**; only agriculture, which is its own aggregate `A`,
  can be reported regionally. Any regional claim in the paper must be confined
  to the agricultural cases.
- **The structural business series ends in 2020** and the current replacement
  starts in 2022. Where a case needs sector context after 2020 there is a
  two-year hole and a break in the series across it, so post-2020 sector
  context is read from the enterprise's own reporting, flagged as such.

Tier B therefore reports **trajectory and survival** rather than profitability.
This is a real limitation; it is arguably also more robust, since survival is
observed rather than self-reported.

### 9.3 No causal attribution at organisation level
2009–2026 contains the financial crisis, COVID, the energy price shock and
CBAM. Organisation-level change over that span is dominated by those events.
Tier B traces mechanisms and describes trajectories; it does not attribute
outcomes to scenario alignment, and the paper says so explicitly.

### 9.4 Scope
Agriculture and mining, EU level, English-language sources only — matching the
tool's scope and the WP1/D1.2 review. National and regional instruments are
outside this study.

## 10. Open decisions

1. Target journal, which affects framing and length.
2. Author list and contributions.
3. *k* in "top-*k* ranked topics" for Tier B sampling — fix before WP2.
4. Whether the expert rating in §5.3 is done by one co-author or two (two gives
   inter-rater agreement; one is faster).
