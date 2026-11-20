# Validation study — protocol

**Status:** draft for co-author review · **Version:** 0.1 · **Date:** 2026-10-30
**Conducted in the open — see §11.**
**Tool under study:** the Policy & Grant Finder (`docs/finder/`) in the public
repository `Tobi-Wan-Kenob1/GreenInformationFactory_Prototype`. Every path
below of the form `docs/…` or `src/…` refers to that repository; paths without
a prefix are in this one.
**Pre-registration:** filed 2026-11-20 on OSF, public —
[doi:10.17605/OSF.IO/QC2SP](https://doi.org/10.17605/OSF.IO/QC2SP); registered material at
tag `prereg-v1`. Changes after filing are in Appendix B.

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
gif finder-data --since 1990-01-01 --until 2009-12-31 --out data/frozen-A1
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

Note that tool fixes belong in the public prototype repository, not here; this
repository carries the study, not the instrument.

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
   from these codes), **separately for the policy side and the funding side**.
   Discard any code matching more than **20 %** of *either* side — a term that
   broad is not a topic on that side. This filter uses input data only, so it
   introduces no leakage.
3. Discard codes absent from the corpus, and collapse codes whose term sets
   coincide, keeping the higher paper count.
4. Of those remaining, take the **ten with the highest codebook paper count**.
   Each becomes a single-keyword query set.
5. Ties broken alphabetically. The resulting queries, the thresholds and the
   computed per-side document frequencies are recorded verbatim in §8.

**Two seed sets, each matched to the hypotheses it can test.** Step 2 above is
applied in two variants, both fixed before any outcome data is retrieved:

| Variant | Rule | Serves |
|---|---|---|
| **Broad** | as steps 1–5 | H1, H2 |
| **Bridging** | as above, plus: keep only codes present in **both** the policy and the funding corpus | H3, H4 |

The reason is structural rather than convenient. H1 and H2 rank topics by
subsequent uptake and want the widest defensible seed set — ten queries
yielding roughly 150 topics, which is the *n* §4 assumes. H3 and H4 compare
bridge topics against single-corpus ones, and a query term that appears in
only one corpus cannot produce a bridge topic at all, so under the broad rule
those hypotheses would be tested on whatever handful of terms happened to span
both sides.

Measured on the frozen corpora, the broad rule yields queries spanning both
sides for 4 of 10 in A1 and 6 of 10 in A2; the bridging rule yields 8 queries
in A1 and a full 10 in A2, all spanning both sides. Registering one rule for
all four hypotheses would therefore mean either accepting that H3 and H4 rest
on four terms, or halving the seed set for H1 and H2. Declaring both in
advance, with their roles, costs nothing in rigour and is reported as two
pre-specified analyses rather than one plus a rescue.

Both selections are computed from the same frozen corpus in the same run, so
neither is chosen after seeing the other's results.

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

**Fixing *k* (decided, pre-specified).** The frame should hold **200–600
distinct organisations**. *k* is not set directly, because the number of
organisations per topic is not known until the corpus is frozen; it is derived
by rule:

> Take topics in rank order, accumulating their distinct participating
> organisations, and stop at the smallest *k* whose frame reaches **200**. If
> adding the *k*-th topic would carry the frame past **600**, stop at *k* − 1
> and report the frame size reached.

So *k* is whatever the data makes it, within a band chosen in advance rather
than after seeing which value gives a convenient answer. Both the rule and the
resulting *k* and frame size go into §8. If rank order cannot reach 200
organisations even using every topic, that is reported as a finding about
corpus thinness, and Tier B proceeds on the frame available — it is
illustrative, so a smaller frame weakens the case studies without touching the
Tier A validation claim.

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

Secondary, and cheap: **two** domain raters score a stratified sample of ~100
returned documents for topical relevance (precision), and the extracted topics
are compared against independently-derived topic lists — ex-post Commission
programme evaluations and euroSciVoc classifications.

