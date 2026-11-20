# Correcting the OSF registration (doi:10.17605/OSF.IO/QC2SP)

Read back through OSF's public API on 2026-11-20. The registration is public,
accepted and dated 2026-11-20T08:27:36Z, but it differs from the
pre-registration in four ways. The template on screen was newer than the one
`OSF_FILING.md` was written against, which explains most of them:

| Field | As filed | Problem |
|---|---|---|
| Foreknowledge of data | *Data exists but the authors have not observed it yet … certify that they have not accessed any of that data* | **Not true.** The CORDIS files with the outcome-window projects were downloaded and their field completeness inspected (pre-registration §9.1). |
| Explanation of foreknowledge | empty | The §9.1 disclosure belongs here. |
| Sample size | the rationale text, duplicated | The sample-size text is missing. |
| Causal interpretation, additional blinding, randomization, other planned analysis | empty | |
| Files | none attached | "Data collection procedures" says the data are *attached as prereg-v1-data.zip*. |

No hypothesis, measure, test or threshold differs. Everything filed matches
the pre-registration at commit `8d023f4`.

**How to fix it:**
1. Deposit the files (step A).
2. Link them under Resources (step B).
3. Submit an Update (step C).

A registration's files cannot be changed after submission, even by an Update.
Resources can be added at any time, and the Update records its justification
next to the original. Don't withdraw and re-file: that throws away the
timestamp, which is the point of registering.

---

## A — deposit the three files (≈ 5 min)

1. osf.io → **Create new project**.
   - Title: `Policy & Grant Finder back-test — registered material (prereg-v1)`
   - Storage: Germany – Frankfurt.
2. **Files** → upload the three files sent earlier: `PREREGISTRATION.md`,
   `PROTOCOL.md` and `prereg-v1-data.zip`.
3. Make the project **Public**: Settings, or the *Make Public* button.
4. Project overview → **Create DOI**. Note the DOI.

The files' SHA-256s, which the Update below quotes so the deposit can be checked:

```
78d91753e665319926dbe1434e7bd22f2bca010c4a456dac3c1c1f0d120e8990  PREREGISTRATION.md
58cfa8b6761c53b1bfb6a597aab4ca2507a88b9244efb0eb9127672b3dfd336d  PROTOCOL.md
876fac9996bd4ebd14437a3b484865a8d27f924236a4df8074f4692c46b253e2  prereg-v1-data.zip
```

## B — link it to the registration

Open the registration → **Resources** → **Add resource**. Add it twice with the
project DOI from A.4:
- **Data**, with the description `Frozen corpora, query selections and recorded tool output (paper/data at tag prereg-v1)`
- **Materials**, with the description `Pre-registration document and study protocol at tag prereg-v1`

## C — submit an Update

Registration → **Updates** → **Update**. Paste the justification, then change
only the fields below. Leave every other field as it is.

**Justification**
```
Corrections made on the day of registration, before any outcome data was retrieved or analysed. No hypothesis, outcome measure, test, threshold or exclusion is changed; every corrected field now matches the pre-registration document at commit 8d023f45439b2b8c19b8956d628b71194ecd5b78 (tag prereg-v1).
(1) Foreknowledge: the option first selected certified that the authors had not accessed the data. That was wrong: the CORDIS files containing outcome-window projects had been downloaded and their field completeness inspected. The option is corrected and the explanation, omitted at filing, added.
(2) Sample size: the field repeated the sample-size rationale; the sample-size text is restored.
(3) Four fields left empty at filing (causal interpretation, additional blinding, randomization, other planned analysis) are completed from the same document.
(4) The registration was created without attached files although "Data collection procedures" said the data were attached. The files are deposited in a public OSF project linked under Resources, and their SHA-256 checksums are given in that field so the deposit can be verified.
```

**Foreknowledge of data or evidence** → select:
> **Authors' limited observation of the data could not influence their analysis decisions.**

**Explanation of foreknowledge and managing unintended influences**
```
What was accessed: the CORDIS bulk project files for FP5, FP6, FP7, H2020 and Horizon Europe, which contain the outcome-window projects, and EUR-Lex/CELLAR for acts up to each freeze date.
What was observed: only how completely fields are filled (signature date, SME flag, activity type, organisation identifiers), across all programmes. This fixed two design choices before any analysis depended on them: start date stands in for the empty signature date, and SME status cannot be a sampling stratum. Neither carries information about which topics were later funded.
What was not done: no outcome-window project has been matched to any topic or query; no EC contribution, project count or organisation count has been computed for any topic; no outcome-window EUR-Lex act has been retrieved. None of the outcome measures exists in any form.
How influence is managed: the input corpora are frozen and checksummed (manifests in paper/data/), the queries are selected by a fixed rule from an independent codebook, and the tool's output was recorded before registration. Each step is in a dated public commit before this registration (tag prereg-v1). Full statement: PREREGISTRATION.md §9.1.
```

**Study type**: uncheck *Other* and check
> **Non-randomized study**

(It is correlational on archival records, and that option now exists.)

**Intention for causal interpretation** → check:
> **No causal relationship inferred**

**Additional blinding during research or analysis**
```
For the secondary retrieval-quality check only: two raters score returned documents for topical relevance in randomised order, with the tool's rank and topic class hidden (PREREGISTRATION.md §11).
```

**Randomization**
```
No randomisation of units. Permutation and bootstrap procedures use seeds fixed in the analysis code and reported.
```

**Data collection procedures**: replace only the line
`Archived at paper/data/ in the repository, commit 8d023f45439b2b8c19b8956d628b71194ecd5b78; also attached as prereg-v1-data.zip.`
with
```
Archived at paper/data/ in the repository, commit 8d023f45439b2b8c19b8956d628b71194ecd5b78 (tag prereg-v1). A copy is deposited in the public OSF project linked under Resources, SHA-256:
  78d91753e665319926dbe1434e7bd22f2bca010c4a456dac3c1c1f0d120e8990  PREREGISTRATION.md
  58cfa8b6761c53b1bfb6a597aab4ca2507a88b9244efb0eb9127672b3dfd336d  PROTOCOL.md
  876fac9996bd4ebd14437a3b484865a8d27f924236a4df8074f4692c46b253e2  prereg-v1-data.zip
```

**Sample size**
```
Fixed by the frozen corpora and the query rule, not chosen. Broad seed set: 10 queries per arm, 122 (A1) and 129 (A2) distinct topics. Bridging seed set: 8 queries in A1 (only eight codes occur on both sides of the 2009 corpus; the rule does not pad) and 10 in A2, 126 and 145 distinct topics. H4: 87 codebook codes per arm; A1: 39 blind spots vs 14 covered (34 neither, left out); A2: 26 blind spots vs 16 covered (45 neither, left out).
```

**Other planned analysis**
```
Tier B case studies (about 10 organisations, stratified by CORDIS activity type and country, FP7 onward, including dissolved entities) are illustrative mechanism evidence only, with no causal attribution (PREREGISTRATION.md §8). A secondary retrieval-quality check: two raters, about 100 documents, Cohen's kappa on 20 in common (§11). Any analysis not listed in this registration is reported as exploratory.
```

Then **Review** → **Submit**. As the only admin you'll be asked to **Accept
Changes**.

Tell me when it's through. I'll re-run the check, which compares the deposit's
hashes too, and record the registration as filed.
