"""Deterministically build the five-company first-round retrospective; no network access.

Read docs/design/first-round-study.md. The earlier Claude Code ratings were extended and corrected
by Codex; on 14 November 2026 Claude Code rated the 39 remaining cells under the owner's choice of
the venture study's convention (GAP_RULE_CELLS, each with its basis). Outcomes were known to both
tools; author review is pending. Only build_reference_set() and readme() use OUTCOMES. Nothing is
fitted to those outcomes.
"""

import json
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from statistics import median
from typing import Any

from mcda_studio.domain.evidence import Claim, EvidenceDossier, Origin, Source
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.domain.project import Project
from mcda_studio.domain.reference_cases import ReferenceCases
from mcda_studio.services import project_service as ps
from mcda_studio.services import reference_case_service, screening_summary_service
from mcda_studio.storage.json_repository import JsonProjectRepository

HERE = Path(__file__).parent
STUDY = HERE.parent / "nz_venture_screening"
PROJECT_ID = "nz_first_round_retrospective"
ORIGIN = Origin(
    kind="tool",
    proposed_by="Claude Code draft, extended and checked by Codex (draft; author review pending)",
    tool_id="claude-code",
)
COMPANIES = [
    ("vertus_energy", "Vertus Energy", "2021-10-27"),
    ("croptide", "Croptide", "2021-12-14"),
    ("rosterlab", "RosterLab", "2021-12-17"),
    ("argo_navis", "Argo Navis Aerospace", "2020-09-21"),
    ("helico", "Helico", "2022-05-09"),
]
ANCHORS = {key: date.fromisoformat(anchor) for key, _, anchor in COMPANIES}
STARTS = {key: anchor.replace(year=anchor.year - 1) for key, anchor in ANCHORS.items()}
ENDS = {key: anchor + timedelta(days=180) for key, anchor in ANCHORS.items()}
# name, reference URL, publication/capture date, classification.
SOURCES = {
    "vertus_scoop": (
        "Scoop (Vertus Energy company release)",
        (
            "https://www.scoop.co.nz/stories/BU2110/S00671/vertus-energy-raises-12m-t"
            "o-boost-biofuel-production.htm"
        ),
        "2021-10-27",
        "self_reported",
    ),
    "vertus_uoa": (
        "University of Auckland news",
        (
            "https://www.auckland.ac.nz/en/news/2022/01/27/biofuel-start-up-make-foss"
            "il-fuels-extinct.html"
        ),
        "2022-01-27",
        "self_reported",
    ),
    "helico_about": (
        "Helico About page (Wayback capture)",
        "https://web.archive.org/web/20220817231820/https://www.helico.bio/about",
        "2022-08-17",
        "self_reported",
    ),
    "croptide_scoop": (
        "Scoop (Croptide company release)",
        "https://www.scoop.co.nz/stories/BU2112/S00399.htm",
        "2021-12-15",
        "self_reported",
    ),
    "rosterlab_prn": (
        "PR Newswire (Quidnet Ventures release)",
        (
            "https://www.prnewswire.com/news-releases/rosterlab-raises-500k-pre-seed-"
            "from-quidnet-ventures-mat-fund-and-the-university-of-auckland-investors-"
            "fund-to-enter-the-new-zealand-market-301447073.html"
        ),
        "2021-12-17",
        "self_reported",
    ),
    "rosterlab_finsmes": (
        "FinSMEs",
        "https://www.finsmes.com/?p=214803",
        "2021-12-20",
        "independent",
    ),
    "rosterlab_site": (
        "RosterLab website (Wayback capture)",
        "https://web.archive.org/web/20220124/https://www.rosterlab.com/",
        "2022-01-24",
        "self_reported",
    ),
    "argo_site": (
        "Argo Navis Aerospace website (Wayback capture)",
        "https://web.archive.org/web/20200921113457/https://www.argonavis.aero/",
        "2020-09-21",
        "self_reported",
    ),
    "helico_site": (
        "Helico website (Wayback capture)",
        "https://web.archive.org/web/20220517/https://www.helico.bio/",
        "2022-05-17",
        "self_reported",
    ),
    "helico_early_site": (
        "Helico website, Science page (earlier own-site Wayback capture)",
        "https://web.archive.org/web/20201227141106/https://www.helico.bio/about-us",
        "2020-12-27",
        "self_reported",
    ),
    "helico_finsmes": (
        "FinSMEs",
        "https://www.finsmes.com/?p=228095",
        "2022-05-18",
        "independent",
    ),
    "helico_biospectrum": (
        "BioSpectrum Asia",
        (
            "https://www.biospectrumasia.com/index.php/news/53/20324/biopharma-helico"
            "-raises-seed-funding-for-producing-edible-medicines.html"
        ),
        "2022-05-18",
        "unknown",
    ),
}
OWN_SITES = {
    "rosterlab": {"rosterlab_site"},
    "argo_navis": {"argo_site"},
    "helico": {"helico_site", "helico_early_site", "helico_about"},
}
# Publisher, original URL, capture date, stated year, US$ bn, forecast CAGR %, segment, period.
# Paired estimates only. Duplicate publishers are refused rather than given extra votes.
MARKETS = {
    "vertus_energy": [
        (
            "Grand View Research",
            "https://www.grandviewresearch.com/industry-analysis/biogas-market",
            "2021-10-29",
            2021,
            "60.06",
            "4.4",
            "Biogas",
            "2021–2028",
        ),
        (
            "Fortune Business Insights",
            "https://www.fortunebusinessinsights.com/industry-reports/biogas-market-100910",
            "2021-11-25",
            2021,
            "25.61",
            "5.4",
            "Biogas",
            "2021–2028",
        ),
    ],
    "croptide": [
        (
            "MarketsandMarkets",
            "https://www.marketsandmarkets.com/PressReleases/smart-irrigation.asp",
            "2021-12-01",
            2021,
            "1.2",
            "14.9",
            "Smart irrigation",
            "2021–2026",
        ),
        (
            "Allied Market Research",
            "https://www.alliedmarketresearch.com/smart-irrigation-market",
            "2022-01-27",
            2020,
            "1.44",
            "13.9",
            "Smart irrigation",
            "2021–2030",
        ),
    ],
    "rosterlab": [
        (
            "Grand View Research",
            "https://www.grandviewresearch.com/industry-analysis/workforce-management-market",
            "2021-11-09",
            2020,
            "6.67",
            "10.5",
            "Workforce management",
            "2018–2025",
        ),
        (
            "MarketsandMarkets",
            "https://www.marketsandmarkets.com/PressReleases/workforce-management.asp",
            "2022-01-18",
            2020,
            "6.0",
            "9.3",
            "Workforce management",
            "2020–2025",
        ),
    ],
    "argo_navis": [
        (
            "MarketsandMarkets",
            "https://www.marketsandmarkets.com/PressReleases/space-propulsion.asp",
            "2020-10-13",
            2020,
            "6.7",
            "16.2",
            "Space propulsion",
            "2020–2025",
        ),
    ],
    "helico": [
        (
            "Coherent Market Insights",
            (
                "https://www.coherentmarketinsights.com/market-insight/plant-based-biolog"
                "ics-market-2394"
            ),
            "2022-08-05",
            2020,
            "0.0194",
            "3.4",
            "Plant-based biologics",
            "2020–2027",
        ),
    ],
}
MARKET_LIMITS = {
    "vertus_energy": (
        "Broad biogas segment, not a digester-control equipment TAM; publishers d"
        "isagree substantially."
    ),
    "croptide": (
        "Two publishers; 2021 and latest-earlier 2020 values are not extrapolated to a common year."
    ),
    "rosterlab": (
        "Two publishers; broad workforce management, not healthcare scheduling software alone."
    ),
    "argo_navis": (
        "One paired estimate; broad space propulsion includes satellites as well "
        "as launch vehicles."
    ),
    "helico": (
        "One eligible publisher; 2020 value, not extrapolated to 2022; no biosimilars proxy used."
    ),
}
# leaf -> (value, source key, rubric step and short claim in our own words).
# Missing cells are deliberately absent, not imputed from silence or from later outcomes.
CELLS: dict[str, dict[str, tuple[str | float, str, str]]] = {
    "vertus_energy": {
        "hq_country": (
            "New Zealand",
            "vertus_scoop",
            ("Mandate: Auckland facilities and a South Auckland demonstration site are described."),
        ),
        "stage": (
            "Pre-seed",
            "vertus_scoop",
            "Mandate: the NZ$1.2m round is explicitly labelled pre-seed.",
        ),
        "sector": (
            "Climate and energy",
            "vertus_scoop",
            "Mandate: BRIO raises biofuel output inside anaerobic digesters.",
        ),
        "founder_problem_fit": (
            "Recognised domain expert",
            "vertus_scoop",
            (
                "Step 4: Dr Danilo Perez is a biotechnology engineer with over a decade i"
                "n methane microbial research."
            ),
        ),
        "team_completeness": (
            "Two key roles named",
            "vertus_scoop",
            (
                "Step 2: Howard is COO and Perez and Gonzales provide domain/technical ex"
                "pertise; a separately named commercial lead is not established. The form"
                "er step-3 draft inferred a part-time role without support."
            ),
        ),
        "problem_severity": (
            "Company statement only",
            "vertus_scoop",
            (
                "Step 1: the company describes low methane yields and high digester opera"
                "ting costs; its release is not independent confirmation."
            ),
        ),
        "defensibility": (
            "Claimed, no protectable asset",
            "vertus_scoop",
            (
                "Step 2: BRIO has claimed performance advantages; no filed patent or excl"
                "usive licence is identified in this source."
            ),
        ),
        "readiness": (
            "Pilot-ready",
            "vertus_scoop",
            (
                "Pilot-ready: funding will expand field pilots; a first demonstration pla"
                "nt is planned for early 2022."
            ),
        ),
        "route_to_market": (
            "Offshore markets named",
            "vertus_scoop",
            (
                "Step 2: early discussions with digester operators in the US, Latin Ameri"
                "ca and Europe are reported."
            ),
        ),
        "customer_validation": (
            "Company claim only",
            "vertus_scoop",
            (
                "Step 1: favourable operator feedback is company-reported; independent va"
                "lidation is planned before securing customers."
            ),
        ),
        "commercial_stage": (
            "Pre-revenue",
            "vertus_uoa",
            (
                "Step 1 (draft): the January 2022 account says validation precedes securi"
                "ng local and international customers; no commercial delivery is describe"
                "d."
            ),
        ),
        "track_record": (
            "Prior venture or 5+ years operating",
            "vertus_uoa",
            (
                "Step 2: co-founder Freddy Gonzalez describes an earlier startup attempt "
                "ten years before Vertus; no outcome or outside capital is stated."
            ),
        ),
    },
    "croptide": {
        "hq_country": (
            "New Zealand",
            "croptide_scoop",
            "Mandate: the release places the company in Hawke's Bay, New Zealand.",
        ),
        "stage": (
            "Pre-seed",
            "croptide_scoop",
            "Mandate: the NZ$1m round is explicitly labelled pre-seed.",
        ),
        "sector": (
            "Agritech and food",
            "croptide_scoop",
            "Mandate: plant sensors support irrigation decisions for fruit and wine growers.",
        ),
        "founder_problem_fit": (
            "Adjacent experience",
            "croptide_scoop",
            (
                "Step 2: the founders were engineering students; the release does not est"
                "ablish three years in horticulture."
            ),
        ),
        "team_completeness": (
            "Two key roles named",
            "croptide_scoop",
            (
                "Step 2: technical co-founders and commercial director Nick Fitzpatrick a"
                "re named; no separate domain/regulatory lead is established."
            ),
        ),
        "track_record": (
            "Prior venture or 5+ years operating",
            "croptide_scoop",
            (
                "Step 2: Penny previously founded an electric-weeding venture in 2019; Fi"
                "tzpatrick spent ten years establishing T&G offices. A qualifying senior "
                "role at scale is not explicitly established."
            ),
        ),
        "problem_severity": (
            "Independently confirmed",
            "croptide_scoop",
            (
                "Step 2: named grower representative David Allen confirms the need, altho"
                "ugh his quotation is carried in a company release."
            ),
        ),
        "defensibility": (
            "Claimed, no protectable asset",
            "croptide_scoop",
            (
                "Step 2: a more precise stem-tissue sensing approach is claimed; no filed"
                " patent or exclusive licence is named."
            ),
        ),
        "readiness": (
            "Pilot-ready",
            "croptide_scoop",
            (
                "Pilot-ready: named growers have signed up for summer trials in three New"
                " Zealand regions."
            ),
        ),
    },
    "rosterlab": {
        "hq_country": (
            "New Zealand",
            "rosterlab_finsmes",
            "Mandate: the company is explicitly described as New Zealand-based.",
        ),
        "stage": (
            "Pre-seed",
            "rosterlab_prn",
            "Mandate: the total NZ$500k round is labelled pre-seed; Quidnet's share is NZ$150k.",
        ),
        "sector": (
            "Fintech and B2B software",
            "rosterlab_prn",
            "Mandate: rostering software sold to organisations, initially healthcare providers.",
        ),
        "founder_problem_fit": (
            "3+ years in the domain",
            "rosterlab_site",
            (
                "Step 3 (draft): the website describes three years of rostering IP; the r"
                "ound release (https://www.prnewswire.com/news-releases/rosterlab-raises-"
                "500k-pre-seed-from-quidnet-ventures-mat-fund-and-the-university-of-auckl"
                "and-investors-fund-to-enter-the-new-zealand-market-301447073.html, 2021-"
                "12-17) attributes the underlying work to co-founder Isaac Cleland's PhD."
                " Commercial industry experience is not established."
            ),
        ),
        "team_completeness": (
            "One key role named",
            "rosterlab_prn",
            (
                "Step 1: Cleland is identified with the technical work; co-founders Ge an"
                "d Feng are named without commercial or domain-lead roles."
            ),
        ),
        "problem_severity": (
            "Company statement only",
            "rosterlab_site",
            (
                "Step 1: the company states that healthcare staff lose time to administra"
                "tion; no independently quantified cost is supplied."
            ),
        ),
        "defensibility": (
            "Claimed, no protectable asset",
            "rosterlab_site",
            (
                "Step 2: algorithmic IP and benchmark performance are claimed; no filed p"
                "atent, exclusive licence or proprietary dataset is named."
            ),
        ),
        "readiness": (
            "Prototype",
            "rosterlab_prn",
            (
                "Prototype (draft): existing research technology underlies software still"
                " funded for application development and initial product launch."
            ),
        ),
        "customer_validation": (
            "Company claim only",
            "rosterlab_site",
            (
                "Step 1: rostering capabilities are company claims; no independently veri"
                "fiable customer or trial is named."
            ),
        ),
        "commercial_stage": (
            "Pre-revenue",
            "rosterlab_prn",
            (
                "Step 1 (draft): funds support the initial product launch; this is not pr"
                "oof that no other revenue existed."
            ),
        ),
    },
    "argo_navis": {
        "hq_country": (
            "New Zealand",
            "argo_site",
            "Mandate: the company lists its contact address in Parnell, Auckland.",
        ),
        "sector": (
            "Space and advanced hardware",
            "argo_site",
            "Mandate: chemical propulsion systems for the space industry.",
        ),
        "founder_problem_fit": (
            "Recognised domain expert",
            "argo_site",
            (
                "Step 4: both founders have doctorates in rocket dynamics/control and Roc"
                "ket Lab experience, including a senior mission-delivery role."
            ),
        ),
        "team_completeness": (
            "Two key roles named",
            "argo_site",
            (
                "Step 2: CEO Avinash Rao and CTO Malcolm Snowdon are named; a separate do"
                "main/regulatory lead is not established."
            ),
        ),
        "track_record": (
            "Senior role at scale or funded venture",
            "argo_site",
            (
                "Step 3 (draft): Rao led Electron guidance and became Rocket Lab's Direct"
                "or of Mission Delivery; the source does not establish a scaled-company e"
                "xecutive role for step 4."
            ),
        ),
        "defensibility": (
            "Claimed, no protectable asset",
            "argo_site",
            (
                "Step 2: performance, cost, scalability and reliability differentiation i"
                "s claimed; no protected asset is named."
            ),
        ),
    },
    "helico": {
        "hq_country": (
            "New Zealand",
            "helico_finsmes",
            "Mandate: the company is described as Auckland, New Zealand-based.",
        ),
        "stage": (
            "Seed",
            "helico_finsmes",
            "Mandate: AUD 1.8m is explicitly labelled seed, not pre-seed.",
        ),
        "sector": (
            "Health and medtech",
            "helico_finsmes",
            "Mandate: plant-based production of biopharmaceutical medicines.",
        ),
        "problem_severity": (
            "Company statement only",
            "helico_site",
            (
                "Step 1: the company presents lower-cost access to medicines as its aim; "
                "independent cost evidence is not supplied."
            ),
        ),
        "defensibility": (
            "Claimed, no protectable asset",
            "helico_finsmes",
            (
                "Step 2: a proprietary computational platform is described, but no filed "
                "patent, exclusive licence or proprietary dataset is identified."
            ),
        ),
        "customer_validation": (
            "Company claim only",
            "helico_site",
            (
                "Step 1: services for pharmaceutical and biotech clients are offered with"
                "out an independently verifiable named customer."
            ),
        ),
        "team_completeness": (
            "All three, one part-time",
            "helico_about",
            (
                "Step 3: Vensky leads commercial work, Wang technical bioinformatics, and"
                " Marcel advises on manufacturing and CMC/regulatory work. This is the Au"
                "gust 2022 team, not proof of appointments at the announcement."
            ),
        ),
        "track_record": (
            "Prior venture or 5+ years operating",
            "helico_about",
            (
                "Step 2: VP Technology and Operation Coline Mei-Barker has five years of "
                "CRO scientific, project-management and business-development experience; "
                "founder-only experience is not established."
            ),
        ),
        "board_advisors": (
            "Independent chair or domain advisor",
            "helico_about",
            (
                "Step 3: named advisors include plant-physiology scientist David Jackson "
                "and plant-made pharmaceutical manufacturing specialist Sylvain Marcel; t"
                "heir appointment dates are not stated."
            ),
        ),
    },
}
# Owner decisions in chat, 14 November 2026: rate the 39 formerly missing cells with the venture
# study's own convention. When the eligible sources read say nothing, the rubric's lowest
# "nothing public" label applies (None named, None public, No offshore route stated,
# Pre-revenue, Company claim only, No dated public milestone, Concept); regulatory burden is a
# sector judgement ("no product approval regime identified"); competitive intensity names funded
# players from an in-window publisher page. Argo Navis's stage uses one stated window exception.
# Basis is reported per company: thin public records fall to the lowest labels, which biases
# against companies that later closed. No outcome was consulted to choose a label.
ABSENCE = "Absence rule (owner decision, 14 Nov 2026; the venture study's convention): "
SECTOR = "Sector judgement (owner decision, 14 Nov 2026; the venture study's convention): "
EXCEPTION = "Window exception (owner decision, 14 Nov 2026): "
WINDOW_EXCEPTIONS = {("argo_navis", "stage"): "argo_satnews"}
GAP_RULE_SOURCES = {
    "argo_satnews": (
        "SatNews",
        "https://satnews.com/2023/03/13/argo-navis-aerospace-poised-to-propel-rocket-engines/",
        "2023-03-13",
        "independent",
    ),
    "helico_callaghan": (
        "Callaghan Innovation customer story",
        "https://www.callaghaninnovation.govt.nz/stories/health-food/",
        "2021-11-08",
        "unknown",
    ),
    "vertus_gvr_page": (
        "Grand View Research, biogas market (Wayback capture)",
        (
            "https://web.archive.org/web/20211029/https://www.grandviewresearch.com/industry-analysis/biogas-market"
        ),
        "2021-10-29",
        "independent",
    ),
    "croptide_mm_page": (
        "MarketsandMarkets, smart irrigation release (Wayback capture)",
        (
            "https://web.archive.org/web/20211201/https://www.marketsandmarkets.com/PressReleases/smart-irrigation.asp"
        ),
        "2021-12-01",
        "independent",
    ),
    "rosterlab_gvr_page": (
        "Grand View Research, workforce management market (Wayback capture)",
        (
            "https://web.archive.org/web/20211109/https://www.grandviewresearch.com/industry-analysis/workforce-management-market"
        ),
        "2021-11-09",
        "independent",
    ),
    "argo_mm_page": (
        "MarketsandMarkets, space propulsion release (Wayback capture)",
        (
            "https://web.archive.org/web/20201013/https://www.marketsandmarkets.com/PressReleases/space-propulsion.asp"
        ),
        "2020-10-13",
        "independent",
    ),
    "helico_cmi_page": (
        "Coherent Market Insights, plant-based biologics market (Wayback capture)",
        (
            "https://web.archive.org/web/20220805124836/https://www.coherentmarketinsights.com/market-insight/plant-based-biologics-market-2394"
        ),
        "2022-08-05",
        "independent",
    ),
}
# leaf -> (value, source key, basis, note). Basis: observed, absence, sector or exception.
GAP_RULE_CELLS: dict[str, dict[str, tuple[str, str, str, str]]] = {
    "vertus_energy": {
        "board_advisors": (
            "None named",
            "vertus_scoop",
            "absence",
            (
                "No director or advisor is named; NOAB Ventures' John Wood is described as an "
                "investor bringing energy experience, not as a director or advisor."
            ),
        ),
        "regulatory_burden": (
            "No approval required",
            "vertus_scoop",
            "sector",
            (
                "BRIO is process technology inside anaerobic digesters; no product approval regime "
                "is identified in the sources read. Organism or site permits were not researched."
            ),
        ),
        "competitive_intensity": (
            "Several funded leaders",
            "vertus_gvr_page",
            "observed",
            (
                "Judgement: the release compares BRIO with other digester systems on the market; "
                "the in-window publisher page names Air Liquide, Wartsila and EnviTec Biogas, all "
                "listed, among digester-system leaders. Broad: they build whole plants rather than "
                "in-digester boosters."
            ),
        ),
        "partnerships": (
            "None public",
            "vertus_scoop",
            "absence",
            (
                "Every named organisation is an investor or accelerator; the demonstration farm "
                "and research institute are unnamed."
            ),
        ),
        "milestone_delivery": (
            "Announced, none yet due",
            "vertus_uoa",
            "observed",
            (
                "Step 2: the October release scheduled a first demonstration plant for early 2022; "
                "the January account still describes expanding pilots, and no delivery is reported "
                "inside the window."
            ),
        ),
    },
    "croptide": {
        "board_advisors": (
            "None named",
            "croptide_scoop",
            "absence",
            (
                "No director or advisor is named; Icehouse Ventures, K1W1 and Masfen Group are "
                "investors."
            ),
        ),
        "regulatory_burden": (
            "No approval required",
            "croptide_scoop",
            "sector",
            "Plant-mounted water sensors and software; no product approval regime is identified.",
        ),
        "competitive_intensity": (
            "Several funded leaders",
            "croptide_mm_page",
            "observed",
            (
                "Judgement: the in-window publisher page names listed or listed-owned "
                "smart-irrigation leaders including The Toro Company, Netafim and Jain Irrigation. "
                "Broad: most sell irrigation control rather than stem sensors."
            ),
        ),
        "route_to_market": (
            "No offshore route stated",
            "croptide_scoop",
            "absence",
            (
                "The eligible release names New Zealand trial regions only; the NZ Herald's "
                "paywalled body is not used."
            ),
        ),
        "customer_validation": (
            "Unpaid trial",
            "croptide_scoop",
            "observed",
            (
                "Step 2: T&G Global, Pernod Ricard Winemakers, Cloudy Bay, Indevin and Ngai "
                "Tukairangi Trust joined summer pilots, with Pernod Ricard quoted; payment is not "
                "stated, so the venture study's convention gives an unpaid trial."
            ),
        ),
        "commercial_stage": (
            "Pre-revenue",
            "croptide_scoop",
            "absence",
            "Only pilots are described; no revenue or paying customer is stated.",
        ),
        "partnerships": (
            "None public",
            "croptide_scoop",
            "absence",
            "The named organisations are pilot customers or investors, not non-customer partners.",
        ),
        "milestone_delivery": (
            "No dated public milestone",
            "croptide_scoop",
            "absence",
            "Funds progress current pilots and development; no dated future milestone is stated.",
        ),
    },
    "rosterlab": {
        "track_record": (
            "None public",
            "rosterlab_prn",
            "absence",
            (
                "The three co-founders' research and competition wins are named; no earlier "
                "venture or 5+ years operating is stated."
            ),
        ),
        "board_advisors": (
            "None named",
            "rosterlab_prn",
            "absence",
            "Investors promise governance support, but no director or advisor is named.",
        ),
        "regulatory_burden": (
            "No approval required",
            "rosterlab_site",
            "sector",
            "Rostering software; no product approval regime is identified.",
        ),
        "competitive_intensity": (
            "Several funded leaders",
            "rosterlab_gvr_page",
            "observed",
            (
                "Judgement: the company says it is faster than current solutions; the in-window "
                "publisher page names Kronos, SAP, Oracle and Infor as prominent "
                "workforce-management players. Broad: general workforce management, not healthcare "
                "rostering alone."
            ),
        ),
        "route_to_market": (
            "No offshore route stated",
            "rosterlab_prn",
            "absence",
            (
                "Launch targets New Zealand healthcare; overseas expansion is mentioned without a "
                "named market or process."
            ),
        ),
        "partnerships": (
            "None public",
            "rosterlab_prn",
            "absence",
            (
                "The University of Auckland origin and the completed VentureLab programme are not "
                "a current named partner; the others are investors."
            ),
        ),
        "milestone_delivery": (
            "No dated public milestone",
            "rosterlab_prn",
            "absence",
            "An initial product launch is planned without a date.",
        ),
    },
    "argo_navis": {
        "stage": (
            "Pre-seed",
            "argo_satnews",
            "exception",
            (
                "SatNews (13 March 2023) reports that WNT Ventures provided NZ$1m in a pre-seed "
                "round in 2020; the in-window website already named WNT Ventures as a backer. Used "
                "for this mandate cell only; it is never a reference-case rating."
            ),
        ),
        "board_advisors": (
            "None named",
            "argo_site",
            "absence",
            (
                "Only the two co-founders are named; WNT Ventures and Callaghan Innovation are "
                "named as backers."
            ),
        ),
        "problem_severity": (
            "Company statement only",
            "argo_site",
            "observed",
            (
                "Step 1: the site claims an unmatched combination of performance, scalability, "
                "reliability and cost; no independent source confirms the problem."
            ),
        ),
        "readiness": (
            "Concept",
            "argo_site",
            "absence",
            (
                "The capture lists propulsion specialities but states no prototype, test or "
                "product status."
            ),
        ),
        "regulatory_burden": (
            "No approval required",
            "argo_site",
            "sector",
            (
                "A propulsion-system supplier; no product approval regime is identified for the "
                "component itself. Launch licences, propellant permits and export controls were "
                "not researched."
            ),
        ),
        "competitive_intensity": (
            "Several funded leaders",
            "argo_mm_page",
            "observed",
            (
                "Judgement: the in-window publisher page names Safran, Aerojet Rocketdyne, "
                "Northrop Grumman, IHI and SpaceX as leading space-propulsion players; all are "
                "listed or heavily funded."
            ),
        ),
        "route_to_market": (
            "No offshore route stated",
            "argo_site",
            "absence",
            "No offshore market, channel or entity is stated.",
        ),
        "customer_validation": (
            "Company claim only",
            "argo_site",
            "absence",
            "No customer, trial or pilot is named.",
        ),
        "commercial_stage": (
            "Pre-revenue",
            "argo_site",
            "absence",
            "No revenue or customer is stated.",
        ),
        "partnerships": (
            "None public",
            "argo_site",
            "absence",
            (
                "Callaghan Innovation is named as a backer; no programme or non-funding "
                "partnership is stated."
            ),
        ),
        "milestone_delivery": (
            "No dated public milestone",
            "argo_site",
            "absence",
            "No dated plan is stated.",
        ),
    },
    "helico": {
        "founder_problem_fit": (
            "3+ years in the domain",
            "helico_about",
            "observed",
            (
                "Step 3: co-founder Wayman Puna is described with extensive biotechnology "
                "experience in plant synthetic biology and co-founder Xiaoming Wang holds a "
                "bioengineering PhD; 'extensive' is not quantified. August 2022 page."
            ),
        ),
        "readiness": (
            "Concept",
            "helico_site",
            "observed",
            (
                "Step 1: the site says expression is still to be validated in plants on a path to "
                "proof of concept; stable-line services are offered without a delivered example."
            ),
        ),
        "regulatory_burden": (
            "Approval required, not started",
            "helico_finsmes",
            "sector",
            (
                "Plant-made therapeutic proteins need medicines approval before human use; the "
                "company holds only an EPA approval for GMO research and development."
            ),
        ),
        "competitive_intensity": (
            "Several funded leaders",
            "helico_cmi_page",
            "observed",
            (
                "Judgement: the in-window publisher page names iBio, Protalix, Medicago, Pfizer "
                "and Kentucky BioProcessing among plant-based biologics players; several are "
                "listed."
            ),
        ),
        "route_to_market": (
            "No offshore route stated",
            "helico_site",
            "absence",
            (
                "Seed licensing 'anywhere in the world' is a vision; no offshore market, licensee "
                "or process is named."
            ),
        ),
        "commercial_stage": (
            "Pre-revenue",
            "helico_site",
            "absence",
            (
                "Services are offered to pharmaceutical and biotech clients, but no client or "
                "revenue is stated."
            ),
        ),
        "partnerships": (
            "Partner in an active programme",
            "helico_callaghan",
            "observed",
            (
                "Step 3: Callaghan Innovation supports Helico through grants, the HealthTech "
                "Activator market-validation programme, Beyond IP and its R&D Solutions team. The "
                "page states 8 Nov 2021; its metadata says 16 Aug 2023 and no earlier archive "
                "capture was found, so this date needs review."
            ),
        ),
        "milestone_delivery": (
            "No dated public milestone",
            "helico_site",
            "absence",
            (
                "No dated plan is stated in the eligible pages; a three-to-five-year vision is not "
                "a milestone."
            ),
        ),
    },
}
PREFIX = {"observed": "", "absence": ABSENCE, "sector": SECTOR, "exception": EXCEPTION}
SOURCES.update(GAP_RULE_SOURCES)
for _alt, _cells in GAP_RULE_CELLS.items():
    for _leaf, (_value, _key, _basis, _note) in _cells.items():
        if _leaf in CELLS[_alt]:
            raise ValueError(f"{_alt}/{_leaf}: gap-rule cell already rated")
        CELLS[_alt][_leaf] = (_value, _key, PREFIX[_basis] + _note)