**Rating procedure (decided, pre-specified).** Two raters, so agreement is
measurable rather than asserted. Each rates 60 documents, of which 20 are
common to both — a 20 % overlap of the 100. Relevance is scored on a
three-point scale (relevant / marginal / not relevant) against a written
definition fixed before rating begins. **Cohen's κ** is computed on the overlap
and reported with the precision estimate, whatever it comes to; a low κ is a
finding about topical judgement in this domain, not a result to be suppressed
or re-rated until it improves. Disagreements within the overlap are resolved by
discussion, the resolution is recorded, and precision is reported both before
and after resolution. Raters see documents in randomised order and are not told
each document's rank or whether it came from a bridge topic, so the rating
cannot track the hypothesis under test.

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

### 6.2 How the policy corpus is built

The policy side is not simply "whatever EUR-Lex returns for the scope
keywords". Two construction rules apply, both recorded in every snapshot and
corpus manifest so a corpus states what it was willing to include. Appendix A.2
gives the evidence that made them necessary and what they cost.

**Routine instruments are excluded.** Thirteen title fragments mark the
Commission's standing market administration: *standard import value*, *world
market price*, *export refund*, *import duties*, *import duty*,
*representative price*, *minimum selling price*, *allocation coefficient*,
*import licence*, *export licence*, *production levy*, *invitation to tender*,
and *corrigendum*. Each names an instrument type rather than a subject, so the
rule removes a kind of act and not a topic. It is applied inside the SPARQL
query: these acts are also the most recent, so with `ORDER BY DESC(date) LIMIT
n` they would consume the whole result budget and filtering afterwards would
leave a handful of acts per period.

An act excluded this way is not a policy an organisation can align with, which
is what the tool is for — the entry price of pears is re-published every few
days. A reader who disagrees can see the patterns and re-run without them;
`gif freeze` takes the filter off on request.

**Acts carry an excerpt of their own text.** CELLAR serves the act by CELEX, so
each document gets roughly 600 characters of its opening recitals in addition
to its EuroVoc descriptors. The opening says what an act is for; the operative
articles that follow are long, repetitive and far less discriminating.

Enrichment is best-effort and every outcome is counted. Old acts exist only as
scans, some have no English expression, and CELLAR answers 404 for a few CELEX
numbers that SPARQL hands out — 31 of 148 in arm A1. An act that cannot be
enriched keeps the summary it had. A corpus enriched for only part of its
documents without saying so would be worse than one not enriched at all,
because the thin part would read as an absence of topic rather than an absence
of text.

**Requiring a minimum number of EuroVoc descriptors is available and not
used.** It was measured — 15 acts lost at a threshold of two, 22 at four — and
rejected, because enrichment addresses the same weakness without discarding
real acts.

## 7. Work packages

- **WP0 — feasibility. Done, 2026-10-30.** All four outcome sources confirmed
  reachable without credentials and checked field by field; findings and the
  four design changes they forced are recorded in §6.1. Probe:
  `paper/analysis/wp0_probe.py`, run by `.github/workflows/wp0-probe.yml`.
