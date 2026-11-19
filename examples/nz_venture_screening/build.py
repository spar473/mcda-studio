"""Builds the venture screening study in examples/nz_venture_screening/ (November 2026).

"Which early-stage New Zealand startups should a hypothetical generalist seed/Series A fund
prioritise for its next due-diligence slots?" Eight real companies, public information only, as
of 4 November 2026. Every rating is the study author's judgement against the written rubrics in
docs/design/vc-screening-study.md; every fact behind a rating is a claim in evidence.json with its
source. Not investment advice, not a prediction of success, companies neither contacted nor
affiliated.

    python examples/nz_venture_screening/build.py

The model is built with the public services API, like the other examples, so the engine stays
domain-neutral: everything venture-specific is data in this file. Writes project.json,
evidence.json and decision.json, and refreshes the starter manifest that opens the study.
"""

import hashlib
import json
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from mcda_studio.domain.criteria import (
    ControlPoint,
    Direction,
    LinearValueFunction,
    PiecewiseLinearValueFunction,
    QualitativeValueFunction,
)
from mcda_studio.domain.decision import DecisionDetails
from mcda_studio.domain.evidence import Claim, EvidenceDossier, Origin, Review, Source
from mcda_studio.domain.outranking import (
    LinearPreferenceFunction,
    PrometheeCriterion,
    PrometheeModel,
    UsualFunction,
    VShapeFunction,
)
from mcda_studio.domain.preferences import AnalysisConfiguration, Scenario, WeightProfile
from mcda_studio.domain.project import Project
from mcda_studio.domain.requirements import LabelsRequirement
from mcda_studio.domain.scales import Scale, ScaleType
from mcda_studio.domain.sorting import SortingAudit, SortingModel
from mcda_studio.domain.uncertainty import (
    CategoricalDistribution,
    CellUncertainty,
    GroupUncertainty,
    SmaaModel,
    UniformDistribution,
)
from mcda_studio.services import decision_record_service as decisions
from mcda_studio.services import project_service as ps
from mcda_studio.storage.json_repository import JsonProjectRepository

HERE = Path(__file__).parent
STARTER = HERE.parent / "starter_templates" / "venture_screening_study"

#: Every fact is read on this date; a source published more than 12 months earlier is outdated.
AS_OF = date(2026, 11, 4)
OUTDATED_BEFORE = AS_OF - timedelta(days=365)
REVIEWED_AT = datetime(2026, 11, 4, 12, 0, tzinfo=timezone(timedelta(hours=13)))
AUTHOR = "Study author"
REVIEWER = "Study author (illustrative review)"

Kind = Literal["observed", "judgement", "proxy"]
Classification = Literal["independent", "self_reported", "unknown"]

# ----------------------------------------------------------------------------------------------
# Sources: key -> (name, URL, publication date or None when undated, relationship to the company)
# ----------------------------------------------------------------------------------------------

SOURCES: dict[str, tuple[str, str, date | None, Classification]] = {
    # Captivate Technology
    "massey_2026": (
        "Massey University news",
        "https://www.massey.ac.nz/about/news/massey-spin-out-captivate-technology-appoints-ceo-following-seed-funding/",
        date(2026, 2, 19),
        "self_reported",
    ),
    "kiwinet_cap": (
        "KiwiNet success story",
        "https://kiwinet.org.nz/SuccessStories/CaptivateTechnology",
        None,
        "self_reported",
    ),
    "ceda_cap": (
        "CEDA (Manawatū) success stories",
        "https://ceda.nz/?p=240732",
        date(2026, 6, 30),
        "independent",
    ),
    "masseyventures_2023": (
        "Massey Ventures news",
        "https://www.masseyventures.co.nz/10112023",
        date(2023, 11, 10),
        "self_reported",
    ),
    "svante_2022": (
        "Svante news release",
        "https://svanteinc.com/2022/12/15/chevron-invests-in-carbon-capture-and-removal-technology-company-svante/",
        date(2022, 12, 15),
        "independent",
    ),
    "carbonclean_2022": (
        "World Cement",
        "https://www.worldcement.com/special-reports/13052022/carbon-clean-raises-us150m-in-record-carbon-capture-funding-round",
        date(2022, 5, 13),
        "independent",
    ),
    # Wellumio
    "wellumio_home": ("Wellumio website", "https://www.wellumio.com/", None, "self_reported"),
    "wellumio_journey": (
        "Wellumio: Our Journey",
        "https://www.wellumio.com/ourjourney",
        None,
        "self_reported",
    ),
    "wellumio_disclaimer": (
        "Wellumio product disclaimer",
        "https://www.wellumio.com/disclaimer",
        None,
        "self_reported",
    ),
    "idealog_wel": (
        "Idealog",
        "https://idealog.co.nz/venture/2026/02/kiwi-stroke-diagnostic-venture-secures-7m",
        date(2026, 2, 11),
        "independent",
    ),
    "hlth_wel": (
        "HLTH news",
        "https://hlth.com/insights/news/wellumio-raises-7-28m-led-by-nuance-connected-capital-to-advance-portable-mri-for-stroke-care-2026-02-12",
        date(2026, 2, 12),
        "independent",
    ),
    "hitc_wel": (
        "HIT Consultant",
        "https://hitconsultant.net/2026/07/24/wellumio-closes-9m-pre-series-a-axana-portable-stroke-mri/",
        date(2026, 7, 24),
        "independent",
    ),
    "umd_hyperfine": (
        "University of Maryland ECE news",
        "https://ece.umd.edu/news/story/hyperfine-begins-trading-on-the-nasdaq-global-market",
        date(2021, 12, 23),
        "independent",
    ),
    # Scentian Bio
    "scoop_sce": (
        "Scoop press release",
        "https://www.scoop.co.nz/stories/SC2604/S00014.htm",
        date(2026, 4, 8),
        "self_reported",
    ),
    "uoa_sce": (
        "University of Auckland news",
        "https://www.auckland.ac.nz/en/news/2025/12/08/scentian-bio-reimagining-smell-as-sensors.html",
        date(2025, 12, 8),
        "independent",
    ),
    "gai_sce": (
        "Global AgInvesting",
        "https://globalaginvesting.com/?p=9588",
        date(2023, 9, 27),
        "independent",
    ),
    "aryballe_2020": (
        "Cosmetics Business",
        "https://cosmeticsbusiness.com/-digital-nose-creator-aryballe-raises-7m-to-meet-fragrance-technology-demand--167667",
        date(2020, 7, 13),
        "independent",
    ),
    # Hectre
    "punakaiki_hec": (
        "Punakaiki Fund announcement",
        "https://punakaikifund.co.nz/hectre-welcomed-to-punakaiki-fund-portfolio-in-12m-series-a-capital-raise/",
        date(2026, 2, 12),
        "self_reported",
    ),
    "fruitnet_hec": (
        "Fruitnet (Eurofruit)",
        "https://www.fruitnet.com/eurofruit/orchard-tech-firm-hectre-secures-funding-for-ai-based-expansion/270555.article",
        date(2026, 2, 13),
        "independent",
    ),
    "hectre_about": ("Hectre: About us", "https://hectre.com/about-us/", None, "self_reported"),
    "hectre_home": ("Hectre website", "https://www.hectre.com/", None, "self_reported"),
    "dir_sort": (
        "DIResearch via MarketPublishers",
        "https://marketpublishers.com/report/equipment/food-beverage-equipment/fruit-n-vegetable-sorting-machine-research-report-dir.html",
        date(2025, 6, 1),
        "independent",
    ),
    # Wych
    "startupdaily_wych": (
        "Startup Daily",
        "https://www.startupdaily.net/topic/funding/kiwi-data-fintech-wych-raises-nz1-5-million-for-open-banking/",
        date(2025, 9, 30),
        "independent",
    ),
    "wych_io": ("Wych website", "https://www.wych.io/", None, "self_reported"),
    "kiwibank_2026": (
        "Kiwibank media release",
        "https://www.kiwibank.co.nz/about-us/news-and-updates/media-releases/kiwibank-leads-market-with-open-banking-for-individual-business-customers/",
        date(2026, 5, 28),
        "independent",
    ),
    "cfotech_akahu": (
        "CFOtech Australia",
        "https://cfotech.com.au/story/red-bird-ventures-leads-1-4m-investment-in-nz-fintech-akahu",
        date(2023, 10, 13),
        "independent",
    ),
    # Upstock
    "upstock_about": ("Upstock: About", "https://www.upstock.app/about", None, "self_reported"),
    "startupdaily_ups": (
        "Startup Daily",
        "https://www.startupdaily.net/?p=112718",
        date(2023, 6, 30),
        "independent",
    ),
    "scoop_ups": (
        "Scoop press release",
        "https://www.scoop.co.nz/stories/BU2206/S00121.htm",
        date(2022, 6, 8),
        "self_reported",
    ),
    "insidefmcg_ups": (
        "Inside FMCG (partnered content)",
        "https://insidefmcg.com.au/2025/01/20/upstock-transforms-fmcg-by-automating-wholesale-ordering-and-logistics/",
        date(2025, 1, 20),
        "self_reported",
    ),
    "fmcgbusiness_ups": (
        "FMCG Business",
        "https://fmcgbusiness.co.nz/?p=47571",
        date(2024, 8, 13),
        "independent",
    ),
    "verdict_choco": (
        "Verdict Foodservice",
        "https://www.verdictfoodservice.com/news/choco-funding/",
        date(2021, 7, 21),
        "independent",
    ),
    # Kea Aerospace
    "newswire_kea": (
        "Newswire",
        "https://newswire.co.nz/2026/08/kea-aerospace-17-5-million-christchurch-factory-solar-aircraft/",
        date(2026, 8, 9),
        "independent",
    ),
    "kea_news": (
        "Kea Aerospace news and events",
        "https://www.keaaerospace.com/news-and-events/",
        None,
        "self_reported",
    ),
    "wiki_kea": (
        "Wikipedia: Kea Aerospace",
        "https://en.wikipedia.org/wiki/Kea_Aerospace",
        None,
        "independent",
    ),
    "wiki_rocket": (
        "Wikipedia: Mark Rocket",
        "https://en.wikipedia.org/wiki/Mark_Rocket",
        None,
        "independent",
    ),
    "caplight_kea": (
        "Caplight company page",
        "https://www.caplight.com/company/keaaerospace",
        None,
        "unknown",
    ),
    "totaltele_aalto": (
        "Total Telecom",
        "https://totaltele.com/ntt-docomo-and-space-compass-commit-100m-to-haps-specialist-aalto/",
        date(2024, 6, 3),
        "independent",
    ),
    # Hnry
    "hnry_news": (
        "Hnry news",
        "https://hnry.co.nz/resources/news/hnry-raises-30-mil-to-accelerate-growth/",
        date(2025, 12, 8),
        "self_reported",
    ),
    "hnry_home": ("Hnry website", "https://hnry.co.nz/", None, "self_reported"),
    "hnry_about": ("Hnry: About", "https://hnry.co.nz/about/", None, "self_reported"),
    "hnry_xero": (
        "Hnry: compare with Xero",
        "https://hnry.co.nz/compare/xero/",
        None,
        "self_reported",
    ),
}