BASIS = {
    (alt, leaf): basis
    for alt, cells in GAP_RULE_CELLS.items()
    for leaf, (_, _, basis, _) in cells.items()
}
# Outcomes are deliberately separate from CELLS and never consumed by build_project/dossier.
OUTCOMES = {
    "vertus_energy": (
        "Larger follow-on round raised",
        "2024-06-27",
        "Tech.eu",
        (
            "https://tech.eu/2024/06/27/vertus-energy-raises-eur875m-seed-funding-for"
            "-waste-to-x-biotech-solutions/"
        ),
        "2024-06-27",
        "A EUR 8.75m seed round led by Energy Capital Ventures was reported.",
    ),
    "croptide": (
        "Larger follow-on round raised",
        "2023-12-13",
        "Fruitnet",
        (
            "https://www.fruitnet.com/produce-plus/croptide-to-launch-commercial-pilo"
            "ts-following-seed-funding-raise/257555.article"
        ),
        "2023-12-13",
        (
            "A NZ$4.25m seed round with US investors and Icehouse Ventures was report"
            "ed; lead not stated."
        ),
    ),
    "rosterlab": (
        "Larger follow-on round raised",
        "2024-11-27",
        "University of Auckland",
        (
            "https://www.auckland.ac.nz/en/news/2024/11/27/rosterlab-levels-support-h"
            "ealthcare-workers.html"
        ),
        "2024-11-27",
        ("A NZ$1.75m seed round led by Movac with Pacific Channel and UniServices was reported."),
    ),
    "argo_navis": (
        "Liquidator appointed",
        "2023-12-05",
        "New Zealand Gazette, 2023-al5719",
        "https://gazette.govt.nz/notice/id/2023-al5719",
        "2023-12-08",
        (
            "The notice records a liquidator's appointment on 5 December 2023 by shar"
            "eholder resolution."
        ),
    ),
    "helico": (
        "Liquidator appointed",
        "2025-12-19",
        "New Zealand Gazette, 2026-al121",
        "https://gazette.govt.nz/notice/id/2026-al121",
        "2026-01-13",
        (
            "Joint liquidators were appointed to Rau Bio Limited, trading as Helico B"
            "io, on 19 December 2025."
        ),
    ),
}


