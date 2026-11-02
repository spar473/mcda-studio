# ruff: noqa: E501  (mutation targets are literal source text and cannot be wrapped)
"""Mutation check across every layer: API, store, services, weighting and profiles, sensitivity,
scenarios, analysis records/exports and the frontend logic.

Each mutation is injected alone into a scratch COPY of the repository; the relevant test suite must
then fail. A mutation the suite does not notice is reported as SURVIVED and the script exits 1.
The working tree is never modified. An unmodified baseline run must pass first.

    python scripts/mutation_check.py [--backend-only | --frontend-only | --seam-only |
                                      --sorting-only | --smaa-only | --promethee-only |
                                      --ahp-only | --comparison-only | --feasibility-only |
                                      --measurement-range-only | --derived-only |
                                      --evidence-workspace-only | --decision-only |
                                      --calculation-only | --uncertainty-only | --proposals-only |
                                      --models-only | --proxy-only | --benchmark-only]

Groups are named after the milestone that introduced them (B3 weighting, B4 sensitivity, B5
scenarios, B6 results) or after the development itself (RETRY: analysis retry; COVERAGE:
measurement coverage; BACKUP: library backup and restore; SEAM: the method seam; SORTING:
value-based sorting and the rest of the seam; SMAA: SMAA-2; PROMETHEE: PROMETHEE II; AHP: AHP; COMPARISON: the method comparison view; FEASIBILITY: the feasibility check). Each group uses
the backend or frontend suites that prove its rules.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Mutation:
    name: str
    file: str
    old: str
    new: str


BACKEND = [
    Mutation(
        "B1 edit applies partial operations instead of refusing all",
        "src/mcda_studio/api/app.py",
        'raise from_mcda_error(exc, f"operations[{i}]") from exc',
        "continue",
    ),
    Mutation(
        "B2 save ignores If-Match",
        "src/mcda_studio/api/app.py",
        "store.replace(project, _strip_etag(if_match))",
        "store.replace(project, None)",
    ),
    Mutation(
        "B3 store never detects a stale revision",
        "src/mcda_studio/storage/project_store.py",
        "if current != expected_fingerprint:",
        "if False:",
    ),
    Mutation(
        "B4 create overwrites an existing id",
        "src/mcda_studio/storage/project_store.py",
        "            if path.exists():\n                raise ProjectExistsError",
        "            if False:\n                raise ProjectExistsError",
    ),
    Mutation(
        "B5 duplicate keeps the original id",
        "src/mcda_studio/services/project_service.py",
        "clone.id = uuid.uuid4().hex[:16]",
        "clone.id = project.id",
    ),
    Mutation(
        "B6 delete destroys the file instead of moving it to the trash",
        "src/mcda_studio/storage/project_store.py",
        "            path.replace(target)\n            return target",
        "            path.unlink()\n            return target",
    ),
    Mutation(
        "B7 clear_performance clears a whole row and column",
        "src/mcda_studio/services/project_service.py",
        "if not (p.alternative_id == alt_id and p.criterion_id == crit_id)\n    ]\n    return out\n\n\ndef clear_criterion_performances",
        "if not (p.alternative_id == alt_id or p.criterion_id == crit_id)\n    ]\n    return out\n\n\ndef clear_criterion_performances",
    ),
    Mutation(
        "B8 project ids are not validated (path traversal)",
        "src/mcda_studio/storage/project_store.py",
        "            _ID.validate_python(project_id)",
        "            pass",
    ),
    Mutation(
        "B9 save accepts a body whose id differs from the URL",
        "src/mcda_studio/api/app.py",
        "if project.id != project_id:",
        "if False:",
    ),
    Mutation(
        "B10 clear_judgement clears every rating",
        "src/mcda_studio/services/project_service.py",
        "_profile(out, profile_id).judgements.pop(node_id, None)",
        "_profile(out, profile_id).judgements.clear()",
    ),
]

# C1 recovery and ownership rules, exercised by API and focused storage behaviour.
BACKEND += [
    Mutation(
        "C1 library ownership is never acquired",
        "src/mcda_studio/storage/library_lock.py",
        "fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)",
        "pass",
    ),
    Mutation(
        "C1 recovery accepts a mismatched project identity",
        "src/mcda_studio/storage/project_store.py",
        "if project.id != expected_id:",
        "if False:",
    ),
    Mutation(
        "C1 restore overwrites an active project",
        "src/mcda_studio/storage/project_store.py",
        """os.link(
                        staged.name,
                        destination.name,
                        src_dir_fd=root_fd,
                        dst_dir_fd=root_fd,
                        follow_symlinks=False,
                    )""",
        "os.replace(staged.name, destination.name, src_dir_fd=root_fd, dst_dir_fd=root_fd)",
    ),
    Mutation(
        "C1 successful restore discards its retained recovery entry",
        "src/mcda_studio/storage/project_store.py",
        "return self._read(destination)",
        "os.unlink(entry, dir_fd=directory)\n                return self._read(destination)",
    ),
]

FRONTEND = [
    Mutation(
        "F1 project is always dirty",
        "frontend/src/model/session.ts",
        "return state.draft.fingerprint !== state.saved.fingerprint;",
        "return true;",
    ),
    Mutation(
        "F2 'move up' allowed on the first sibling",
        "frontend/src/model/tree.ts",
        "return index > 0 ? {",
        "return index >= 0 ? {",
    ),
    Mutation(
        "F3 edits are no longer serialised",
        "frontend/src/state/editorStore.ts",
        "const run = this.chain.then(job);",
        "const run = job();",
    ),
    Mutation(
        "F4 a stale-revision error is not treated as a conflict",
        "frontend/src/state/editorStore.ts",
        'if (err.code === "STALE_REVISION") {',
        'if (err.code === "NEVER") {',
    ),
    Mutation(
        "F5 Escape commits the draft it discards (number input)",
        "frontend/src/components/ui.tsx",
        '        if (e.key === "Escape") {\n          cancelled.current = true;\n          setDraft(shown);',
        '        if (e.key === "Escape") {\n          setDraft(shown);',
    ),
    Mutation(
        "F6 issue path: alternative and criterion swapped",
        "frontend/src/model/issues.ts",
        'return { kind: "performance", alternativeId: m[1], criterionId: m[2] };',
        'return { kind: "performance", alternativeId: m[2], criterionId: m[1] };',
    ),
    Mutation(
        "F7 renaming a label forgets the entered measurements",
        "frontend/src/model/measurement.ts",
        '    if (p.value === old) {\n      ops.push({\n        op: "set_performance"',
        '    if (false as boolean) {\n      ops.push({\n        op: "set_performance"',
    ),
    Mutation(
        "F8 changing measurement family keeps stale measurements",
        "frontend/src/model/defaults.ts",
        "clearsMeasurements: crossesFamily && old != null",
        "clearsMeasurements: false",
    ),
    Mutation(
        "F9 save does not send If-Match",
        "frontend/src/api/client.ts",
        'headers: { "If-Match": `"${ifMatch}"` },',
        "headers: {},",
    ),
]


# B3 (weighting milestone): hierarchical swing weighting, preference profiles and reference integrity.
B3_BACKEND = [
    Mutation(
        "W1 global weights add local weights instead of multiplying them",
        "src/mcda_studio/methods/mavt/weighting.py",
        "        for node_id in tree.path(leaf):\n            w *= local[node_id]",
        "        for node_id in tree.path(leaf):\n            w += local[node_id]",
    ),
    Mutation(
        "W2 a branch share ignores its ancestors",
        "src/mcda_studio/methods/mavt/weighting.py",
        "        for step in tree.path(node_id):\n            w *= local[step]",
        "        for step in [node_id]:\n            w *= local[step]",
    ),
    Mutation(
        "W3 an explicitly selected profile is ignored",
        "src/mcda_studio/domain/project.py",
        "        wanted = configuration.weight_profile_id\n        if wanted is None:",
        "        wanted = None\n        if wanted is None:",
    ),
    # Note: making this `deep=False` is an EQUIVALENT mutant, not a defect. Every service returns
    # `_rebuild(...)`, i.e. `Project.model_validate(project.model_dump())`, so the round trip
    # reconstructs every nested object and two profiles in one returned project can never alias.
    # The mutations below are the ones that would be real cross-profile defects.
    Mutation(
        "W4 a duplicated profile does not carry the source's ratings",
        "src/mcda_studio/services/project_service.py",
        'clone = source.model_copy(deep=True, update={"id": new_id, "name": name})',
        'clone = source.model_copy(deep=True, update={"id": new_id, "name": name, "judgements": {}})',
    ),
    Mutation(
        "W10 a rating edit ignores the selected profile and writes to the first one",
        "src/mcda_studio/services/project_service.py",
        "    prof = _profile(out, profile_id)\n    prof.judgements[node_id] = rating",
        "    prof = _profile(out, None)\n    prof.judgements[node_id] = rating",
    ),
    Mutation(
        "W5 a referenced profile is deleted and silently falls back",
        "src/mcda_studio/services/project_service.py",
        "    if refs and replacement_profile_id is None:",
        "    if False:",
    ),
    Mutation(
        "W6 a missing swing rating is silently treated as zero",
        "src/mcda_studio/domain/preferences.py",
        "                err(\n"
        '                    "MISSING_JUDGEMENT",\n'
        '                    f"no swing rating for {kid!r} among siblings of {group}",\n'
        "                    where,\n"
        "                )\n"
        "                group_ok = False\n"
        "                continue",
        "                ratings.append(0.0)\n                continue",
    ),
    Mutation(
        "W7 renaming a profile changes its stable id",
        "src/mcda_studio/services/project_service.py",
        "    _profile(out, profile_id).name = _profile_name(name)",
        "    _profile(out, profile_id).id = _profile_name(name)",
    ),
]

B3_FRONTEND = [
    Mutation(
        "W8 a weight preview computed for another profile is accepted",
        "frontend/src/state/usePreviews.ts",
        "      requireProfile && result.weight_profile_id !== context.resolvedProfileId ||",
        "      false && result.weight_profile_id !== context.resolvedProfileId ||",
    ),
    Mutation(
        "W9 switching the viewed profile rewrites the saved default",
        "frontend/src/components/ProfileManager.tsx",
        "onChange={(e) => onSelect(e.target.value || null)}>",
        "onChange={(e) => { onSelect(e.target.value || null); "
        'void manage({ op: "set_default_weight_profile", profile_id: e.target.value || null }); }}>',
    ),
]


# B4 (sensitivity milestone): one-way weight sensitivity and the arbitrary-weight probe.
B4_BACKEND = [
    Mutation(
        "S1 redistribution uses the unstable 1 - w_k denominator",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "    rest = math.fsum(prep.local[s] for s in siblings)",
        "    rest = 1.0 - prep.local[node_id]",
    ),
    Mutation(
        "S2 the probe redistributes the siblings equally instead of proportionally",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "        local[sib] = (1.0 - t) * prep.local[sib] / rest\n    return local",
        "        local[sib] = (1.0 - t) / len(siblings)\n    return local",
    ),
    Mutation(
        "S3 crossovers are read off the sample grid instead of solved exactly",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "                t_star = d0 / (d0 - d1)",
        "                t_star = round(d0 / (d0 - d1), 2)",
    ),
    Mutation(
        "S4 a pairwise swap below the leader is reported as a winner change",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "        if lo >= base - _EPS and who != base_winner:",
        "        if lo >= base - _EPS:",
    ),
    Mutation(
        "S5 the probe ranks by array position instead of competition rank",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "    ranks = rank_values(values)\n    order = ordered_indices(values)",
        "    order = ordered_indices(values)\n    ranks = [order.index(i) + 1 for i in range(len(values))]",
    ),
    Mutation(
        "S6 the probe reports path shares from the unvaried model",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "        path_shares=path_shares(prep.tree, local),",
        "        path_shares=path_shares(prep.tree, prep.local),",
    ),
    Mutation(
        "S7 the probe ignores the requested weight and answers at the baseline",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "    values = overall_values(prep.partial, _global_with(prep, node_id, weight))",
        "    values = overall_values(prep.partial, _global_with(prep, node_id, base))",
    ),
    Mutation(
        "S8 the probe accepts a weight outside [0, 1]",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "    if not math.isfinite(weight) or not 0.0 <= weight <= 1.0:",
        "    if False:",
    ),
    Mutation(
        "S9 the probe resolves the first profile instead of the configured one",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "        weight_profile_id=prep.profile.id,",
        "        weight_profile_id=project.weight_profiles[0].id,",
    ),
]

# B7 retains every B0–B6 target and guards the independently found tie-reporting defects.
B4_BACKEND += [
    Mutation(
        "R1 sensitivity ranking changes compare sorted IDs instead of competition ranks",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "ranking_differs_from_baseline=ranks != base_ranks,",
        "ranking_differs_from_baseline=ranking != baseline_ranking,",
    ),
    Mutation(
        "R2 sensitivity winner changes compare only the first sorted alternative",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "winner_differs_from_baseline={alts[i] for i, rank in enumerate(ranks) if rank == 1}\n        != {alts[i] for i, rank in enumerate(base_ranks) if rank == 1},",
        "winner_differs_from_baseline=ranking[0] != baseline_ranking[0] if ranking else False,",
    ),
]

B4_FRONTEND = [
    Mutation(
        "S10 a probe computed for another profile or weight is accepted",
        "frontend/src/state/useSensitivity.ts",
        "        result.weight_profile_id !== context.resolvedProfileId ||",
        "        false ||",
    ),
    # Note: "the cursor persists an edit" is NOT expressible as a mutation here.
    # SensitivityPanel is never given an apply/save function, so the read-only property holds
    # by construction rather than by a runtime check. It is asserted directly instead: the
    # component test proves api.edit and api.saveProject are never called, and the browser test
    # proves the stored bytes, the ETag and the Undo button are unchanged after a cursor sweep.
    Mutation(
        "S11 the cursor accepts a weight outside [0, 1] and probes it",
        "frontend/src/components/SensitivityPanel.tsx",
        "if (v !== null && v >= 0 && v <= 1) setCursor(v);",
        "if (v !== null) setCursor(v);",
    ),
    Mutation(
        "S12 hiding an alternative drops it from the numerical table too",
        "frontend/src/components/SensitivityPanel.tsx",
        '        <table className="grid compact" aria-label="Sensitivity values">',
        '        <table className="grid compact" aria-label="Sensitivity values" hidden={hidden.length > 0}>',
    ),
]


B5_BACKEND = [
    Mutation(
        "C1 scenario override corrupts the base function",
        "src/mcda_studio/services/project_service.py",
        "    _scenario(out, scenario_id).value_function_overrides[criterion_id] = value_function.model_copy(",
        "    out.tree().node(criterion_id).value_function = value_function.model_copy(deep=True)\n    _scenario(out, scenario_id).value_function_overrides[criterion_id] = value_function.model_copy(",
    ),
    Mutation(
        "C2 automatic resolution ignores the scenario profile",
        "src/mcda_studio/domain/project.py",
        "            wanted = scenario.weight_profile_id if scenario else None",
        "            wanted = None",
    ),
    Mutation(
        "C3 duplication aliases source override state (both copy barriers removed)",
        "src/mcda_studio/services/project_service.py",
        '    return add_scenario(\n        project, source.model_copy(deep=True, update={"id": new_id, "name": _profile_name(name)})\n    )',
        '    out = _copy(project)\n    out.scenarios.append(source.model_copy(update={"id": new_id, "name": _profile_name(name)}))\n    return out',
    ),
    Mutation(
        "C4 Reset to Base freezes a copy of the current base",
        "src/mcda_studio/services/project_service.py",
        "    _scenario(out, scenario_id).value_function_overrides.pop(criterion_id, None)",
        "    _scenario(out, scenario_id).value_function_overrides[criterion_id] = out.tree().node(criterion_id).value_function.model_copy(deep=True)",
    ),
    Mutation(
        "C5 deletion leaves the saved default dangling",
        "src/mcda_studio/services/project_service.py",
        "        out.analysis.scenario_id = replacement_scenario_id",
        "        pass",
    ),
    Mutation(
        "C6 sensitivity probe computes base instead of the requested scenario",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "    cfg = configuration or project.analysis\n    prep = prepare_mavt(project, cfg)\n    base = _check_variable(prep, node_id)",
        '    cfg = (configuration or project.analysis).model_copy(update={"scenario_id": None})\n    prep = prepare_mavt(project, cfg)\n    base = _check_variable(prep, node_id)',
    ),
]
B5_FRONTEND = [
    Mutation(
        "C7 obsolete scenario completion bypasses the request generation gate",
        "frontend/src/state/useAnalysisRequest.ts",
        "        if (current) setDone({ key, result });",
        "        setDone({ key, result });",
    ),
    Mutation(
        "C8 comparison rows align by ranking position instead of alternative ID",
        "frontend/src/components/ScenarioPanel.tsx",
        "value:outcome?.values[a.id]",
        "value:outcome?.values[outcome.ranking[project.alternatives.indexOf(a)] ?? a.id]",
    ),
    Mutation(
        "C9 comparison accepts the wrong resolved preference profile",
        "frontend/src/state/useScenarioAnalysis.tsx",
        "scenario.weight_profile_id!==context.resolvedProfileId",
        "false",
    ),
]


def run_scenarios(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    return (
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-x",
                "-p",
                "no:cacheprovider",
                "tests/unit/test_scenario_management.py",
                "tests/api/test_api_scenarios.py",
                "tests/unit/test_sensitivity_probe.py",
                "tests/regression/test_infrastructure_procurement.py",
                "tests/properties/test_scenarios.py",
            ],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


B6_BACKEND = [
    Mutation(
        "V1 contribution segments use the first leaf weight for every criterion",
        "src/mcda_studio/methods/mavt/aggregation.py",
        "float(w[j]) * float(prep.partial[i, j])",
        "float(w[0]) * float(prep.partial[i, j])",
    ),
    Mutation(
        "V6 dominance relationship display is derived from overall scores instead of partial-value edges",
        "src/mcda_studio/services/results_service.py",
        "    edges = {(pair.dominator_id, pair.dominated_id) for pair in result.dominance}",
        "    edges = {(a.alternative_id, b.alternative_id) for a in result.alternatives for b in result.alternatives if a.overall_value > b.overall_value}",
    ),
    Mutation(
        "V8 CSV bypasses the untrusted-text safety encoding",
        "src/mcda_studio/services/results_service.py",
        "        return safe_csv_text(value)",
        "        return value",
    ),
    Mutation(
        "V9 export accepts a digest belonging to another completed context",
        "src/mcda_studio/services/results_service.py",
        "    if record.record_digest != expected_record_digest:",
        "    if False:",
    ),
    Mutation(
        "V12 result path shares are incorrectly replaced by local weights",
        "src/mcda_studio/services/results_service.py",
        '        "path_shares": path_shares(prep.tree, prep.local),',
        '        "path_shares": prep.local,',
    ),
]
B6_FRONTEND = [
    Mutation(
        "V2 ranking chart labels use array positions instead of competition ranks",
        "frontend/src/components/results/ResultsCharts.tsx",
        "· rank {alt.rank}</text>\n      </g>;\n    })}\n  </Frame>;\n}\n\nexport function ContributionsChart",
        "· rank {i + 1}</text>\n      </g>;\n    })}\n  </Frame>;\n}\n\nexport function ContributionsChart",
    ),
    Mutation(
        "V3 contributions are joined to the first alternative instead of their stable ID",
        "frontend/src/components/results/ResultsCharts.tsx",
        "const value = alt.weighted_contributions[criterion.criterion_id];",
        "const value = record.result.alternatives[0]?.weighted_contributions[criterion.criterion_id];",
    ),
    Mutation(
        "V4 completed records accept the wrong resolved profile",
        "frontend/src/state/useAnalysisRecord.ts",
        "common.weight_profile_id !== (reads ? profile : null) ||",
        "false ||",
    ),
    Mutation(
        "V5 record requests share a constant identity across revisions and configurations",
        "frontend/src/state/useAnalysisRecord.ts",
        "useAnalysisRequest(key, errors === 0, load)",
        'useAnalysisRequest("constant-record", errors === 0, load)',
    ),
    Mutation(
        "V7 hidden criteria incorrectly change a contribution bar's reported total",
        "frontend/src/components/results/ResultsCharts.tsx",
        "{formatValue(alt.overall_value, view.precision)} · rank {alt.rank}</text>\n      </g>;\n    })}\n  </Frame>;\n}\n\n/** The existing",
        "{formatValue(alt.overall_value * (view.hidden_criterion_ids.length ? .5 : 1), view.precision)} · rank {alt.rank}</text>\n      </g>;\n    })}\n  </Frame>;\n}\n\n/** The existing",
    ),
    Mutation(
        "V10 SVG provenance conceals hidden criterion series",
        "frontend/src/components/results/ResultsCharts.tsx",
        'view.hidden_criterion_ids.join(", ") || "none"',
        '"none"',
    ),
    Mutation(
        "V11 late export completion bypasses cancellation/context/operation checks",
        "frontend/src/components/ResultsPanel.tsx",
        "if (controller.signal.aborted || liveRecord.current !== token || exportController.current !== controller) return;",
        "if (false) return;",
    ),
]
RETRY_FRONTEND = [
    Mutation(
        "RT1 Retry clears the failure but never re-sends the request",
        "frontend/src/state/useAnalysisRequest.ts",
        "    setRetries((r) => ({ key, count: (r.key === key ? r.count : 0) + 1 }));",
        "    setRetries((r) => r);",
    ),
    Mutation(
        "RT2 Retry leaves the old failure on screen while re-requesting",
        "frontend/src/state/useAnalysisRequest.ts",
        "    setDone(null);\n",
        "",
    ),
    Mutation(
        "RT3 a Retry captured under an obsolete context still acts",
        "frontend/src/state/useAnalysisRequest.ts",
        "    if (liveKey.current !== key) return;",
        "    if (liveKey.current === null) return;",
    ),
]


COVERAGE_FRONTEND = [
    Mutation(
        "Coverage zero measurements are treated as missing",
        "frontend/src/model/coverage.ts",
        "    measurements.set(key, performance.value);",
        "    if (performance.value) measurements.set(key, performance.value);",
    ),
    Mutation(
        "Coverage descendants under collapsed branches are omitted",
        "frontend/src/model/coverage.ts",
        "  const leaves = leafIds(tree).flatMap(id => {",
        "  const leaves = leafIds(tree).filter(id => tree.byId.get(id)?.parent_id == null).flatMap(id => {",
    ),
    Mutation(
        "Coverage empty model is reported as complete",
        "frontend/src/model/coverage.ts",
        '  if (index.expected === 0) return "Add alternatives/criteria · 0 expected cells";',
        '  if (index.expected === 0) return "100% complete";',
    ),
    Mutation(
        "Coverage duplicate and orphaned measurements inflate entered counts",
        "frontend/src/model/coverage.ts",
        "  const entered = measurements.size;",
        "  const entered = project.performances.length;",
    ),
]


BACKUP_BACKEND = [
    Mutation(
        "Backup archive member names outside the allowlist are accepted",
        "src/mcda_studio/storage/library_backup.py",
        "if _member_kind(name) is None:",
        "if False:",
    ),
    Mutation(
        "Backup duplicate archive member names are accepted",
        "src/mcda_studio/storage/library_backup.py",
        "if folded in seen:",
        "if False:",
    ),
    Mutation(
        "Backup member size limit is never enforced",
        "src/mcda_studio/storage/library_backup.py",
        "if len(data) > limit:",
        "if False:",
    ),
    Mutation(
        "Backup restore truncates an existing file instead of refusing it",
        "src/mcda_studio/storage/library_backup.py",
        "os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW",
        "os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW",
    ),
    Mutation(
        "Backup reads a library without taking its ownership",
        "src/mcda_studio/storage/library_backup.py",
        "with LibraryOwnership(root):",
        "with suppress():",
    ),
    Mutation(
        "Backup restore accepts an existing target directory",
        "src/mcda_studio/storage/library_backup.py",
        "os.mkdir(destination)",
        "os.makedirs(destination, exist_ok=True)",
    ),
    Mutation(
        "Backup verification compares sizes but not hashes",
        "src/mcda_studio/storage/library_backup.py",
        'if len(data) != entry["size"] or _sha256(data) != entry["sha256"]:',
        'if len(data) != entry["size"]:',
    ),
    Mutation(
        "Backup restore never writes the incomplete marker",
        "src/mcda_studio/storage/library_backup.py",
        '_write_new(INCOMPLETE_MARKER, b"restore in progress\\n", time.time_ns(), root_fd)',
        "pass",
    ),
    Mutation(
        "Backup archive members missing from the manifest are accepted",
        "src/mcda_studio/storage/library_backup.py",
        'problems += [f"{p!r}: in the archive but not in the manifest" for p in sorted(archived - paths)]',
        "pass",
    ),
    Mutation(
        "Backup serve starts on an unfinished restore",
        "src/mcda_studio/startup.py",
        "    ensure_restore_complete(root)\n",
        "",
    ),
    Mutation(
        "Backup app startup accepts an unfinished restore",
        "src/mcda_studio/api/app.py",
        "            ensure_restore_complete(app.state.store.root)\n",
        "",
    ),
]


SEAM_BACKEND = [
    Mutation(
        "Seam capability check never refuses a method",
        "src/mcda_studio/methods/base.py",
        "if method is not None and capability not in method.capabilities:",
        "if False:",
    ),
    Mutation(
        "Seam validation always runs MAVT's checks instead of the configured method's",
        "src/mcda_studio/methods/base.py",
        "issues.extend(method.validate(project, configuration))",
        'issues.extend(get_method("mavt").validate(project, configuration))',
    ),
    Mutation(
        "Seam version-1 record is built for any method",
        "src/mcda_studio/methods/base.py",
        "if method is not None and method.name != RECORD_V1_METHOD:",
        "if False:",
    ),
    Mutation(
        "Seam unknown parameters are silently ignored",
        "src/mcda_studio/methods/base.py",
        "for key in sorted(set(parameters) - set(model.model_fields)):",
        "for key in []:",
    ),
    Mutation(
        "Seam MAVT dominance_check accepts loosely typed values",
        "src/mcda_studio/methods/mavt/parameters.py",
        "dominance_check: StrictBool = True",
        "dominance_check: bool = True",
    ),
    Mutation(
        "Seam sensitivity skips its capability check",
        "src/mcda_studio/services/analysis_service.py",
        '    _require(project, configuration, "weight_sensitivity")\n    result = _sens.weight_sensitivity(',
        "    result = _sens.weight_sensitivity(",
    ),
    Mutation(
        "Seam weight preview skips its capability check",
        "src/mcda_studio/services/analysis_service.py",
        '    _require(project, configuration, "swing_weights")\n',
        "",
    ),
    Mutation(
        "Seam unsupported method maps to a generic 400",
        "src/mcda_studio/api/errors.py",
        '(MethodNotSupportedError, 422, "METHOD_NOT_SUPPORTED")',
        '(MethodNotSupportedError, 400, "METHOD_NOT_SUPPORTED")',
    ),
]


SORTING_BACKEND = [
    Mutation(
        "Sorting compares with <= at a boundary, so a value on it goes to the lower class",
        "src/mcda_studio/methods/sorting/classes.py",
        "return sum(1 for b in boundaries if value < b - TIE_TOL)",
        "return sum(1 for b in boundaries if value <= b)",
    ),
    Mutation(
        "Sorting class order is inverted",
        "src/mcda_studio/methods/sorting/classes.py",
        "class_id=model.classes[index].id,",
        "class_id=model.classes[len(model.classes) - 1 - index].id,",
    ),
    Mutation(
        "Sorting class-change root has the wrong sign",
        "src/mcda_studio/methods/sorting/sensitivity.py",
        "weight=g0 / (g0 - g1),",
        "weight=g0 / (g1 - g0),",
    ),
    Mutation(
        "Sorting version-2 record is written for MAVT",
        "src/mcda_studio/services/results_service.py",
        "build_v2 = VERSION_2_RECORDS.get(cfg.method)",
        "build_v2 = VERSION_2_RECORDS.get(cfg.method, _sorting_record)",
    ),
    Mutation(
        "Sorting schema version is written too high (always the newest)",
        "src/mcda_studio/domain/project.py",
        "return max([1, *used])",
        "return SCHEMA_VERSION",
    ),
    Mutation(
        "Sorting absent method section is written as null",
        "src/mcda_studio/domain/project.py",
        "sorting: SortingModel | None = Field(default=None, exclude_if=lambda v: v is None)",
        "sorting: SortingModel | None = Field(default=None, exclude_if=lambda v: False)",
    ),
    Mutation(
        "Sorting out-of-order boundaries are accepted instead of refused",
        "src/mcda_studio/methods/sorting/classes.py",
        "if not upper.lower_boundary - lower.lower_boundary > 2 * TIE_TOL:",
        "if not abs(upper.lower_boundary - lower.lower_boundary) > 2 * TIE_TOL:",
    ),
    Mutation(
        "Sorting audit pool includes the cut-off class",
        "src/mcda_studio/methods/sorting/classes.py",
        "if a.class_rank > cutoff + 1]",
        "if a.class_rank >= cutoff + 1]",
    ),
    Mutation(
        "Sorting never warns about local anchors",
        "src/mcda_studio/methods/sorting/classes.py",
        "    if anchored:\n",
        "    if False:\n",
    ),
    Mutation(
        "Sorting a version-1 file holding a sorting section is accepted",
        "src/mcda_studio/storage/json_repository.py",
        'if "sorting" in raw:',
        "if False:",
    ),
    Mutation(
        "Sorting a new saved method keeps the previous method's parameters",
        "src/mcda_studio/services/project_service.py",
        "        out.analysis.parameters = {}\n",
        "",
    ),
    Mutation(
        "Sorting CLI shows the class above for a change below the baseline",
        "src/mcda_studio/cli.py",
        "names[c.class_after if raising else c.class_before]",
        "names[c.class_after]",
    ),
]

SORTING_FRONTEND = [
    Mutation(
        "Sorting panel registry ignores declared capabilities",
        "frontend/src/components/results/panels.ts",
        ".filter((p) => info === undefined || capabilities.has(p.capability));",
        ".filter(() => true);",
    ),
    Mutation(
        "Sorting Classes panel is registered for MAVT",
        "frontend/src/components/results/panels.ts",
        "  mavt: MAVT_PANELS,",
        '  mavt: [{ id: "classes", label: "Classes", capability: "value_scores" }, ...MAVT_PANELS],',
    ),
    Mutation(
        "Sorting method view writes the saved default",
        "frontend/src/components/AnalysisControls.tsx",
        "onChange={(e) => onSelect({ method: e.target.value, parameters: null })}>",
        "onChange={(e) => { onSelect({ method: e.target.value, parameters: null }); onUseMethodAsDefault?.(); }}>",
    ),
    Mutation(
        "Sorting viewed method reuses the saved method's parameters",
        "frontend/src/state/analysisContext.ts",
        "...(method === project.analysis.method ? structuredClone(project.analysis.parameters) : {}),",
        "...structuredClone(project.analysis.parameters),",
    ),
    Mutation(
        "Sorting record check accepts any record version",
        "frontend/src/state/useAnalysisRecord.ts",
        "if (record.record_version !== expectedVersion ||",
        "if (false ||",
    ),
    Mutation(
        "Sorting Sensitivity shows the class above for a change below the baseline",
        "frontend/src/components/SensitivityPanel.tsx",
        "classes.get(raising ? c.class_after : c.class_before)",
        "classes.get(c.class_after)",
    ),
]


SMAA_BACKEND = [
    Mutation(
        "SMAA tied first places are counted as sole first",
        "src/mcda_studio/methods/smaa/engine.py",
        "sole += (first & ~shared_first[:, None]).sum(axis=0)",
        "sole += first.sum(axis=0)",
    ),
    Mutation(
        "SMAA near-ties are never summed again, so ties are broken by position",
        "src/mcda_studio/methods/smaa/engine.py",
        "NEAR_TIE = 1e-9",
        "NEAR_TIE = -1.0",
    ),
    Mutation(
        "SMAA samples a triangular distribution as uniform",
        "src/mcda_studio/methods/smaa/engine.py",
        "return np.where(u < split, rising, falling)",
        "return a + u * (b - a)",
    ),
    Mutation(
        "SMAA ignores the seed",
        "src/mcda_studio/methods/smaa/engine.py",
        "rng = np.random.Generator(np.random.PCG64(seed))",
        "rng = np.random.Generator(np.random.PCG64(0))",
    ),
    Mutation(
        "SMAA zero events get a zero upper bound, as a Wald interval would",
        "src/mcda_studio/methods/smaa/intervals.py",
        "upper = 1.0 - (alpha / 2) ** (1.0 / n)",
        "upper = 0.0",
    ),
    Mutation(
        "SMAA performance run also varies the weights",
        "src/mcda_studio/methods/smaa/engine.py",
        'if run in {"preference", "combined"}:',
        "if True:",
    ),
    Mutation(
        "SMAA shared-draw cells keep their entered values",
        "src/mcda_studio/methods/smaa/engine.py",
        """        for _, members in plan.shared:
            for i in members:
                cell = plan.cells[i]
                partial[:, cell.alternative, cell.leaf] = cell.partial(uniforms[:, column])""",
        """        for _, members in plan.shared:
            for i in []:
                cell = plan.cells[i]
                partial[:, cell.alternative, cell.leaf] = cell.partial(uniforms[:, column])""",
    ),
    Mutation(
        "SMAA zero rating intervals are not refused",
        "src/mcda_studio/methods/smaa/validation.py",
        "if group.intervals and all(hi == 0.0 for _, hi in group.intervals.values()):",
        "if False:",
    ),
    Mutation(
        "SMAA unsupported dependence is accepted",
        "src/mcda_studio/methods/smaa/validation.py",
        'if model.dependence != "independent":',
        "if False:",
    ),
    Mutation(
        "SMAA a distribution may reach outside the value-function domain",
        "src/mcda_studio/methods/smaa/validation.py",
        "and (min(support) < domain.lower or max(support) > domain.upper)",
        "and False",
    ),
    Mutation(
        "SMAA absent uncertainty section is written as null",
        "src/mcda_studio/domain/project.py",
        "smaa: SmaaModel | None = Field(default=None, exclude_if=lambda v: v is None)",
        "smaa: SmaaModel | None = Field(default=None, exclude_if=lambda v: False)",
    ),
    Mutation(
        "SMAA section written as schema version 2",
        "src/mcda_studio/domain/project.py",
        '"smaa": 3, "promethee"',
        '"smaa": 2, "promethee"',
    ),
]

SMAA_FRONTEND = [
    Mutation(
        "SMAA Acceptability view drops its label",
        "frontend/src/components/results/AcceptabilityView.tsx",
        "<strong>{result.label[0]?.toUpperCase()}{result.label.slice(1)}.</strong>",
        "<strong></strong>",
    ),
    Mutation(
        "SMAA record check accepts acceptabilities that do not match the project",
        "frontend/src/state/useAnalysisRecord.ts",
        'throw Error("Acceptabilities do not match the project\'s alternatives and classes.");',
        "void 0;",
    ),
    Mutation(
        "SMAA run settings follow into another method",
        "frontend/src/components/AnalysisControls.tsx",
        "onChange={(e) => onSelect({ method: e.target.value, parameters: null })}>",
        "onChange={(e) => onSelect({ method: e.target.value })}>",
    ),
]


PROMETHEE_BACKEND = [
    Mutation(
        "PROMETHEE q and p swapped in the linear function",
        "src/mcda_studio/methods/promethee/flows.py",
        "q, p = function.q, function.p",
        "p, q = function.q, function.p",
    ),
    Mutation(
        "PROMETHEE flows not divided by n - 1",
        "src/mcda_studio/methods/promethee/flows.py",
        "    others = n - 1\n",
        "    others = 1\n",
    ),
    Mutation(
        "PROMETHEE minimise ignored",
        "src/mcda_studio/methods/promethee/flows.py",
        'signs = [1 if c.direction == "maximise" else -1 for c in criteria]',
        "signs = [1 for c in criteria]",
    ),
    Mutation(
        "PROMETHEE U-shape counts a difference equal to q as preference",
        "src/mcda_studio/methods/promethee/flows.py",
        "return 0.0 if d <= function.q + tol else 1.0",
        "return 0.0 if d < function.q - tol else 1.0",
    ),
    Mutation(
        "PROMETHEE thresholds compared without the tolerance",
        "src/mcda_studio/methods/promethee/validation.py",
        "return THRESHOLD_REL * max(1.0, abs(x_a), abs(x_b))",
        "return 0.0",
    ),
    Mutation(
        "PROMETHEE weights not normalised",
        "src/mcda_studio/methods/promethee/flows.py",
        "weights = [c.weight / total for c in criteria]",
        "weights = [c.weight for c in criteria]",
    ),
    Mutation(
        "PROMETHEE net flow taken as the positive flow alone",
        "src/mcda_studio/methods/promethee/flows.py",
        "net = [positive[a] - negative[a] for a in range(n)]",
        "net = [positive[a] for a in range(n)]",
    ),
    Mutation(
        "PROMETHEE incomparable pairs reported as indifferent",
        "src/mcda_studio/methods/promethee/flows.py",
        'alternative_a=ids[a], alternative_b=ids[b], relation="incomparable"',
        'alternative_a=ids[a], alternative_b=ids[b], relation="indifferent"',
    ),
    Mutation(
        "PROMETHEE via-others part dropped, so the flow gap no longer reconciles",
        "src/mcda_studio/methods/promethee/explanation.py",
        "via_others=flow_gap - head_to_head,",
        "via_others=0.0,",
    ),
    Mutation(
        "PROMETHEE capped difference reported as partial",
        "src/mcda_studio/methods/promethee/explanation.py",
        'return "no_preference" if degree == 0.0 else "full" if degree == 1.0 else "partial"',
        'return "no_preference" if degree == 0.0 else "partial"',
    ),
    Mutation(
        "PROMETHEE absent section is written as null",
        "src/mcda_studio/domain/project.py",
        "promethee: PrometheeModel | None = Field(default=None, exclude_if=lambda v: v is None)",
        "promethee: PrometheeModel | None = Field(default=None, exclude_if=lambda v: False)",
    ),
    Mutation(
        "PROMETHEE section written as schema version 3",
        "src/mcda_studio/domain/project.py",
        '"promethee": 4, "ahp"',
        '"promethee": 3, "ahp"',
    ),
]

PROMETHEE_FRONTEND = [
    Mutation(
        "PROMETHEE flows drawn on the 0-1 value axis",
        "frontend/src/components/results/FlowsView.tsx",
        "LEFT + (flow - FLOW_AXIS.min) / (FLOW_AXIS.max - FLOW_AXIS.min) * WIDTH",
        "LEFT + flow * WIDTH",
    ),
    Mutation(
        "PROMETHEE Flows view drops its label",
        "frontend/src/components/results/FlowsView.tsx",
        "<strong>{capital(result.label)}.</strong>",
        "<strong></strong>",
    ),
    Mutation(
        "PROMETHEE a pair ordered differently is missing from the explanation",
        "frontend/src/components/results/FlowsView.tsx",
        "{explanation.pairs.map(pair =>",
        "{explanation.pairs.slice(1).map(pair =>",
    ),
    Mutation(
        "PROMETHEE record check accepts flows that do not match the project",
        "frontend/src/state/useAnalysisRecord.ts",
        'throw Error("Outranking flows do not match the project\'s alternatives and criteria.");',
        "void 0;",
    ),
    Mutation(
        "PROMETHEE MAVT previews requested for the viewed PROMETHEE method",
        "frontend/src/state/usePreviews.ts",
        'const VALUE_MODEL_METHODS = new Set(["mavt", "mavt_sorting", "smaa2"]);',
        'const VALUE_MODEL_METHODS = new Set(["mavt", "mavt_sorting", "smaa2", "promethee2"]);',
    ),
]


AHP_BACKEND = [
    Mutation("AHP wrong reciprocal", "src/mcda_studio/methods/ahp/matrix.py",
             "        m[c][r] = 1.0 / j.value", "        m[c][r] = j.value"),
    Mutation("AHP off-by-one random-index lookup", "src/mcda_studio/methods/ahp/matrix.py",
             "    return RANDOM_INDEX[n - 1]", "    return RANDOM_INDEX[min(n, len(RANDOM_INDEX) - 1)]"),
    Mutation("AHP unnormalised priorities", "src/mcda_studio/methods/ahp/matrix.py",
             "            w = [x / total for x in v]", "            w = v"),
    Mutation("AHP distributive and ideal synthesis swapped", "src/mcda_studio/methods/ahp/engine.py",
             '    ideal = params.synthesis == "ideal"', '    ideal = params.synthesis == "distributive"'),
    Mutation("AHP warning at CR >= 0.10 instead of above it", "src/mcda_studio/methods/ahp/matrix.py",
             "        inconsistent=cr > CR_THRESHOLD,", "        inconsistent=cr >= CR_THRESHOLD,"),
    Mutation("AHP triad index takes only one of its two ratios", "src/mcda_studio/methods/ahp/matrix.py",
             "        index = min(abs(1 - z / (x * y)), abs(1 - x * y / z))", "        index = abs(1 - z / (x * y))"),
    Mutation("AHP global priorities not multiplied down the tree", "src/mcda_studio/methods/ahp/engine.py",
             "    global_ = {leaf: math.prod(local[node] for node in tree.path(leaf)) for leaf in leaves}",
             "    global_ = {leaf: local[leaf] for leaf in leaves}"),
    Mutation("AHP iteration cap ignored, returning a partial vector", "src/mcda_studio/methods/ahp/matrix.py",
             "    raise ConvergenceError(", "    return w, math.fsum(_multiply(m, w)), MAX_ITERATIONS\n    raise ConvergenceError("),
    Mutation("AHP absent section is written as null", "src/mcda_studio/domain/project.py",
             "ahp: AhpModel | None = Field(default=None, exclude_if=lambda v: v is None)",
             "ahp: AhpModel | None = Field(default=None, exclude_if=lambda v: False)"),
    Mutation("AHP section written as schema version 4", "src/mcda_studio/domain/project.py",
             '"ahp": 5, "requirements"', '"ahp": 4, "requirements"'),
]  # fmt: skip

AHP_FRONTEND = [
    Mutation("AHP view drops its label", "frontend/src/components/results/AhpView.tsx",
             "<strong>{capital(result.label)}.</strong>", "<strong></strong>"),
    Mutation("AHP triad cells not highlighted", "frontend/src/components/PairwisePanel.tsx",
             "const marked = inTriad(a, b) && analysis?.inconsistent === true;", "const marked = false;"),
    Mutation("AHP consistency warning not shown", "frontend/src/components/PairwisePanel.tsx",
             '{analysis.inconsistent && <p role="status" className="warning"', '{false && <p role="status" className="warning"'),
    Mutation("AHP record check accepts mismatched priorities", "frontend/src/state/useAnalysisRecord.ts",
             'throw Error("AHP priorities do not match the project\'s alternatives and criteria.");', "void 0;"),
    Mutation("AHP record check expects the viewed profile and scenario", "frontend/src/state/useAnalysisRecord.ts",
             'const reads = configuration.method !== "ahp";', "const reads = true;"),
]  # fmt: skip


COMPARISON_BACKEND = [
    Mutation("COMPARISON a method silently dropped from the columns", "src/mcda_studio/services/comparison_service.py",
             "    wanted = [m for m in order if methods is None or m in methods]",
             '    wanted = [m for m in order if (methods is None or m in methods) and m != "promethee2"]'),
    Mutation("COMPARISON every column labelled with the first method", "src/mcda_studio/services/comparison_service.py",
             "        method = get_method(name)", "        method = get_method(order[0])"),
    Mutation("COMPARISON a failed column omitted instead of shown", "src/mcda_studio/services/comparison_service.py",
             "        except McdaError as exc:\n", "        except McdaError as exc:\n            continue\n"),
    Mutation("COMPARISON SMAA-2's leader taken from MAVT's reference ranking", "src/mcda_studio/services/comparison_service.py",
             "        return cells, [smaa.leader_id]", "        return cells, [smaa.ranking[0].alternative_id]"),
    Mutation("COMPARISON agreement declared when a column has a tied leader", "src/mcda_studio/services/comparison_service.py",
             "else all(len(c.leaders) == 1 and set(c.leaders) == set(ok[0].leaders) for c in ok)",
             "else all(set(c.leaders) == set(ok[0].leaders) for c in ok)"),
    Mutation("COMPARISON a reason taken from the wrong pair", "src/mcda_studio/services/comparison_service.py",
             "        a, b = mavt[0], leaders[0]", "        a, b = mavt[0], mavt[0]"),
    Mutation("COMPARISON class agreement always declared", "src/mcda_studio/services/comparison_service.py",
             "                    agree=cell.class_id == other.class_id,", "                    agree=True,"),
]  # fmt: skip

COMPARISON_FRONTEND = [
    Mutation("COMPARISON two columns drawn on a shared axis", "frontend/src/components/ComparePanel.tsx",
             'return column.method === "promethee2" ? [-1, 1] : [0, 1];', "return [0, 1];"),
    Mutation("COMPARISON a column header without its method", "frontend/src/components/ComparePanel.tsx",
             '<span className="column-method">{c.method_label}</span>', '<span className="column-method"></span>'),
    Mutation("COMPARISON a failed column hides its typed error", "frontend/src/components/ComparePanel.tsx",
             "Did not run: <code>{c.error.code}</code>", "Did not run <code></code>"),
]  # fmt: skip


FEASIBILITY_BACKEND = [
    Mutation("FEASIBILITY duplicate measurements use the last value", "src/mcda_studio/services/feasibility_service.py",
             "            if counts[key] > 1:", "            if False:"),
    Mutation("FEASIBILITY an inclusive minimum compared with >", "src/mcda_studio/services/feasibility_service.py",
             "if r.minimum_inclusive and not x >= r.minimum:", "if r.minimum_inclusive and not x > r.minimum:"),
    Mutation("FEASIBILITY an inclusive maximum compared with <", "src/mcda_studio/services/feasibility_service.py",
             "if r.maximum_inclusive and not x <= r.maximum:", "if r.maximum_inclusive and not x < r.maximum:"),
    Mutation("FEASIBILITY an exclusive minimum compared with >=", "src/mcda_studio/services/feasibility_service.py",
             "if not r.minimum_inclusive and not x > r.minimum:", "if not r.minimum_inclusive and not x >= r.minimum:"),
    Mutation("FEASIBILITY an exclusive maximum compared with <=", "src/mcda_studio/services/feasibility_service.py",
             "if not r.maximum_inclusive and not x < r.maximum:", "if not r.maximum_inclusive and not x <= r.maximum:"),
    Mutation("FEASIBILITY a missing measurement treated as fail", "src/mcda_studio/services/feasibility_service.py",
             'return done("unknown", "no measurement")', 'return done("fail", "no measurement")'),
    Mutation("FEASIBILITY a missing measurement treated as pass", "src/mcda_studio/services/feasibility_service.py",
             'return done("unknown", "no measurement")', 'return done("pass", "no measurement")'),
    Mutation("FEASIBILITY a failure compensated when most requirements pass", "src/mcda_studio/services/feasibility_service.py",
             '    if "fail" in statuses:\n        return "fail"', '    if statuses.count("fail") * 2 > len(statuses):\n        return "fail"'),
    Mutation("FEASIBILITY unknown outranking fail", "src/mcda_studio/services/feasibility_service.py",
             '    if "fail" in statuses:\n        return "fail"\n    if "unknown" in statuses:\n        return "unknown"',
             '    if "unknown" in statuses:\n        return "unknown"\n    if "fail" in statuses:\n        return "fail"'),
    Mutation("FEASIBILITY the unit check skipped", "src/mcda_studio/services/feasibility_service.py",
             "            if r.unit != scale.unit:", "            if False:"),
    Mutation("FEASIBILITY an absent section written as an empty list", "src/mcda_studio/services/project_service.py",
             "    out.requirements = [r.model_copy(deep=True) for r in requirements] or None",
             "    out.requirements = [r.model_copy(deep=True) for r in requirements]"),
    Mutation("FEASIBILITY the section written as version 5", "src/mcda_studio/domain/project.py",
             '"ahp": 5, "requirements": 6}', '"ahp": 5, "requirements": 5}'),
]  # fmt: skip

FEASIBILITY_FRONTEND = [
    Mutation("FEASIBILITY a failing alternative hidden from the comparison", "frontend/src/components/ComparePanel.tsx",
             "<tbody>{rows.map((id) =>",
             '<tbody>{rows.filter((id) => feasibility?.alternatives.find((a) => a.alternative_id === id)?.status !== "fail").map((id) =>'),
    Mutation("FEASIBILITY the status not shown beside the ranking", "frontend/src/components/ResultsPanel.tsx",
             '{feasibility.status === "ready" && <FeasibilityView result={feasibility.result} project={project}/>}', ""),
    Mutation("FEASIBILITY unknown shown as pass", "frontend/src/components/results/FeasibilityView.tsx",
             'unknown: "unknown" }', 'unknown: "passes" }'),
]  # fmt: skip


MEASUREMENT_RANGE_BACKEND = [
    Mutation("RANGE ignores rank changes", "src/mcda_studio/methods/mavt/measurement_range.py",
             "rank_change = any(rank_values(item[1])[i] != baseline_rank for item in (minimum, maximum))",
             "rank_change = False"),
    Mutation("RANGE ignores class changes", "src/mcda_studio/methods/mavt/measurement_range.py",
             "class_change = any(", "class_change = False and any("),
    Mutation("RANGE reverses rank tie threshold", "src/mcda_studio/methods/mavt/measurement_range.py",
             'Fraction(baseline[k]) - Fraction(TIE_TOL)', 'Fraction(baseline[k]) + Fraction(TIE_TOL)'),
    Mutation("RANGE reverses class tolerance", "src/mcda_studio/methods/mavt/measurement_range.py",
             'Fraction(b) - Fraction(TIE_TOL)', 'Fraction(b) + Fraction(TIE_TOL)'),
    Mutation("RANGE drops flat boundary intervals", "src/mcda_studio/methods/mavt/measurement_range.py",
             'a, b = left, right', 'continue'),
    Mutation("RANGE accepts an excluded baseline", "src/mcda_studio/methods/mavt/measurement_range.py",
             'or not lower <= measurement <= upper:', 'or False:'),
    Mutation("RANGE ignores scenario functions", "src/mcda_studio/methods/mavt/measurement_range.py",
             'if prep.scenario\n', 'if False\n'),
]  # fmt: skip

EVIDENCE_WORKSPACE_BACKEND = [
    Mutation(
        "EVIDENCE ignores changed history",
        "src/mcda_studio/services/evidence_workspace_service.py",
        "if workspace.digest != workspace_digest(workspace):",
        "if False:",
    ),
    Mutation(
        "EVIDENCE ignores reviewed preview digest",
        "src/mcda_studio/services/evidence_workspace_service.py",
        "if current.preview.review_digest != expected_review_digest:",
        "if False:",
    ),
    Mutation(
        "EVIDENCE overwrites original dossier during review",
        "src/mcda_studio/services/evidence_workspace_service.py",
        "candidate = workspace.model_copy(deep=True)",
        "candidate = workspace",
    ),
    Mutation(
        "EVIDENCE treats differing accepted value as support",
        "src/mcda_studio/services/evidence_workspace_service.py",
        "and change.after == raw[cell]",
        "",
    ),
    Mutation(
        "EVIDENCE accepts invalid or conflicting values",
        "src/mcda_studio/services/evidence_workspace_service.py",
        "if errors:\n            raise ValidationFailed",
        "if False:\n            raise ValidationFailed",
    ),
    Mutation(
        "EVIDENCE does not replay review history",
        "src/mcda_studio/services/evidence_workspace_service.py",
        "for event in workspace.reviews:",
        "for event in []:",
    ),
]

FRONTEND += [
    Mutation(
        "EVIDENCE confirms a preview for changed intent",
        "frontend/src/components/EvidenceWorkspacePanel.tsx",
        "const current = candidate?.key === key ? candidate.result : null;",
        "const current = candidate?.result ?? null;",
    ),
    Mutation(
        "EVIDENCE loses unexported review guard",
        "frontend/src/components/EvidenceWorkspacePanel.tsx",
        "setDocument(current.workspace); setDirty(true);",
        "setDocument(current.workspace); setDirty(false);",
    ),
    Mutation(
        "DERIVED exports a compilation from an earlier context",
        "frontend/src/components/CalculationWorkspaceView.tsx",
        "const compilation = compiled?.key === key ? compiled.bundle : null;",
        "const compilation = compiled?.bundle ?? null;",
    ),
    Mutation(
        "DERIVED permits compilation before explicit target review",
        "frontend/src/components/CalculationWorkspaceView.tsx",
        "disabled={copyKey !== key || pending}",
        "disabled={pending}",
    ),
    Mutation(
        "CALCULATION applies before explicit acknowledgement",
        "frontend/src/components/CalculationWorkspaceView.tsx",
        "disabled={applyKey !== key || locked} onClick={() => { void applyNow(); }}",
        "disabled={locked} onClick={() => { void applyNow(); }}",
    ),
    Mutation(
        "CALCULATION records an application whose edit differs",
        "frontend/src/components/CalculationWorkspaceView.tsx",
        "if (after !== application.project_fingerprint) throw",
        "if (false) throw",
    ),
    Mutation(
        "CALCULATION records a proposal from an earlier context",
        "frontend/src/components/CalculationWorkspaceView.tsx",
        "      const next = await api.proposeCalculation(project, result.workspace, event, result.preview.review_digest);\n      if (liveKey.current !== captured) return;",
        "      const next = await api.proposeCalculation(project, result.workspace, event, result.preview.review_digest);",
    ),
    Mutation(
        "CALCULATION loses unexported history guard",
        "frontend/src/components/DerivedMeasurementsPanel.tsx",
        "if (exported) { setOriginal(workspace); setDirty(false); } else setDirty(true);",
        "if (exported) { setOriginal(workspace); setDirty(false); } else setDirty(false);",
    ),
    Mutation(
        "CALCULATION edits an unbound workspace",
        "frontend/src/components/CalculationWorkspaceView.tsx",
        "const locked = !bound || pending || busy || !name;",
        "const locked = pending || busy || !name;",
    ),
]

CALCULATION_BACKEND = [
    Mutation("CALCULATION trial accepts every formula", "src/mcda_studio/services/derived_service.py",
             'return _run(project, model, frozenset({formula_id}), structure)', 'return _run(project, model, frozenset(f.id for f in model.formulas), structure)'),
    Mutation("CALCULATION ignores changed history", "src/mcda_studio/services/calculation_workspace_service.py",
             "if workspace.digest != workspace_digest(workspace):", "if False:"),
    Mutation("CALCULATION does not replay history", "src/mcda_studio/services/calculation_workspace_service.py",
             "for index, event in enumerate(workspace.events):", "for index, event in enumerate([]):"),
    Mutation("CALCULATION lets a definition carry its review", "src/mcda_studio/services/calculation_workspace_service.py",
             "if entry.review is not None:", "if False:"),
    Mutation("CALCULATION moves a redefined entry to the end", "src/mcda_studio/services/calculation_workspace_service.py",
             "return [item if x.id == item.id else x for x in items]", "return [x for x in items if x.id != item.id] + [item]"),
    Mutation("CALCULATION redefines a unit", "src/mcda_studio/services/calculation_workspace_service.py",
             "if event.unit in m.units:", "if False:"),
    Mutation("CALCULATION trusts the recorded application", "src/mcda_studio/services/calculation_workspace_service.py",
             "if applied.fingerprint() != event.project_fingerprint:", "if False:"),
    Mutation("CALCULATION applies an unreviewed digest", "src/mcda_studio/services/calculation_workspace_service.py",
             "if report.review_digest != event.review_digest:", "if False:"),
    Mutation("CALCULATION rebinds across projects", "src/mcda_studio/services/calculation_workspace_service.py",
             "if event.project.id != project.id:", "if False:"),
    Mutation("CALCULATION treats an earlier revision as bound", "src/mcda_studio/services/calculation_workspace_service.py",
             'if current == state.bindings[-1]', 'if current in state.bindings'),
    Mutation("CALCULATION accepts a formula that does not calculate", "src/mcda_studio/services/calculation_workspace_service.py",
             'if check is not None and check.status != "calculates":', "if False:"),
    Mutation("CALCULATION accepts a factor without a value", "src/mcda_studio/services/calculation_workspace_service.py",
             "if factor is not None and value is None:", "if False:"),
    Mutation("CALCULATION ignores the acknowledged digest", "src/mcda_studio/services/calculation_workspace_service.py",
             "if current.preview.review_digest != expected_review_digest:", "if False:"),
    Mutation("CALCULATION edits an unbound workspace", "src/mcda_studio/services/calculation_workspace_service.py",
             'elif current.relationship != "bound":\n        raise StaleRevisionError', 'elif False:\n        raise StaleRevisionError'),
    Mutation("CALCULATION applies without a change", "src/mcda_studio/services/calculation_workspace_service.py",
             "if not any(c.changed for c in current.changes):", "if False:"),
    Mutation("CALCULATION usage ignores intermediates", "src/mcda_studio/services/calculation_workspace_service.py",
             "elif name in refs and name not in seen:", "elif False:"),
    Mutation("CALCULATION overwrites the input workspace", "src/mcda_studio/services/calculation_workspace_service.py",
             "candidate = workspace.model_copy(deep=True)", "candidate = workspace"),
    Mutation("CALCULATION changes compare by tolerance", "src/mcda_studio/services/calculation_workspace_service.py",
             "changed=c.before != c.value,", "changed=c.before is None or abs(float(c.before) - c.value) > 1,"),
    Mutation("DECISION record nonfinite numbers reach the server", "src/mcda_studio/services/decision_service.py",
             "    except ValueError as exc:\n        raise ModelEditError(", "    except KeyError as exc:\n        raise ModelEditError("),
]  # fmt: skip


UNCERTAINTY_BACKEND = [
    Mutation("UNCERTAINTY draws coupled factors independently", "src/mcda_studio/services/factor_uncertainty_service.py",
             "realised[factor] = plan.marginals[factor].quantile(uniforms[:, column])",
             "realised[factor] = plan.marginals[factor].quantile(rng.random(draws))"),
    Mutation("UNCERTAINTY enumerates coupled factors independently", "src/mcda_studio/services/factor_uncertainty_service.py",
             "            blocks.append(_segments(plan, members))",
             "            blocks.extend([(p, {m: v}) for p, v in plan.marginals[m].atoms or [] if p > 0] for m in members)"),
    Mutation("UNCERTAINTY traverses factors in declaration order", "src/mcda_studio/services/factor_uncertainty_service.py",
             "independent = sorted(f for f in marginals if f not in grouped)",
             "independent = [f for f in marginals if f not in grouped]"),
    Mutation("UNCERTAINTY drops an invalid draw silently", "src/mcda_studio/services/factor_uncertainty_service.py",
             "raise DrawError(exc.code, draw, formula_id, str(exc), sorted(plan.fixed)) from exc",
             "break"),
    Mutation("UNCERTAINTY ignores the model digest", "src/mcda_studio/services/factor_uncertainty_service.py",
             "if uncertainty.model_digest != report.model_digest:", "if False:"),
    Mutation("UNCERTAINTY samples a derived output", "src/mcda_studio/services/factor_uncertainty_service.py",
             "        if d.factor_id in formulas:", "        if False:"),
    Mutation("UNCERTAINTY accepts duplicate distributions", "src/mcda_studio/services/factor_uncertainty_service.py",
             'if count > 1:\n            add("UNCERTAINTY_DUPLICATE"', 'if False:\n            add("UNCERTAINTY_DUPLICATE"'),
    Mutation("UNCERTAINTY accepts a zero denominator support", "src/mcda_studio/services/factor_uncertainty_service.py",
             "if b[0] <= 0 <= b[1]:", "if False:"),
    Mutation("UNCERTAINTY shares one column for every factor", "src/mcda_studio/services/factor_uncertainty_service.py",
             "realised[factor] = plan.marginals[factor].quantile(uniforms[:, column])",
             "realised[factor] = plan.marginals[factor].quantile(uniforms[:, 0])"),
    Mutation("UNCERTAINTY swaps the triangular branches", "src/mcda_studio/services/factor_uncertainty_service.py",
             "return np.where(u < split, rising, falling)", "return np.where(u < split, falling, rising)"),
    Mutation("UNCERTAINTY accepts an unreviewed coupling", "src/mcda_studio/services/factor_uncertainty_service.py",
             'add("UNCERTAINTY_UNREVIEWED", "the stated coupling requires acceptance", path)', "pass"),
]  # fmt: skip


UNCERTAINTY_BACKEND += [
    Mutation("UNCERTAINTY integration discards a bad draw and reduces its denominator", 'src/mcda_studio/services/factor_analysis_service.py',
             '        evaluated = evaluate_draw(compiled, cfg, plan, values, index)\n        by_id = {a.alternative_id: a for a in evaluated.alternatives}\n        for a, alternative in enumerate(prep.alt_ids):\n            partial[index, a] = [by_id[alternative].partial_values[leaf] for leaf in prep.leaf_ids]\n        row = FactorDraw(\n            index=index,\n            probability=str(probability) if exact else None,\n            factors={s: values[s] for s in sorted(plan.fixed)},\n            formulas={f: values[f] for f in plan.order},\n            measurements={a: by_id[a].raw_measurements for a in prep.alt_ids},\n            values={a: by_id[a].overall_value for a in prep.alt_ids},\n            ranks={a: by_id[a].rank for a in prep.alt_ids},\n            classes={a.alternative_id: a.class_id for a in evaluated.assignments}\n            if isinstance(evaluated, MavtSortingResult)\n            else {},\n        )\n        rows_digest.update((derived._digest(row.model_dump(mode="json")) + "\\n").encode())\n        if index < TRACE_ROWS:\n            trace.append(row)\n', '        try:\n            evaluated = evaluate_draw(compiled, cfg, plan, values, index)\n        except factors.DrawError:\n            partial[index] = np.nan\n            continue\n        by_id = {a.alternative_id: a for a in evaluated.alternatives}\n        for a, alternative in enumerate(prep.alt_ids):\n            partial[index, a] = [by_id[alternative].partial_values[leaf] for leaf in prep.leaf_ids]\n        row = FactorDraw(\n            index=index,\n            probability=str(probability) if exact else None,\n            factors={s: values[s] for s in sorted(plan.fixed)},\n            formulas={f: values[f] for f in plan.order},\n            measurements={a: by_id[a].raw_measurements for a in prep.alt_ids},\n            values={a: by_id[a].overall_value for a in prep.alt_ids},\n            ranks={a: by_id[a].rank for a in prep.alt_ids},\n            classes={a.alternative_id: a.class_id for a in evaluated.assignments}\n            if isinstance(evaluated, MavtSortingResult)\n            else {},\n        )\n        rows_digest.update((derived._digest(row.model_dump(mode="json")) + "\\n").encode())\n        if index < TRACE_ROWS:\n            trace.append(row)\n    valid = ~np.isnan(partial).any(axis=(1, 2))\n    probabilities = [p for i, p in enumerate(probabilities) if valid[i]]\n    partial = partial[valid]\n    n = len(partial)\n'),
    Mutation("UNCERTAINTY samples a factor twice", "src/mcda_studio/services/factor_uncertainty_service.py",
             "realised[factor] = plan.marginals[factor].quantile(uniforms[:, column])",
             "realised[factor] = (plan.marginals[factor].quantile(uniforms[:, column]) + plan.marginals[factor].quantile(rng.random(draws))) / 2"),
    Mutation("UNCERTAINTY reused factor gets a different realization", "src/mcda_studio/services/factor_uncertainty_service.py",
             "result = calculate(plan.trees[formula_id], cache.__getitem__)",
             "result = calculate(plan.trees[formula_id], lambda name: Quantity(cache[name].value * (1.1 if formula_id == plan.order[-1] else 1.0), cache[name].dimension))"),
    Mutation("UNCERTAINTY silently accepts cell uncertainty on a derived target", "src/mcda_studio/services/derived_service.py",
             "if project.smaa and any(", "if False and any("),
]  # fmt: skip


PROPOSALS_BACKEND = [
    Mutation('PROPOSALS imported outputs accepted without review', 'src/mcda_studio/services/proposal_service.py',
             'for proposal in intake.proposals:\n        review = latest.get(proposal.id)\n        if review is None or review.status == "rejected":', 'for proposal in intake.proposals:\n        review = latest.get(proposal.id) or ProposalReviewDetails(status="accepted", reviewer="Imported output", reviewed_at=proposal.run_at, primary_source_id=proposal.source_ids[0] if proposal.source_ids else None)\n        if review is None or review.status == "rejected":'),
    Mutation('PROPOSALS correction rewrites the original payload', 'src/mcda_studio/services/proposal_service.py',
             '        candidate.reviews.append(event.model_copy(deep=True))', '        if event.review.corrected_payload is not None:\n            next(p for p in candidate.intake.proposals if p.id == event.proposal_id).payload = event.review.corrected_payload.model_copy(deep=True)\n        candidate.reviews.append(event.model_copy(deep=True))'),
    Mutation('PROPOSALS accepts review on another project revision', 'src/mcda_studio/services/proposal_service.py',
             '    if current.stale:', '    if False:'),
    Mutation('PROPOSALS accepts unresolved original sources', 'src/mcda_studio/services/proposal_service.py',
             '    if not refs or any(ref not in intake.sources for ref in refs):', '    if False:'),
    Mutation('PROPOSALS permits two active claims on one cell', 'src/mcda_studio/services/proposal_service.py',
             '                other_id != proposal.id', '                False and other_id != proposal.id'),
    Mutation('PROPOSALS confidence rescales an imported measurement', 'src/mcda_studio/services/proposal_service.py',
             '        original_value = original_cell[0] if original_cell is not None else value', '        original_value = original_cell[0] if original_cell is not None else value\n        if isinstance(original_value, float) and proposal.confidence is not None:\n            original_value *= proposal.confidence.value'),
    Mutation('PROPOSALS bulk review skips blocked item check', 'src/mcda_studio/services/proposal_service.py',
             '        if any(e.proposal_id not in eligible for e in events):', '        if False:'),
    Mutation('PROPOSALS accepts missing or changed model card', 'src/mcda_studio/services/proposal_service.py',
             '    if card is None or evidence._digest(card.model_dump(mode="json")) != proposal.model_card_digest:', '    if False:'),
    Mutation('PROPOSALS registry addition replaces an original source', 'src/mcda_studio/services/proposal_service.py',
             '        if key in registry and registry[key] != value:', '        if False:'),
    Mutation('PROPOSALS compile ignores acknowledged review history', 'src/mcda_studio/services/proposal_service.py',
             '        current.stale\n        or current.review_digest != expected_review_digest\n        or workspace.digest != expected_workspace_digest', '        False'),
    Mutation('PROPOSALS CSV imports the valid subset of a malformed batch', 'src/mcda_studio/services/proposal_import_service.py',
             '                    _fail(f"CSV line {line}: {exc}")', '                    continue'),
]  # fmt: skip

PROPOSALS_FRONTEND = [
    Mutation('PROPOSALS delayed import published in a newer context', 'frontend/src/components/ExternalProposalsPanel.tsx',
             'const acceptsResponse = (captured: string) => live.current === captured;', 'const acceptsResponse = (captured: string) => true;'),
    Mutation('PROPOSALS blocked item selectable for bulk review', 'frontend/src/components/ExternalProposalsPanel.tsx',
             'disabled={!r.bulk_eligible || busy}', 'disabled={busy}'),
]  # fmt: skip


MODELS_BACKEND = [
    Mutation('MODELS formula output changes by one percent', 'src/mcda_studio/services/model_checks_service.py', '    value = reference[specification.formula_id]', '    value = reference[specification.formula_id] * 1.01'),
    Mutation('MODELS duplicate shared-factor draws per alternative', 'src/mcda_studio/services/factor_analysis_service.py', '        if check_draw is not None:\n            check_draw(values, index)', '        if check_draw is not None:\n            check_draw(values, index)\n            for target_index, (formula, _, _) in enumerate(plan.targets):\n                independent = factors.sample(plan, parameters.seed + target_index + 1, 1)\n                values[formula] = float(independent.values[formula][0])'),
    Mutation('MODELS average two model outputs', 'src/mcda_studio/services/model_comparison_service.py', '    left, right = _snapshot(project, comparison.left), _snapshot(project, comparison.right)', '    left, right = _snapshot(project, comparison.left), _snapshot(project, comparison.right)\n    if left.run is not None and right.run is not None:\n        left.run.value = (left.run.value + right.run.value) / 2'),
    Mutation('MODELS source bounds inferred as uniform draws', 'src/mcda_studio/services/model_checks_service.py', '    if isinstance(request, SourceRange):\n        planning = FactorUncertaintyModel(\n            project_fingerprint=project.fingerprint(), model_digest=scoped.uncertainty.model_digest\n        )', '    if isinstance(request, SourceRange):\n        from mcda_studio.domain.factor_uncertainty import FactorDistribution\n        from mcda_studio.domain.uncertainty import UniformDistribution\n        planning = FactorUncertaintyModel(\n            project_fingerprint=project.fingerprint(), model_digest=scoped.uncertainty.model_digest,\n            distributions=[FactorDistribution(factor_id=item.factor_id, distribution=UniformDistribution(lower=item.lower, upper=item.upper), origin=item.origin, review=item.review) for item in request.intervals],\n        )\n        request = SampledRange(draws=1000, seed=7)'),
    Mutation('MODELS erase disagreement when ranges overlap', 'src/mcda_studio/services/model_comparison_service.py', '    if comparison.review is None or comparison.review.status != "accepted":', '    if left.run is not None and right.run is not None and max(left.run.range.lower, right.run.range.lower) <= min(left.run.range.upper, right.run.range.upper):\n        questions = []\n    if comparison.review is None or comparison.review.status != "accepted":'),
    Mutation('MODELS fresh starter retains old acceptances', 'src/mcda_studio/services/starter_template_service.py', '            if key == "review":', '            if False and key == "review":'),
    Mutation('MODELS ignore template digest', 'src/mcda_studio/services/starter_template_service.py', '    if template.digest != template_digest(template):', '    if False:'),
    Mutation('MODELS template-specific engine branch', 'src/mcda_studio/services/starter_template_service.py', '    project = original.model_copy(deep=True)', '    project = original.model_copy(deep=True)\n    if request.template_id not in {"blank", "supplier_selection", "infrastructure_procurement", "venture_screening"}:\n        raise ModelEditError("template-specific engine branch")'),
    Mutation('MODELS ignore quantity-check binding', 'src/mcda_studio/services/model_checks_service.py', '        or checks.digest != checks_digest(checks)', '        or False'),
    Mutation('MODELS add hidden tolerance to exact boundary', 'src/mcda_studio/services/model_checks_service.py', '    return (\n        math.isfinite(value)', '    value = value - 1e-12\n    return (\n        math.isfinite(value)'),
    Mutation('MODELS source bounds depend on unused probability group', 'src/mcda_studio/services/model_checks_service.py', '    if uncertainty and not isinstance(specification.range, SourceRange):', '    if uncertainty:'),
    Mutation('MODELS skip quantity-check preflight', 'src/mcda_studio/services/model_checks_service.py', '    preflight(specification.checks, plan)', '    pass'),
    Mutation('MODELS skip per-draw check', 'src/mcda_studio/services/model_checks_service.py', '            check_values(specification.checks, row, index)', '            pass'),
    Mutation('MODELS compile unreviewed comparison', 'src/mcda_studio/services/model_comparison_service.py', '    checks.accepted(\n        comparison.review,\n        "MODEL_COMPARISON_REVIEW",\n        "review the comparison before choosing a target",\n    )', '    pass'),
    Mutation('MODELS ignore acknowledged selection revision', 'src/mcda_studio/services/model_comparison_service.py', '    if current.stale or current.review_digest != expected_review_digest:\n        raise StaleRevisionError(\n            "Model selection acknowledgement changed; inspect both models again"\n        )', '    if False:\n        raise StaleRevisionError(\n            "Model selection acknowledgement changed; inspect both models again"\n        )'),
    Mutation('MODELS ignore reviewed target scope', 'src/mcda_studio/services/model_comparison_service.py', '    if not known_scope(selection.target_scope) or selection.target_scope != specification.scope:', '    if False:'),
]  # fmt: skip

MODELS_FRONTEND = [
    Mutation('MODELS compile without acknowledgement', 'frontend/src/components/ModelComparisonsPanel.tsx', ' || ack !== key || scopeAck !==', ' || false || scopeAck !=='),
    Mutation('MODELS late review replaces newer context', 'frontend/src/components/ModelComparisonsPanel.tsx', 'const result = await action(); if (captured === liveAction.current)', 'const result = await action(); if (true)'),
]  # fmt: skip


PROXY_BACKEND = [
    Mutation(
        "PROXY treats a supporting assertion as another numeric score",
        "src/mcda_studio/services/proxy_criterion_service.py",
        "            and proposals.measurement(r.effective) is not None",
        "            and True",
    ),
    Mutation(
        "PROXY offsets a failed feasibility check with proxy preference",
        "src/mcda_studio/services/proxy_criterion_service.py",
        '            half.reason = ""',
        '            if index == 1 and half.feasibility is not None:\n                for alternative in half.feasibility.alternatives:\n                    alternative.status = "pass"\n                    alternative.failed = []\n            half.reason = ""',
    ),
    Mutation(
        "PROXY reuses scores after a feature observation date changes",
        "src/mcda_studio/services/proxy_criterion_service.py",
        '                "observations": {f.id: f.observed_at.isoformat() for f in state.features},',
        '                "observations": {},',
    ),
    Mutation(
        "PROXY permits stale feature-factor model links",
        "src/mcda_studio/services/proxy_criterion_service.py",
        "    if inputs.model is not None and inputs.model.project_fingerprint != project.fingerprint():",
        "    if False:",
    ),
    Mutation(
        "PROXY silently activates disabled plan",
        "src/mcda_studio/services/proxy_criterion_service.py",
        "    if not inspection.state.enabled:",
        "    if False:",
    ),
    Mutation(
        "PROXY uses confidence metadata as weight",
        "src/mcda_studio/services/proxy_criterion_service.py",
        "        row = rows[0]",
        "        row = rows[0]\n        if row.original.confidence is not None:\n            for profile in draft.weight_profiles:\n                if state.criterion.id in profile.judgements:\n                    profile.judgements[state.criterion.id] *= row.original.confidence.value",
    ),
    Mutation(
        "PROXY hides failed half in pair status",
        "src/mcda_studio/services/proxy_criterion_service.py",
        '    complete = all(half.status == "completed" for half in halves)',
        '    complete = any(half.status == "completed" for half in halves)',
    ),
    Mutation(
        "PROXY drops original baseline from bundle",
        "src/mcda_studio/services/proxy_criterion_service.py",
        "        without_proxy=halves[0],",
        "        without_proxy=halves[1],",
    ),
    Mutation(
        "PROXY ignores explicit baseline-only overlap",
        "src/mcda_studio/services/proxy_criterion_service.py",
        '        if overlap.resolution == "baseline_only":',
        "        if False:",
    ),
    Mutation(
        "PROXY changes non-proxy shared draws",
        "src/mcda_studio/services/proxy_criterion_service.py",
        "                    half.project, model, uncertainty, inputs.factor_parameters, check_draw=record",
        '                    half.project, model, uncertainty, inputs.factor_parameters.model_copy(update={"seed": inputs.factor_parameters.seed + index}), check_draw=record',
    ),
    Mutation(
        "PROXY substitutes a formula score",
        "src/mcda_studio/services/proxy_criterion_service.py",
        "                expression=id,",
        '                expression=f"{id} * 0.99",',
    ),
    Mutation(
        "PROXY treats explicit zero swing as nonzero default",
        "src/mcda_studio/services/proxy_criterion_service.py",
        "            profile.judgements[leaf.id] = rating",
        "            profile.judgements[leaf.id] = rating or 1.0",
    ),
    Mutation(
        "PROXY permits unacknowledged unknown card facts",
        "src/mcda_studio/services/proxy_criterion_service.py",
        "        and (acks.unknown_facts or not inspection.unknown_facts)",
        "        and True",
    ),
    Mutation(
        "PROXY ignores the preview revision",
        "src/mcda_studio/services/proxy_criterion_service.py",
        "    if inspection.review_digest != request.expected_review_digest:",
        "    if False:",
    ),
    Mutation(
        "PROXY bypasses licence restrictions",
        "src/mcda_studio/services/proxy_criterion_service.py",
        '    if (\n        not state.licence_compatible\n        or not _accepted(state.licence_review)\n        or state.card_facts.get("licence") is None\n        or state.card_facts["licence"].unknown\n        or state.card_facts.get("use_restrictions") is None\n        or state.card_facts["use_restrictions"].unknown\n    ):\n        issues.append(\n            _problem(\n                "PROXY_LICENCE",\n                "Known licence and use restrictions must be explicitly reviewed as compatible",\n            )\n        )\n',
        '    if False:\n        issues.append(_problem("PROXY_LICENCE", "Licence is unresolved"))\n',
    ),
]

# BENCHMARK: the standalone classifier agreement benchmark, against its independent oracles.
BENCHMARK_BACKEND = [
    Mutation(
        "BENCHMARK bypasses the human agreement gate",
        "scripts/classifier_agreement_benchmark.py",
        'passed = gate_passes(point["kappa"], interval["interval"], coverage)',
        "passed = True",
    ),
    Mutation(
        "BENCHMARK scores training items as held-out test items",
        "scripts/classifier_agreement_benchmark.py",
        'id for id, item in items.items() if item["split"] == "test" and item["eligible"]',
        'id for id, item in items.items() if item["split"] in ("test", "train") and item["eligible"]',
    ),
    Mutation(
        "BENCHMARK chooses the majority baseline from test labels",
        "scripts/classifier_agreement_benchmark.py",
        'if item["split"] == "train" and item["eligible"] and id in references',
        'if item["split"] == "test" and item["eligible"] and id in references',
    ),
    Mutation(
        "BENCHMARK omits abstentions from recall",
        "scripts/classifier_agreement_benchmark.py",
        "support = sum(matrix[label].values())",
        'support = sum(v for k, v in matrix[label].items() if k != "__abstention__")',
    ),
    Mutation(
        "BENCHMARK replaces an undefined replicate with zero",
        "scripts/classifier_agreement_benchmark.py",
        "            if value is None:\n                undefined.append(index)",
        "            if value is None:\n                values.append(Fraction(0))",
    ),
    Mutation(
        "BENCHMARK resamples reviewer labels independently of their panels",
        "scripts/classifier_agreement_benchmark.py",
        "            row = matrix[selection].sum(axis=0)",
        "            row = np.concatenate([matrix[selection].sum(axis=0)[:2], matrix[rng.integers(0, len(units), size=len(units))].sum(axis=0)[2:]])",
    ),
    Mutation(
        "BENCHMARK discards undefined replicates and still reports an interval",
        "scripts/classifier_agreement_benchmark.py",
        "    interval = None\n    if not undefined:",
        "    interval = None\n    if True:",
    ),
    Mutation(
        "BENCHMARK weights calibration frequencies by reported confidence",
        "scripts/classifier_agreement_benchmark.py",
        "Fraction(sum(event for _, event in selected), n) if n else None",
        "sum((p * event for p, event in selected), Fraction()) / n if n else None",
    ),
    Mutation(
        "BENCHMARK omits an input digest from the sealed report",
        "scripts/classifier_agreement_benchmark.py",
        "        hashes[key] = sha(content)",
        '        if key != "adjudications":\n            hashes[key] = sha(content)',
    ),
]

PROXY_FRONTEND = [
    Mutation(
        "PROXY hides failed feasibility beside a preferred rank",
        "frontend/src/components/ProxyCriterionPanel.tsx",
        "<StatusBadge result={half.feasibility} alternativeId={row.alternative_id}/>",
        "<span>passes</span>",
    ),
    Mutation(
        "PROXY runs without complete UI acknowledgements",
        "frontend/src/components/ProxyCriterionPanel.tsx",
        '["card", "overlap", "weight_changes", ...(preview.unknown_facts.length ? ["unknown_facts"] : [])].every(a => acks.includes(candidateKey + a))',
        "true",
    ),
    Mutation(
        "PROXY publishes a late paired result",
        "frontend/src/components/ProxyCriterionPanel.tsx",
        "if (captured === live.current) { setPair({ key: captured, result });",
        "if (true) { setPair({ key: live.current, result });",
    ),
]


def run_benchmark(work: Path) -> bool:
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/unit/test_classifier_agreement_benchmark.py",
    ]
    result = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True)
    if result.returncode:
        # A fixture refused by the script's own BenchmarkError guard (for example a changed gate
        # digest invalidating the bound adjudications) counts; any other crash does not.
        failures = [
            line
            for line in result.stdout.splitlines()
            if line.startswith("FAILED ")
            or (line.startswith("ERROR ") and "BenchmarkError" in result.stdout)
        ]
        if not failures:
            raise RuntimeError(
                "Benchmark mutant did not reach a test assertion:\n" + result.stdout + result.stderr
            )
        print("\n".join(failures), flush=True)
    return result.returncode == 0


def run_proxy(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/regression/test_proxy_reference.py",
        "tests/test_proxy_criterion.py",
        "tests/test_proxy_api_cli.py",
    ]
    result = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True)
    if result.returncode:
        failures = [line for line in result.stdout.splitlines() if line.startswith("FAILED ")]
        if not failures:
            raise RuntimeError(
                "Proxy mutant did not reach a test assertion:\n" + result.stdout + result.stderr
            )
        print("\n".join(failures), flush=True)
    return result.returncode == 0


def run_models(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/unit/test_model_comparisons.py",
        "tests/unit/test_rounding_oracle.py",
        "tests/unit/test_starter_templates.py",
        "tests/properties/test_model_properties.py",
        "tests/regression/test_market_models_reference.py",
        "tests/api/test_api_model_comparisons.py",
    ]
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_proposals(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/unit/test_external_proposals.py",
        "tests/properties/test_proposal_properties.py",
        "tests/regression/test_external_proposals_reference.py",
        "tests/api/test_api_proposals.py",
    ]
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_uncertainty(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "tests/regression/test_factor_uncertainty_reference.py", "tests/regression/test_factor_analysis_reference.py", "tests/api/test_api_factor_uncertainty.py"]  # fmt: skip
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_calculation(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "tests/unit/test_calculation_workspace.py", "tests/regression/test_calculation_workspace_reference.py",
           "tests/api/test_api_calculations.py", "tests/api/test_api_decisions.py"]  # fmt: skip
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


EVIDENCE_COMPILATION_BACKEND = [
    # The initial bundle-digest guard is redundant with full reconstruction (as for calculation
    # bundles), so removing it alone is an equivalent acceptance mutation and is not listed.
    Mutation("EVIDENCE compilation ignores the acknowledged review history", "src/mcda_studio/services/evidence_compilation_service.py",
             'if workspace.digest != workspace_digest:', 'if False:'),
    Mutation("EVIDENCE compilation bypasses the reviewed preview digest", "src/mcda_studio/services/evidence_compilation_service.py",
             'compiled = evidence.compile_copy(project, dossier, review_digest)',
             'compiled = evidence.compile_copy(project, dossier, evidence.preview(project, dossier).review_digest)'),
    Mutation("EVIDENCE bundle skips independent reconstruction", "src/mcda_studio/services/evidence_compilation_service.py",
             'if expected != bundle:', 'if False:'),
    Mutation("EVIDENCE bundle reconstructs from its compiled copy", "src/mcda_studio/services/evidence_compilation_service.py",
             '            bundle.workspace.source_project,\n', '            bundle.project,\n'),
    Mutation("PROVENANCE receipt ignores the copy's own fingerprint", "src/mcda_studio/services/provenance_service.py",
             'if copy.id != receipt.copy_project_id or copy.fingerprint() != receipt.copy_fingerprint:',
             'if copy.id != receipt.copy_project_id:'),
    Mutation("PROVENANCE receipt ignores its recorded copy ID", "src/mcda_studio/services/provenance_service.py",
             'if copy.id != receipt.copy_project_id or copy.fingerprint()', 'if copy.fingerprint()'),
    Mutation("PROVENANCE receipt accepts more than an ID change", "src/mcda_studio/services/provenance_service.py",
             'if _with_id(copy, receipt.original_project_id).fingerprint() != receipt.original_fingerprint:', 'if False:'),
    Mutation("PROVENANCE receipt binds a different artifact", "src/mcda_studio/services/provenance_service.py",
             'if receipt.original_fingerprint != artifact.compiled_fingerprint:', 'if False:'),
    Mutation("PROVENANCE treats a look-alike copy as compiled", "src/mcda_studio/services/provenance_service.py",
             'elif current == artifact.compiled_fingerprint:',
             'elif current == artifact.compiled_fingerprint or project.performances == artifact.project.performances:'),
    Mutation("PROVENANCE binding skips artifact verification", "src/mcda_studio/services/provenance_service.py",
             'evidence_compilation.verify(artifact)', 'evidence_compilation.bundle_digest(artifact)'),
    Mutation("PROVENANCE import drops the copy receipt", "src/mcda_studio/api/app.py",
             'receipt = provenance.copy_receipt(original, project)', 'receipt = None'),
]  # fmt: skip

FRONTEND += [
    Mutation(
        "EVIDENCE exports a compilation from an earlier context",
        "frontend/src/components/EvidenceCompilationPanel.tsx",
        "const bundle = compiled?.key === key ? compiled.bundle : null;",
        "const bundle = compiled?.bundle ?? null;",
    ),
    Mutation(
        "EVIDENCE compiles before explicit acknowledgement",
        "frontend/src/components/EvidenceCompilationPanel.tsx",
        "disabled={acknowledged !== key || compiling}",
        "disabled={compiling}",
    ),
    Mutation(
        "EVIDENCE trusts a compilation of another history",
        "frontend/src/components/EvidenceCompilationPanel.tsx",
        " || result.workspace.digest !== inspection.workspace.digest",
        "",
    ),
    Mutation(
        "PROVENANCE shows a binding for another project revision",
        "frontend/src/components/ArtifactBindingStatus.tsx",
        "if (result.current_fingerprint !== fingerprint) throw",
        "if (result.current_fingerprint === null) throw",
    ),
    Mutation(
        "EVIDENCE opens a bundle without Python verification",
        "frontend/src/components/EvidenceWorkspacePanel.tsx",
        "? await api.inspectEvidenceCompilation(project, document, signal)",
        "? { inspection: await api.inspectEvidence(project, document, signal), compilation: document as EvidenceCompilation }",
    ),
]


D = "src/mcda_studio/services/decision_record_service.py"
DECISION_BACKEND = [
    # The relationship guard inside anchoring is defensive: a matched fingerprint always binds as
    # compiled or verified_copy, so removing it is equivalent and is not listed.
    Mutation("DECISION drops unavailable analyses", D,
             'analyses = [_analysis(project, c) for c in details.configurations]',
             'analyses = [a for a in (_analysis(project, c) for c in details.configurations) if a.status == "completed"]'),
    Mutation("DECISION trace ignores evidence changes", D,
             '                if change is not None:', '                if False:'),
    Mutation("DECISION trace loses calculation inputs", D,
             'entry.inputs = list(calculation.source_ids)', 'entry.inputs = []'),
    Mutation("DECISION revision skips the predecessor digest", D,
             '    if isinstance(previous, DecisionRecordV2):\n        if previous.digest != digest(previous):',
             '    if isinstance(previous, DecisionRecordV2):\n        if False:'),
    Mutation("DECISION allows a predecessor from another project", D,
             'if previous is not None and previous.project.id != project.id:', 'if False:'),
    Mutation("DECISION verify skips reconstruction", D,
             'if expected != (record.anchors, record.measurement_trace, record.feasibility, record.notices):',
             'if False:'),
    Mutation("DECISION verify skips analysis digests", D,
             'if not _analysis_digest_ok(sealed):', 'if False:'),
    Mutation("DECISION reopening skips reference validation", D,
             '_refuse(_reference_issues(project, record.decision) + _analysis_issues(record))',
             '_refuse(_analysis_issues(record))'),
    Mutation("DECISION accepts an unknown selection", D,
             'if chosen is not None and chosen not in ids:', 'if False:'),
    Mutation("DECISION accepts a completed snapshot without a record", D,
             'if snapshot.status == "completed" and sealed is None:', 'if False:'),
    Mutation("DECISION accepts an unavailable snapshot with a record", D,
             'if snapshot.status == "unavailable" and (sealed is not None or not snapshot.reason):',
             'if snapshot.status == "unavailable" and not snapshot.reason:'),
    Mutation("DECISION accepts a sealed analysis of another configuration", D,
             'or sealed.result.configuration != configuration\n            or envelope != configuration',
             'or False'),
    Mutation("DECISION revises from an unverified predecessor", D,
             '        verify(previous)\n', ''),
    Mutation("DECISION hides failed requirements beside the choice", D,
             '        if status.failed:', '        if False:'),
    Mutation("DECISION accepts a mismatched predecessor summary", D,
             'isinstance(record, DecisionRecordV2) and record.predecessor != summary', 'False'),
    Mutation("DECISION accepts an unknown considered alternative", D,
             '        if a not in ids\n', '        if False\n'),
    Mutation("DECISION cites one artifact twice", D,
             'if len(set(digests)) != len(digests):', 'if False:'),
]  # fmt: skip

FRONTEND += [
    Mutation(
        "DECISION exports a preview from an earlier context",
        "frontend/src/components/DecisionRecordPanel.tsx",
        "const record = candidate?.key === key ? candidate.record : null;",
        "const record = candidate?.record ?? null;",
    ),
    Mutation(
        "DECISION trusts a record for another project revision",
        "frontend/src/components/DecisionRecordPanel.tsx",
        "if (result.project_fingerprint !== fingerprint || result.previous_digest",
        "if (result.previous_digest",
    ),
    Mutation(
        "DECISION loses the unexported record guard",
        "frontend/src/components/DecisionRecordPanel.tsx",
        "const dirty = record !== null && exportedKey !== key;",
        "const dirty = false;",
    ),
]


def run_decision(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "tests/unit/test_decision_record_v2.py", "tests/unit/test_decision_record.py",
           "tests/api/test_api_decisions.py"]  # fmt: skip
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_evidence_compilation(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "tests/unit/test_evidence_compilation.py", "tests/unit/test_provenance.py",
           "tests/api/test_api_evidence_compilation.py"]  # fmt: skip
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_evidence_workspace(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "tests/unit/test_evidence.py", "tests/unit/test_evidence_workspace.py",
           "tests/api/test_api_evidence.py", "tests/unit/test_questions.py", "tests/api/test_api_questions.py"]  # fmt: skip
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


DERIVED_BACKEND = [
    # Removing the initial digest check is redundant: complete reconstruction also compares the
    # digest. Do not count that equivalent acceptance behaviour as a killed integrity defect.
    Mutation("DERIVED bundle loses its original project snapshot", "src/mcda_studio/services/derived_service.py",
             'source_project=project.model_copy(deep=True),', 'source_project=compiled.model_copy(deep=True),'),
    Mutation("DERIVED bundle skips independent reconstruction", "src/mcda_studio/services/derived_service.py",
             'if expected != document:', 'if False:'),
    Mutation("DERIVED bundle bypasses compilation digest", "src/mcda_studio/services/derived_service.py",
             'compiled = compile_copy(project, model, review_digest)', 'compiled = compile_copy(project, model, preview(project, model).review_digest)'),
    Mutation("DERIVED bypasses source acceptance", "src/mcda_studio/services/derived_service.py",
             'if review is None or review.status == "rejected":', 'if False:'),
    Mutation("DERIVED bypasses formula acceptance", "src/mcda_studio/services/derived_service.py",
             'if not accepted and name not in assume_accepted:', 'if False:'),
    Mutation("DERIVED ignores output dimensions", "src/mcda_studio/services/derived_service.py",
             'if result.dimension != dimension(formula.unit):', 'if False:'),
    Mutation("DERIVED adds incompatible dimensions", "src/mcda_studio/methods/formulas.py",
             'if a.dimension != b.dimension:', 'if False:'),
    Mutation("DERIVED drops cycle detection", "src/mcda_studio/services/derived_service.py",
             'if name in active:', 'if False:'),
    Mutation("DERIVED loses upstream factor identities", "src/mcda_studio/services/derived_service.py",
             'upstream[name].update(upstream[key])', 'upstream[name].add(key)'),
    Mutation("DERIVED divides by multiplication", "src/mcda_studio/methods/formulas.py",
             'value = a.value / b.value if isinstance(node.op, ast.Div) else a.value * b.value',
             'value = a.value * b.value'),
]  # fmt: skip


def run_derived(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "tests/unit/test_derived.py", "tests/regression/test_derived_reference.py",
           "tests/api/test_api_derived.py", "tests/unit/test_derived_compilation.py"]  # fmt: skip
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_measurement_range(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "tests/unit/test_measurement_range.py", "tests/unit/test_questions.py",
           "tests/regression/test_measurement_range_oracle.py", "tests/api/test_api_questions.py"]  # fmt: skip
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_feasibility(work: Path) -> bool:
    """The feasibility check's rules live in its unit, reference, API and schema suites."""
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "tests/unit/test_feasibility.py", "tests/regression/test_feasibility_reference.py",
           "tests/api/test_api_feasibility.py", "tests/unit/test_schema_versions.py"]  # fmt: skip
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_comparison(work: Path) -> bool:
    """The comparison's rules live in its unit, reference and API suites."""
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "tests/unit/test_method_comparison.py", "tests/regression/test_comparison_reference.py",
           "tests/api/test_api_methods_compare.py"]  # fmt: skip
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_ahp(work: Path) -> bool:
    """AHP's rules live in its unit, reference, API and schema suites."""
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
           "tests/unit/test_ahp.py", "tests/regression/test_ahp_reference.py",
           "tests/api/test_api_ahp.py", "tests/unit/test_schema_versions.py"]  # fmt: skip
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_promethee(work: Path) -> bool:
    """PROMETHEE II's rules live in its unit, reference, API and schema suites."""
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/unit/test_promethee.py",
        "tests/regression/test_promethee_reference.py",
        "tests/api/test_api_promethee.py",
        "tests/unit/test_schema_versions.py",
    ]
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_smaa(work: Path) -> bool:
    """SMAA-2's rules live in its unit, reference, API and schema suites."""
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/unit/test_smaa.py",
        "tests/regression/test_smaa_reference.py",
        "tests/api/test_api_smaa.py",
        "tests/unit/test_schema_versions.py",
    ]
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_sorting(work: Path) -> bool:
    """Value-based sorting's rules live in its unit, schema, property, regression and API suites."""
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/unit/test_sorting.py",
        "tests/unit/test_sorting_sensitivity.py",
        "tests/unit/test_schema_versions.py",
        "tests/properties/test_sorting_properties.py",
        "tests/regression/test_supplier_qualification.py",
        "tests/api/test_api_sorting.py",
        "tests/api/test_api_analysis_exports.py",
    ]
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_results(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    return (
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "-x",
                "-p",
                "no:cacheprovider",
                "tests/unit/test_analysis_records.py",
                "tests/api/test_api_analysis_exports.py",
                "tests/regression",
            ],
            cwd=work,
            env=env,
            capture_output=True,
            text=True,
        ).returncode
        == 0
    )