# ----------------------------------------------------------------------------------------------
# Value tree. Labels on every labelled scale run from worst to best for the fund.
# ----------------------------------------------------------------------------------------------

FIVE = (0.0, 0.25, 0.5, 0.75, 1.0)
FOUR = (0.0, 1 / 3, 2 / 3, 1.0)

OBJECTIVES = [
    ("mandate", "Mandate (screened, not scored)"),
    ("team", "Team"),
    ("problem_solution", "Problem and solution"),
    ("market", "Market"),
    ("traction", "Traction"),
]

HQ_LABELS = ["Other", "Australia", "New Zealand"]
STAGE_LABELS = ["Pre-seed", "Seed", "Series A", "Series B or later"]
SECTORS = [
    "Climate and energy",
    "Health and medtech",
    "Agritech and food",
    "Fintech and B2B software",
    "Space and advanced hardware",
    "Consumer and marketplaces",
]
SECTOR_LABELS = ["Other", *SECTORS]


@dataclass(frozen=True)
class Leaf:
    id: str
    name: str
    parent: str
    labels: tuple[str, ...]  # empty for a numeric leaf
    rubric: str


LEAVES: list[Leaf] = [
    Leaf("hq_country", "HQ country", "mandate", tuple(HQ_LABELS), "Country of the head office."),
    Leaf(
        "stage",
        "Stage",
        "mandate",
        tuple(STAGE_LABELS),
        "Last disclosed round by the primary source's label; pre-Series A maps to Seed; without "
        "a published label, a judgement from round size and dilution.",
    ),
    Leaf("sector", "Sector", "mandate", tuple(SECTOR_LABELS), "The study's own sector label."),
    Leaf(
        "founder_problem_fit",
        "Founder-problem expertise",
        "team",
        (
            "No public evidence",
            "Adjacent experience",
            "3+ years in the domain",
            "Recognised domain expert",
            "Core inventor with commercial experience",
        ),
        "1 no public evidence of domain experience; 2 adjacent field or under 3 years; 3 at least "
        "3 years in the target industry or its research field; 4 recognised expert (doctorate "
        "plus 5 years, or senior operating role in the industry); 5 the founder's own work is the "
        "basis of the core product, plus commercial experience in the target industry.",
    ),
    Leaf(
        "team_completeness",
        "Team completeness",
        "team",
        (
            "One key role named",
            "Two key roles named",
            "All three, one part-time",
            "All three full-time",
            "Next-stage leads named",
        ),
        "Technical, commercial and domain/regulatory leads, each a named person: 1 one; 2 two; "
        "3 all three, one part-time or advisory; 4 all three full-time; 5 plus named leads for "
        "the next stage's main function.",
    ),
    Leaf(
        "track_record",
        "Prior venture or operating track record",
        "team",
        (
            "None public",
            "Prior venture or 5+ years operating",
            "Senior role at scale or funded venture",
            "Prior exit or scaled-company executive",
            "Several founders at that level",
        ),
        "1 none public; 2 prior venture with no known outcome, or 5+ years operating; 3 senior "
        "role in a company of 100+ staff, or a prior venture that raised outside capital; 4 a "
        "prior venture with a known exit, or executive of a scaled company; 5 two or more at 4.",
    ),
    Leaf(
        "board_advisors",
        "Advisors, board and key hires",
        "team",
        (
            "None named",
            "Named, not domain-relevant",
            "Independent chair or domain advisor",
            "Sector and investor directors",
            "Directors plus senior industry hire",
        ),
        "1 none named; 2 named without relevant domain or investor experience; 3 an independent "
        "chair or one relevant domain advisor; 4 sector and investor directors; 5 level 4 plus a "
        "named senior hire from a leading firm in the target industry.",
    ),
    Leaf(
        "problem_severity",
        "Problem severity and willingness to pay",
        "problem_solution",
        (
            "Company statement only",
            "Independently confirmed",
            "Cost independently quantified",
            "Quantified with a budget holder",
            "Customers already pay for a substitute",
        ),
        "1 stated only by the company; 2 an independent source confirms it; 3 an independent "
        "source quantifies its cost or impact; 4 plus a named budget holder or obligation; 5 plus "
        "evidence that customers already pay for an inferior substitute.",
    ),
    Leaf(
        "defensibility",
        "Differentiation and defensibility",
        "problem_solution",
        (
            "None stated",
            "Claimed, no protectable asset",
            "Filed patent or proprietary data",
            "Granted patent or exclusive licence",
            "Granted IP plus compounding advantage",
        ),
        "1 none stated; 2 differentiation claimed, no protectable asset; 3 filed patent, exclusive "
        "licence or proprietary dataset; 4 granted patent or exclusive licence in a major market; "
        "5 plus a publicly evidenced compounding advantage.",
    ),
    Leaf(
        "readiness",
        "Product or technology readiness",
        "problem_solution",
        ("Concept", "Prototype", "Pilot-ready", "Commercial"),
        "Concept, prototype, pilot-ready (in pilots or trials), commercial (sold and delivered).",
    ),
    Leaf(
        "regulatory_burden",
        "Regulatory and certification burden (minimise)",
        "problem_solution",
        (
            "Approval required, not started",
            "Approval required, under way",
            "Approved in one market or certification only",
            "No approval required",
        ),
        "Worst to best: approval required and not started; required and under way; obtained in "
        "one major market or certification only; no product approval required.",
    ),
    Leaf(
        "market_size",
        "Addressable market size",
        "market",
        (),
        "US$ bn, 2025, the median of distinct publishers' public estimates for the narrowest "
        "named segment containing the core product.",
    ),
    Leaf(
        "market_growth",
        "Market growth",
        "market",
        (),
        "% CAGR, the median of the same publishers' stated forecast CAGRs.",
    ),
    Leaf(
        "competitive_intensity",
        "Competitive intensity (minimise)",
        "market",
        (
            "Several funded leaders",
            "One or two funded leaders",
            "Unfunded direct competitors",
            "No direct competitor identified",
        ),
        "A funded leader is a direct competitor with US$10m+ disclosed funding or a public "
        "listing: three or more; one or two; direct competitors below that; none identified.",
    ),
    Leaf(
        "route_to_market",
        "Route to global markets",
        "market",
        (
            "No offshore route stated",
            "Offshore markets named",
            "Offshore process under way",
            "Offshore approval or entity",
            "Operating in 2+ offshore markets",
        ),
        "Access, not customers: 1 none stated; 2 target markets named; 3 offshore approval, "
        "accreditation or channel process under way; 4 obtained, or an offshore entity; 5 "
        "operating in two or more offshore markets with local staff.",
    ),
    Leaf(
        "customer_validation",
        "Customer validation",
        "traction",
        ("Company claim only", "Unpaid trial", "Paid pilot", "Production customers"),
        "The strongest independently verifiable customer evidence.",
    ),
    Leaf(
        "commercial_stage",
        "Commercial stage",
        "traction",
        ("Pre-revenue", "First revenue", "Repeatable revenue", "Scaling"),
        "Breadth and repeatability of revenue: none; first; multiple recurring customers; "
        "stated growth with revenue in several markets.",
    ),
    Leaf(
        "partnerships",
        "Strategic partnerships and channels",
        "traction",
        (
            "None public",
            "MoU or research collaboration",
            "Partner in an active programme",
            "Commercial agreement with an established firm",
            "Two or more commercial agreements",
        ),
        "Non-customer partners: 1 none; 2 MoU or research collaboration; 3 a named partner in an "
        "active programme; 4 a commercial, distribution or manufacturing agreement with an "
        "established firm; 5 two or more at 4.",
    ),
    Leaf(
        "milestone_delivery",
        "Milestone delivery",
        "traction",
        (
            "No dated public milestone",
            "Announced, none yet due",
            "Delivered, some late or missed",
            "Delivered on or near plan",
            "Two or more delivered on plan",
        ),
        "Earlier public plans compared with later outcomes.",
    ),
]
LEAF = {leaf.id: leaf for leaf in LEAVES}