def check_date(alt: str, key: str, leaf: str | None = None) -> None:
    if leaf is not None and WINDOW_EXCEPTIONS.get((alt, leaf)) == key:
        return  # the owner's single stated exception, for that one cell only
    when = date.fromisoformat(SOURCES[key][2])
    if when > ENDS[alt] or (when < STARTS[alt] and key not in OWN_SITES.get(alt, set())):
        raise ValueError(f"{alt}/{key}: rating source outside the permitted window")


def market_values(alt: str) -> tuple[float, float]:
    estimates = MARKETS[alt]
    publishers = [e[0] for e in estimates]
    if not estimates or len(set(publishers)) != len(publishers):
        raise ValueError(f"{alt}: estimates need distinct publishers")
    for _, _, captured, year, _, _, _, _ in estimates:
        if not STARTS[alt] <= date.fromisoformat(captured) <= ENDS[alt]:
            raise ValueError(f"{alt}: market capture outside window")
        if year > ANCHORS[alt].year:
            raise ValueError(f"{alt}: market year after anchor year")
    size = float(median([Decimal(e[4]) for e in estimates]))
    growth = float(median([Decimal(e[5]) for e in estimates]))
    return size, growth


def market_description(alt: str) -> str:
    details = []
    for publisher, url, captured, year, size, growth, segment, period in MARKETS[alt]:
        archive = f"https://web.archive.org/web/{captured.replace('-', '')}/{url}"
        details.append(
            f"{publisher}: {segment}; {year} US${size} bn; {growth}% CAGR ({period}); "
            f"captured {captured}; {archive} (original {url})."
        )
    return " ".join(details) + " " + MARKET_LIMITS[alt]


