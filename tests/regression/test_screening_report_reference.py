"""The screening report against independent answers.

The numbers in the report's tables are parsed back out of the HTML and compared with the
plain-Python screening-summary oracle (which never imports the application) and with Open
Questions. A committed
golden report for the venture study pins the whole document. Regenerate it, deliberately, with:

    mcda report screening examples/nz_venture_screening/project.json \
      --evidence examples/nz_venture_screening/evidence.json --generated-on 2026-11-07 \
      --out tests/fixtures/screening_report_nz_venture_screening.html
    mcda report screening examples/supplier_qualification/project.json --generated-on 2026-11-07 \
      --out tests/fixtures/screening_report_supplier_qualification.html
"""

import re
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
import screening_summary_oracle as oracle

from mcda_studio.domain.evidence import EvidenceDossier
from mcda_studio.domain.preferences import AnalysisConfiguration
from mcda_studio.services import questions_service, screening_report_service
from mcda_studio.storage.json_repository import JsonProjectRepository

ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "examples" / "nz_venture_screening"
GOLDEN = ROOT / "tests" / "fixtures" / "screening_report_nz_venture_screening.html"
SUPPLIER = ROOT / "examples" / "supplier_qualification"
SUPPLIER_GOLDEN = ROOT / "tests" / "fixtures" / "screening_report_supplier_qualification.html"
VENTURE_PHRASES = ("investment", "companies were not contacted", "startup", "public information")
GENERATED_ON = date(2026, 11, 7)
repo = JsonProjectRepository()


def study():
    project = repo.load(STUDY / "project.json")
    dossier = EvidenceDossier.model_validate_json((STUDY / "evidence.json").read_text())
    return project, dossier


def render(**kwargs) -> str:
    project, dossier = study()
    return screening_report_service.screening_report(
        project, None, kwargs.pop("dossier", dossier), generated_on=GENERATED_ON, **kwargs
    )


class Tables(HTMLParser):
    """Headings followed by their tables, as lists of cell text."""

    def __init__(self) -> None:
        super().__init__()
        self.sections: list[tuple[str, list[list[str]]]] = []
        self._heading = ""
        self._buffer: list[str] | None = None
        self._tag = ""
        self._row: list[str] | None = None
        self._rows: list[list[str]] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in {"h2", "h3"}:
            self._tag, self._buffer = tag, []
        elif tag == "table":
            self._rows = []
        elif tag == "tr":
            self._row = []
        elif tag in {"td", "th"}:
            self._buffer, self._tag = [], tag

    def handle_endtag(self, tag):
        if tag in {"h2", "h3"} and self._buffer is not None:
            self._heading = "".join(self._buffer).strip()
            self._buffer = None
        elif tag in {"td", "th"} and self._buffer is not None and self._row is not None:
            self._row.append("".join(self._buffer).strip())
            self._buffer = None
        elif tag == "tr" and self._row is not None and self._rows is not None:
            self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._rows is not None:
            self.sections.append((self._heading, self._rows))
            self._rows = None

    def handle_data(self, data):
        if self._buffer is not None:
            self._buffer.append(data)


def tables(html: str) -> dict[str, list[list[str]]]:
    parser = Tables()
    parser.feed(html)
    return dict(parser.sections)


