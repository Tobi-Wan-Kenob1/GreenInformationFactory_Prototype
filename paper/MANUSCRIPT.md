# Does a policy–funding topic tool see where the money goes? A pre-registered back-test on EU policy and research funding, 2009 and 2013

**Draft v0.2 — 2026-11-21 · for co-author review · not submitted** · target: see `JOURNALS.md`

*Authors:* [author list deferred — protocol §10]
*Correspondence:* [to be added]
*Pre-registration:* OSF, [doi:10.17605/OSF.IO/QC2SP](https://doi.org/10.17605/OSF.IO/QC2SP)
*Registered material:* Zenodo, [doi:10.5281/zenodo.24392976](https://doi.org/10.5281/zenodo.24392976)
*Code, data and results:* `Tobi-Wan-Kenob1/GreenInformationFactory_Prototype`, branch `claude/validation-paper`, tag `prereg-v1`

> **Drafting conventions.** Every number below is taken from a committed file
> named in the text, and none was typed from memory. `[REF: …]` marks a place
> that needs a citation; none has been invented. `[TIER B]` marks text that
> waits on the case work. `[DECIDE]` marks a choice for the authors.

---

## Abstract

**Background.** Tools that mine policy documents and funding records for
"emerging" or "bridging" topics are increasingly offered to researchers,
funders and firms. They are rarely tested against what happened afterwards.

**Methods.** We back-tested one such tool, the open-source Policy & Grant Finder.
- **Input.** We froze its input at two past dates, 31 December 2009 and
  31 December 2013: EU acts in agriculture and mining from EUR-Lex, and FP6/FP7
  projects from CORDIS that had started by then.
- **Queries.** Selected by a fixed rule from an independent literature codebook.
- **Order of work.** We recorded the tool's output and pre-registered four
  hypotheses before retrieving any outcome data.
- **Outcome.** Each topic's share of the EC contribution to all FP7, H2020 and
  Horizon Europe projects that started later: 76 949 projects (€164 bn) after
  2009 and 61 051 (€135 bn) after 2013.

**Results.**
- **Ranking.** The tool's ranking of topics within a list did not predict later
  funding in either arm (mean Spearman ρ = 0.01 and −0.03). Ranking by raw
  document frequency did at least as well (difference −0.13 and −0.11).
- **Classification.** Bridge topics, those the tool finds in both policy and
  funding documents, took up more later funding than single-corpus topics in
  both arms (probability of superiority 0.72 in each; Holm-adjusted p < 0.001).
  Codebook codes the tool flagged as blind spots took up less than covered
  codes (0.14 and 0.11; p < 0.001).
- **Headline effect.** The tool's top decile took up 1.7 and 2.1 times the
  median topic's share, with 95 % intervals reaching 1.
- **Exploratory frequency control.** After controlling for how often a term
  occurred in the input corpus, the bridge effect shrank but remained (partial
  r = 0.16 and 0.19, one-sided p ≈ 0.04). The blind-spot effect could not be
  separated from frequency.

**Conclusions.**
- The tool's classification of topics carries information about later funding;
  its ranking does not.
- Much of what the classification captures is the persistence of common
  vocabulary. The bridge construct adds a modest amount beyond it, mostly
  among rarer terms.
- The back-test also exposed a defect: generic words (*will*, *develop*) were
  being offered as topics.
- We recommend that tools of this kind publish frequency baselines alongside
  their rankings.

**Keywords:** research funding; EU policy; back-testing; pre-registration;
text mining; bioeconomy; CORDIS; EUR-Lex

---

## 1 Introduction

Researchers, funders and companies increasingly use text-mining tools to find
out where policy and funding attention is heading [REF: horizon-scanning and
research-intelligence tools]. A common construct is the *bridge*: a topic that
appears in both policy documents and funding records, presumed to mark where
political intent and resources meet [REF: policy–science alignment
literature]. Such tools are evaluated, when at all, by face validity:
whether their output looks sensible to experts [REF]. Face validity cannot
show whether the output carries information about the future. A tool that
restates which words are common will look sensible and predict nothing that a
word count would not.

A back-test can show it. Freeze the tool's input at a past date *T*, record its
output, and only then compare it with what happened after *T*. The design is
standard in forecasting [REF: forecast evaluation, out-of-sample testing]. It
is unusual in research-policy tooling. One reason is that it needs historical
corpora reconstructed as they stood at *T*. Another is that its credibility
depends on the order of operations: an outcome seen before the analysis is
fixed contaminates the analysis however carefully it is later dated [REF:
pre-registration, garden of forking paths].

We report a pre-registered back-test of the Policy & Grant Finder, an
open-source tool developed within the BioFairNet project (Horizon Europe,
grant 101181568) for agriculture and the mining of raw materials. We ask four
questions:
- whether its topic ranking predicts later funding;
- whether that ranking beats naive counting;
- whether its bridge topics outperform single-corpus topics;
- whether the codebook codes it flags as blind spots were in fact neglected
  afterwards.

We also describe what organisations funded under its top topics did next, as
illustrative case material.

The contribution is threefold:
- **Evidence** on whether a representative policy–funding tool sees ahead.
- **A protocol** for back-testing such tools that others can reuse. It covers
  frozen corpora with checksummed manifests, rule-based query selection,
  hermetic recording, and a one-shot analysis.
- **A frank account** of where the protocol had to be corrected, and why.

## 2 The tool under test

The Policy & Grant Finder runs in a web browser (`docs/finder/` in the
repository). For a keyword query it does five things:
- **Retrieves** EU acts from EUR-Lex/CELLAR and EU funding records: open calls
  from Funding & Tenders, and funded projects from CORDIS.
- **Tokenises** titles and summaries into words and adjacent-word bigrams,
  after removing stop words.
- **Ranks** three lists of up to 15 topics:
  - *policy topics*, by document frequency among the acts;
  - *grant topics*, by document frequency among the funding records;
  - *bridge topics*: terms present on both sides, ranked by the smaller of
    their two document shares.
- **Codebook coverage:** shows, for each of 87 codes from the BioFairNet
  literature review [REF: BioFairNet D1.2], whether the retrieved documents
  address it on both sides, one side or neither. A code addressed on neither
  side is presented as a *blind spot*.
- **Scenarios:** builds them from selected topics, with indicative CO₂ and
  cost figures.

The tool implicitly makes four claims:
- its topic ranking points to where attention will go;
- the bridge construct sharpens that;
- its blind spots mark real neglect;
- its CO₂ and cost figures estimate real quantities.

The last are assumption-based heuristics with declared parameters, not
estimators fitted to data. They are outside this study, and nothing here
validates them (protocol §9.1).

## 3 Methods

The study protocol (`paper/PROTOCOL.md`) records every design decision and
every change, each dated, with the evidence that prompted it (Appendix A
before registration, B after, C exploratory).

### 3.1 Design

**Two freeze points form an internal replication.**

| Arm | *T* | Input corpus | Outcome window |
|---|---|---|---|
| A1 | 2009-12-31 | EU acts ≤ *T*; FP6 and FP7 projects started ≤ *T* | 2010–2026 |
| A2 | 2013-12-31 | EU acts ≤ *T*; FP6 and FP7 projects started ≤ *T* | 2014–2026 |

**Availability at *T* is enforced in code.** CORDIS leaves the signature date
empty for FP6 and FP7, so a project enters an input corpus only if it *started*
by *T*. Signature precedes start, so the rule can exclude a project the tool
could have seen but never admit one it could not. Input and outcome
populations are disjoint by construction.

**Order of operations.**
1. Freeze the corpora.
2. Select queries by rule.
3. Run the tool and record its output.
4. Register.
5. Retrieve outcome data and run the analysis, once.

Steps 1–3 were committed before registration, which was filed on OSF at
2026-11-20T08:27:36Z. The analysis code was committed before outcome
retrieval (§3.7). The outcome data was retrieved at 10:34:12Z the same day,
and committed before the analysis ran.

### 3.2 Input corpora

**How the corpora were built.**
- Built by `gif freeze`, which refuses to write a corpus that breaches its
  window or whose sources answered only in part.
- Each corpus has a manifest holding per-file SHA-256 digests, content digests
  (stable under re-serialisation), observed date ranges, and the tool's commit.
- Policy documents come from CELLAR's SPARQL endpoint, by ten scope keywords:
  *agriculture, mining, bioeconomy, biomass, soil, circular economy, carbon
  farming, raw materials, land use, just transition*.
- Thirteen title fragments that name instrument types, not subjects, exclude
  routine market instruments. Without this exclusion, 110 of 148 acts in A1
  were import price notices and similar (protocol A.2).
- Each act carries the opening of its own text, retrieved by CELEX number.

**What the frozen corpora hold.**

| | A1 | A2 |
|---|---|---|
| Acts | 148 (1994-03-10 – 2009-12-18) | 150 (1994-05-05 – 2013-12-18) |
| Acts with own text | 117 | 123 |
| Call topics | 0 | 1 |
| Funded projects | 679 (2003-08-01 – 2009-12-01) | 1 372 (2003-08-01 – 2013-12-13) |
| `manifest.json` SHA-256 | `afd89a28…44a1a8` | `9e899358…fe8cb5` |

Full digests are in `paper/data/REGISTRATION_VALUES.md`.

### 3.3 Query selection

**Queries are derived by rule from the BioFairNet literature codebook**, which
was produced independently of the tool and before the study [REF: D1.2]. The
rule:
1. Take the 51 codes in its barriers and drivers dimensions.
2. Discard codes absent from the corpus, and any code matching more than 20 %
   of the documents on either side.
3. Collapse codes with identical term sets.
4. Take the ten with the most supporting papers, ties broken alphabetically.

Matching uses a leading word boundary, is case-insensitive and applies no
thesaurus. The tool's own thesaurus would have made the measurement
self-referential.

**Two seed sets.**
- A *broad* set (H1, H2), identical in both arms: *land, water, demand,
  landscape, database, dataset, efficiency, technology, standard, transport*.
- A *bridging* set (H3, H4), which also requires each code to appear on both
  sides of the corpus, since a term absent from one side cannot form a bridge.
  Only eight codes meet that condition in A1 (ten in A2). The rule does not
  pad.

### 3.4 Recording

**How the tool was run.** A headless browser drove the tool itself over each
frozen corpus, with all outbound requests blocked and the tool's demonstration
data mapped to empty files. That way it could read only the frozen input.

**What was recorded for each query:** the three ranked lists, the bridge
labels, the codebook coverage for all 87 codes, and the metrics.

**Scale:** 122 (A1) and 129 (A2) distinct topics in the broad set; 126 and 145
in the bridging set.

### 3.5 Outcome measures

**Population.** Every FP7, H2020 and Horizon Europe project in the CORDIS bulk
archives that started in the outcome window: 76 949 projects with €163.9 bn
of EC contribution in A1, and 61 051 with €135.2 bn in A2. No project lacked a
recorded contribution.

**Primary measure.** A topic's EC contribution to the projects whose title,
objective or euroSciVoc labels match it, as a *share* of the window's total.
Framework programme budgets differ by multiples, so absolute euros are not
comparable across them.

**Secondary measures.** Matching project count; distinct participating
organisations; matching EUR-Lex acts in the window.

**The act measure is a sample, not a census.** Acts were retrieved exactly as
the input corpus was built, under its 150-act budget, so the A1 act sample
starts in December 2012 rather than January 2010 (protocol B.3).

### 3.6 Hypotheses and analysis

| | Hypothesis | Unit | Test |
|---|---|---|---|
| H1 | The tool's topic ranking predicts subsequent uptake | Each ranked list with ≥ 5 topics | Mean within-list Spearman ρ; permutation within lists |
| H2 | The tool beats raw document-frequency ranking | Same lists | Mean ρ<sub>tool</sub> − ρ<sub>frequency</sub>; sign-flip permutation |
| H3 | Bridge topics outperform single-corpus topics | Distinct topics, bridging set | Mann–Whitney U |
| H4 | Blind-spot codes show lower uptake than covered codes | Codebook codes, bridging set | Mann–Whitney U |

**Testing rules.**
- All tests are one-sided in the registered direction at α = 0.05, with
  Holm–Bonferroni across H1–H4 within each arm.
- Permutation and bootstrap procedures use 10 000 draws, with seeds fixed in
  code.
- The arms are analysed separately and never pooled.

**Effect sizes.**
- H3 and H4: the probability of superiority, P(a > b) + ½P(a = b).
- Headline: the median uptake of the tool's top-decile topics divided by the
  median topic's. A topic is in the top decile if it holds rank
  ≤ ⌈0.1 × list length⌉ in some list.

**Significance is secondary to effect size**, as registered.

**Unit definitions** (protocol B.2):
- A topic is a bridge topic if any run lists it as one.
- A code is a blind spot if the tool marks it unaddressed in every run, and
  covered if it marks it addressed on both sides in at least one run. Codes
  that are neither are left out of H4.

### 3.7 Integrity measures and corrections

**Code freeze.** The outcome and analysis code (`paper/analysis/wp3_*.py`),
its synthetic-data tests, and the operational definitions the registration
left open (protocol B.2) were committed before outcome retrieval. They were
then run once by a workflow that refuses to run if results already exist. The
code was exercised on the real recorded output with randomly generated
outcomes. It reproduced the registered unit counts, and every test returned
null, as it should on random data.

**Correcting the OSF form.** The OSF template on screen differed from the one
our filing guide assumed. As a result, the first submission certified that the
authors had not accessed the outcome data, which was not true. We had
downloaded the CORDIS files containing the outcome-window projects and
inspected how completely their fields were filled. That inspection is what
established that start date must stand in for signature date, and that SME
status cannot be a sampling stratum. No outcome measure was computed from it.

The form was corrected the same day, before any outcome retrieval, by two OSF
updates with stated justifications (protocol B.1). The registered files were
deposited on Zenodo and linked to the registration.


### 3.8 Exploratory analysis: controlling for frequency

**Why.** H3 and H4 compare classes defined by presence in the input corpus.
Presence goes with frequency, and frequent terms match more later projects.
So after seeing the registered results, we asked whether the classes carry
information beyond frequency.

**Method** (protocol C.1, committed before it was run):
- The partial Spearman correlation between class and uptake, given each unit's
  document frequency in its frozen corpus. Frequency was computed with the
  same function that selected the queries.
- p from permutation within frequency terciles; bootstrap 95 % intervals.

**A rule fixed in advance:** if the classes did not overlap in frequency, the
effect would be reported as inseparable rather than modelled some other way.
This analysis is exploratory and is labelled so throughout.

### 3.9 Illustrative case studies (Tier B)

**The registered frame rule did not work on these data.** It accumulates
top-ranked topics until 200–600 participating organisations are reached. With
topics matched on their term alone, the first topic already exceeded the
ceiling (*land* matched projects with 12 241 organisations), so the rule
yielded an empty frame.

**Deviation 1 (protocol B.4, decided before sampling).** We redefined the unit
as a bridge topic within its query, as the tool presents it. Frame projects
had to match both terms and start in the arm's first three outcome years. The
sample was ten organisations, five per arm, allocated across CORDIS activity
types and spread across countries.

**That draw had two problems.** It sampled outside the study's scope (a boiler
maker and a space solar-cell manufacturer, among others), and it included an
author's institution.

**Deviation 2 (protocol B.6, decided after seeing the first draw).** Frame
projects must also match the input corpus's scope keywords, and authors'
institutions are excluded. The frame was re-drawn with new seeds. Both draws
are published (`paper/results/tierb/`, `paper/results/tierb-scoped/`).

**The cases are illustrative mechanism evidence only.** They carry no causal
attribution: the period spans the financial crisis, the pandemic, the energy
price shock and the introduction of CBAM (protocol §9.3).

## 4 Results

### 4.1 Registered hypotheses

**Table 1.** Registered tests, by arm (`paper/results/RESULTS.md`). One-sided p;
Holm-adjusted across H1–H4 within each arm.

| | A1 (*T* = 2009) | A2 (*T* = 2013) |
|---|---|---|
| H1 lists used | 15 | 17 |
| **H1** mean ρ [95 % CI] | 0.01 [−0.13, 0.16] | −0.03 [−0.16, 0.11] |
| H1 p (Holm) | 0.44 (0.89) | 0.68 (1.00) |
| **H2** mean Δρ [95 % CI] | −0.13 [−0.27, −0.02] | −0.11 [−0.28, 0.01] |
| H2 p (Holm) | 0.99 (0.99) | 0.91 (1.00) |
| **H3** P(bridge > single) [95 % CI] | 0.72 [0.62, 0.81] | 0.72 [0.64, 0.80] |
| H3 median share, bridge vs single | 0.093 vs 0.026 | 0.086 vs 0.011 |
| H3 n (bridge, single) | 27, 99 | 41, 104 |
| H3 p (Holm) | 0.0002 (0.0007) | 0.00002 (0.00005) |
| **H4** P(blind > covered) [95 % CI] | 0.14 [0.04, 0.26] | 0.11 [0.02, 0.22] |
| H4 median share, blind vs covered | 0.006 vs 0.053 | 0.005 vs 0.053 |
| H4 n (blind, covered) | 39, 14 | 26, 16 |
| H4 p (Holm) | 0.00003 (0.0001) | 0.00001 (0.00005) |
| **Headline:** top-decile / median uptake [95 % CI] | 1.68 [0.88, 2.90] | 2.09 [1.00, 4.16] |
| **Supported** | H3, H4 | H3, H4 |

**H1 and H2 were not supported in either arm.**
- Within the lists the tool produced, a topic's rank carried no information
  about its later share of funding.
- Ranking the same topics by their raw document frequency across both corpora
  did better: decisively in A1 (the interval excludes zero), and in the same
  direction in A2.

**H3 and H4 were supported, and replicated across arms with almost identical
effect sizes.**
- A randomly chosen bridge topic took up more later funding than a randomly
  chosen single-corpus topic about 72 % of the time.
- A randomly chosen blind-spot code took up more than a covered code only 11–14 %
  of the time.

**The headline effect is ambiguous.** The tool's top decile took up 1.7–2.1
times the median topic's share. Both intervals reach 1, so the registered
headline effect is not distinguishable from no advantage.

**Secondary measures** (descriptive, as registered):
- Mean within-list ρ with project count was 0.00 and −0.05; with participating
  organisations, 0.02 and −0.04.
- With later EUR-Lex acts it was 0.13 and 0.10: the only outcome on which the
  ranking leaned, weakly, the predicted way.

### 4.2 Exploratory: classification beyond frequency

**Table 2.** Partial Spearman correlation of class with uptake, controlling for
input-corpus frequency (`paper/results/exploratory/FREQUENCY_CONTROL.md`).
**Exploratory, not registered.**

| | A1 | A2 |
|---|---|---|
| ρ(input frequency, uptake), topics | 0.74 | 0.81 |
| **H3** partial r [95 % CI] | 0.16 [−0.03, 0.34] | 0.19 [0.02, 0.36] |
| H3 one-sided p | 0.041 | 0.046 |
| H3 P(bridge > single), by frequency tercile (low, mid, high) | 0.91, 0.66, 0.57 | 0.87, 0.66, 0.50 |
| ρ(input frequency, uptake), codes | 0.69 | 0.79 |
| **H4** partial r [95 % CI] | −0.03 [−0.30, 0.25] | 0.07 [−0.35, 0.40] |
| H4 blind / covered codes in the top frequency tercile | 3 / 14 | 0 / 14 |

**Frequency alone does most of the work.**
- How often a term appeared in the 2009 or 2013 corpus correlates 0.7–0.8 with
  its later share of funding.
- The bridge label keeps a modest association with uptake beyond that,
  consistently in both arms. It is concentrated among rare terms, where a
  bridge topic beats a single-corpus topic nearly nine times in ten.
- Among common terms the label adds little or nothing.

**H4 cannot be separated from frequency.** Covered codes sit almost entirely in
the top frequency tercile and blind spots in the lower two. The registered H4
effect may be real, but these data cannot distinguish it from common words
staying common.

### 4.3 Case studies

[TIER B: ten organisations, five per arm, sampled under protocol B.6
(`paper/cases/`). Summarise status today (operating, merged, dissolved),
trajectory since *T*, and the link, if any, between the sampled topic and what
the organisation did. Report attrition as a finding (protocol §5.2).]

### 4.4 Retrieval quality

[RATERS: two domain raters, 60 documents each with 20 in common, blinded to
rank and topic class (protocol §5.3, B.7). Report precision and Cohen's κ.]

## 5 Discussion

### 5.1 What the tool sees, and what it does not

**The tool's lists contain information about the future; their order does
not.** Whether a topic is a bridge topic, or a codebook code a blind spot,
told us something about later funding, robustly and in two independent
periods. Where a topic sat within its list told us nothing. This matters for
how such tools are presented: most interfaces lead with a ranked list.

**Part of H2 is a mismatch of information, and we report it as one.**
- The tool's single-corpus lists are ordered by frequency on *one* side.
- The registered comparator counted *both* sides.
- So "the tool loses to naive counting" partly means "one-sided counting loses
  to two-sided counting". That is itself an argument for the bridge construct.
- H1, whose lists include the tool's bridge lists (ordered by the smaller of
  the two shares), was null too. The bridge ordering was not tested on its
  own, and we draw no conclusion about it separately.

**Most of what the classification captures is the persistence of vocabulary.**
- Terms that were common in EU policy and funding in 2009 stayed common.
- The bridge construct adds something beyond that. It is modest: partial r
  0.16–0.19, one interval reaching zero. It is concentrated where it would be
  most useful, among terms that are not yet common.
- That is the most defensible claim the evidence supports for the bridge idea.
  It is weaker than the claim such tools implicitly make, and it is the claim
  this paper makes.

### 5.2 A defect found by the back-test

**Some of the tool's "topics" were filler words.** The single-corpus lists
included *will*, *develop*, *part* and *aims*. *will* alone matched projects
carrying 90 % of the EC contribution in A1's outcome window.

**These words could not have created the H3 or H4 effects.** They are
single-corpus topics, and H4 concerns codebook codes. They do dilute the
ranked lists that H1 and H2 test.

**The fix came after registration.** The stop list was extended after the
registered run, guarded by a test, and none of the registered results uses the
fixed version (protocol B.5). A back-test that finds a defect in the tool it
tests has done part of its job. We report it as a result.

### 5.3 For tool builders and users

[DRAFT — to develop with co-authors]
- **Publish a frequency baseline next to every ranking.** If the ranking does
  not beat it, say so in the interface.
- **Treat classifications as evidence and orderings as presentation**, unless
  an ordering has been back-tested.
- **Back-testing is feasible with open data.** CORDIS and CELLAR reach back far
  enough to freeze corpora at past dates. The integrity cost is mostly
  procedural: freeze, select by rule, record hermetically, register, run once.

### 5.4 Limitations

- **Scope.** Agriculture and mining, at EU level, from English-language
  sources. The ten scope keywords define the input. A different scope may
  behave differently.
- **Matching.** A leading word boundary means *land* also matches *landscape*.
  This was registered and applied as registered. It inflates the uptake of
  short terms equally in every comparison, but it is coarse.
- **Uptake.** EC contribution share measures funding attention, not impact. It
  says nothing about whether funded work succeeded.
- **Shared vocabulary.** The tool's topics and our outcome matching both rely on
  vocabulary, so a shared drift in wording (a term falling out of fashion) is
  read as uptake or its absence.
- **H4 circularity.** The same codebook drives the tool's coverage panel and
  the H4 units, so H4 tests the panel against its own vocabulary. We stated
  this before registration.
- **Retrieval quality** rests on a two-rater relevance check of a sample of
  returned documents (§4.4), not on the full set.
  [RATERS: results pending]
- **Tier B.** Its frame was redefined twice. The second time came after a
  draw had been seen. Its cases are illustrative and are not evidence for or
  against the tool.

## 6 Conclusion

**Frozen at 2009 and 2013 and tested against what the EU funded afterwards,
the Policy & Grant Finder's ranking did not see ahead.** Its classification
did. Bridge topics took up more later funding and blind spots less, in both
periods. Most of that signal is the persistence of common vocabulary, and the
bridge construct adds a modest amount beyond it.

A tool of this kind should be judged against a frequency baseline. On that
standard, this one earns a narrower claim than it makes: it helps sort topics,
not rank them.

---

## Data and code availability

**Everything is public.**
- Protocol, pre-registration, frozen corpora with manifests, query selections,
  recorded tool output, outcome data, analysis code, results, and case
  dossiers: repository `Tobi-Wan-Kenob1/GreenInformationFactory_Prototype`,
  branch `claude/validation-paper`. The registered state is tagged `prereg-v1`.
- Registered material, archived: Zenodo, doi:10.5281/zenodo.24392976.
- Pre-registration: OSF, doi:10.17605/OSF.IO/QC2SP, with two same-day updates.
- The tool under test, at commit `8ff0b35`, is in the same repository.

A Zenodo release of the full results, analysis code and case dossiers
accompanies submission, with its own DOI.

## Funding

BioFairNet, Horizon Europe, grant agreement 101181568.

## Author contributions

[CRediT statement, once the author list is fixed]

## Competing interests

**Some authors developed the tool under test.** This is why queries were
selected by rule from an independently produced codebook, the analysis was
pre-registered and frozen before outcome retrieval, and every step is public.

Authors' own institutions are excluded from the case-study sample (protocol
B.6).

[Complete per journal policy.]

## References

[REF list to be compiled. Needed at least for:
- research-intelligence and horizon-scanning tools;
- policy–science alignment;
- forecast evaluation and out-of-sample testing;
- pre-registration and analytic flexibility;
- CORDIS and EUR-Lex as research data;
- BioFairNet D1.2.]