def source(alt: str, key: str, note: str, leaf: str | None = None) -> Source:
    check_date(alt, key, leaf)
    name, url, when, classification = SOURCES[key]
    return Source(
        name=name,
        reference=url,
        date=date.fromisoformat(when),
        location="Relevant article body or archived company page",
        description=(
            f"Judgement: {note} Read from saved page on 13 November 2026. "
            "Draft; author review pending."
        ),
        classification=classification,
    )


def build_project() -> Project:
    study = JsonProjectRepository().load(STUDY / "project.json")
    project = Project(
        id=PROJECT_ID,
        title="Looking back: five NZ first rounds (public information)",
        description=(
            "A hypothetical seed/Series A fund's retrospective diligence screen of fi"
            "ve New Zealand companies at their first funding rounds, using public sou"
            "rces from 12 months before each anchor through 180 days after it and ear"
            "lier own-site captures. Claude Code draft extended and checked by Codex,"
            " with hindsight; author review pending. Market years are each company's "
            "anchor year or latest stated earlier year, not the copied rubric's 2025."
            " Cells the eligible sources are silent on carry the rubric's lowest 'nothi"
            "ng public' label, as in the venture study (owner decision, 14 November 2026"
            "). Not investment advice. Not a prediction. Companies neither contacted"
            " nor affiliated."
        ),
        decision_maker="Hypothetical seed/Series A fund partners",
        criteria=study.criteria,
        weight_profiles=study.weight_profiles,
        sorting=study.sorting,
        requirements=study.requirements,
        analysis=AnalysisConfiguration(method="mavt_sorting"),
    )
    for alt, name, _ in COMPANIES:
        project = ps.add_alternative(project, name, alt_id=alt)
        for leaf, (value, key, _) in CELLS[alt].items():
            check_date(alt, key, leaf)
            project = ps.set_performance(project, alt, leaf, value)
        size, growth = market_values(alt)
        project = ps.set_performance(project, alt, "market_size", size)
        project = ps.set_performance(project, alt, "market_growth", growth)
    return project