#: Market-size value function on a fixed domain (owner judgement, 4 November 2026).
MARKET_SIZE_DOMAIN = (0.01, 200.0)
MARKET_SIZE_POINTS = [(0.01, 0.0), (0.1, 0.15), (1.0, 0.35), (5.0, 0.65), (25.0, 0.9), (200.0, 1.0)]
MARKET_GROWTH_DOMAIN = (0.0, 40.0)

#: Swing ratings: (Technical/IP-led, Commercial/traction-led). Owner judgements, 4 November 2026.
SWINGS: dict[str, tuple[float, float]] = {
    "mandate": (0, 0),
    "team": (90, 80),
    "problem_solution": (100, 60),
    "market": (60, 80),
    "traction": (50, 100),
    "hq_country": (100, 100),
    "stage": (100, 100),
    "sector": (100, 100),
    "founder_problem_fit": (100, 80),
    "team_completeness": (70, 100),
    "track_record": (50, 70),
    "board_advisors": (40, 40),
    "problem_severity": (60, 100),
    "defensibility": (100, 70),
    "readiness": (80, 80),
    "regulatory_burden": (50, 60),
    "market_size": (100, 100),
    "market_growth": (60, 70),
    "competitive_intensity": (70, 60),
    "route_to_market": (50, 80),
    "customer_validation": (100, 90),
    "commercial_stage": (50, 100),
    "partnerships": (80, 50),
    "milestone_delivery": (60, 70),
}
PROFILES = [
    ("technical_ip", "Technical/IP-led"),
    ("commercial_traction", "Commercial/traction-led"),
]

CLASSES: list[tuple[str, float | None]] = [
    ("Prioritise for diligence", 0.60),
    ("Monitor", 0.40),
    ("Not now", None),
]

COMPANIES = [
    ("captivate", "Captivate Technology"),
    ("wellumio", "Wellumio"),
    ("scentian_bio", "Scentian Bio"),
    ("hectre", "Hectre"),
    ("wych", "Wych"),
    ("upstock", "Upstock"),
    ("kea_aerospace", "Kea Aerospace"),
    ("hnry", "Hnry"),
]

# ----------------------------------------------------------------------------------------------
# Market estimates: 2025 values stated on each publisher's public page, retrieved 4 November 2026.
# A page stating two 2025 values more than 5% apart is excluded (listed in the README).
# (publisher, URL, page date, US$ bn 2025, forecast CAGR %)
# ----------------------------------------------------------------------------------------------

Estimate = tuple[str, str, date, float, float]
MARKETS: dict[str, tuple[str, list[Estimate]]] = {
    "captivate": (
        "Point-source carbon capture",
        [
            (
                "The Business Research Company (via GII)",
                "https://www.giiresearch.com/report/tbrc1985099-point-source-carbon-capture-device-pscd-global.html",
                date(2026, 3, 16),
                3.45,
                14.6,
            ),
            (
                "Market Intelo",
                "https://marketintelo.com/report/point-source-carbon-capture-market/amp",
                date(2026, 6, 11),
                7.2,
                15.3,
            ),
        ],
    ),
    "wellumio": (
        "Portable magnetic resonance imaging",
        [
            (
                "Straits Research",
                "https://straitsresearch.com/report/portable-magnetic-resonance-imaging-market",
                date(2026, 9, 18),
                2.71,
                5.8,
            ),
            (
                "The Business Research Company (via GII)",
                "https://gii.tw/report/tbrc1706115-portable-magnetic-resonance-imaging-mri-global.html",
                date(2025, 9, 10),
                3.78,
                6.7,
            ),
            (
                "Mordor Intelligence",
                "https://www.mordorintelligence.com/industry-reports/portable-magnetic-resonance-imaging-market",
                date(2026, 9, 11),
                4.38,
                6.05,
            ),
            (
                "Reportprime",
                "https://www.reportprime.com/portable-mri-r9073.md",
                AS_OF,
                0.47786,
                12.65,
            ),
        ],
    ),
    "scentian_bio": (
        "Electronic nose (e-nose)",
        [
            (
                "Global Market Insights",
                "https://www.gminsights.com/industry-analysis/e-nose-electronic-nose-market",
                date(2026, 8, 1),
                0.0597,
                9.5,
            ),
            (
                "Mordor Intelligence",
                "https://www.mordorintelligence.com/industry-reports/electronic-nose-market",
                date(2026, 9, 11),
                0.14628,
                12.26,
            ),
            (
                "Market Research Future",
                "https://www.marketresearchfuture.com/reports/electronic-nose-market-22638",
                date(2026, 10, 27),
                1.58,
                10.1,
            ),
            ("Market.us", "https://scoop.market.us/?p=58472", date(2025, 7, 22), 44.01, 18.5),
        ],
    ),
    "hectre": (
        "Fruit and vegetable sorting machines",
        [
            (
                "360iResearch (via GII)",
                "https://www.giiresearch.com/report/ires2008217-fruit-vegetable-sorting-machine-market-by-machine.html",
                date(2026, 7, 30),
                1.26,
                7.28,
            ),
            (
                "DIResearch (via MarketPublishers)",
                "https://marketpublishers.com/report/equipment/food-beverage-equipment/fruit-n-vegetable-sorting-machine-research-report-dir.html",
                date(2025, 6, 1),
                0.76252,
                6.8,
            ),
            (
                "PW Consulting",
                "https://pmarketresearch.com/worldwide-fruit-and-vegetable-sorting-machine-market-research",
                date(2026, 6, 10),
                2.1854,
                7.12,
            ),
        ],
    ),
    "wych": (
        "Open banking",
        [
            (
                "Grand View Research",
                "https://www.grandviewresearch.com/industry-analysis/open-banking-systems-market",
                date(2026, 6, 1),
                39.8,
                28.2,
            ),
            (
                "Next Move Strategy Consulting",
                "https://www.nextmsc.com/report/open-banking-market-bf5510",
                date(2026, 9, 30),
                27.85,
                22.8,
            ),
            (
                "Precedence Research",
                "https://www.precedenceresearch.com/open-banking-market",
                date(2026, 9, 21),
                35.72,
                21.0,
            ),
        ],
    ),
    "upstock": (
        "B2B food marketplace platforms",
        [
            (
                "The Insight Partners",
                "https://www.theinsightpartners.com/reports/b2b-food-marketplace-platform-market",
                date(2026, 7, 31),
                47.63,
                17.5,
            ),
            (
                "Verified Market Research",
                "https://www.verifiedmarketresearch.com/product/b2b-food-marketplace-platforms-market/",
                date(2026, 9, 1),
                28.14,
                16.2,
            ),
        ],
    ),
    "kea_aerospace": (
        "High-altitude pseudo-satellites (HAPS)",
        [
            (
                "Reanin",
                "https://www.reanin.com/reports/high-altitude-pseudo-satellites-market",
                date(2026, 9, 1),
                1.02,
                8.3,
            ),
            (
                "SNS Insider",
                "https://www.snsinsider.com/press-release/global-high-altitude-pseudo-satellite-market",
                date(2026, 9, 29),
                1.20,
                17.0,
            ),
            (
                "Spherical Insights",
                "https://www.sphericalinsights.com/blogs/top-10-high-altitude-pseudo-satellite-haps-market-companies-advancing-persistent-connectivity-and-surveillance",
                date(2026, 9, 1),
                1.13,
                21.65,
            ),
            (
                "Aviation & Defense Market Reports (via GII)",
                "https://www.giiresearch.com/report/avd1858531-global-high-altitude-pseudo-satellites-market.html",
                date(2025, 11, 1),
                3.90,
                12.73,
            ),
        ],
    ),
    "hnry": (
        "Small-business accounting software",
        [
            (
                "Market Research Future",
                "https://marketresearchfuture.com/reports/small-business-accounting-software-market-32881",
                date(2026, 9, 17),
                8.22,
                6.92,
            ),
            (
                "Market Intelo",
                "https://marketintelo.com/report/small-business-accounting-software-market",
                date(2026, 6, 21),
                9.6,
                9.8,
            ),
        ],
    ),
}

