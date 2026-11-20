# Filing the pre-registration on OSF — what to enter where

> **Filed 2026-11-20 as [doi:10.17605/OSF.IO/QC2SP](https://doi.org/10.17605/OSF.IO/QC2SP).**
> The template on screen was a newer version than the one this guide was
> written against: its field names and options differ. What that caused,
> and the correction, are in `OSF_UPDATE.md`.

**Where:** OSF Registries, <https://osf.io/registries> — free, run by the Center
for Open Science, time-stamped and read-only once submitted, and it issues a DOI
for public registrations. It is the standard registry for non-clinical
pre-registrations and what journals' open-science badges check against.

**Template:** **"OSF Preregistration"** (the standard one,
doi:10.17605/OSF.IO/WEKMB). It covers hypotheses, design, sampling, variables
and analysis, which is the shape of our document. The "Open-Ended Registration"
would also be accepted, but reviewers look for the structured fields.

**What fixes it:** the repository state below. Every hash in the registration
can be checked against these files.

- Repository: <https://github.com/Tobi-Wan-Kenob1/GreenInformationFactory_Prototype>
- Branch `claude/validation-paper`, commit `8d023f45439b2b8c19b8956d628b71194ecd5b78`, tag `prereg-v1`
- Pre-registration: `paper/PREREGISTRATION.md` · Protocol: `paper/PROTOCOL.md`
- Corpora, query selections, recorded output: `paper/data/`

Field labels below are OSF's as of November 2026; if one reads slightly
differently on screen, the order is the same.

---

## Step 1 — make an OSF project and upload the three files (≈ 5 min)

Registering *from a project* archives the project's files with the
registration, permanently. Files cannot be added once it is submitted, so
upload them first.

1. Sign in at osf.io → **Create new project**.
   - Title: `Policy & Grant Finder back-test (BioFairNet)`
   - Storage location: **Germany – Frankfurt** (EU data, EU project).
2. In the project → **Files** → OSF Storage → upload:
   - `PREREGISTRATION.md`
   - `PROTOCOL.md`
   - `prereg-v1-data.zip` (the `paper/data/` folder, 2.3 MB)

   All three were sent to you in this conversation, so on the iPad: save them
   to Files, then upload from Files.
3. Leave the project **private** for now. A registration's privacy is set
   separately from the project's.

## Step 2 — start the registration

Project → **Registrations** tab → **New registration** → choose
**OSF Preregistration** → **Create draft**.

## Step 3 — metadata page

| Field | Enter |
|---|---|
| **Title** | `Does the Policy & Grant Finder's ranking predict what was funded? A pre-registered back-test on EU policy and funding records, 2009 and 2013` |
| **Description** | `Back-test of an open-source tool that ranks topics across EU policy documents and EU-funded projects. The tool was run on corpora frozen at 2009-12-31 and 2013-12-31; its recorded output is compared with what the EU funded afterwards. Corpora, query selection and tool output are archived with SHA-256 manifests before any outcome measure was computed. Scope: agriculture and mining, EU level. Part of BioFairNet (Horizon Europe, grant 101181568).` |
| **Contributors** | You, as admin. Co-authors can be added later. Contributors stay editable after submission, so the deferred author list is not a problem. Every admin must approve, so add others as *Read* if you don't want them in the approval loop. |
| **License** | `CC-By Attribution 4.0 International` |
| **Subjects** | Social and Behavioral Sciences → Public Policy; Life Sciences → Agriculture; Social and Behavioral Sciences → Science and Technology Studies |
| **Tags** | `back-test`, `research funding`, `EU policy`, `CORDIS`, `EUR-Lex`, `bioeconomy`, `agriculture`, `mining`, `BioFairNet`, `preregistration` |

## Step 4 — the template, field by field

Each answer below can be pasted as is. Where it says "see §n", the attached
`PREREGISTRATION.md` has the full text. Pasting the summary *and* pointing to
the attachment is normal practice.

### Study information

**Hypotheses**
```
Four directional hypotheses, each tested against a comparator fixed in advance (PREREGISTRATION.md §2):
H1  The tool's topic ranking predicts subsequent funding uptake. Comparator: random rankings, permutation test, 10,000 draws. Broad seed set.
H2  The full pipeline beats naive counting. Comparator: raw keyword document-frequency ranking. Broad seed set.
H3  Bridge topics (present in both policy and funding corpora) show higher subsequent uptake than single-corpus topics. Bridging seed set.
H4  Codebook codes the tool flags as blind spots show lower subsequent uptake than covered codes. Bridging seed set.
Not under test: the tool's indicative CO2 and cost figures, which are assumption-based heuristics (§1).
```

### Design plan

**Study type** → choose **Other** and enter:
```
Retrospective validation (back-test) of a software tool on archival administrative records: EUR-Lex/CELLAR legislation and CORDIS project records.
```

**Blinding** → choose **No blinding is involved in this study.**

**Is there any additional blinding in this study?**
```
For the secondary retrieval-quality check only: two raters score returned documents for topical relevance in randomised order, with the tool's rank and topic class hidden (§11).
```

**Study design**
```
Two freeze points, an internal replication: arm A1 at T = 2009-12-31 (outcome window 2010-2026) and arm A2 at T = 2013-12-31 (outcome window 2014-2026). For each arm the input corpus contains only records available at T: EU acts dated on or before T, and FP6/FP7 projects that started on or before T (enforced in code; signature date is empty in both programmes, so start date is used, which is conservative). Input and outcome sets are disjoint by construction. The tool was run on the frozen corpus and its output recorded before any outcome measure was computed. Unit of analysis: the topic (122-145 distinct topics per arm and seed set); for H4, the codebook code (87). Details: PREREGISTRATION.md §3-§5.
```

**Randomization**
```
No randomisation of units. Permutation and bootstrap procedures use seeds fixed in the analysis code and reported.
```

### Sampling plan

**Existing data** → choose **Registration prior to analysis of the data.**

**Explanation of existing data**
```
The input corpora have been built, frozen and archived, and the tool has been run on them; that is the design. The CORDIS bulk files that contain the post-T outcome projects were downloaded and their field completeness inspected (signature date, SME flag, activity type, organisation identifiers), which determined design choices before any of them depended on outcomes. No post-T project has been matched to any topic; no outcome measure has been computed in any form; no outcome-window EUR-Lex act has been retrieved. Full statement: PREREGISTRATION.md §9.1. Every step's output is in a dated public commit before this registration.
```

**Data collection procedures**
```
Input: EUR-Lex via the CELLAR SPARQL endpoint (agriculture and mining subject codes; routine market instruments excluded by 13 title fragments naming instrument types; opening recitals added from CELLAR), and CORDIS bulk project files for FP6 and FP7. Frozen with `gif freeze`, which refuses a corpus that breaches its window or whose sources only partly answered, and writes a manifest of per-file SHA-256s and content digests.
Registered corpora (manifest.json SHA-256):
  A1  afd89a28d22cf15cab6ac1947137f98ee1ed87297f0f1c3e634263f29c44a1a8  (827 documents: 148 acts, 679 projects)
  A2  9e8993581ed95109d7fd2680ab0ead992b32ed4efc7b20bbb0075df3a9fe8cb5  (1,523 documents: 150 acts, 1 call, 1,372 projects)
Archived at paper/data/ in the repository, commit 8d023f45439b2b8c19b8956d628b71194ecd5b78; also attached as prereg-v1-data.zip.
Queries: derived by rule from the independent BioFairNet WP1/D1.2 literature codebook (§5); neither the tool's author nor the analyst picks them.
Outcomes (after registration): CORDIS FP7, H2020 and Horizon Europe projects starting in the outcome window, and EUR-Lex acts in the outcome window, matched to topics by the same word-boundary rule.
```

**Sample size**
```
Fixed by the frozen corpora and the query rule, not chosen. Broad seed set: 10 queries per arm, 122 (A1) and 129 (A2) distinct topics. Bridging seed set: 8 queries in A1 (only eight codes occur on both sides of the 2009 corpus; the rule does not pad) and 10 in A2, 126 and 145 distinct topics. H4: 87 codebook codes per arm; A1: 39 blind spots vs 14 covered (34 neither, left out); A2: 26 blind spots vs 16 covered (45 neither, left out).
```

**Sample size rationale**
```
No power analysis: the population is every topic the rule-selected queries produce from the complete frozen corpus. Because n is in the low hundreds, the effect size (top-decile vs median uptake ratio) is primary and significance secondary; a small but significant correlation will not be presented as evidence that the tool is useful (§7).
```

**Stopping rule**
```
Not applicable: archival data, complete corpora. For the illustrative Tier B case studies, topics are added in rank order until the organisation frame reaches 200 and stopped before it passes 600 (§8).
```

### Variables

**Manipulated variables**
```
None. The study is observational on archival records.
```

**Measured variables**
```
Predictor: the tool's recorded topic rank, bridge/single-corpus label and codebook coverage status (recorded.json, recorded-both-sides.json in paper/data/).
Primary outcome: EC contribution (EUR) to outcome-window projects whose title, objective or euroSciVoc classification matches the topic, as a share of total programme contribution in that window (absolute euros are not comparable across FP7, H2020 and Horizon Europe).
Secondary outcomes: matching project count; distinct participating organisations; count of outcome-window EUR-Lex acts matching the topic.
```

**Indices**
```
Uptake share = matched EC contribution / total EC contribution of all projects in the outcome window. Matching: leading word boundary, case-insensitive, no thesaurus.
```

### Analysis plan

**Statistical models**
```
H1/H2: unit = each recorded ranked list (run x scope) with at least five topics. Spearman's rho between tool rank and uptake rank per list; statistic = unweighted mean rho. H1 null: ranks permuted within lists, 10,000 draws. H2: comparator ranks topics by raw document frequency; sign-flip permutation of the per-list difference rho_tool - rho_frequency.
H3: distinct topics, bridge (bridge in any run) vs single-corpus; Mann-Whitney U.
H4: codebook codes; blind spot = 'not addressed' in every run of the bridging set, covered = addressed on both sides in at least one run; Mann-Whitney U.
Effect size reported in the abstract: top-decile vs median uptake ratio. 95% percentile bootstrap CIs, 10,000 resamples. Arms analysed separately and reported side by side, never pooled. Full text: PREREGISTRATION.md §7, §7.1, §7.2.
```

**Transformations**
```
Ranks for correlation. Outcome expressed as a share of programme contribution within the window, so programmes with different budgets are comparable. No other transformation.
```

**Inference criteria**
```
One-sided tests in the predicted direction, alpha = 0.05, Holm-Bonferroni across the four hypotheses within each arm. A hypothesis is supported in an arm only if its corrected test passes and the effect is in the predicted direction; support in both arms is reported as replicated, in one as not replicated. Effect size takes precedence over significance.
```

**Data exclusion**
```
None beyond those built into the frozen corpus (window rule; routine market instruments) and the query rule (codes matching >20% of either side, absent codes, duplicate term sets). No topic, project or act is removed after outcome data is seen.
```

**Missing data**
```
A topic matching no outcome-window project has uptake 0 and stays in. A project with no recorded EC contribution counts toward project and organisation counts, contributes EUR 0 to the primary measure, and the number of such projects is reported per arm. Acts whose text could not be retrieved (31 in A1, 27 in A2) are represented by title and metadata, as frozen.
```

**Exploratory analysis**
```
Tier B case studies (about 10 organisations, stratified by CORDIS activity type and country, FP7 onward, including dissolved entities) are illustrative mechanism evidence only, with no causal attribution (§8). A secondary retrieval-quality check: two raters, about 100 documents, Cohen's kappa on 20 in common (§11). Any analysis not listed above is reported as exploratory.
```

### Other

**Other**
```
Protocol: paper/PROTOCOL.md, with all pre-filing changes and their evidence in Appendix A (A.1-A.5). Recorded tool output SHA-256 (paper/data/):
  A1 recorded.json             208b11bb59ff88b1c1484583c582cacb47e19c2f6103a9dd2c35d9f81161ba4a
  A1 recorded-both-sides.json  caaa32d6a83f017265438560b49cd6b8f8eb740aaab5648b589888bad87d59cb
  A2 recorded.json             08be072d55cd4dee29f77866737a9f55973119fd23415b347b7dfda549fe309a
  A2 recorded-both-sides.json  d67b3fd44bd869f7edfbb4b2c69ce0909313d737766095508a67df332a0f22f3
Tool commit for the app under test: 8ff0b3537e5b9e1d938b2e90abc392811ac2c35e. Funding: BioFairNet, Horizon Europe grant 101181568. Target journal and author list are deferred and affect nothing registered here.
```

## Step 5 — submit

1. **Review** → **Register**.
2. If asked about components: none.
3. Choose **Make registration public immediately** (§9: public, not embargoed).
   Only public registrations get a DOI.
4. **Submit.** You get an approval e-mail. Approve it, or it auto-approves after
   48 hours. The registration date is the submission date either way.
5. Don't touch the project's files while it says *Archiving*. Changing them then
   makes the archive fail.

## Step 6 — afterwards (tell me the DOI)

- Metadata → **Funding**: European Commission · award number `101181568` ·
  award title `BioFairNet`.
- Send me the DOI. I'll write it into `PREREGISTRATION.md` (status: filed),
  README and protocol. Outcome retrieval (WP3) starts only after that commit.
- Optional: Resources → add the GitHub repo as **Analytic Code** once it has a
  DOI (e.g. via Zenodo), for the open-code badge.

If something must change after filing, use **Update** on the registration
(with a justification) and add a dated deviation to the protocol. Never
withdraw and re-file.