def build_dossier(project: Project) -> EvidenceDossier:
    claims = []
    for alt, _, _ in COMPANIES:
        for leaf, (value, key, note) in CELLS[alt].items():
            claims.append(
                Claim(
                    id=f"{alt}__{leaf}",
                    alternative_id=alt,
                    criterion_id=leaf,
                    value=value,
                    unit=None,
                    source=source(alt, key, note, leaf),
                    origin=ORIGIN,
                    review=None,
                )
            )
        for leaf, value, unit in zip(
            ("market_size", "market_growth"), market_values(alt), ("US$ bn", "% CAGR"), strict=True
        ):
            estimates = MARKETS[alt]
            latest = max(e[2] for e in estimates)
            url = next(e[1] for e in estimates if e[2] == latest)
            market_source = Source(
                name="Market estimates: " + "; ".join(e[0] for e in estimates),
                reference=f"https://web.archive.org/web/{latest.replace('-', '')}/{url}",
                date=date.fromisoformat(latest),
                location="Publisher market overview and report scope",
                classification="independent",
                description=(
                    f"Judgement: {leaf}: median of {len(estimates)} distinct publisher "
                    f"estimate(s), {value} {unit}. Anchor-year rule overrides the unchanged "
                    f"2025 rubric wording. {market_description(alt)} Draft; author review pending."
                ),
            )
            claims.append(
                Claim(
                    id=f"{alt}__{leaf}",
                    alternative_id=alt,
                    criterion_id=leaf,
                    value=value,
                    unit=unit,
                    source=market_source,
                    origin=ORIGIN,
                    review=None,
                )
            )
    return EvidenceDossier(project_fingerprint=project.fingerprint(), claims=claims)