#: Excluded by the stated rule: the page gives two 2025 values more than 5% apart.
EXCLUDED_ESTIMATES = [
    (
        "scentian_bio",
        "Spherical Insights",
        "https://www.sphericalinsights.com/blogs/top-25-companies-in-global-electronic-nose-market-industry-intelligence-report-by-spherical-insights-2026-2035",
        "states US$1.47bn and US$47bn for 2025 on the same page",
    ),
]


def market_cells(alt: str) -> tuple[float, float, float, float, float, float]:
    """Median size, min, max; median CAGR, min, max."""
    estimates = MARKETS[alt][1]
    sizes = [e[3] for e in estimates]
    growth = [e[4] for e in estimates]
    return (
        statistics.median(sizes),
        min(sizes),
        max(sizes),
        statistics.median(growth),
        min(growth),
        max(growth),
    )


# ----------------------------------------------------------------------------------------------
# Rubric cells: alternative -> leaf -> (value, source key, location on the page, note, kind).
# Notes paraphrase the source; quotations are avoided.
# ----------------------------------------------------------------------------------------------

Cell = tuple[str, str, str, str, Kind]

CELLS: dict[str, dict[str, Cell]] = {
    "captivate": {
        "hq_country": (
            "New Zealand",
            "massey_2026",
            "Body",
            "Based in Palmerston North.",
            "observed",
        ),
        "stage": (
            "Seed",
            "massey_2026",
            "Headline and body",
            "Closed a seed round led by WNT Ventures.",
            "observed",
        ),
        "sector": (
            "Climate and energy",
            "massey_2026",
            "Body",
            "Industrial carbon dioxide capture.",
            "judgement",
        ),
        "founder_problem_fit": (
            "Recognised domain expert",
            "massey_2026",
            "Body",
            "Professor Shane Telfer founded the company from his Massey chemistry lab; no public "
            "commercial experience in the target industry.",
            "judgement",
        ),
        "team_completeness": (
            "All three, one part-time",
            "ceda_cap",
            "Team",
            "CEO (Salisbury), founder and CTO (Telfer) and a process engineer named; full-time "
            "status of the domain role not stated.",
            "judgement",
        ),
        "track_record": (
            "Senior role at scale or funded venture",
            "massey_2026",
            "CEO appointment",
            "New CEO has 20+ years of international strategy and transformation experience and is a "
            "chartered director.",
            "judgement",
        ),
        "board_advisors": (
            "Independent chair or domain advisor",
            "massey_2026",
            "Chair quote",
            "A chair (Callum Streeter) is named; independence not stated.",
            "judgement",
        ),
        "problem_severity": (
            "Independently confirmed",
            "kiwinet_cap",
            "Market section",
            "Industrial emitters and biogas operators named as the problem holders; no independent "
            "cost figure on the pages read.",
            "judgement",
        ),
        "defensibility": (
            "Filed patent or proprietary data",
            "kiwinet_cap",
            "Technology",
            "Describes a patented MOF material (MUF-16); jurisdiction and grant status not stated.",
            "judgement",
        ),
        "readiness": (
            "Pilot-ready",
            "ceda_cap",
            "Deployments",
            "Eight field demonstrations and a Canadian pilot at a gas processing site.",
            "observed",
        ),
        "regulatory_burden": (
            "No approval required",
            "kiwinet_cap",
            "Technology",
            "Capture equipment for industrial sites; no product approval regime identified.",
            "judgement",
        ),
        "competitive_intensity": (
            "One or two funded leaders",
            "svante_2022",
            "Headline",
            "Svante (US$318m Series E, solid-sorbent point-source capture); Carbon Clean also "
            "raised US$150m (World Cement, 13 May 2022).",
            "judgement",
        ),
        "route_to_market": (
            "Offshore process under way",
            "ceda_cap",
            "Deployments",
            "Alberta pilot with North American partners CarbonQuest and Cielo.",
            "observed",
        ),
        "customer_validation": (
            "Unpaid trial",
            "kiwinet_cap",
            "Pilots",
            "Pilot hosts named (Contact Energy, Tourmaline); no paying customer named.",
            "judgement",
        ),
        "commercial_stage": (
            "Pre-revenue",
            "kiwinet_cap",
            "Pilots",
            "No commercial customers named.",
            "judgement",
        ),
        "partnerships": (
            "Partner in an active programme",
            "ceda_cap",
            "Deployments",
            "CAD$4.2m project with Tourmaline, CarbonQuest and Cielo.",
            "observed",
        ),
        "milestone_delivery": (
            "Delivered, some late or missed",
            "masseyventures_2023",
            "Body",
            "Announced a NZ$4m seed raise in November 2023; a NZ$3m seed closed in February "
            "2026 (Massey University).",
            "judgement",
        ),
    },
    "wellumio": {
        "hq_country": (
            "New Zealand",
            "hlth_wel",
            "First paragraph",
            "Described as New Zealand-based.",
            "observed",
        ),
        "stage": (
            "Seed",
            "hitc_wel",
            "Headline",
            "Pre-Series A closed July 2026 (maps to Seed).",
            "observed",
        ),
        "sector": (
            "Health and medtech",
            "wellumio_home",
            "Product",
            "Portable MRI brain scanner.",
            "judgement",
        ),
        "founder_problem_fit": (
            "Recognised domain expert",
            "wellumio_journey",
            "Founders",
            "CEO is an MD PhD with a 15-year career in neuromonitoring research.",
            "observed",
        ),
        "team_completeness": (
            "Next-stage leads named",
            "wellumio_journey",
            "2023-2024",
            "Technical co-founders, a commercialisation lead, a general manager and a VP Product "
            "Development (ex-GE Healthcare) are named.",
            "judgement",
        ),
        "track_record": (
            "Senior role at scale or funded venture",
            "wellumio_journey",
            "2024",
            "VP Product Development spent 8 years at GE Healthcare as a global product manager.",
            "judgement",
        ),
        "board_advisors": (
            "Independent chair or domain advisor",
            "wellumio_journey",
            "2024",
            "A clinical advisory board was formed; an investor director is named (Idealog).",
            "judgement",
        ),
        "problem_severity": (
            "Cost independently quantified",
            "idealog_wel",
            "Body",
            "Reports that under 5% of stroke patients are treated within the first hour.",
            "judgement",
        ),
        "defensibility": (
            "Granted patent or exclusive licence",
            "idealog_wel",
            "Body",
            "A US patent for the underlying technique was granted in December 2025.",
            "observed",
        ),
        "readiness": (
            "Pilot-ready",
            "idealog_wel",
            "Body",
            "First-in-human feasibility trials and a hospital trial.",
            "judgement",
        ),
        "regulatory_burden": (
            "Approval required, under way",
            "wellumio_disclaimer",
            "Statement",
            "Products are under clinical investigation and not for sale.",
            "observed",
        ),
        "competitive_intensity": (
            "One or two funded leaders",
            "umd_hyperfine",
            "Body",
            "Hyperfine (Swoop portable MRI) is Nasdaq-listed.",
            "judgement",
        ),
        "route_to_market": (
            "Offshore approval or entity",
            "wellumio_home",
            "Contact",
            "Offices in Clayton (Australia) and Menlo Park (United States).",
            "observed",
        ),
        "customer_validation": (
            "Unpaid trial",
            "wellumio_journey",
            "2024",
            "Trial partnership with the Royal Melbourne Hospital; not a sale.",
            "judgement",
        ),
        "commercial_stage": (
            "Pre-revenue",
            "wellumio_disclaimer",
            "Statement",
            "Not for sale.",
            "observed",
        ),
        "partnerships": (
            "Partner in an active programme",
            "wellumio_journey",
            "2024",
            "Clinical trial partnership with the Royal Melbourne Hospital.",
            "observed",
        ),
        "milestone_delivery": (
            "Delivered on or near plan",
            "hitc_wel",
            "Body",
            "First close in February 2026 followed by an oversubscribed final close in July 2026.",
            "judgement",
        ),
    },
    "scentian_bio": {
        "hq_country": (
            "New Zealand",
            "scoop_sce",
            "Dateline",
            "Auckland, New Zealand.",
            "observed",
        ),
        "stage": (
            "Seed",
            "scoop_sce",
            "Headline",
            "Pre-Series A, April 2026 (maps to Seed).",
            "observed",
        ),
        "sector": (
            "Agritech and food",
            "scoop_sce",
            "Body",
            "Initial market is food quality control.",
            "judgement",
        ),
        "founder_problem_fit": (
            "Recognised domain expert",
            "uoa_sce",
            "Body",
            "Scientific founder spent nearly two decades at Plant and Food Research.",
            "observed",
        ),
        "team_completeness": (
            "Two key roles named",
            "uoa_sce",
            "Body",
            "CEO and lead scientist named; no domain or regulatory lead named.",
            "judgement",
        ),
        "track_record": (
            "Prior exit or scaled-company executive",
            "uoa_sce",
            "Body",
            "CEO founded a Silicon Valley start-up later acquired by Ancestry.com.",
            "observed",
        ),
        "board_advisors": (
            "Independent chair or domain advisor",
            "gai_sce",
            "Body",
            "An agrifood investor (Finistere Ventures) joined the board.",
            "judgement",
        ),
        "problem_severity": (
            "Independently confirmed",
            "uoa_sce",
            "Body",
            "Zespri innovation-fund pilot on harvest timing.",
            "judgement",
        ),
        "defensibility": (
            "Filed patent or proprietary data",
            "uoa_sce",
            "Body",
            "Patents filed; a library of 74 synthesised insect receptors.",
            "observed",
        ),
        "readiness": (
            "Pilot-ready",
            "scoop_sce",
            "Body",
            "Preparing commercial launch; shipping expected within months of April 2026.",
            "observed",
        ),
        "regulatory_burden": (
            "No approval required",
            "scoop_sce",
            "Body",
            "Food quality control first; health uses are later.",
            "judgement",
        ),
        "competitive_intensity": (
            "One or two funded leaders",
            "aryballe_2020",
            "Body",
            "Aryballe (digital olfaction) had raised EUR17m by July 2020.",
            "judgement",
        ),
        "route_to_market": (
            "Offshore markets named",
            "scoop_sce",
            "Body",
            "Worked with some of the world's largest food companies; no offshore entity stated.",
            "judgement",
        ),
        "customer_validation": (
            "Paid pilot",
            "uoa_sce",
            "Body",
            "Paid pilots with five major global food companies.",
            "observed",
        ),
        "commercial_stage": (
            "First revenue",
            "uoa_sce",
            "Body",
            "Paid pilots; commercial launch pending.",
            "judgement",
        ),
        "partnerships": (
            "Partner in an active programme",
            "uoa_sce",
            "Body",
            "Pilot through Zespri's innovation fund; Gates Foundation grant.",
            "observed",
        ),
        "milestone_delivery": (
            "Announced, none yet due",
            "scoop_sce",
            "Body",
            "Shipping expected within months of April 2026; delivery not yet reported.",
            "judgement",
        ),
    },
    "hectre": {
        "hq_country": (
            "New Zealand",
            "fruitnet_hec",
            "First paragraph",
            "Auckland-based.",
            "observed",
        ),
        "stage": (
            "Series A",
            "punakaiki_hec",
            "Headline",
            "NZ$12m Series A, February 2026.",
            "observed",
        ),
        "sector": (
            "Agritech and food",
            "punakaiki_hec",
            "Body",
            "Fruit imaging and orchard software.",
            "judgement",
        ),
        "founder_problem_fit": (
            "3+ years in the domain",
            "hectre_about",
            "Leadership",
            "CEO has 7+ years in the agriculture sector.",
            "observed",
        ),
        "team_completeness": (
            "All three full-time",
            "hectre_about",
            "Leadership",
            "CEO, CTO and a head of global sales with 10+ years in fruit post-harvest.",
            "observed",
        ),
        "track_record": (
            "Prior exit or scaled-company executive",
            "hectre_about",
            "Leadership",
            "CTO was GM of Product at Xero.",
            "observed",
        ),
        "board_advisors": (
            "None named",
            "hectre_about",
            "Whole page",
            "No board or advisors named on the pages read.",
            "judgement",
        ),
        "problem_severity": (
            "Company statement only",
            "hectre_home",
            "Testimonials",
            "Customer outcomes appear only as testimonials on the company site.",
            "judgement",
        ),
        "defensibility": (
            "Filed patent or proprietary data",
            "punakaiki_hec",
            "Body",
            "Quality data on 17 billion apples and 37 billion cherries.",
            "observed",
        ),
        "readiness": (
            "Commercial",
            "hectre_about",
            "Milestones",
            "Products sold since 2016-2017.",
            "observed",
        ),
        "regulatory_burden": (
            "No approval required",
            "hectre_home",
            "Products",
            "Software and imaging; no product approval regime identified.",
            "judgement",
        ),
        "competitive_intensity": (
            "One or two funded leaders",
            "dir_sort",
            "Manufacturer list",
            "TOMRA, a listed company, is among the sorting-machine manufacturers profiled.",
            "judgement",
        ),
        "route_to_market": (
            "Offshore approval or entity",
            "hectre_about",
            "Milestones",
            "Customers in the US, Canada, Italy, Chile and Mexico; no offshore entity confirmed.",
            "judgement",
        ),
        "customer_validation": (
            "Production customers",
            "fruitnet_hec",
            "Body",
            "Named customers in Italy, Spain and Washington State.",
            "observed",
        ),
        "commercial_stage": (
            "Scaling",
            "punakaiki_hec",
            "Body",
            "Revenue growing about 100% a year; customers on three continents.",
            "observed",
        ),
        "partnerships": (
            "None public",
            "hectre_about",
            "Whole page",
            "No partners named; integrations mentioned without names.",
            "judgement",
        ),
        "milestone_delivery": (
            "Delivered on or near plan",
            "punakaiki_hec",
            "Body",
            "Series A targeted at NZ$10m and extended to NZ$12m.",
            "judgement",
        ),
    },
    "wych": {
        "hq_country": (
            "New Zealand",
            "startupdaily_wych",
            "Body",
            "Founded in Auckland in 2018.",
            "observed",
        ),
        "stage": (
            "Seed",
            "startupdaily_wych",
            "Body",
            "First external round (NZ$1.5m) after bootstrapping; no label published.",
            "judgement",
        ),
        "sector": (
            "Fintech and B2B software",
            "wych_io",
            "Products",
            "Open banking infrastructure.",
            "judgement",
        ),
        "founder_problem_fit": (
            "3+ years in the domain",
            "startupdaily_wych",
            "Body",
            "Founder has run the open banking business since 2018.",
            "judgement",
        ),
        "team_completeness": (
            "One key role named",
            "wych_io",
            "Whole page",
            "Only the founder is named in a leadership role.",
            "judgement",
        ),
        "track_record": (
            "Prior venture or 5+ years operating",
            "startupdaily_wych",
            "Body",
            "Founder described as a tech entrepreneur; earlier ventures not named.",
            "judgement",
        ),
        "board_advisors": (
            "None named",
            "wych_io",
            "Whole page",
            "No board or advisors named.",
            "judgement",
        ),
        "problem_severity": (
            "Independently confirmed",
            "kiwibank_2026",
            "Body",
            "Kiwibank delivered open banking ahead of a regulatory deadline.",
            "judgement",
        ),
        "defensibility": (
            "Claimed, no protectable asset",
            "wych_io",
            "Accreditation",
            "Accreditation and integrations; no patent or exclusive licence stated.",
            "judgement",
        ),
        "readiness": (
            "Commercial",
            "kiwibank_2026",
            "Body",
            "Live with Kiwibank from 28 May 2026.",
            "observed",
        ),
        "regulatory_burden": (
            "Approved in one market or certification only",
            "wych_io",
            "Accreditation",
            "ACCC-accredited CDR provider in Australia; SOC 2.",
            "observed",
        ),
        "competitive_intensity": (
            "Unfunded direct competitors",
            "cfotech_akahu",
            "Body",
            "Akahu raised NZ$1.4m; no direct competitor with US$10m+ identified.",
            "judgement",
        ),
        "route_to_market": (
            "Offshore approval or entity",
            "wych_io",
            "Footer",
            "Wych Australia Pty Ltd with a North Sydney office and CDR accreditation.",
            "observed",
        ),
        "customer_validation": (
            "Production customers",
            "kiwibank_2026",
            "Body",
            "Kiwibank's first open banking partner.",
            "observed",
        ),
        "commercial_stage": (
            "Repeatable revenue",
            "startupdaily_wych",
            "Body",
            "Clients include a tier-1 Australian bank, non-bank lenders and fintechs.",
            "judgement",
        ),
        "partnerships": (
            "Commercial agreement with an established firm",
            "kiwibank_2026",
            "Body",
            "Integration partner connecting Kiwibank with accredited third parties.",
            "observed",
        ),
        "milestone_delivery": (
            "Delivered on or near plan",
            "kiwibank_2026",
            "Body",
            "Planned Kiwibank services from 2026 (Startup Daily, 2025); launched 28 May 2026.",
            "judgement",
        ),
    },
    "upstock": {
        "hq_country": (
            "New Zealand",
            "startupdaily_ups",
            "First paragraph",
            "Described as a Kiwi B2B marketplace.",
            "observed",
        ),
        "stage": (
            "Seed",
            "startupdaily_ups",
            "Body",
            "Raised NZ$6m in 2023; public pages give no round label.",
            "judgement",
        ),
        "sector": (
            "Consumer and marketplaces",
            "upstock_about",
            "Tagline",
            "Wholesale ordering marketplace for foodservice.",
            "judgement",
        ),
        "founder_problem_fit": (
            "3+ years in the domain",
            "upstock_about",
            "Founders",
            "Founder owns a soft-drink brand and built the tool for his own wholesale orders.",
            "observed",
        ),
        "team_completeness": (
            "All three, one part-time",
            "upstock_about",
            "Team",
            "CEO and co-founder from Xero, a supplier-founder and a sales team named.",
            "judgement",
        ),
        "track_record": (
            "Several founders at that level",
            "startupdaily_ups",
            "Body",
            "Co-founder was on Xero's 2006 founding team; CEO was Xero's CPO.",
            "observed",
        ),
        "board_advisors": (
            "Sector and investor directors",
            "upstock_about",
            "Board",
            "Independent directors include an Icehouse Ventures executive and a Yelp SVP.",
            "observed",
        ),
        "problem_severity": (
            "Company statement only",
            "scoop_ups",
            "Quote",
            "Company says most hospitality businesses still order on paper.",
            "judgement",
        ),
        "defensibility": (
            "Claimed, no protectable asset",
            "insidefmcg_ups",
            "Body",
            "Claims the largest FMCG marketplace in New Zealand; no IP stated.",
            "judgement",
        ),
        "readiness": (
            "Commercial",
            "insidefmcg_ups",
            "Body",
            "Thousands of customers.",
            "observed",
        ),
        "regulatory_burden": (
            "No approval required",
            "upstock_about",
            "Tagline",
            "Ordering software; no product approval regime identified.",
            "judgement",
        ),
        "competitive_intensity": (
            "One or two funded leaders",
            "verdict_choco",
            "Body",
            "Choco (restaurant-supplier ordering) raised US$100m in 2021.",
            "judgement",
        ),
        "route_to_market": (
            "Offshore approval or entity",
            "startupdaily_ups",
            "Body",
            "Crossed to Australia after the 2023 raise.",
            "judgement",
        ),
        "customer_validation": (
            "Production customers",
            "insidefmcg_ups",
            "Body",
            "Thousands of customers across every Australian state (self-reported).",
            "observed",
        ),
        "commercial_stage": (
            "Scaling",
            "insidefmcg_ups",
            "Body",
            "Revenue in New Zealand and Australia, growing rapidly (self-reported, January 2025).",
            "judgement",
        ),
        "partnerships": (
            "Commercial agreement with an established firm",
            "fmcgbusiness_ups",
            "Body",
            "Woolworths order automation for suppliers, August 2024.",
            "observed",
        ),
        "milestone_delivery": (
            "Delivered on or near plan",
            "startupdaily_ups",
            "Body",
            "The 2022 raise targeted up to NZ$6m (Scoop); NZ$6m reported in 2023.",
            "judgement",
        ),
    },
    "kea_aerospace": {
        "hq_country": (
            "New Zealand",
            "newswire_kea",
            "Body",
            "Christchurch manufacturing and operations base.",
            "observed",
        ),
        "stage": (
            "Series A",
            "newswire_kea",
            "Body",
            "NZ$17.5m venture round for just under 20% of the company; no label published.",
            "judgement",
        ),
        "sector": (
            "Space and advanced hardware",
            "wiki_kea",
            "Lead",
            "Solar-powered stratospheric aircraft.",
            "judgement",
        ),
        "founder_problem_fit": (
            "3+ years in the domain",
            "wiki_rocket",
            "Career",
            "Seed investor and co-director of Rocket Lab 2007-2011.",
            "observed",
        ),
        "team_completeness": (
            "Two key roles named",
            "wiki_kea",
            "Infobox",
            "Two co-founders named; roles beyond CEO not stated.",
            "judgement",
        ),
        "track_record": (
            "Prior exit or scaled-company executive",
            "wiki_rocket",
            "Career",
            "Sold one of two internet companies he co-founded (2006).",
            "observed",
        ),
        "board_advisors": (
            "None named",
            "kea_news",
            "Whole page",
            "No board or advisors named.",
            "judgement",
        ),
        "problem_severity": (
            "Independently confirmed",
            "newswire_kea",
            "Body",
            "A government official pointed to value for agencies.",
            "judgement",
        ),
        "defensibility": (
            "Claimed, no protectable asset",
            "wiki_kea",
            "Whole page",
            "No patents or licences stated.",
            "judgement",
        ),
        "readiness": (
            "Prototype",
            "newswire_kea",
            "Body",
            "Mk1 flew to the stratosphere; the Mk2 is about three years away.",
            "observed",
        ),
        "regulatory_burden": (
            "Approval required, under way",
            "wiki_kea",
            "History",
            "In the government's Airspace Integration Trials Programme.",
            "judgement",
        ),
        "competitive_intensity": (
            "One or two funded leaders",
            "totaltele_aalto",
            "Body",
            "AALTO (Airbus Zephyr) received a US$100m commitment in 2024.",
            "judgement",
        ),
        "route_to_market": (
            "Offshore process under way",
            "kea_news",
            "8 May 2026",
            "Imagery work with German payload partners; NASA partnership.",
            "judgement",
        ),
        "customer_validation": (
            "Unpaid trial",
            "kea_news",
            "25 Jun 2025",
            "Government-funded NASA partnership; no customer named.",
            "judgement",
        ),
        "commercial_stage": (
            "Pre-revenue",
            "newswire_kea",
            "Body",
            "No customers or contracts reported.",
            "judgement",
        ),
        "partnerships": (
            "Partner in an active programme",
            "kea_news",
            "25 Mar and 25 Jun 2025",
            "NASA partnership and a Li-S Energy collaboration agreement.",
            "observed",
        ),
        "milestone_delivery": (
            "Delivered, some late or missed",
            "kea_news",
            "12 Feb 2025",
            "Stratospheric flight achieved February 2025; the round it was to catalyse closed "
            "August 2026.",
            "judgement",
        ),
    },
    "hnry": {
        "hq_country": (
            "New Zealand",
            "hnry_news",
            "Body",
            "Headquarters in Wellington.",
            "observed",
        ),
        "stage": (
            "Series B or later",
            "hnry_news",
            "Headline",
            "Series C, December 2025.",
            "observed",
        ),
        "sector": (
            "Fintech and B2B software",
            "hnry_home",
            "Overview",
            "Accounting and tax automation for sole traders.",
            "judgement",
        ),
        "founder_problem_fit": (
            "Adjacent experience",
            "hnry_about",
            "Story",
            "Founders were self-employed contractors who lived the problem.",
            "judgement",
        ),
        "team_completeness": (
            "Two key roles named",
            "hnry_news",
            "Body",
            "CEO and Head of UK named; other leads not named on the pages read.",
            "judgement",
        ),
        "track_record": (
            "None public",
            "hnry_about",
            "Story",
            "No earlier ventures named for the founders.",
            "judgement",
        ),
        "board_advisors": (
            "Independent chair or domain advisor",
            "hnry_news",
            "Body",
            "A Movac partner joins the board.",
            "judgement",
        ),
        "problem_severity": (
            "Independently confirmed",
            "hnry_news",
            "Body",
            "Tax filing is a statutory obligation; the 420,000 sole-trader figure is the "
            "company's.",
            "judgement",
        ),
        "defensibility": (
            "Claimed, no protectable asset",
            "hnry_home",
            "Overview",
            "Service and app; no IP stated.",
            "judgement",
        ),
        "readiness": (
            "Commercial",
            "hnry_about",
            "Timeline",
            "Launched in New Zealand in 2017.",
            "observed",
        ),
        "regulatory_burden": (
            "Approved in one market or certification only",
            "hnry_home",
            "Overview",
            "Tax-intermediary status not stated on the pages read.",
            "judgement",
        ),
        "competitive_intensity": (
            "One or two funded leaders",
            "hnry_xero",
            "Headline",
            "Positions itself against Xero (ASX-listed, Startup Daily) and MYOB.",
            "judgement",
        ),
        "route_to_market": (
            "Operating in 2+ offshore markets",
            "hnry_about",
            "Timeline",
            "Australia since 2020 and the UK since February 2025, with staff in each.",
            "observed",
        ),
        "customer_validation": (
            "Production customers",
            "hnry_about",
            "Timeline",
            "Tens of thousands of sole traders.",
            "observed",
        ),
        "commercial_stage": (
            "Scaling",
            "hnry_about",
            "Milestones",
            "NZ$2bn annualised payments across three markets.",
            "observed",
        ),
        "partnerships": (
            "None public",
            "hnry_home",
            "Partners link",
            "Partners page linked without named partners; stadium naming rights are marketing.",
            "judgement",
        ),
        "milestone_delivery": (
            "Delivered on or near plan",
            "hnry_about",
            "Timeline",
            "Sequential launches in Australia (2020) and the UK (2025).",
            "judgement",
        ),
    },
}