def sig4(value: float) -> str:
    """Four significant digits, no exponent, "< 0.0001" for tiny nonzero values (own code)."""
    if value != 0 and abs(value) < 0.0001:
        return ("−" if value < 0 else "") + "< 0.0001"
    text = format(Decimal(format(value, ".4g")), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def rows_of(html: str, profile_name: str) -> dict[str, dict[str, str]]:
    table = tables(html)[profile_name]
    header, body = table[0], table[1:]
    return {row[1]: dict(zip(header, row, strict=True)) for row in body}


PROFILES = {"Technical/IP-led": "technical_ip", "Commercial/traction-led": "commercial_traction"}


@pytest.mark.parametrize("name", PROFILES)
def test_every_summary_number_in_the_report_equals_the_independent_oracle(name):
    project, dossier = study()
    html = render()
    truth = oracle.summary(
        __import__("json").loads(project.model_dump_json()), PROFILES[name], None
    )["rows"]
    alternatives = {a.id: a.name for a in project.alternatives}
    classes = {
        c["id"]: c["name"]
        for c in __import__("json").loads(project.model_dump_json())["sorting"]["classes"]
    }
    cfg = AnalysisConfiguration(method="mavt", weight_profile_id=PROFILES[name])
    counts: dict[str, int] = {}
    for q in questions_service.open_questions(project, cfg, dossier).questions:
        if q.alternative_id:
            counts[q.alternative_id] = counts.get(q.alternative_id, 0) + 1
    parsed = rows_of(html, name)
    assert set(parsed) == set(alternatives.values())
    requirement_names = {r.id: r.name for r in project.requirements}
    for alt_id, row in truth.items():
        shown = parsed[alternatives[alt_id]]
        assert shown["Rank"] == str(row["rank"])
        assert shown["Overall value"] == sig4(row["value"])
        assert shown["Class (margin)"] == f"{classes[row['class']]} ({sig4(row['margin'])})"
        assert shown["Open questions"] == str(counts.get(alt_id, 0))
        contributions = "; ".join(f"{n} {sig4(a)}" for n, a in _drivers(project, alt_id, name))
        assert shown["Two largest contributions"] == contributions
        assert [sig4(a) for _, a in _drivers(project, alt_id, name)] == [
            sig4(c) for c in row["drivers"]
        ]
        passed = row["requirements"] == "pass"
        assert (shown["Mandate"] == "Meets all") == passed
        assert shown["Mandate"].startswith("Fails") == (row["requirements"] == "fail")
        kind = row["fragility"][0]
        change = shown["Closest change"]
        if kind == "change":
            assert re.search(rf"[+−]{re.escape(sig4(row['fragility'][1]))} weight on ", change), (
                change
            )
        elif kind == "tied":
            assert change.startswith("tied now with")
        else:
            assert change == "no one-way change in [0, 1]"
    assert any(r["Mandate"].startswith("Fails: ") for r in parsed.values())
    assert {n for n in requirement_names.values()} >= {"Stage at most Series A"}


def _drivers(project, alt_id, profile_name):
    """The two largest weighted contributions with names, from the oracle's contributions."""
    parts = oracle.contributions(
        __import__("json").loads(project.model_dump_json()), PROFILES[profile_name], None
    )[alt_id]
    names = {n.id: n.name for n in project.criteria}
    positive = sorted(
        ((a, leaf) for leaf, a in parts.items() if a > 0.0),
        key=lambda item: (-item[0], list(parts).index(item[1])),
    )
    return [(names[leaf], a) for a, leaf in positive[:2]]


def test_the_partner_comparison_matches_each_profiles_own_ranks_and_classes():
    project, _ = study()
    html = render()
    table = tables(html)["Profile comparison"]
    header = table[0]
    assert header == [
        "Alternative",
        "Technical/IP-led: rank",
        "Technical/IP-led: class",
        "Commercial/traction-led: rank",
        "Commercial/traction-led: class",
    ]
    by_profile = {name: rows_of(html, name) for name in PROFILES}
    for row in table[1:]:
        for i, name in enumerate(PROFILES):
            summary = by_profile[name][row[0]]
            assert row[1 + 2 * i] == summary["Rank"]
            assert row[2 + 2 * i] == summary["Class (margin)"].rsplit(" (", 1)[0]
    ranks = {row[0]: (row[1], row[3]) for row in table[1:]}
    assert ranks["Wellumio"] == ("2", "5")  # the profiles really differ, so a mix-up is visible


def test_the_wrong_profile_cannot_pass_a_selected_profile_is_the_only_one_shown():
    html = render(profile_ids=["commercial_traction"])
    assert "Commercial/traction-led" in tables(html) and "Technical/IP-led" not in tables(html)
    assert "Profile comparison" in html
    assert "one weight profile" in html  # one profile: nothing to compare, and it says so
    rows = rows_of(html, "Commercial/traction-led")
    assert rows["Wellumio"]["Rank"] == "5" and rows["Hectre"]["Rank"] == "2"
    with pytest.raises(Exception, match="does not exist"):
        render(profile_ids=["nope"])


def test_the_fixed_statements_are_neutral_and_the_judgement_count_has_two_figures():
    html = render()
    for sentence in (
        "This report supports a screening decision. It is not advice and does not recommend any "
        "option.",
        "An overall value is a preference value under the stated weights, never a probability or "
        "a forecast.",
        "It rests on the information recorded in the project and, where supplied, its evidence "
        "dossier.",
        "71 of 128 scored ratings rest on judgement alone (71 of 112 qualitative or ordinal "
        "ratings).",
    ):
        assert sentence in html
    assert "Hnry" in html and "Fails: Stage at most Series A" in html
    text = re.sub(r"<[^>]+>", " ", html)
    assert "Upstock" in text and "Leader by method under Technical/IP-led" in text
    assert "No consensus is claimed" in text
    assert (
        "Judgement-only ratings: 71 of 128 scored ratings (55.47%); 71 of 112 qualitative or "
        "ordinal ratings (63.39%)" in text
    )
    assert "Claims: 154" in text and "Outdated" in text and "Disputed" in text


def test_no_venture_statement_is_in_the_engines_fixed_text():
    for line in screening_report_service.DISCLAIMER:
        assert not any(phrase in line.lower() for phrase in VENTURE_PHRASES)


def test_the_projects_own_description_sits_in_the_read_this_first_box_above_the_list():
    project, _ = study()
    html = render()
    box = html.split('<div class="disclaimer">')[1].split("</div>")[0]
    assert box.startswith(f'<p class="statement">{project.description}')
    assert box.index(project.description) < box.index("Read this first")
    # The study's own conditions come from its description, not from the engine.
    for phrase in ("not investment advice", "companies were not contacted", "public information"):
        assert phrase in project.description.lower().replace(";", "")
    assert html.count(project.description) == 1
    bare = project.model_copy(update={"description": ""})
    box = screening_report_service.screening_report(bare, None, None).split(
        '<div class="disclaimer">'
    )[1]
    assert box.startswith("<strong>Read this first</strong>")


def test_notes_are_appended_to_the_box_and_html_escaped():
    project, dossier = study()
    html = screening_report_service.screening_report(
        project, None, dossier, notes=["  Funded by <b>us</b> & them.  ", "Second statement."]
    )
    box = html.split('<div class="disclaimer">')[1].split("</div>")[0]
    assert box.endswith(
        "<li>Funded by &lt;b&gt;us&lt;/b&gt; &amp; them.</li><li>Second statement.</li></ul>"
    )
    assert "<b>us</b>" not in html
    assert '"notes": 2' in html.replace("&quot;", '"')
    assert screening_report_service.screening_report(project, None, dossier) == render_plain()


def render_plain() -> str:
    project, dossier = study()
    return screening_report_service.screening_report(project, None, dossier)


def test_notes_have_at_most_twenty_lines_of_three_hundred_characters():
    project, _ = study()
    make = screening_report_service.screening_report
    assert "<li>" + "a" * 300 + "</li>" in make(project, None, None, notes=["a" * 300])
    with pytest.raises(Exception, match="at most 300 characters"):
        make(project, None, None, notes=["a" * 301])
    twenty = [f"Note {i}" for i in range(20)]
    assert "<li>Note 19</li>" in make(project, None, None, notes=twenty)
    with pytest.raises(Exception, match="at most 20 notes"):
        make(project, None, None, notes=[*twenty, "one more"])
    with pytest.raises(Exception, match="cannot be empty"):
        make(project, None, None, notes=["fine", "   "])


def test_the_provenance_footer_names_the_project_the_app_the_profiles_and_the_options():
    project, dossier = study()
    html = render()
    text = re.sub(r"<[^>]+>", " ", html)
    assert project.fingerprint() in text
    assert "0.1.0" in text and "technical_ip" in text and "commercial_traction" in text
    assert "Evidence dossier digest" in text and "generated_on" in text and "2026-11-07" in text
    assert "Generated on:" in html


def test_the_same_inputs_give_the_same_bytes_and_no_date_unless_asked():
    project, dossier = study()
    first = screening_report_service.screening_report(project, None, dossier)
    again = screening_report_service.screening_report(project, None, dossier)
    assert first == again
    assert "Generated on" not in first and "2026" not in re.sub(
        r"[0-9a-f]{64}", "", first.split("Provenance")[1].split("Generation options")[0]
    )
    assert render() != first and render() == render()


def test_the_report_is_self_contained_no_script_no_remote_asset_no_link():
    html = render()
    assert "<script" not in html.lower() and "javascript:" not in html.lower()
    assert not re.search(r"<(link|img|iframe|object|embed|video|audio|source)\b", html, re.I)
    assert not re.search(r"\b(src|href|srcset|action)\s*=", html, re.I)
    assert "@import" not in html and "url(" not in html and "@font-face" not in html
    assert "<svg" not in html  # no chart: nothing to draw from Python tonight
    assert "@page { size: A4;" in html and "<!doctype html>" in html
    # URLs can only appear as plain text inside question wording, never as something to load
    assert not re.search(r'["\']https?://', html)


def test_numbers_follow_the_display_rules_no_exponents_and_less_than_for_tiny_values():
    html = render()
    visible = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    visible = re.sub(r"[0-9a-f]{64}", "", visible)
    assert not re.search(r"\d[eE][+-]?\d", visible)
    assert "< 0.0001" not in html or "&lt; 0.0001" in html
    assert screening_report_service._n(0.00001234) == "< 0.0001"
    assert screening_report_service._n(0.0) == "0"
    assert screening_report_service._n(0.123456789) == "0.1235"
    assert screening_report_service._n(1234567.0) == "1235000"


def test_sections_the_project_cannot_supply_are_one_plain_line_not_invented():
    project, dossier = study()
    bare = project.model_copy(update={"sorting": None, "requirements": None})
    html = screening_report_service.screening_report(bare, None, None, ["technical_ip"])
    text = re.sub(r"<[^>]+>", " ", html)
    assert "No classes are set up." in text
    assert "The project states no mandatory requirements." in text
    assert "No evidence dossier was supplied." in text
    assert "The project has one weight profile, so there is nothing to compare." in text
    assert "Class (margin)" not in html and "Mandate" not in tables(html)["Technical/IP-led"][0]
    assert "Judgement-only" not in text and "71 of" not in text and "judgement alone" not in text
    assert "No evidence dossier was supplied, so the share" in text
    stale = dossier.model_copy(update={"project_fingerprint": "0" * 64})
    again = screening_report_service.screening_report(project, None, stale)
    assert "does not match this project revision" in again


def test_a_model_the_engine_cannot_evaluate_gives_an_unavailable_line_not_a_table():
    project, _ = study()
    import mcda_studio.services.project_service as ps

    broken = ps.clear_performance(project, "upstock", "board_advisors")
    html = screening_report_service.screening_report(broken, None, None)
    assert "Ranking unavailable" in html and "measurement" in html
    assert "<table>" not in html.split("Profile comparison")[0]


def test_looking_never_changes_the_project():
    project, dossier = study()
    before = project.fingerprint()
    screening_report_service.screening_report(project, None, dossier)
    assert project.fingerprint() == before


def test_the_committed_golden_report_is_regenerated_byte_for_byte():
    assert GOLDEN.read_text(encoding="utf-8") == render()


def supplier_report() -> str:
    project = repo.load(SUPPLIER / "project.json")
    return screening_report_service.screening_report(project, None, None, generated_on=GENERATED_ON)


def test_the_supplier_qualification_golden_report_is_regenerated_byte_for_byte():
    assert SUPPLIER_GOLDEN.read_text(encoding="utf-8") == supplier_report()


def test_a_report_for_a_non_venture_example_has_no_venture_phrase():
    text = re.sub(r"<[^>]+>", " ", supplier_report()).lower()
    for phrase in VENTURE_PHRASES:
        assert phrase not in text
    assert "supplier qualification" in text and "screening decision" in text