def build_reference_set(project: Project) -> dict[str, Any]:
    sources = {}
    cases = []
    for alt, name, anchor in COMPANIES:
        claims, ratings = [], []
        for leaf, (value, key, note) in CELLS[alt].items():
            if (alt, leaf) in WINDOW_EXCEPTIONS:
                continue  # dated after the snapshot; a mandate cell that is never compared
            check_date(alt, key)
            claim_id = f"{alt}__{leaf}"
            sources[key] = source(alt, key, note).model_dump(mode="json")
            claims.append(
                dict(id=claim_id, text=note, source=key, origin=ORIGIN.model_dump(mode="json"))
            )
            ratings.append(dict(criterion_id=leaf, label=value, claim_ids=[claim_id], note=note))
        label, as_of, publisher, url, published, text = OUTCOMES[alt]
        outcome_id, outcome_source = f"{alt}__outcome", f"{alt}__outcome_source"
        sources[outcome_source] = dict(
            name=publisher,
            reference=url,
            date=published,
            description=(
                "Outcome context only; never a rating input. Read saved page on 13 November 2026."
            ),
            classification="independent",
        )
        claims.append(
            dict(
                id=outcome_id,
                text=text,
                source=outcome_source,
                origin=ORIGIN.model_dump(mode="json"),
            )
        )
        context = [
            dict(label="Round announcement / anchor date", value=anchor),
            dict(
                label="Rating window",
                value=(
                    f"{STARTS[alt].isoformat()} to {ENDS[alt].isoformat()} inclusive; "
                    "earlier own-site captures allowed"
                ),
            ),
        ]
        if alt == "argo_navis":
            context.append(
                dict(
                    label="Anchor qualification",
                    value=(
                        "Earliest saved website capture naming WNT Ventures; first-round date unc"
                        "onfirmed. No later round-label evidence used for ratings."
                    ),
                )
            )
        if alt == "helico":
            context.append(
                dict(
                    label="Round label", value="First round labelled seed, not pre-seed; AUD 1.8m."
                )
            )
        cases.append(
            dict(
                id=alt,
                name=name,
                snapshot_date=ENDS[alt].isoformat(),
                context=context,
                claims=claims,
                ratings=ratings,
                outcome=dict(label=label, as_of=as_of, note=text, claim_ids=[outcome_id]),
            )
        )
    return dict(
        kind="reference-cases",
        version=1,
        id=PROJECT_ID + "_cases",
        title="Five first-round snapshots",
        description=(
            "Draft, author review pending; rated with hindsight. Five cases are not r"
            "epresentative. The cases are the project's own companies: leave a compan"
            "y's own case out (exclude_same_id) to compare it with the other four. Si"
            "milarity predicts nothing."
        ),
        criteria_from=project.id,
        cases=cases,
        sources=sources,
    )