#: Disputed claims left open (unreviewed, differing from the accepted claim on the same cell).
DISPUTED: list[tuple[str, str, str, float | str, str | None, str, str, Kind]] = [
    (
        "disputed_kea_stage",
        "kea_aerospace",
        "stage",
        "Seed",
        None,
        "caplight_kea",
        "Summary fields",
        "Aggregator lists the last round as crowdfunding (Nov 2025) with no stage label; read as seed.",
    ),
    (
        "disputed_scentian_market",
        "scentian_bio",
        "market_size",
        8.0,
        "US$ bn",
        "scoop_sce",
        "Body",
        "Company-stated food quality control market of over US$8bn.",
    ),
]


# ----------------------------------------------------------------------------------------------
# Building the project
# ----------------------------------------------------------------------------------------------


def _labelled(leaf: Leaf) -> dict[str, object]:
    if leaf.id == "hq_country":
        mapping = {"Other": 0.0, "Australia": 0.0, "New Zealand": 1.0}
        return {
            "scale": Scale(type=ScaleType.CATEGORICAL, labels=list(leaf.labels)),
            "value_function": QualitativeValueFunction(mapping=mapping),
        }
    if leaf.id == "sector":
        mapping = {label: (0.0 if label == "Other" else 1.0) for label in leaf.labels}
        return {
            "scale": Scale(type=ScaleType.CATEGORICAL, labels=list(leaf.labels)),
            "value_function": QualitativeValueFunction(mapping=mapping),
        }
    values = FIVE if len(leaf.labels) == 5 else FOUR
    return {
        "scale": Scale(type=ScaleType.ORDINAL, labels=list(leaf.labels)),
        "value_function": QualitativeValueFunction(
            mapping=dict(zip(leaf.labels, values, strict=True))
        ),
    }