def copy_repo(dest: Path, with_frontend: bool) -> None:
    ignore = shutil.ignore_patterns(
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".hypothesis",
        ".mypy_cache",
        ".ruff_cache",
        "dist",
        "test-results",
        ".e2e-store",
        "e2e",
    )
    for item in ("src", "tests", "docs", "examples", "scripts", "pyproject.toml"):
        src = ROOT / item
        (shutil.copytree if src.is_dir() else shutil.copy2)(
            src, dest / item, **({"ignore": ignore} if src.is_dir() else {})
        )
    if with_frontend:
        shutil.copytree(ROOT / "frontend", dest / "frontend", ignore=ignore)
        (dest / "frontend" / "node_modules").symlink_to(ROOT / "frontend" / "node_modules")


def run_backend(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/api",
        "tests/unit/test_project_store.py",
        "tests/unit/test_recovery.py",
        "tests/unit/test_project_service.py",
    ]
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_weights(work: Path) -> bool:
    """The B3 rules live in the weighting, profile, property and regression suites."""
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/api",
        "tests/regression",
        "tests/properties/test_weight_profile_properties.py",
        "tests/unit/test_weighting.py",
        "tests/unit/test_weight_profiles.py",
        "tests/unit/test_swing_ranges.py",
    ]
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_sensitivity(work: Path) -> bool:
    """The B4 rules live in the sensitivity, probe, regression and API suites."""
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/api",
        "tests/regression",
        "tests/unit/test_sensitivity.py",
        "tests/unit/test_sensitivity_probe.py",
    ]
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_backup(work: Path) -> bool:
    """The library backup rules live in their unit suite."""
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/unit/test_library_backup.py",
    ]
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_seam(work: Path) -> bool:
    """The method seam's rules live in its API suite, with a test-only fake method."""
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/api/test_api_method_seam.py",
    ]
    return subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True).returncode == 0


