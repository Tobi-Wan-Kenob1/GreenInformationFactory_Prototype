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
| **A1** | 2009-12-31 | EU policies ≤ 2009 (CELLAR reaches 2004; the current snapshot holds 50 pre-2010 acts). **Policy-only** — see §4.2 | 2010–2026 (FP7 remainder, H2020, Horizon Europe) |
| **A2** | 2013-12-31 | Policies ≤ 2013 **plus** FP7 projects started ≤ 2013 as the funding landscape visible at *T* | 2014–2026 (H2020, Horizon Europe) |

Two freeze points give an internal replication. A1 is the stronger test (longer
window, and it exercises the policy-only path); A2 is nearly free once the
CORDIS adapter exists.

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
  arm's *T*, and record the assertion output in §8. For A1 this means the
  grants file is expected to be **empty** after filtering.

Note that tool fixes belong on `main`, not on this branch; this branch carries
the study, not the instrument.

### 4.2 Leakage — the trap to design out

It is tempting to feed CORDIS **projects** into the tool as the historical
"grant" corpus. That would invalidate the back-test: projects are awarded
*after* the call, so a corpus of projects started after *T* contains outcome
information the tool could not have had at *T*. The ranking would then partly
restate the answer.

Two consequences, both binding:

1. **A1 uses policies only.** The Funding & Tenders API indexes Horizon 2020
   onward, so no pre-2010 call topics are retrievable from it — verified: the
   current snapshot has 0 grants before 2010 and 2 before 2014. Rather than
   substitute projects (leakage), A1 runs on the policy corpus alone, which the
   tool supports natively.
2. **A2 may use FP7 projects started ≤ 2013**, because at the end of 2013 those
   awards were public knowledge — "what was already being funded" is legitimate
   available-at-*T* information. Projects starting after *T* are excluded.

CORDIS is therefore primarily an **outcome** dataset, and only secondarily an
input (A2 alone, with the date restriction above).

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

**Sampling rule (stated before sampling).** Stratify by organisation type (SME
/ large enterprise / research organisation / public body) and by country; take
*n* ≈ 10; **include every sampled entity that has since dissolved or exited**,
up to a third of the sample, and report attrition as a finding rather than a
gap.

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
| **CORDIS** project + organisation datasets (FP7, H2020, Horizon Europe) | Outcome uptake; Tier B sampling frame | Open, data.europa.eu | **Adapter to build (§7, WP1)** |
| EU ETS / EUTL | Verified installation CO₂, 2005+ | Open | To verify |
| Eurostat (SBS, NUTS-2 employment, GVA) | Sector/region economic and social context | Open | To verify |
| GLEIF LEI records | Entity status — survival/dissolution for Tier B attrition | Open | To verify |

Exact dataset names and field availability are confirmed in WP0 before they are
relied on; the sandbox cannot reach EU hosts, but a CI runner can, which is how
the finder's own endpoints were characterised.

## 7. Work packages

- **WP0 — feasibility.** Confirm CORDIS dataset structure and the fields needed
  (EC contribution, start date, participant organisation, classification);
  confirm EUTL, Eurostat and GLEIF access. Output: a short data-availability
  note appended here.
- **WP1 — tool work (on `main`, not this branch).**
  (a) Fix the date-window defect in `build_snapshot` (§4.1) so a frozen corpus
  cannot contain post-*T* documents, with tests.
  (b) `gif cordis`: ingest FP7/H2020/HE projects and organisations into the
  finder's document shape, enforcing the available-at-*T* restriction of §4.2
  in code, with tests. Permanently extends the tool's coverage below 2014 — a
  contribution in its own right.
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
| Economic | Entity survival/status (GLEIF, registries); subsequent EU funding received (CORDIS); sector/region GVA and turnover (Eurostat) | Firm revenue, margin, productivity |
| Social | Regional employment and training indicators (NUTS-2); project-reported social outcomes | Firm-level employment quality, wages |
| Environmental | Verified installation CO₂ (EUTL) — but only for ETS-covered installations, which excludes most agricultural SMEs | Firm-level footprint for non-ETS entities |

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
