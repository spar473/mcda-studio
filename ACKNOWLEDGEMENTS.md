# Acknowledgements, credits and licence scope

MCDA Studio is an independent project by Sooyoung Park. This file credits everything the project
relies on, and says exactly what the [MIT licence](LICENSE) does and does not cover. If you hold
rights in anything here and think it should be credited differently or removed, please open an
issue on the repository. It will be dealt with promptly.

## What the MIT licence covers

| Covered by MIT | **Not** covered by MIT |
| --- | --- |
| Source code in `src/`, `frontend/`, `tests/`, `scripts/` | Names and trademarks of third parties: DECERNS, and the startups and data providers named in the examples |
| Example build scripts and project files in `examples/` | Third-party software, which keeps its own licence (listed below) |
| Documentation written for this project | REA's own code, which is not included here |

## The original study report

- **Title and author:** *Prioritising New Zealand Deep-Tech Startups for Venture Capital Due
  Diligence*, Sooyoung Park, September 2026.
- **Copyright:** © 2026 Sooyoung Park. All rights reserved.
- **Not distributed:** the report is not included in this repository or its packages.
  [`docs/reference/original-study/`](docs/reference/original-study/README.md) holds its citation
  and a summary of how each section is encoded as data.
- **Sources:** the report's reference list credits its 15 public sources.

## DECERNS

The analysis in the original study was carried out in DECERNS, a multi-criteria decision analysis
software package (<https://decerns.com>), described in:

> Yatsalo, B., Didenko, V., Gritsyuk, S., & Sullivan, T. (2015). Decerns: A framework for
> multi-criteria decision analysis. *International Journal of Computational Intelligence Systems,
> 8*(3), 467. <https://doi.org/10.1080/18756891.2015.1023586>

- **No DECERNS material in the software.** MCDA Studio contains no DECERNS source code, binaries,
  assets, text or file formats. It was written independently from published MCDA mathematics and
  the report's printed results.
- **Canvas layout.** The Model canvas's general arrangement (goal on the left, objectives and
  criteria to the right, the options in a column beyond them, small markers for weighting and
  value functions) was modelled on the value tree shown in the report's Figure 1. It was
  implemented independently in HTML, CSS and SVG with its own visual design and wording, and uses
  no DECERNS assets.
- **No DECERNS inspection.** No DECERNS installation was ever inspected or reverse-engineered for
  this project.
- **No affiliation.** MCDA Studio is not affiliated with, endorsed by or compatible with DECERNS.
  Matching the report's numbers is not a compatibility claim. "DECERNS" is used only to describe
  the workflow that inspired the project.

## REA (Reverse Engineer Anything)

[REA](https://github.com/morluto/rea) (npm package `rea-agents`) is MIT-licensed, © its authors.
It was used as an optional, external research tool.

- **Not part of the application.** It is not bundled, imported or needed to build, test or run
  MCDA Studio.
- **Not included here:** the research notes and REA smoke test are not part of this
  public repository.
- **What it was run on:** only small test applications written for this project. It was never used
  on DECERNS.

## Real organisations and data sources

- **The startups.** The VC example names four real New Zealand startups: Hyades, Forever Harvest,
  Kura Dynamics and Outlier Space.
  - Their information comes from public sources cited in the report: company pages, funding news,
    and investor and programme notes.
  - The ratings are the author's screening judgements, not investment advice. See the disclaimer
    in [`examples/nz_deeptech_vc/README.md`](examples/nz_deeptech_vc/README.md).
  - None of the companies took part or reviewed the ratings.
- **Market data.** Single headline market-size and growth figures are taken, with citation, from
  published reports by Fortune Business Insights, Global Market Insights and Grand View Research.
  They are used only as screening proxies.
- **Initial criteria.** These were informed by the Vanguard programme and by Plug and Play Tech
  Center investor-deck material, as described in the report.
- **No affiliation or endorsement** from any of these organisations.

## Methods background

The mathematics follows standard multi-criteria decision analysis practice. Standard texts on these
methods include:

- Keeney, R. L., & Raiffa, H. (1976). *Decisions with Multiple Objectives: Preferences and Value
  Tradeoffs*. Wiley.
- von Winterfeldt, D., & Edwards, W. (1986). *Decision Analysis and Behavioral Research*. Cambridge
  University Press.
- Belton, V., & Stewart, T. J. (2002). *Multiple Criteria Decision Analysis: An Integrated
  Approach*. Kluwer Academic Publishers.

## Open-source software

MCDA Studio is built on the following direct dependencies, each under its own licence. Transitive
dependencies have their own licences, recorded in `frontend/package-lock.json` and in each installed
Python package.

**Python runtime:**

- NumPy (BSD-3-Clause; includes components under 0BSD, MIT and Zlib)
- Pydantic (MIT)
- Typer (MIT)
- Rich (MIT)
- FastAPI (MIT)
- Starlette (BSD-3-Clause)
- Uvicorn (BSD-3-Clause)

**Python development and build:**

- pytest (MIT)
- Hypothesis (MPL-2.0)
- SciPy (BSD-3-Clause; used only for independent cross-checks in tests)
- HTTPX (BSD-3-Clause)
- Ruff (MIT)
- mypy (MIT)
- Hatchling (MIT)

**Frontend runtime:**

- React and React DOM (MIT)

**Frontend development:**

- Vite and @vitejs/plugin-react (MIT)
- TypeScript (Apache-2.0)
- Vitest (MIT)
- Playwright Test (Apache-2.0)
- Testing Library: jest-dom, react, user-event (MIT)
- jsdom (MIT)
- ESLint, @eslint/js, typescript-eslint, eslint-plugin-react-hooks, globals (MIT)
- openapi-typescript (MIT)
- @types/node, @types/react, @types/react-dom (MIT)

The built frontend (`frontend/dist`, not committed) bundles React. Any future packaged release
must include the licence notices of bundled components.

## AI assistance

The software, tests and documentation were developed with AI coding assistants. The author directed
the work and reviewed the results. The assistants were:

- **OpenAI Codex**, the main implementation environment.
- **ChatGPT**, for architecture and mathematical review.
- **Anthropic Claude Code**, which is credited as co-author on commits made with it.

All numerical behaviour is checked by independent oracles and tests rather than taken on trust from
any tool.