def run_frontend(work: Path) -> bool:
    cmd = ["npx", "vitest", "run", "--reporter=dot", "--bail=1"]
    return (
        subprocess.run(cmd, cwd=work / "frontend", capture_output=True, text=True).returncode == 0
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend-only", action="store_true")
    ap.add_argument("--frontend-only", action="store_true")
    ap.add_argument("--scenario-only", action="store_true")
    ap.add_argument("--results-only", action="store_true")
    ap.add_argument("--backup-only", action="store_true")
    ap.add_argument("--seam-only", action="store_true")
    ap.add_argument("--sorting-only", action="store_true")
    ap.add_argument("--smaa-only", action="store_true")
    ap.add_argument("--promethee-only", action="store_true")
    ap.add_argument("--ahp-only", action="store_true")
    ap.add_argument("--comparison-only", action="store_true")
    ap.add_argument("--feasibility-only", action="store_true")
    ap.add_argument("--measurement-range-only", action="store_true")
    ap.add_argument("--derived-only", action="store_true")
    ap.add_argument("--evidence-workspace-only", action="store_true")
    ap.add_argument("--decision-only", action="store_true")
    ap.add_argument("--calculation-only", action="store_true")
    ap.add_argument("--uncertainty-only", action="store_true")
    ap.add_argument("--proposals-only", action="store_true")
    ap.add_argument("--models-only", action="store_true")
    ap.add_argument("--proxy-only", action="store_true")
    ap.add_argument("--benchmark-only", action="store_true")
    args = ap.parse_args()
    todo = (
        ([] if args.frontend_only else [(m, run_backend) for m in BACKEND])
        + ([] if args.frontend_only else [(m, run_weights) for m in B3_BACKEND])
        + ([] if args.frontend_only else [(m, run_sensitivity) for m in B4_BACKEND])
        + ([] if args.frontend_only else [(m, run_scenarios) for m in B5_BACKEND])
        + ([] if args.frontend_only else [(m, run_results) for m in B6_BACKEND])
        + ([] if args.frontend_only else [(m, run_backup) for m in BACKUP_BACKEND])
        + ([] if args.frontend_only else [(m, run_seam) for m in SEAM_BACKEND])
        + ([] if args.frontend_only else [(m, run_sorting) for m in SORTING_BACKEND])
        + ([] if args.frontend_only else [(m, run_smaa) for m in SMAA_BACKEND])
        + ([] if args.frontend_only else [(m, run_promethee) for m in PROMETHEE_BACKEND])
        + ([] if args.frontend_only else [(m, run_ahp) for m in AHP_BACKEND])
        + ([] if args.frontend_only else [(m, run_comparison) for m in COMPARISON_BACKEND])
        + ([] if args.frontend_only else [(m, run_feasibility) for m in FEASIBILITY_BACKEND])
        + (
            []
            if args.frontend_only
            else [(m, run_measurement_range) for m in MEASUREMENT_RANGE_BACKEND]
        )
        + ([] if args.frontend_only else [(m, run_derived) for m in DERIVED_BACKEND])
        + (
            []
            if args.frontend_only
            else [(m, run_evidence_workspace) for m in EVIDENCE_WORKSPACE_BACKEND]
        )
        + (
            []
            if args.frontend_only
            else [(m, run_evidence_compilation) for m in EVIDENCE_COMPILATION_BACKEND]
        )
        + ([] if args.frontend_only else [(m, run_decision) for m in DECISION_BACKEND])
        + ([] if args.frontend_only else [(m, run_calculation) for m in CALCULATION_BACKEND])
        + ([] if args.frontend_only else [(m, run_uncertainty) for m in UNCERTAINTY_BACKEND])
        + ([] if args.frontend_only else [(m, run_proposals) for m in PROPOSALS_BACKEND])
        + ([] if args.frontend_only else [(m, run_models) for m in MODELS_BACKEND])
        + ([] if args.frontend_only else [(m, run_proxy) for m in PROXY_BACKEND])
        + ([] if args.frontend_only else [(m, run_benchmark) for m in BENCHMARK_BACKEND])
        + (
            []
            if args.backend_only
            else [
                (m, run_frontend)
                for m in FRONTEND
                + B3_FRONTEND
                + B4_FRONTEND
                + B5_FRONTEND
                + B6_FRONTEND
                + RETRY_FRONTEND
                + COVERAGE_FRONTEND
                + SORTING_FRONTEND
                + SMAA_FRONTEND
                + PROMETHEE_FRONTEND
                + AHP_FRONTEND
                + COMPARISON_FRONTEND
                + FEASIBILITY_FRONTEND
                + PROPOSALS_FRONTEND
                + MODELS_FRONTEND
                + PROXY_FRONTEND
            ]
        )
    )
    if args.scenario_only:
        todo = [(m, r) for m, r in todo if m in B5_BACKEND + B5_FRONTEND]
    if args.results_only:
        todo = [(m, r) for m, r in todo if m in B6_BACKEND + B6_FRONTEND]
    if args.backup_only:
        todo = [(m, r) for m, r in todo if m in BACKUP_BACKEND]
    if args.seam_only:
        todo = [(m, r) for m, r in todo if m in SEAM_BACKEND]
    if args.sorting_only:
        todo = [(m, r) for m, r in todo if m in SORTING_BACKEND + SORTING_FRONTEND]
    if args.smaa_only:
        todo = [(m, r) for m, r in todo if m in SMAA_BACKEND + SMAA_FRONTEND]
    if args.comparison_only:
        todo = [(m, r) for m, r in todo if m in COMPARISON_BACKEND + COMPARISON_FRONTEND]
    if args.feasibility_only:
        todo = [(m, r) for m, r in todo if m in FEASIBILITY_BACKEND + FEASIBILITY_FRONTEND]
    if args.measurement_range_only:
        todo = [(m, r) for m, r in todo if m in MEASUREMENT_RANGE_BACKEND]
    if args.derived_only:
        todo = [(m, r) for m, r in todo if m in DERIVED_BACKEND or m.name.startswith("DERIVED")]
    if args.evidence_workspace_only:
        todo = [
            (m, r)
            for m, r in todo
            if m in EVIDENCE_WORKSPACE_BACKEND + EVIDENCE_COMPILATION_BACKEND
            or m.name.startswith(("EVIDENCE", "PROVENANCE"))
        ]
    if args.decision_only:
        todo = [(m, r) for m, r in todo if m.name.startswith("DECISION")]
    if args.calculation_only:
        todo = [(m, r) for m, r in todo if m.name.startswith(("CALCULATION", "DERIVED"))]
    if args.proposals_only:
        todo = [(m, r) for m, r in todo if m in PROPOSALS_BACKEND + PROPOSALS_FRONTEND]
    if args.proxy_only:
        todo = [(m, r) for m, r in todo if m in PROXY_BACKEND + PROXY_FRONTEND]
    if args.benchmark_only:
        todo = [(m, r) for m, r in todo if m in BENCHMARK_BACKEND]
    if args.models_only:
        todo = [(m, r) for m, r in todo if m in MODELS_BACKEND + MODELS_FRONTEND]
    if args.uncertainty_only:
        todo = [(m, r) for m, r in todo if m in UNCERTAINTY_BACKEND]
    if args.ahp_only:
        todo = [(m, r) for m, r in todo if m in AHP_BACKEND + AHP_FRONTEND]
    if args.promethee_only:
        todo = [(m, r) for m, r in todo if m in PROMETHEE_BACKEND + PROMETHEE_FRONTEND]
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "repo"
        work.mkdir()
        copy_repo(work, with_frontend=not args.backend_only)
        survivors = 0
        for m, runner in todo:
            target = work / m.file
            original = target.read_text(encoding="utf-8")
            if original.count(m.old) != 1:
                print(f"INVALID  {m.name}: the text to mutate occurs {original.count(m.old)} times")
                survivors += 1
                continue
            target.write_text(original.replace(m.old, m.new), encoding="utf-8")
            try:
                passed = runner(work)
            finally:
                target.write_text(original, encoding="utf-8")
            print(f"{'SURVIVED' if passed else 'killed  '}  {m.name}", flush=True)
            survivors += passed
        # the unmutated copy must pass, or "killed" proves nothing
        base_ok = all(
            r(work)
            for r in {
                run_backend if not args.frontend_only else None,
                run_weights if not args.frontend_only else None,
                run_sensitivity if not args.frontend_only else None,
                run_scenarios if not args.frontend_only else None,
                run_results if not args.frontend_only else None,
                run_backup if not args.frontend_only else None,
                run_seam if not args.frontend_only else None,
                run_sorting if not args.frontend_only else None,
                run_smaa if not args.frontend_only else None,
                run_promethee if not args.frontend_only else None,
                run_ahp if not args.frontend_only else None,
                run_comparison if not args.frontend_only else None,
                run_feasibility if not args.frontend_only else None,
                run_measurement_range if not args.frontend_only else None,
                run_derived if not args.frontend_only else None,
                run_evidence_workspace if not args.frontend_only else None,
                run_evidence_compilation if not args.frontend_only else None,
                run_decision if not args.frontend_only else None,
                run_calculation if not args.frontend_only else None,
                run_uncertainty if not args.frontend_only else None,
                run_proposals if not args.frontend_only else None,
                run_models if not args.frontend_only else None,
                run_proxy if not args.frontend_only else None,
                run_benchmark if not args.frontend_only else None,
                run_frontend if not args.backend_only else None,
            }
            - {None}
        )
        print(f"baseline of the unmutated copy: {'passes' if base_ok else 'FAILS'}")
        print(f"{len(todo) - survivors} of {len(todo)} killed")
        return 0 if survivors == 0 and base_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