def _numeric(leaf: Leaf) -> dict[str, object]:
    if leaf.id == "market_size":
        lower, upper = MARKET_SIZE_DOMAIN
        return {
            "scale": Scale(type=ScaleType.RATIO, unit="US$ bn", lower=lower, upper=upper),
            "value_function": PiecewiseLinearValueFunction(
                points=[ControlPoint(x=x, value=v) for x, v in MARKET_SIZE_POINTS]
            ),
        }
    lower, upper = MARKET_GROWTH_DOMAIN
    return {
        "scale": Scale(type=ScaleType.RATIO, unit="% CAGR", lower=lower, upper=upper),
        "value_function": LinearValueFunction(direction=Direction.INCREASING),
    }


def measurements(alt: str) -> dict[str, float | str]:
    size, _, _, growth, _, _ = market_cells(alt)
    values: dict[str, float | str] = {leaf: cell[0] for leaf, cell in CELLS[alt].items()}
    values["market_size"] = size
    values["market_growth"] = growth
    return values


def _smaa() -> SmaaModel:
    cells: list[CellUncertainty] = []
    for alt, _ in COMPANIES:
        _, s_lo, s_hi, _, g_lo, g_hi = market_cells(alt)
        cells.append(
            CellUncertainty(
                alternative_id=alt,
                criterion_id="market_size",
                distribution=UniformDistribution(lower=s_lo, upper=s_hi),
            )
        )
        cells.append(
            CellUncertainty(
                alternative_id=alt,
                criterion_id="market_growth",
                distribution=UniformDistribution(lower=g_lo, upper=g_hi),
            )
        )
        for leaf_id, (value, _, _, _, kind) in CELLS[alt].items():
            leaf = LEAF[leaf_id]
            if kind != "judgement" or leaf.parent == "mandate":
                continue
            i, last = leaf.labels.index(value), len(leaf.labels) - 1
            if i == 0:
                outcome = {leaf.labels[0]: 0.5, leaf.labels[1]: 0.5}
            elif i == last:
                outcome = {leaf.labels[last - 1]: 0.5, leaf.labels[last]: 0.5}
            else:
                outcome = {leaf.labels[i - 1]: 0.25, leaf.labels[i]: 0.5, leaf.labels[i + 1]: 0.25}
            cells.append(
                CellUncertainty(
                    alternative_id=alt,
                    criterion_id=leaf_id,
                    distribution=CategoricalDistribution(
                        labels=list(outcome), probabilities=list(outcome.values())
                    ),
                )
            )
    top = {node: tuple(sorted(SWINGS[node])) for node, _ in OBJECTIVES}
    groups = [
        GroupUncertainty(
            parent_id=None,
            kind="rating_intervals",
            intervals={node: (float(lo), float(hi)) for node, (lo, hi) in top.items()},
        )
    ]
    return SmaaModel(cells=cells, groups=groups)


