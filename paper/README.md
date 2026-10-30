# Validation study — paper workspace

Everything for the validation paper on the Policy & Grant Finder lives here,
on the `claude/validation-paper` branch. The tool itself stays on `main`; this
branch adds the study around it.

| File | What it is |
|------|------------|
| `PROTOCOL.md` | The study protocol — design, hypotheses, data sources, analysis plan, limitations. **Read this first.** |
| `analysis/wp0_probe.py` | Read-only data-availability probe. Takes section letters (`A` catalogue, `B` CORDIS, `C` Eurostat, `D` GLEIF, `E` ETS) to re-check one source; findings are recorded in protocol §6.1. |

Planned, not yet present: `PREREGISTRATION.md` (generated from the protocol
before outcome data is retrieved), `data/` (frozen corpora and linked outcome
tables), further `analysis/` scripts producing the paper's figures and tables.

The probe needs internet access to EU hosts, which the development sandbox
denies, so it runs on a GitHub Actions runner via
`.github/workflows/wp0-probe.yml` — a temporary workflow that lives on this
branch and fires when the probe is pushed, so nothing had to be added to
`main`. Delete it once the data sources stop moving.

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
- [ ] WP1 — on `main`: fix the `finder-data` date-window defect; `gif cordis`
      adapter (extends the tool below 2014 — WP0 found CORDIS reaches FP1/1984)
- [ ] WP2 — freeze corpora, run tool, pre-register
- [ ] WP3 — outcomes and analysis
- [ ] WP4 — case studies
- [ ] WP5 — write-up and FAIR release

Tool changes go on `main`. This branch carries the study, not the instrument.
