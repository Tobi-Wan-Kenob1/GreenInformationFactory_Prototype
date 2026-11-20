# Validation study — paper workspace

**Public, and conducted in the open** — see `PROTOCOL.md` §11.

Everything for the validation paper on the Policy & Grant Finder lives here, on
the `claude/validation-paper` branch. The tool itself lives on `main`; this
branch adds the study around it.

Pin the tool by commit when it matters: a frozen corpus is only reproducible
against a stated commit, so the manifests record the commit hash rather than a
branch name.

| File | What it is |
|------|------------|
| `PROTOCOL.md` | The study protocol — design, hypotheses, data sources, analysis plan, limitations. **Read this first.** |
| `PREREGISTRATION.md` | Generated from the protocol. Not yet filed; §9 lists what is still to be pasted in at filing. |
| `analysis/wp0_probe.py` | Read-only data-availability probe. Takes section letters (`A` catalogue, `B` CORDIS, `C` Eurostat, `D` GLEIF, `E` ETS) to re-check one source; findings are recorded in protocol §6.1. |

Planned, not yet present: `data/` (frozen corpora and linked outcome tables)
and the scripts producing the paper's figures and tables. The frozen corpora
currently live as Actions artifacts, named in `PREREGISTRATION.md` §4.

The probe needs internet access to EU hosts, which some development sandboxes
deny, so it runs on a GitHub Actions runner via
`.github/workflows/wp0-probe.yml` — with an optional
`sections` input to re-check one source. If that file is missing, the probe
still runs anywhere with Python, `requests` and ordinary internet access.

## The one rule that matters

The study is a **back-test**: the tool is run on a corpus frozen at a past date,
its ranking is recorded, and only then is it compared against what subsequently
happened. That ordering is what makes the result credible, and it is easy to
destroy by accident.

So: **no outcome data is retrieved until the protocol is pre-registered and the
frozen tool output is committed and tagged.** Protocol §8 says what gets frozen;
§4.2 explains the specific leakage trap (feeding later-awarded CORDIS projects
in as if they were the historical funding landscape) and how the design avoids
it.

If you need to look at outcome data to settle a design question, do it on a
separate scratch branch and record it as exploratory — don't fold it back into
the frozen inputs.

## Status

- [x] Design restructured around what the tool actually claims
- [x] Protocol drafted (v0.1, for co-author review)
- [x] WP0 — CORDIS / ETS / Eurostat / GLEIF confirmed; findings in §6.1
- [x] WP1 — on the tool branch: date-window defect fixed; `gif cordis` adapter
      added (extends the tool below 2014 — CORDIS reaches FP1/1984); act-text
      enrichment and the routine-act filter (§6.2)
- [x] WP2 — corpora frozen with manifests, queries selected by rule, tool
      output recorded; pre-registration drafted
- [ ] WP2 — **file the registration and tag the repository.** Nothing in WP3
      may start before this: see `PREREGISTRATION.md` §9
- [ ] WP3 — outcomes and analysis
- [ ] WP4 — case studies
- [ ] WP5 — write-up and FAIR release

Tool changes go on `main`. This branch carries the study, not the instrument.