def _promethee() -> PrometheeModel:
    criteria: list[PrometheeCriterion] = []
    for leaf in LEAVES:
        if leaf.parent == "mandate":
            coding = {label: float(i + 1) for i, label in enumerate(leaf.labels)}
            criteria.append(
                PrometheeCriterion(
                    criterion_id=leaf.id,
                    direction="maximise",
                    weight=0.0,
                    function=UsualFunction(),
                    coding=coding,
                )
            )
        elif leaf.id == "market_size":
            criteria.append(
                PrometheeCriterion(
                    criterion_id=leaf.id,
                    direction="maximise",
                    weight=6.25,
                    function=LinearPreferenceFunction(q=1.0, p=20.0),
                )
            )
        elif leaf.id == "market_growth":
            criteria.append(
                PrometheeCriterion(
                    criterion_id=leaf.id,
                    direction="maximise",
                    weight=6.25,
                    function=LinearPreferenceFunction(q=2.0, p=10.0),
                )
            )
        else:
            coding = {label: float(i + 1) for i, label in enumerate(leaf.labels)}
            criteria.append(
                PrometheeCriterion(
                    criterion_id=leaf.id,
                    direction="maximise",
                    weight=6.25,
                    function=VShapeFunction(p=2.0),
                    coding=coding,
                )
            )
    return PrometheeModel(criteria=criteria)


def _requirements() -> list[LabelsRequirement]:
    return [
        LabelsRequirement(
            id="hq_in_nz",
            name="Head office in New Zealand",
            criterion_id="hq_country",
            allowed=["New Zealand"],
            rationale="Fund mandate (hypothetical).",
        ),
        LabelsRequirement(
            id="stage_at_most_series_a",
            name="Stage at most Series A",
            criterion_id="stage",
            allowed=["Pre-seed", "Seed", "Series A"],
            rationale="Seed/Series A fund (hypothetical).",
        ),
        LabelsRequirement(
            id="sector_in_fund_list",
            name="Sector in the fund's list",
            criterion_id="sector",
            allowed=list(SECTORS),
            rationale="Generalist fund; 'Other' is outside the list.",
        ),
    ]


def build_project() -> Project:
    p = ps.new_project(
        "Venture screening: NZ startups for due diligence (public information)",
        description=(
            "Which early-stage New Zealand startups should a hypothetical generalist seed/Series A "
            "fund prioritise for its next due-diligence slots? Eight real companies, public "
            "information as of 4 November 2026, rated by the study author against written "
            "rubrics. A screening and prioritisation model: not investment advice, not a "
            "prediction of success; the companies were not contacted and are not affiliated."
        ),
        decision_maker="Hypothetical fund partners (Technical/IP-led and Commercial/traction-led)",
        method="mavt_sorting",
    )
    p = p.model_copy(update={"id": "nz_venture_screening_study"})  # fixed id: reproducible file
    for profile_id, name in PROFILES:
        p = ps.add_weight_profile(p, WeightProfile(id=profile_id, name=name))
    p = ps.remove_weight_profile(p, p.weight_profiles[0].id, PROFILES[0][0])
    p = ps.set_default_weight_profile(p, None)  # automatic: the first profile
    for alt, name in COMPANIES:
        p = ps.add_alternative(p, name, alt_id=alt)
    for obj, name in OBJECTIVES:
        p = ps.add_criterion(p, name, crit_id=obj)
    for leaf in LEAVES:
        kwargs = _labelled(leaf) if leaf.labels else _numeric(leaf)
        p = ps.add_criterion(p, leaf.name, leaf.parent, leaf.id, **kwargs)  # type: ignore[arg-type]
    for alt, _ in COMPANIES:
        for leaf_id, value in measurements(alt).items():
            p = ps.set_performance(p, alt, leaf_id, value)
    for i, (profile_id, _) in enumerate(PROFILES):
        for node, ratings in SWINGS.items():
            p = ps.set_judgement(p, node, float(ratings[i]), profile_id)
    p = ps.add_scenario(
        p,
        Scenario(
            id="linear_market_size",
            name="Linear market size (same fixed range)",
            value_function_overrides={
                "market_size": LinearValueFunction(direction=Direction.INCREASING)
            },
        ),
    )
    p = ps.set_sorting_model(
        p,
        SortingModel(
            classes=ps.sorting_classes(CLASSES),
            audit=SortingAudit(below_class_id="monitor", sample_size=1, seed=2026),
        ),
    )
    p = ps.set_requirements(p, _requirements())
    p = ps.set_smaa_model(p, _smaa())
    return ps.set_promethee_model(p, _promethee())


# ----------------------------------------------------------------------------------------------
# Evidence dossier and decision record
# ----------------------------------------------------------------------------------------------

RETRIEVED = "Retrieved 4 November 2026."


def _source(key: str, location: str, note: str, kind: Kind) -> Source:
    name, url, published, classification = SOURCES[key]
    dated = f"Published {published.isoformat()}." if published else "Undated page."
    return Source(
        name=name,
        reference=url,
        location=location,
        date=published or AS_OF,
        description=f"{kind.capitalize()}: {note} {dated} {RETRIEVED}",
        classification=classification,
    )