- **WP1 — tool work (on the public repository's `main`, not here).**
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

**The registration is public, not embargoed** (§11). An earlier draft planned
an embargo to reconcile registration with confidentiality; the study is open,
so there is nothing to reconcile and the registration is readable from the day
it is filed.

What that changes is only who can check the dates, and the answer is now
anyone. What it does not change is the ordering, which is the whole point.
**A registration filed after the outcome data has been seen is worthless
however it is dated.** Working in the open makes this easier to verify and no
easier to fudge: the registration, the corpus manifests and the recorded tool
output all carry timestamps a reader can inspect, so the claim that the
ranking preceded the outcomes stands or falls on the record rather than on our
word. The ordering in §4.2 and in `paper/README.md` is not negotiable.

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

1. Target journal, which affects framing and length. **Deferred by decision**
   until the validations are finished.
2. Author list and contributions. **Deferred by decision**, as above.

Settled since v0.1:

- ***k* for Tier B sampling** — frame target 200–600 distinct organisations,
  *k* derived by the rule in §5.2.
- **Raters for §5.3** — two, with a 20 % overlap and Cohen's κ.
- **Publication of the study material** — see §11.

## 11. Everything is public

**Decision, superseding the one below.** The study is conducted in the open:
protocol, pre-registration, frozen corpora, analysis and results all live in
the public repository as they are produced. Nothing is withheld until
submission.

The consequence worth stating is for §8. An open study does not need an
embargoed registration — the registration can be public from the moment it is
filed — but the **ordering** it enforces matters more here, not less. Working
in the open means the dates are checkable by anyone: the registration, the
corpus manifests and the recorded tool output are all timestamped where a
reader can see them, so a claim that the ranking preceded the outcome data can
be verified rather than taken on trust. The discipline in §4.2 and in
`paper/README.md` is unchanged and is not negotiable.

What this costs, recorded so it is a choice and not an oversight: anyone
reading this can run the same study. The protection against being scooped is
the registration date and the work itself, not secrecy.

### 11.1 The earlier decision, and why it was reversed

For the record, since a reader will find it in the history. Study material was
initially to be kept non-public until submission, on the reasoning that the
protocol, hypotheses, selection rule and frozen corpora describe a result
nobody has published, and that a reader could run the same study faster. The
instrument was to stay public either way — it is a Horizon Europe deliverable
and there was no case for hiding it — so the split was between the tool and the
study built around it.

Two things undid it in practice. The material was already public before the
decision was taken: nine commits from `dd84ea7` to `38c66e4` on 2026-10-30,
plus eight public Actions runs carrying the probe output, and removing them
would have reduced discoverability without retracting anything already
fetched. And the private repository the study would have moved to could not be
reached: the GitHub App serving these sessions is scoped to public
repositories, so every session would have faced the same obstacle while
WP2-WP5 all handle study data.

Rather than keep a confidentiality rule that the setup could not enforce, the
study is open. That is the honest position: priority rests on a public,
timestamped registration, not on material having been secret.

## Appendix A — changes made before pre-registration

Dated record of every change to the plan above, as §8 requires. All of these
predate the filing of §8 and none involved retrieving outcome data, so they are
revisions to a draft rather than deviations from a registered plan. They are
recorded here because the reasoning is part of the method, and because a reader
comparing this file to its history should not have to reconstruct why it moved.

### A.1 2026-10-30 — WP0 findings (§6.1)
Four design changes forced by what the data actually contains: arm A1 gains a
grant corpus because CORDIS reaches back to FP1; the available-at-*T* rule keys
on `startDate` because `ecSignatureDate` is empty in FP6 and FP7; Tier B draws
on FP7 onward because FP6's participant register is unusable; mining is
reported nationally because the regional accounts cannot isolate it.

### A.2 2026-11-20 — the policy corpus was mostly not policy
The first frozen corpus was built, the tool run on it, and the output recorded.
That exercise is what exposed the problem, which is the purpose of running it.

**What was found.** In arm A1, **110 of 148 acts (74 %)** were routine market
administration — standard import values for fruit and vegetables, re-fixed
every few days as a fresh regulation. The term `standard` matched 77 of 148
acts for that reason alone. Searching EUR-Lex for "agriculture" returns these
in overwhelming preference to policy instruments.

A second, compounding problem: a policy document carried only its title and its
EuroVoc descriptors as searchable text, a few dozen words, against a funded
project's objective. Ten codebook query terms matched 679 projects and
essentially no acts, so anything comparing the two corpora was measuring
metadata rather than policy, and H3 and H4 had nothing to test.

**What changed.** Thirteen title fragments now exclude routine instrument types
in the SPARQL query (§6.2); acts carry an excerpt of their own text fetched
from CELLAR; and the specificity filter in §5.1 step 2 is applied per side,
because a corpus-wide ratio diluted by the larger side had let `regulation`
through at 143 of 148 acts.

**Effect, measured.** Corpus size held at 148 acts — the per-period budget
refills with substantive acts rather than shrinking — while routine acts went
to zero and coverage reached back to 1994 instead of starting at the newest
price notice. 117 of 148 acts (79 %) yielded readable text. Queries spanning
both corpora went from 1 of 10 to 4 of 10 in A1, and the bridging seed set from
1 query to 8 in A1 and 10 in A2. `standard` now matches 6 acts rather than 77.

**What it costs.** The filter is a judgement about what counts as policy, and it
is auditable rather than hidden: the patterns are recorded in every snapshot and
corpus manifest. Each fragment names an instrument type and not a subject, so
it removes a kind of act rather than a topic — but a reader who disagrees with
the judgement can see exactly what was dropped and re-run without it. Requiring
a minimum number of EuroVoc descriptors was measured (15 acts lost at ≥2, 22 at
≥4) and **not adopted**: act-text enrichment addresses the same weakness
without discarding real acts.

### A.3 2026-11-20 — two seed sets instead of one (§5.1)
Declared in advance, each matched to the hypotheses it can test, for the reasons
and with the figures given in §5.1.

### A.4 2026-11-20 — the study is public (§8, §11)
Confidentiality until submission was replaced by working in the open. The
registration is public rather than embargoed; the ordering it enforces is
unchanged.

### A.5 2026-11-20 — completed for filing (pre-registration §4, §5, §7.1, §9.1)
Three gaps found while preparing the filing, closed before it:

- **Bridging-set output had not been recorded.** The benchmark run recorded the
  tool on the broad seed set only, so the four bridging-only codes (*storage*,
  *collection*, *monitoring*, *land use*) that seed H3 and H4 had no recorded
  output. Recorded by `.github/workflows/record-bridging.yml` over the archived
  corpora, after verifying them against their manifests, with the tool at the
  manifests' commit. No re-fetch; the input is unchanged.
- **Blind-spot flags were recorded only as displayed.** The codebook panel
  renders 12 codes per dimension; the tool computes all 87, and H4 compares
  exactly those. The recorder now keeps the tool's own full computation
  (recorder change only; the app is at the manifests' commit), and all four
  recordings were re-made by `.github/workflows/record-full-coverage.yml`,
  which commits nothing unless every previously recorded field comes out
  identical.
- **How runs combine into units was unstated.** Pre-registration §7.2 now fixes
  it: ranked lists for H1/H2, distinct topics for H3 and the effect size,
  codebook codes for H4.
- **Inference criteria were unstated.** One-sided tests at α = 0.05,
  Holm–Bonferroni across the four hypotheses within each arm, and the handling
  of topics with no uptake and projects with no recorded contribution, are now
  fixed in pre-registration §7.1.
- **"No outcome data retrieved" overstated it.** The CORDIS files containing the
  post-*T* projects were downloaded and their field completeness inspected in
  WP0; no outcome measure was computed. Pre-registration §9.1 now says exactly
  that.

## Appendix B — after registration

### B.1 2026-11-20 — filed, then the form corrected the same day
Filed on OSF at 2026-11-20T08:27:36Z, public,
[doi:10.17605/OSF.IO/QC2SP](https://doi.org/10.17605/OSF.IO/QC2SP). Read back
through OSF's public API by `.github/workflows/check-registration.yml`, the form
differed from the pre-registration in four places:

- it certified that the authors had not accessed the data, which §9.1 says is
  not so;
- the explanation field was empty;
- the sample size field repeated its rationale;
- four fields were empty;
- no files were attached, although one field said they were.

The cause was a newer template than the filing guide assumed. The correction is
an OSF Update with a stated justification (`paper/OSF_UPDATE.md`), plus a public
deposit of the registered files linked as a resource. No hypothesis, measure,
test, threshold or exclusion changed. Every corrected field matches the
pre-registration at tag `prereg-v1`, and no outcome data had been retrieved
when it was made.