def readme(project: Project) -> str:
    tree = project.tree()
    leaves = tree.leaves()
    coverage = []
    outcomes = []
    markets = []
    for alt, name, anchor in COMPANIES:
        rated = set(CELLS[alt]) | {"market_size", "market_growth"}
        if [leaf for leaf in leaves if leaf not in rated]:
            raise ValueError(f"{alt}: every cell needs a rating under the owner's rule")
        counts = {basis: 0 for basis in PREFIX}
        for leaf in leaves:
            counts[BASIS.get((alt, leaf), "observed")] += 1
        coverage.append(
            f"| {name} | {counts['observed']} | {counts['absence']} | {counts['sector']} "
            f"| {counts['exception']} | {len(leaves)} |"
        )
        label, as_of, _, url, _, _ = OUTCOMES[alt]
        outcomes.append(
            f"| {name} | {anchor} | {STARTS[alt]} to {ENDS[alt]} | [{label}]({url}) ({as_of}) |"
        )
    names = {alt: name for alt, name, _ in COMPANIES}
    ranked: dict[str, dict[str, tuple[int, float, str]]] = {alt: {} for alt in names}
    for profile in PROFILES:
        summary = screening_summary_service.screening_summary(
            project, AnalysisConfiguration(method="mavt_sorting", weight_profile_id=profile)
        )
        if summary.status != "available":
            raise ValueError(f"{profile}: screening unavailable: {summary.reason}")
        for row in summary.rows:
            assert row.rank is not None and row.value is not None
            ranked[row.alternative_id][profile] = (row.rank, row.value, row.class_name or "")
    order = sorted(names, key=lambda alt: ranked[alt][PROFILES[0]][0])
    results = []
    for alt in order:
        cells = " | ".join(
            f"{ranked[alt][p][0]} ({ranked[alt][p][1]:.4f}, {ranked[alt][p][2]})" for p in PROFILES
        )
        label, as_of, _, url, _, _ = OUTCOMES[alt]
        results.append(f"| {names[alt]} | {cells} | [{label}]({url}) ({as_of}) |")
        size, growth = market_values(alt)
        markets.append(
            f"| {names[alt]} | {size} | {growth} | {len(MARKETS[alt])} | {MARKET_LIMITS[alt]} |"
        )
    return (
        """# Looking back: five New Zealand first rounds

Generated by `build.py` on the study basis of 13 November 2026. Change the builder, not its outputs.

**The decision.** A hypothetical seed/Series A fund screens Vertus Energy, Croptide, RosterLab,
Argo Navis Aerospace and Helico as they stood around their first funding rounds. This is a
look-back showcase, not a validation study. Five companies cannot show whether the method
predicts anything.

**Not investment advice. Not a prediction. Companies neither contacted nor affiliated.
Outcomes are public facts as of the date shown and say nothing about the people involved.**

**Hindsight.** These ratings extend an earlier Claude Code draft. Codex checked and extended it,
and on 14 November 2026 Claude Code rated the 39 remaining cells under the owner's rule; every
tool knew each company's outcome. Every rating is a **draft; author review pending**.
Source-date guards cannot remove hindsight bias. A blind re-rating packet is a next
step, not an independent assessment already completed.

**Survivorship.** Public sources under-report companies that closed. Under the owner's rule a
silent source gives the lowest label, so a thin public record lowers a score; that is a fact
about the record, not about company quality. This selected set of five is not representative.

**Round labels.** Helico's first round was labelled **seed**, not pre-seed. Argo Navis's first-round
date remains unconfirmed: its anchor is the earliest saved company-site capture naming WNT.

## Windows and outcomes (context only)

| Company | Anchor | Allowed window (last day = snapshot) | Outcome (as of) |
| --- | --- | --- | --- |
"""
        + "\n".join(outcomes)
        + """

The owner widened the original 90-day windows in chat on 13 November 2026: sources may be
published or captured from **12 months before the anchor through 180 days after it**, inclusive,
plus earlier captures of that company's own website. Other older sources and later reports are
context only. These wider windows can include post-round progress; they do not recreate an
announcement-day information set. Helico's August team page is explicitly post-announcement.
The sidecar snapshot is the window's last day. No outcome enters `project.json`, `evidence.json`
or `rubrics.json`. Outcomes are never used to tune a criterion, weight, class or rating.

## Coverage and the basis of each rating

| Company | Observed | Absence rule | Sector judgement | Window exception | Cells |
| --- | --- | --- | --- | --- | --- |
"""
        + "\n".join(coverage)
        + """

On 13 November 2026 the first draft left 39 cells missing and the engine refused to rank.
On 14 November 2026 the owner chose the venture study's own convention for them: when the
eligible sources read say nothing, the rubric's lowest "nothing public" label applies (*None
named*, *None public*, *No offshore route stated*, *Pre-revenue*, *Company claim only*, *No
dated public milestone*, *Concept*); regulatory burden is a sector judgement; competitive
intensity names funded players from an in-window publisher page. Every such claim says so
in `evidence.json`. **This rule penalises a thin public record.** Companies that later closed
tend to leave fewer public traces, so the rule biases against them. Argo Navis Aerospace's stage
uses one stated window exception: a 2023 report of its 2020 pre-seed round, for that mandate cell
only. Observed counts include the market cells and every rating drafted before 14 November.

## Results beside what happened next

Python's screening summary under the venture study's two partner profiles: rank, then (value,
class). Outcomes are dated public facts shown for the look-back only; they are inputs to
nothing. Five companies cannot show whether the method predicts anything.

| Company | Technical/IP-led | Commercial/traction-led | What happened next (as of) |
| --- | --- | --- | --- |
"""
        + "\n".join(results)
        + """

Every company falls in the lowest class: the venture study's classes were set for a seed/Series
A fund's current pipeline, and these are first-round snapshots. Several ranks are fragile: the
run report lists which single absence-rule cell, moved one step, would reorder them.

## Market estimates

The venture study's rubrics are copied **word for word**, including their original 2025 market
wording. This retrospective explicitly overrides that year: use the anchor year or the latest
stated year not after it, from a publisher page captured/published within the owner's expanded
window. Median size and median stated CAGR use distinct publishers; no extrapolation.
Raw pages stay in
`$MCDA_DATA/first-round-study-2026-11-13/market/`.

| Company | Median size (US$ bn) | Median forecast CAGR (%) | Publishers | Qualification |
| --- | --- | --- | --- | --- |
"""
        + "\n".join(markets)
        + "\n\n"
        + "\n\n".join(f"**{name}.** {market_description(alt)}" for alt, name, _ in COMPANIES)
        + """

## Open it and reproduce

Import `project.json` in MCDA Studio; open `evidence.json` in Evidence and
`reference-cases.json` in Reference cases. Choose either copied partner profile. The reference
set contains the same five companies, so tick **Leave out this alternative's own case**
(`--exclude-same-id`) to compare each company with the other four; without it a company's
self-match is only a consistency check. Numeric market leaves are not compared by sidecar
version 1. Outcomes are off by default; **Show what happened next** requests them.

```sh
.venv/bin/python examples/nz_first_round_retrospective/build.py
mcda evaluate examples/nz_first_round_retrospective/project.json --profile technical_ip --json
mcda reference-cases examples/nz_first_round_retrospective/project.json \\
  --reference-cases examples/nz_first_round_retrospective/reference-cases.json \\
  --alternative vertus_energy --exclude-same-id
```

`project.json` inherits the venture study's complete criteria, scales, value functions, weight
profiles, sorting classes and mandate requirements at build time. `evidence.json` has one
unreviewed claim per cell. `reference-cases.json` has matching labelled ratings and dated
outcomes. `rubrics.json` is copied byte for byte. The builder validates all source windows and the
sidecar snapshot guard before writing any generated file. No network or private data is needed
to rebuild. See the design and run report under `docs/` for exclusions and review priorities.
"""
    )


PROFILES = ("technical_ip", "commercial_traction")


def canonical(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode()


def build(out: Path) -> None:
    project = build_project()
    dossier = build_dossier(project)
    raw = build_reference_set(project)
    reference = ReferenceCases.model_validate(raw)
    report = reference_case_service.validate(project, reference)
    if not report.valid:
        raise ValueError(f"Invalid reference cases: {report.issues}")
    outputs = {
        "evidence.json": canonical(dossier.model_dump(mode="json")),
        "reference-cases.json": canonical(raw),
        "rubrics.json": (STUDY / "rubrics.json").read_bytes(),
        "README.md": readme(project).encode(),
    }
    out.mkdir(parents=True, exist_ok=True)
    JsonProjectRepository().save(project, out / "project.json")
    for name, content in outputs.items():
        (out / name).write_bytes(content)


if __name__ == "__main__":
    build(Path(sys.argv[1]) if len(sys.argv) > 1 else HERE)