def _outdated(source: Source) -> bool:
    return source.date < OUTDATED_BEFORE


def _accepted() -> Review:
    return Review(
        status="accepted",
        reviewer=REVIEWER,
        reviewed_at=REVIEWED_AT,
        note="Illustrative review by the study author; not an independent verification.",
    )


def _market_source(alt: str, leaf: str) -> Source:
    segment, estimates = MARKETS[alt]
    field = "2025 value" if leaf == "market_size" else "forecast CAGR"
    listed = "; ".join(
        f"{e[0]} {e[3] if leaf == 'market_size' else e[4]} ({e[1]})" for e in estimates
    )
    return Source(
        name=f"Median of {len(estimates)} publisher estimates: {segment}",
        reference="examples/nz_venture_screening/README.md#market-estimates",
        location=f"Each publisher's stated {field}",
        date=min(e[2] for e in estimates),
        description=f"Observed (median rule): {listed}. {RETRIEVED}",
        classification="independent",
    )


def build_dossier(project: Project) -> EvidenceDossier:
    claims: list[Claim] = []
    origin = Origin(kind="human", proposed_by=AUTHOR)
    for alt, _ in COMPANIES:
        for leaf_id, (value, key, location, note, kind) in CELLS[alt].items():
            source = _source(key, location, note, kind)
            claims.append(
                Claim(
                    id=f"{alt}__{leaf_id}",
                    alternative_id=alt,
                    criterion_id=leaf_id,
                    value=value,
                    unit=None,
                    source=source,
                    origin=origin,
                    review=_accepted(),
                    outdated=_outdated(source),
                )
            )
        size, s_lo, s_hi, growth, g_lo, g_hi = market_cells(alt)
        for leaf_id, value, lo, hi, unit in (
            ("market_size", size, s_lo, s_hi, "US$ bn"),
            ("market_growth", growth, g_lo, g_hi, "% CAGR"),
        ):
            source = _market_source(alt, leaf_id)
            claims.append(
                Claim(
                    id=f"{alt}__{leaf_id}",
                    alternative_id=alt,
                    criterion_id=leaf_id,
                    value=value,
                    unit=unit,
                    source=source,
                    origin=origin,
                    review=_accepted(),
                    uncertainty_lower=lo,
                    uncertainty_upper=hi,
                    outdated=_outdated(source),
                )
            )
    for claim_id, alt, leaf_id, value, unit, key, location, note in DISPUTED:
        kind: Kind = "proxy" if leaf_id == "market_size" else "judgement"
        source = _source(key, location, note, kind)
        claims.append(
            Claim(
                id=claim_id,
                alternative_id=alt,
                criterion_id=leaf_id,
                value=value,
                unit=unit,
                source=source,
                origin=origin,
                review=None,
                outdated=_outdated(source),
            )
        )
    return EvidenceDossier(project_fingerprint=project.fingerprint(), claims=claims)


#: The illustrative selection, read from the built results (see the README).
SELECTED = "upstock"


def build_decision(project: Project) -> object:
    configurations = [
        AnalysisConfiguration(method="mavt_sorting", weight_profile_id="technical_ip"),
        AnalysisConfiguration(method="mavt_sorting", weight_profile_id="commercial_traction"),
        AnalysisConfiguration(
            method="mavt", weight_profile_id="technical_ip", scenario_id="linear_market_size"
        ),
        AnalysisConfiguration(
            method="smaa2",
            weight_profile_id="technical_ip",
            parameters={"uncertainty": "performance", "samples": 10_000, "seed": 2026},
        ),
        AnalysisConfiguration(
            method="smaa2",
            weight_profile_id="technical_ip",
            parameters={"uncertainty": "preference", "samples": 10_000, "seed": 2026},
        ),
        AnalysisConfiguration(method="promethee2", weight_profile_id="technical_ip"),
    ]
    details = DecisionDetails(
        owner="Hypothetical fund partner (illustrative)",
        date=AS_OF,
        outcome="selected",
        selected_alternative_id=SELECTED,
        alternatives_considered=[alt for alt, _ in COMPANIES],
        rationale=(
            "Illustrative: not a real decision and not investment advice. This company leads "
            "under both partner profiles and the linear market-size scenario, is the only one in "
            "Prioritise for diligence under both, leads the PROMETHEE II cross-check and most "
            "SMAA-2 draws, and meets the mandate. Its public evidence is more than a year old "
            "and largely self-reported, so the diligence slot's first task is to refresh it."
        ),
        configurations=configurations,
        unresolved_assumptions=[
            "Illustrative: the selected company's claims are outdated under the 12-month rule.",
            "Illustrative: Kea Aerospace's stage is a judgement; an aggregator reading disagrees.",
            "Illustrative: Scentian Bio's market size uses the publisher median, not the company figure.",
            "Illustrative: judgement-only rubric cells are listed in evidence.json and Open Questions.",
            "Illustrative: market estimates differ by publisher; SMAA-2 draws across their full range.",
        ],
        review_triggers=[
            "Illustrative: review by 1 February 2027.",
            "Illustrative: review when any company announces a regulatory approval or a new priced round.",
        ],
    )
    return decisions.create(project, details)


def _canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode()


def build_rubrics() -> dict[str, object]:
    """Each scored leaf's rubric, labels and kind, for a blind second rater (``scripts/rater_kit.py``).

    The mandate leaves are screened, not scored, so they are listed as excluded. Nothing here is a
    rating: it is the scale's own wording.
    """
    objective = dict(OBJECTIVES)
    scored: list[dict[str, object]] = []
    excluded: list[dict[str, object]] = []
    for leaf in LEAVES:
        if leaf.parent == "mandate":
            excluded.append(
                {
                    "id": leaf.id,
                    "name": leaf.name,
                    "parent_id": leaf.parent,
                    "parent_name": objective[leaf.parent],
                    "reason": "Mandate leaf: screened, not scored",
                }
            )
            continue
        numeric = not leaf.labels
        scored.append(
            {
                "id": leaf.id,
                "name": leaf.name,
                "parent_id": leaf.parent,
                "parent_name": objective[leaf.parent],
                "scale_type": "ratio" if numeric else "ordinal",
                "labels": list(leaf.labels),
                "rubric": leaf.rubric,
                "numeric": numeric,
            }
        )
    return {
        "version": 1,
        "study": "nz_venture_screening",
        "as_of": AS_OF.isoformat(),
        "scored_leaves": scored,
        "screened_excluded": excluded,
    }


def write_starter(project_bytes: bytes, dossier_bytes: bytes) -> None:
    """The gallery card: the project and its dossier, hash-checked by the existing loader."""
    STARTER.mkdir(exist_ok=True)
    (STARTER / "project.json").write_bytes(project_bytes)
    (STARTER / "evidence.json").write_bytes(dossier_bytes)
    project_version = json.loads(project_bytes)["schema_version"]
    manifest: dict[str, object] = {
        "artifacts": [
            {
                "for_model": None,
                "id": "project",
                "kind": "project",
                "label": "Project",
                "optional": False,
                "path": "project.json",
                "reset_policy": "draft",
                "schema_version": project_version,
                "sha256": hashlib.sha256(project_bytes).hexdigest(),
            },
            {
                "for_model": None,
                "id": "evidence",
                "kind": "evidence_dossier",
                "label": "Study evidence",
                "optional": False,
                "path": "evidence.json",
                "reset_policy": "draft",
                "schema_version": 1,
                "sha256": hashlib.sha256(dossier_bytes).hexdigest(),
            },
        ],
        "description": (
            "Eight real New Zealand startups from public information (as of 4 November 2026): "
            "mandate check, two partner profiles, classes, SMAA-2, PROMETHEE II and sourced "
            "evidence. Not investment advice."
        ),
        "id": "venture_screening_study",
        "schema_version": 1,
        "source_example": "examples/nz_venture_screening",
        "source_version": "1",
        "tasks": [
            "Read the screening summary and the requirements beside the ranking",
            "Switch between the Technical/IP-led and Commercial/traction-led profiles",
            "Compare classes, SMAA-2 acceptabilities and the PROMETHEE II cross-check",
            "Review the study's evidence and its open questions",
        ],
        "title": "Venture screening",
        "version": "1",
    }
    content = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    manifest["digest"] = hashlib.sha256(content.encode()).hexdigest()
    (STARTER / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    project = build_project()
    JsonProjectRepository().save(project, HERE / "project.json")
    dossier = build_dossier(project)
    (HERE / "evidence.json").write_bytes(_canonical(dossier.model_dump(mode="json")))
    record = build_decision(project)
    (HERE / "decision.json").write_bytes(_canonical(record.model_dump(mode="json")))  # type: ignore[attr-defined]
    (HERE / "rubrics.json").write_bytes(_canonical(build_rubrics()))
    write_starter((HERE / "project.json").read_bytes(), (HERE / "evidence.json").read_bytes())
    print(
        "wrote project.json, evidence.json, decision.json and rubrics.json "
        f"in {HERE} and the starter in {STARTER}"
    )


if __name__ == "__main__":
    main()
