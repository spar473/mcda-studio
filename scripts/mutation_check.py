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
                                      --models-only | --proxy-only | --benchmark-only |
                                      --study-only | --exemplars-only | --summary-only |
                                      --cleanup-only | --gallery-only | --showcase-only |
                                      --reference_cases-only]

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
        '{formatValue(alt.overall_value, "4")} · rank {alt.rank}</text>\n      </g>;\n    })}\n  </Frame>;\n}\n\n/** The existing',
        '{formatValue(alt.overall_value * (view.hidden_criterion_ids.length ? .5 : 1), "4")} · rank {alt.rank}</text>\n      </g>;\n    })}\n  </Frame>;\n}\n\n/** The existing',
    ),
    Mutation(
        "V10 SVG provenance conceals hidden criterion series",
        "frontend/src/components/results/ExportCharts.tsx",
        'view.hidden_criterion_ids.join(", ") || "none"',
        '"none"',
    ),
    Mutation(
        "V11 late export completion bypasses cancellation/context/operation checks",
        "frontend/src/components/ResultsPanel.tsx",
        "if (controller.signal.aborted || !downloadGuard.permits(ticket) || liveRecord.current !== token || exportController.current !== controller) return;",
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
        "upper = 1.0 - portable.power(alpha / 2, 1.0 / n)",
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


STUDY_BACKEND = [
    Mutation("STUDY the stage requirement silently widened to admit later stages",
             "examples/nz_venture_screening/project.json",
             '"allowed": [\n        "Pre-seed",\n        "Seed",\n        "Series A"\n      ]',
             '"allowed": [\n        "Pre-seed",\n        "Seed",\n        "Series A",\n        "Series B or later"\n      ]'),
    Mutation("STUDY the zero-weight mandate branch given weight", "examples/nz_venture_screening/build.py",
             '"mandate": (0, 0),', '"mandate": (10, 0),'),
    Mutation("STUDY a judgement claim recorded as observed", "examples/nz_venture_screening/build.py",
             'description=f"{kind.capitalize()}: {note} {dated} {RETRIEVED}"',
             'description=f"Observed: {note} {dated} {RETRIEVED}"'),
    Mutation("STUDY a market cell entered as the mean, not the median", "examples/nz_venture_screening/build.py",
             "statistics.median(sizes),", "statistics.mean(sizes),"),
]  # fmt: skip


#: The method exemplars (docs/design/method-exemplars.md). Each mutant edits a study's build.py;
#: the runner rebuilds the study, so only the pinned headline facts and the oracles can kill it.
EXEMPLAR_STUDIES = (
    "clinic_site_selection",
    "flood_defence_options",
    "engineering_trade_study",
)
EXEMPLARS_BACKEND = [
    Mutation("EXEMPLARS clinic: one site judgement's row and column swapped",
             "examples/clinic_site_selection/build.py",
             "[(T, S, 2.0), (T, H, 3.0), (T, E, 7.0), (S, H, 2.0), (S, E, 5.0), (H, E, 3.0)],",
             "[(S, T, 2.0), (T, H, 3.0), (T, E, 7.0), (S, H, 2.0), (S, E, 5.0), (H, E, 3.0)],"),
    Mutation("EXEMPLARS clinic: the inconsistent matrix made consistent",
             "examples/clinic_site_selection/build.py",
             "(S, E, 2.0), (H, E, 5.0)],", "(S, E, 6.0), (H, E, 3.0)],"),
    Mutation("EXEMPLARS clinic: the Cost-led profile's access rating changed",
             "examples/clinic_site_selection/build.py",
             '"access": 55.0,', '"access": 95.0,'),
    Mutation("EXEMPLARS clinic: an ordinal label's value moved",
             "examples/clinic_site_selection/build.py",
             '"medium": 0.6,', '"medium": 0.9,'),
    Mutation("EXEMPLARS clinic: a measurement changed",
             "examples/clinic_site_selection/build.py",
             '"bus_service": 8.0,', '"bus_service": 3.0,'),
    Mutation("EXEMPLARS clinic: a group judgement's row and column swapped",
             "examples/clinic_site_selection/build.py",
             '("access", "cost", 2.0)', '("cost", "access", 2.0)'),
    Mutation("EXEMPLARS clinic: the saved method changed",
             "examples/clinic_site_selection/build.py",
             'return ps.set_analysis_method(p, "ahp")', 'return ps.set_analysis_method(p, "mavt")'),
    Mutation("EXEMPLARS clinic: a unit changed",
             "examples/clinic_site_selection/build.py",
             'unit="min"', 'unit="h"'),
    Mutation("EXEMPLARS clinic: a label of the last-placed site changed",
             "examples/clinic_site_selection/build.py",
             '"expansion": "ample",', '"expansion": "limited",'),
    Mutation("EXEMPLARS flood: the protection limit made exclusive",
             "examples/flood_defence_options/build.py",
             "minimum_inclusive=True,", "minimum_inclusive=False,"),
    Mutation("EXEMPLARS flood: the protection limit's value moved",
             "examples/flood_defence_options/build.py",
             "minimum=100.0,", "minimum=120.0,"),
    Mutation("EXEMPLARS flood: the consent set widened to every label",
             "examples/flood_defence_options/build.py",
             'allowed=["routine", "notified", "contested"],',
             'allowed=["routine", "notified", "contested", "not consentable"],'),
    Mutation("EXEMPLARS flood: a cost leaf's PROMETHEE II direction flipped",
             "examples/flood_defence_options/build.py",
             'criterion_id="capital_cost",\n                direction="minimise",',
             'criterion_id="capital_cost",\n                direction="maximise",'),
    Mutation("EXEMPLARS flood: a V-shape threshold changed",
             "examples/flood_defence_options/build.py",
             "function=VShapeFunction(p=20.0),", "function=VShapeFunction(p=45.0),"),
    Mutation("EXEMPLARS flood: the threshold one pair hits exactly moved",
             "examples/flood_defence_options/build.py",
             "function=UShapeFunction(q=0.4),", "function=UShapeFunction(q=0.3),"),
    Mutation("EXEMPLARS flood: a measurement changed",
             "examples/flood_defence_options/build.py",
             '"habitat": 3.2,', '"habitat": 1.2,'),
    Mutation("EXEMPLARS flood: the Cost-conscious profile's protection rating changed",
             "examples/flood_defence_options/build.py",
             '"protection": 60.0,', '"protection": 95.0,'),
    Mutation("EXEMPLARS flood: a unit changed",
             "examples/flood_defence_options/build.py",
             'unit="ha",', 'unit="m2",'),
    Mutation("EXEMPLARS flood: the saved method changed",
             "examples/flood_defence_options/build.py",
             'return ps.set_analysis_method(p, "mavt")', 'return ps.set_analysis_method(p, "promethee2")'),
    Mutation("EXEMPLARS flood: a label's PROMETHEE II code reversed",
             "examples/flood_defence_options/build.py",
             'coding={"low": 1.0, "medium": 2.0, "high": 3.0},',
             'coding={"low": 3.0, "medium": 2.0, "high": 1.0},'),
    Mutation("EXEMPLARS trade: a class boundary moved",
             "examples/engineering_trade_study/build.py",
             '("Shortlist", 0.65),', '("Shortlist", 0.60),'),
    Mutation("EXEMPLARS trade: the payload limit made exclusive",
             "examples/engineering_trade_study/build.py",
             "minimum_inclusive=True,", "minimum_inclusive=False,"),
    Mutation("EXEMPLARS trade: the payload limit's value moved",
             "examples/engineering_trade_study/build.py",
             "minimum=2.0,", "minimum=4.0,"),
    Mutation("EXEMPLARS trade: the maturity requirement widened to every label",
             "examples/engineering_trade_study/build.py",
             'allowed=["prototype", "proven"],', 'allowed=["concept", "prototype", "proven"],'),
    Mutation("EXEMPLARS trade: a stated test spread widened",
             "examples/engineering_trade_study/build.py",
             'uniform(W, "endurance", 165.0, 195.0),', 'uniform(W, "endurance", 165.0, 235.0),'),
    Mutation("EXEMPLARS trade: a categorical probability swapped",
             "examples/engineering_trade_study/build.py",
             'labels=["prototype", "proven"], probabilities=[0.6, 0.4]',
             'labels=["prototype", "proven"], probabilities=[0.4, 0.6]'),
    Mutation("EXEMPLARS trade: the weight-uncertainty interval narrowed",
             "examples/engineering_trade_study/build.py",
             '"cost": (30.0, 70.0),', '"cost": (45.0, 55.0),'),
    Mutation("EXEMPLARS trade: a concept judgement's row and column swapped",
             "examples/engineering_trade_study/build.py",
             "(T, W, 2.0)", "(W, T, 2.0)"),
    Mutation("EXEMPLARS trade: a criteria judgement's row and column swapped",
             "examples/engineering_trade_study/build.py",
             '("performance", "cost", 2.0)', '("cost", "performance", 2.0)'),
    Mutation("EXEMPLARS trade: a PROMETHEE II direction flipped",
             "examples/engineering_trade_study/build.py",
             'criterion_id="unit_cost",\n                direction="minimise",',
             'criterion_id="unit_cost",\n                direction="maximise",'),
    Mutation("EXEMPLARS trade: a PROMETHEE II label code reversed",
             "examples/engineering_trade_study/build.py",
             'function=UsualFunction(),\n                coding={"low": 1.0, "medium": 2.0, "high": 3.0},',
             'function=UsualFunction(),\n                coding={"low": 3.0, "medium": 2.0, "high": 1.0},'),
    Mutation("EXEMPLARS trade: the scenario's control point changed",
             "examples/engineering_trade_study/build.py",
             "ControlPoint(x=120.0, value=0.5),", "ControlPoint(x=120.0, value=0.3),"),
    Mutation("EXEMPLARS trade: the Cost-led profile's performance rating changed",
             "examples/engineering_trade_study/build.py",
             '"performance": 60.0,', '"performance": 95.0,'),
    Mutation("EXEMPLARS trade: a measurement changed",
             "examples/engineering_trade_study/build.py",
             '"endurance": 180.0,', '"endurance": 120.0,'),
    Mutation("EXEMPLARS trade: a unit changed",
             "examples/engineering_trade_study/build.py",
             'unit="NZD k",', 'unit="NZD m",'),
    Mutation("EXEMPLARS trade: the saved method changed",
             "examples/engineering_trade_study/build.py",
             'return ps.set_analysis_method(p, "mavt")', 'return ps.set_analysis_method(p, "ahp")'),
]  # fmt: skip


SUMMARY_BACKEND = [
    Mutation("SUMMARY contributions sorted with the wrong sign", "src/mcda_studio/services/screening_summary_service.py",
             "positive.sort(key=lambda item: (-item[0], order[item[1]]))",
             "positive.sort(key=lambda item: (item[0], order[item[1]]))"),
    Mutation("SUMMARY fragility keeps the largest change, not the smallest", "src/mcda_studio/services/screening_summary_service.py",
             "or (candidate.weight_change < current.weight_change - TIE_TOL)",
             "or (candidate.weight_change > current.weight_change - TIE_TOL)"),
    Mutation("SUMMARY ties ignored", "src/mcda_studio/services/screening_summary_service.py", "        if tied:", "        if False:"),
    Mutation("SUMMARY the selected profile ignored", "src/mcda_studio/services/screening_summary_service.py",
             'mavt = requested.model_copy(update={"method": "mavt", "parameters": {}})',
             'mavt = requested.model_copy(update={"method": "mavt", "parameters": {}, "weight_profile_id": None})'),
    Mutation("SUMMARY zero-weight criteria varied", "src/mcda_studio/services/sensitivity_eligibility.py",
             "(varied if node_global_weight(tree, local, node_id) > 0.0 else excluded)",
             "(varied if node_global_weight(tree, local, node_id) >= 0.0 else excluded)"),
    Mutation("SUMMARY fragility in local, not global, weight", "src/mcda_studio/services/screening_summary_service.py",
             "weight_change=abs(c.weight - base) * scale,", "weight_change=abs(c.weight - base),"),
    Mutation("SUMMARY missing measurements not named in the reason", "src/mcda_studio/services/screening_summary_service.py",
             'missing = codes.count("MISSING_MEASUREMENT")', "missing = 0"),
]  # fmt: skip

SUMMARY_FRONTEND = [
    Mutation("SUMMARY a response for another profile shown", "frontend/src/state/useScreeningSummary.ts",
             'result.status === "available" && (result.weight_profile_id !== context.resolvedProfileId',
             'result.status === "never" && (result.weight_profile_id !== context.resolvedProfileId'),
    Mutation("SUMMARY a raised weight shown as lowered", "frontend/src/components/results/ScreeningSummaryView.tsx",
             'const sign = f.direction === "raise" ? "+" : "−";', 'const sign = f.direction === "raise" ? "−" : "+";'),
    Mutation("SUMMARY a failed requirement shown as met", "frontend/src/components/results/ScreeningSummaryView.tsx",
             'if (r.status === "fail") return', 'if (r.status === "pass") return'),
]  # fmt: skip


#: The neutral gallery and wording development (docs/design/neutral-gallery-and-views.md).
GALLERY_FRONTEND = [
    Mutation("GALLERY the Analyst view opens for every starter",
             "frontend/src/state/viewMode.ts",
             "|| !ANALYST_STARTERS.has(templateId)", "|| false"),
    Mutation("GALLERY a stored hint is accepted for any starter",
             "frontend/src/state/viewMode.ts",
             "&& ANALYST_STARTERS.has(value.templateId)", ""),
    Mutation("GALLERY the membership test is inverted for a stored hint",
             "frontend/src/state/viewMode.ts",
             "ANALYST_STARTERS.has(value.templateId)", "!ANALYST_STARTERS.has(value.templateId)"),
    Mutation("GALLERY a stored hint's fingerprint is no longer checked",
             "frontend/src/state/viewMode.ts",
             '"fingerprint" in value && typeof value.fingerprint === "string"', '"fingerprint" in value && true'),
    Mutation("GALLERY the blank starter no longer comes first",
             "frontend/src/components/Dashboard.tsx",
             '  "blank",\n  "supplier_selection",', '  "supplier_selection",\n  "blank",'),
    Mutation("GALLERY the venture model starter moves ahead of the venture study",
             "frontend/src/components/Dashboard.tsx",
             '  "venture_screening_study",\n  "venture_screening",\n];',
             '  "venture_screening",\n  "venture_screening_study",\n];'),
    Mutation("GALLERY an example's icon falls back to the blank starter's plus sign",
             "frontend/src/components/Dashboard.tsx",
             '    clinic_site_selection: "M4 4h16v16H4zM12 8v8M8 12h8",\n', ""),
    Mutation("GALLERY an example's tagline is dropped",
             "frontend/src/components/Dashboard.tsx",
             '  clinic_site_selection: "Pairwise judgements and swing weights",\n', ""),
    Mutation("GALLERY the old word returns in the alternative drawer",
             "frontend/src/components/CompanyExplorer.tsx",
             'aria-label="Alternative contributions"', 'aria-label="Company contributions"'),
    Mutation("GALLERY the old word returns in the profile comparison",
             "frontend/src/components/results/PartnerComparison.tsx",
             'aria-label="Profile comparison"', 'aria-label="Partner comparison"'),
]  # fmt: skip


CLEANUP_FRONTEND = [
    Mutation("CLEANUP opening a prepared starter waits for a download again", "frontend/src/components/StarterGallery.tsx",
             '<button type="button" className="primary" disabled={busy} onClick={() => void open()}>',
             '<button type="button" className="primary" disabled={busy || !exported} onClick={() => void open()}>'),
    Mutation("CLEANUP a raw code leads the diagnostic again", "frontend/src/components/IssueText.tsx",
             '<><span>{message}</span> <InfoDisclosure', '<><code className="issue-code">{code}</code> <span>{message}</span> <InfoDisclosure'),
    Mutation("CLEANUP a method that did not run shows its code instead of plain words", "frontend/src/components/ComparePanel.tsx",
             "  if (known) return known;", "  if (known) return error.code;"),
]  # fmt: skip


SHOWCASE_QUESTIONS_BACKEND = [
    Mutation(
        "SHOWCASE zero-weight nodes return as winner questions",
        "src/mcda_studio/services/questions_service.py",
        "if sensitivity.node_id not in eligible:",
        "if False:",
    ),
    Mutation(
        "SHOWCASE zero-weight nodes return as class questions",
        "src/mcda_studio/services/questions_service.py",
        "if sweep.node_id not in eligible:",
        "if False:",
    ),
    Mutation(
        "SHOWCASE questions print a raw crossover float",
        "src/mcda_studio/services/questions_service.py",
        "number(change.weight, significant_digits=4)",
        "repr(change.weight)",
    ),
]

SHOWCASE_FIXTURE_BACKEND = [
    Mutation("SHOWCASE fixture rank drift remains exact", "scripts/export_model_test_fixtures.py",
             '    summary = screening.screening_summary(study, commercial).model_dump(mode="json")',
             '    summary = screening.screening_summary(study, commercial).model_dump(mode="json")\n    summary["rows"][0]["rank"] += 1'),
    Mutation("SHOWCASE fixture class drift remains exact", "scripts/export_model_test_fixtures.py",
             '    summary = screening.screening_summary(study, commercial).model_dump(mode="json")',
             '    summary = screening.screening_summary(study, commercial).model_dump(mode="json")\n    summary["rows"][0]["class_id"] = "monitor"'),
    Mutation("SHOWCASE fixture question count drift remains exact", "scripts/export_model_test_fixtures.py",
             '    summary = screening.screening_summary(study, commercial).model_dump(mode="json")',
             '    summary = screening.screening_summary(study, commercial).model_dump(mode="json")\n    summary["rows"][0]["open_questions"] += 1'),
]  # fmt: skip


SHOWCASE_FRONTEND = [
    Mutation("SHOWCASE viewed profile counted as a range change", "frontend/src/state/swingReview.ts",
             "return canonical({ criteria: project.criteria.map((node) => {",
             "return canonical({ viewedProfile: context.resolvedProfileId, criteria: project.criteria.map((node) => {"),
    Mutation("SHOWCASE actual range domain changes ignored", "frontend/src/state/swingReview.ts",
             "range: rangeInputs(vf, node.scale),", "range: null,"),
]  # fmt: skip


SHOWCASE_POLISH_BACKEND = [
    Mutation(
        "POLISH fallback chooses the lowest weight objective",
        "src/mcda_studio/services/screening_details_service.py",
        "key=lambda n: -weights[n]",
        "key=lambda n: weights[n]",
    ),
    Mutation(
        "POLISH detail contributions include unweighted screening leaves",
        "src/mcda_studio/services/screening_details_service.py",
        "if result.global_weights[n] > 0",
        "if result.global_weights[n] >= 0",
    ),
    Mutation(
        "POLISH details return the wrong company row",
        "src/mcda_studio/services/screening_details_service.py",
        "row=next(r for r in summary.rows if r.alternative_id == alternative_id)",
        "row=summary.rows[0]",
    ),
    Mutation(
        "POLISH stale evidence supplies drawer sources",
        "src/mcda_studio/services/screening_details_service.py",
        "claims = verified.claims if verified else []",
        "claims = dossier.claims if dossier else []",
    ),
]
SHOWCASE_POLISH_FRONTEND = [
    Mutation(
        "POLISH default sensitivity ignores the backend suggestion",
        "frontend/src/components/SensitivityPanel.tsx",
        "const nodeId = chosenNode ?? context.criterionId ?? suggested ?? null;",
        "const nodeId = chosenNode ?? context.criterionId ?? null;",
    ),
    Mutation(
        "POLISH all validation errors disable a method",
        "frontend/src/state/useMethodAvailability.ts",
        "response.validation.issues.some(i => MISSING.has(i.code))",
        "response.validation.issues.length > 0",
    ),
    Mutation(
        "POLISH source dates disappear from grouped claims",
        "frontend/src/components/EvidenceClaims.tsx",
        "{c.source.date}. {c.source.description}",
        "{c.source.description}",
    ),
    Mutation(
        "POLISH export changes original numeric geometry",
        "frontend/src/components/results/ExportCharts.tsx",
        "width={alt.overall_value * 650}",
        "width={alt.overall_value * 651}",
    ),
    Mutation(
        "POLISH export changes original text",
        "frontend/src/components/results/ExportCharts.tsx",
        '<text x="605" y={y + 42} textAnchor="middle">MAVT preference value (0–1, dimensionless)</text>',
        '<text x="605" y={y + 42} textAnchor="middle">Changed export axis</text>',
    ),
    Mutation(
        "POLISH export changes original metadata",
        "frontend/src/components/results/ExportCharts.tsx",
        "<metadata>{JSON.stringify(metadata)}</metadata>",
        "<metadata>{JSON.stringify({ changed: metadata })}</metadata>",
    ),
    Mutation(
        "POLISH tiny primary numbers print in scientific notation",
        "frontend/src/components/results/numberDisplay.ts",
        "if (value !== 0 && Math.abs(value) < .0001) return",
        "if (false) return",
    ),
]


SHOWCASE_DRAWER_BACKEND = [
    Mutation("DRAWER detail request edits the submitted project", "src/mcda_studio/services/screening_details_service.py",
             "    summary = screening_summary(project, configuration, dossier)",
             '    project.title += " changed"\n    summary = screening_summary(project, configuration, dossier)'),
]  # fmt: skip

SHOWCASE_DRAWER_FRONTEND = [
    Mutation("DRAWER opening a company edits the source object", "frontend/src/components/CompanyExplorer.tsx",
             "    setTooltip(null); setSelected({ alternativeId, profileId });",
             '    project.title += " changed"; setTooltip(null); setSelected({ alternativeId, profileId });'),
    Mutation("DRAWER freezes the opening analysis context", "frontend/src/components/CompanyExplorer.tsx",
             "export function CompanyExplorer({ project, context, dossier, studyEvidence, onSensitivity, children, blocked = false }: Props) {",
             "export function CompanyExplorer({ project, context: openingContext, dossier, studyEvidence, onSensitivity, children, blocked = false }: Props) {\n  const [context] = useState(openingContext);"),
    Mutation("DRAWER accepts a wrong-company response", "frontend/src/state/useScreeningDetails.ts",
             "alternativeId !== null && result.alternative?.row.alternative_id !== alternativeId", "false"),
    Mutation("DRAWER drops source dates", "frontend/src/components/CompanyExplorer.tsx",
             " · {claim.source.date}</p>", "</p>"),
    Mutation("DRAWER does not return focus to its opener", "frontend/src/components/ui.tsx",
             'if (previous?.isConnected && previous !== document.body && !previous.closest("[hidden],[inert]")) previous.focus();',
             "if (false) previous?.focus();"),
    Mutation("DRAWER loading leaves the keyboard outside its trap", "frontend/src/components/ui.tsx",
             "      if (ref.current.contains(document.activeElement)) return;", "      return;"),
    Mutation("DRAWER probes a rounded display weight", "frontend/src/components/CompanyExplorer.tsx",
             "criterionId: probeCriterion, weight: probeWeight, context",
             "criterionId: probeCriterion, weight: Number(probeWeight.toFixed(4)), context"),
    Mutation("DRAWER tooltip joins another criterion rubric", "frontend/src/components/companyExploration.tsx",
             "project.criteria.find(c => c.id === criterionId)", "project.criteria.find(c => c.id !== criterionId)"),
    Mutation("DRAWER ranking keyboard activation omits the drawer", "frontend/src/components/results/ResultsCharts.tsx",
             "onKeyDown={event => keyboard(event, () => { if (exploration?.blocked) return; onAlternative(id); exploration?.open(id); })}",
             "onKeyDown={event => keyboard(event, () => { if (exploration?.blocked) return; onAlternative(id); })}"),
    Mutation("DRAWER crossover row rounds the backend weight", "frontend/src/components/SensitivityPanel.tsx",
             "setCursor(c.weight);", "setCursor(Number(fmt(c.weight)));"),
    Mutation("DRAWER shared loader drops bundled claims", "frontend/src/components/EvidenceWorkspacePanel.tsx",
             "setDocument(bundled.dossier); setOriginal(bundled.dossier);",
             "setDocument({ ...(bundled.dossier as EvidenceDossier), claims: [] }); setOriginal(bundled.dossier);"),
]  # fmt: skip


SHOWCASE_VIEW_FRONTEND = [
    Mutation("VIEW mode selection edits the project", "frontend/src/components/EditorScreen.tsx",
             "    setView(next); chooseEditorView(projectId, next);",
             '    setView(next); void store.apply([{ op: "update_project", description: next }]); chooseEditorView(projectId, next);'),
    Mutation("VIEW all ordinary projects default to Analyst", "frontend/src/state/viewMode.ts",
             'const preference: EditorView = saved === "analyst" ? "analyst" : "builder";',
             'const preference: EditorView = saved === "builder" ? "builder" : "analyst";'),
    Mutation("VIEW Analyst hides the incomplete-model warning", "frontend/src/components/EditorScreen.tsx",
             'view === "analyst" && validation.issues.some(issue => issue.severity === "error")', "false"),
    Mutation("VIEW changing view remounts the evidence owner", "frontend/src/components/EditorScreen.tsx",
             "<EvidenceWorkspacePanel project={project}", "<EvidenceWorkspacePanel key={view} project={project}"),
]  # fmt: skip

CLEAN_DEMO_GUARD = [
    Mutation("GUARD primary diagnostics expose a raw code", "frontend/src/components/IssueText.tsx",
             '<><span>{message}</span> <InfoDisclosure', '<><span>{code}: {message}</span> <InfoDisclosure'),
    Mutation("GUARD viewed profile or scenario counts as a range change", "frontend/src/state/swingReview.ts",
             "return canonical({ criteria: project.criteria.map((node) => {",
             "return canonical({ viewedProfile: context.resolvedProfileId, viewedScenario: context.scenarioId, criteria: project.criteria.map((node) => {"),
    Mutation("GUARD question prose exposes the raw float", "src/mcda_studio/services/feasibility_service.py",
             "    if significant_digits is not None:\n",
             "    if significant_digits is not None:\n        return repr(float(x))\n"),
]  # fmt: skip


def run_clean_demo_guard(work: Path) -> bool:
    env = {
        **os.environ,
        "PYTHONPATH": str(work / "src"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "MCDA_PYTHON": sys.executable,
    }
    chrome = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if not env.get("MCDA_CHROMIUM") and chrome.is_file():
        env["MCDA_CHROMIUM"] = str(chrome)
    build = subprocess.run(
        ["npm", "run", "build"], cwd=work / "frontend", env=env, capture_output=True, text=True
    )
    if build.returncode:
        raise RuntimeError("Clean-demo mutant did not build:\n" + build.stdout + build.stderr)
    result = subprocess.run(
        ["npx", "playwright", "test", "e2e/clean-demo.spec.ts"],
        cwd=work / "frontend",
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        output = result.stdout + result.stderr
        if "Error: CLEAN_DEMO" not in output:
            raise RuntimeError(
                "Clean-demo mutant did not reach a named guard assertion:\n" + output
            )
        print(output, flush=True)
    return result.returncode == 0


SCREENING_PROFILES_BACKEND = [
    Mutation("PARTNERS averages the separate profile values", "src/mcda_studio/services/screening_profiles_service.py",
             "            change = row.rank - other.rank", "            row.value = other.value = (row.value + other.value) / 2\n            change = row.rank - other.rank"),
    Mutation("PARTNERS ignores the second requested profile", "src/mcda_studio/services/screening_profiles_service.py",
             'requested.model_copy(update={"weight_profile_id": profile_id})', 'requested.model_copy(update={"weight_profile_id": profile_ids[0]})'),
    Mutation("PARTNERS emphasizes one-place movements", "src/mcda_studio/services/screening_profiles_service.py",
             "emphasize=abs(change) >= 2,", "emphasize=abs(change) >= 1,"),
    Mutation("PARTNERS modifies the submitted project", "src/mcda_studio/services/screening_profiles_service.py",
             "    requested = (configuration or project.analysis).model_copy(deep=True)",
             '    project.title += " changed"\n    requested = (configuration or project.analysis).model_copy(deep=True)'),
]  # fmt: skip

SCREENING_PROFILES_FRONTEND = [
    Mutation("PARTNERS substitutes label positions for engine ranks", "frontend/src/components/results/PartnerComparison.tsx",
             "const y1 = 52 + (row.rank - 1) * 42, y2 = 52 + (other.rank - 1) * 42;", "const y1 = labelY1, y2 = labelY2;"),
    Mutation("PARTNERS right endpoint keyboard opens the left profile", "frontend/src/components/results/PartnerComparison.tsx",
             "onKeyDown={event => open(event, other.alternative_id, right.profile_id)}", "onKeyDown={event => open(event, other.alternative_id, left.profile_id)}"),
    Mutation("PARTNERS shows the previous ordered pair while the new pair loads", "frontend/src/state/useProfileComparison.ts",
             "return useAnalysisRequest(key, project.weight_profiles.length >= 2, load);", 'return useAnalysisRequest("frozen-partner-key", project.weight_profiles.length >= 2, load);'),
    Mutation("PARTNERS right dot uses the left class", "frontend/src/components/results/PartnerComparison.tsx",
             "rightColor = classColor(other.class_id);", "rightColor = classColor(movement.line_class_id);"),
]  # fmt: skip


def run_screening_profiles(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-x",
            "-p",
            "no:cacheprovider",
            "tests/unit/test_screening_profiles.py",
            "tests/api/test_api_screening_profiles.py",
        ],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        failures = [line for line in result.stdout.splitlines() if line.startswith("FAILED ")]
        if not failures:
            raise RuntimeError(
                "Partner mutant did not reach an assertion:\n" + result.stdout + result.stderr
            )
        print("\n".join(failures), flush=True)
    return result.returncode == 0


SCREENING_WHAT_IF_BACKEND = [
    Mutation("WHATIF edits the original project", "src/mcda_studio/services/screening_what_if_service.py",
             "    cfg = (configuration or project.analysis).model_copy(deep=True)",
             '    project.title += " changed"\n    cfg = (configuration or project.analysis).model_copy(deep=True)'),
    Mutation("WHATIF ignores one root rating", "src/mcda_studio/services/screening_what_if_service.py",
             "trial = project_service.set_judgement(trial, node, value, profile.id)",
             'trial = project_service.set_judgement(trial, node, value, profile.id) if node != "market" else trial'),
    Mutation("WHATIF replaces omitted roots with zero", "src/mcda_studio/services/screening_what_if_service.py",
             "for node, value in ratings.items():", "for node, value in {**dict.fromkeys(roots, 0.0), **ratings}.items():"),
    Mutation("WHATIF includes the zero-weight mandate as a slider", "src/mcda_studio/services/screening_what_if_service.py",
             "if node in scored_roots\n        and source.result.local_weights[node] > 0\n        and node in profile.judgements",
             "if node in profile.judgements"),
    Mutation("WHATIF loses the leaf judgements", "src/mcda_studio/services/screening_what_if_service.py",
             "    assert trial_profile is not None", "    assert trial_profile is not None\n    trial_profile.judgements = {key: value for key, value in trial_profile.judgements.items() if key in roots}"),
    Mutation("WHATIF caps uncapped raw ratings at 100", "src/mcda_studio/services/screening_what_if_service.py",
             "trial = project_service.set_judgement(trial, node, value, profile.id)",
             "trial = project_service.set_judgement(trial, node, min(value, 100), profile.id)"),
]  # fmt: skip

SCREENING_WHAT_IF_FRONTEND = [
    Mutation("WHATIF request mutates the original project", "frontend/src/state/useScreeningWhatIf.ts",
             "    const result = await api.screeningWhatIf", '    project.title += " changed";\n    const result = await api.screeningWhatIf'),
    Mutation("WHATIF reuses a ready reading under new slider values", "frontend/src/state/useScreeningWhatIf.ts",
             "return useAnalysisRequest(key, enabled, load, 150);", 'return useAnalysisRequest("constant-what-if", enabled, load, 150);'),
    Mutation("WHATIF Reset leaves old callbacks authorized", "frontend/src/state/useWeightTrial.ts",
             "value.sourceKey === sourceKey && value.generation === generation", "value.sourceKey === sourceKey"),
    Mutation("WHATIF normalizes ratings in React", "frontend/src/components/WhatIfWeights.tsx",
             "displayPercent(evaluated.local_weight)", "displayPercent(rating / 100)"),
    Mutation("WHATIF shows the saved question counts during a trial", "frontend/src/components/results/ScreeningSummaryView.tsx",
             'filter((c) => c.available && !(hideOpenQuestions && c.column === "open_questions"))', 'filter((c) => c.available)'),
    Mutation("WHATIF leaves Sensitivity enabled during a trial", "frontend/src/components/EditorScreen.tsx",
             'trial.active ? <p>{RESET_TRIAL}</p> : <ScopedAnalysis', 'false ? <p>{RESET_TRIAL}</p> : <ScopedAnalysis'),
    Mutation("WHATIF leaves company controls enabled", "frontend/src/components/companyExploration.tsx",
             "disabled={exploration.blocked}", "disabled={false}"),
    Mutation("WHATIF allows an in-flight download after trial or Reset", "frontend/src/components/WeightTrialGate.tsx",
             "token !== null && live.current.alive && !live.current.active && live.current.generation === token",
             "token !== null && live.current.alive"),
    Mutation("WHATIF trusts an incorrect echoed rating", "frontend/src/state/useScreeningWhatIf.ts",
             "canonical(result.ratings) !== serializedRatings", "false"),
    Mutation("WHATIF accepts another trial summary fingerprint", "frontend/src/state/useScreeningWhatIf.ts",
             "summary.project_fingerprint !== trial", "false"),
]  # fmt: skip


def run_screening_what_if(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-x",
            "-p",
            "no:cacheprovider",
            "tests/unit/test_screening_what_if.py",
            "tests/api/test_api_screening_what_if.py",
        ],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        failures = [line for line in result.stdout.splitlines() if line.startswith("FAILED ")]
        if not failures:
            raise RuntimeError(
                "What-if mutant did not reach an assertion:\n" + result.stdout + result.stderr
            )
        print("\n".join(failures), flush=True)
    return result.returncode == 0


def run_showcase_polish(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-x",
            "-p",
            "no:cacheprovider",
            "tests/api/test_api_screening_details.py",
        ],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        failures = [line for line in result.stdout.splitlines() if line.startswith("FAILED ")]
        if not failures:
            raise RuntimeError(
                "Polish mutant did not reach an assertion:\n" + result.stdout + result.stderr
            )
        print("\n".join(failures), flush=True)
    return result.returncode == 0


def run_showcase_questions(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-x",
            "-p",
            "no:cacheprovider",
            "tests/unit/test_questions.py",
            "tests/api/test_api_questions.py",
        ],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        failures = [line for line in result.stdout.splitlines() if line.startswith("FAILED ")]
        if not failures:
            raise RuntimeError(
                "Question mutant did not reach an assertion:\n" + result.stdout + result.stderr
            )
        print("\n".join(failures), flush=True)
    return result.returncode == 0


def run_fixture_freshness(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    test = "tests/regression/test_market_models_reference.py::test_new_model_schemas_and_component_contracts_are_current"
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", test],
        cwd=work,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        failures = [
            line for line in result.stdout.splitlines() if line.startswith("FAILED " + test)
        ]
        if not failures:
            raise RuntimeError(
                "Fixture mutant did not reach its freshness assertion:\n"
                + result.stdout
                + result.stderr
            )
        print("\n".join(failures), flush=True)
    return result.returncode == 0


def run_summary(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-x",
        "-p",
        "no:cacheprovider",
        "tests/regression/test_screening_summary_reference.py",
        "tests/api/test_api_screening_summary.py",
    ]
    result = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True)
    if result.returncode:
        failures = [line for line in result.stdout.splitlines() if line.startswith("FAILED ")]
        if not failures:
            raise RuntimeError(
                "Summary mutant did not reach a test assertion:\n" + result.stdout + result.stderr
            )
        print("\n".join(failures), flush=True)
    return result.returncode == 0


def run_study(work: Path) -> bool:
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        "tests/regression/test_nz_venture_screening.py",
    ]
    result = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True)
    if result.returncode:
        failures = [line for line in result.stdout.splitlines() if line.startswith("FAILED ")]
        if not failures:
            raise RuntimeError(
                "Study mutant did not reach a test assertion:\n" + result.stdout + result.stderr
            )
        print("\n".join(failures), flush=True)
    return result.returncode == 0


def run_exemplars(work: Path) -> bool:
    """Rebuild every exemplar from its (possibly mutated) build.py, then run the exemplar tests.

    The study files are restored afterwards, because the harness restores only the mutated source
    file and later runners must see the shipped bytes."""
    env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
    touched = []
    for name in EXEMPLAR_STUDIES:
        touched += [
            work / "examples" / name / "project.json",
            work / "examples" / "starter_templates" / name / "project.json",
            work / "examples" / "starter_templates" / name / "manifest.json",
        ]
    saved = {path: path.read_bytes() for path in touched}
    try:
        for name in EXEMPLAR_STUDIES:
            built = subprocess.run(
                [sys.executable, str(work / "examples" / name / "build.py")],
                cwd=work,
                env=env,
                capture_output=True,
                text=True,
            )
            if built.returncode:
                raise RuntimeError("Exemplar mutant did not build:\n" + built.stdout + built.stderr)
        cmd = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "tests/regression/test_method_exemplars.py",
        ]
        result = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True)
    finally:
        for path, data in saved.items():
            path.write_bytes(data)
    if result.returncode:
        failures = [line for line in result.stdout.splitlines() if line.startswith("FAILED ")]
        if not failures:
            raise RuntimeError(
                "Exemplar mutant did not reach a test assertion:\n" + result.stdout + result.stderr
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
        shutil.copytree(ROOT / "frontend" / "e2e", dest / "frontend" / "e2e")


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
    if subprocess.run(cmd, cwd=work / "frontend", capture_output=True, text=True).returncode == 0:
        return True
    # Several component tests wait on real timers and fail when the machine is busy. Run the same
    # tests again, one file at a time and with the same timeouts: a real defect fails both runs.
    again = [*cmd, "--no-file-parallelism"]
    return (
        subprocess.run(again, cwd=work / "frontend", capture_output=True, text=True).returncode == 0
    )


# ----------------------------------------------------------------------------------------------
# The 7 November 2026 developments (rater kit, screening report, typed-proposal runner, name-swap
# check, decision impact): one registry, one generic runner, one ``--<key>-only`` flag each.
# ----------------------------------------------------------------------------------------------


def pytest_runner(label: str, *tests: str):
    def run(work: Path) -> bool:
        env = {**os.environ, "PYTHONPATH": str(work / "src"), "PYTHONDONTWRITEBYTECODE": "1"}
        cmd = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", *tests]
        result = subprocess.run(cmd, cwd=work, env=env, capture_output=True, text=True)
        if result.returncode:
            # A mutant that breaks a fixture (setup ERROR) is as detected as a failing assertion.
            failures = [
                line
                for line in result.stdout.splitlines()
                if line.startswith(("FAILED ", "ERROR "))
            ]
            if not failures:
                raise RuntimeError(
                    f"{label} mutant did not reach a test assertion:\n"
                    + result.stdout
                    + result.stderr
                )
            print("\n".join(failures), flush=True)
        return result.returncode == 0

    run.label = label  # type: ignore[attr-defined]
    return run


OVERNIGHT: dict[str, tuple[list[Mutation], object]] = {}

RATER_KIT_BACKEND = [
    Mutation(
        "RATER the seed no longer orders companies and criteria",
        "scripts/rater_kit.py",
        'sha(f"{seed}|{scope}|{key}".encode())',
        'sha(f"{scope}|{key}".encode())',
    ),
    Mutation(
        "RATER cannot tell is silently dropped instead of recorded as an abstention",
        "scripts/rater_kit.py",
        "    if lowered == CANNOT_TELL:\n        return -1",
        "    if lowered == CANNOT_TELL:\n        return None",
    ),
    Mutation(
        "RATER the numeric market criteria enter the rater packet",
        "scripts/rater_kit.py",
        '        if leaf["numeric"]:\n            continue',
        "        if False:\n            continue",
    ),
    Mutation(
        "RATER an output inside the repository is accepted",
        "scripts/rater_kit.py",
        "        not resolved.is_relative_to(ROOT),",
        "        True,",
    ),
    Mutation(
        "RATER an existing output file is not refused before writing",
        "scripts/rater_kit.py",
        '        require(not path.exists(), f"Refusing to overwrite {name}")',
        "        pass",
    ),
    Mutation(
        "RATER a rater's choice is converted to the wrong level",
        "scripts/rater_kit.py",
        '"label": None if index < 0 else labels[index],',
        '"label": None if index < 0 else labels[index - 1],',
    ),
    Mutation(
        "RATER the author's ratings are converted one level high",
        "scripts/rater_kit.py",
        "resolved[item] = labels.index(value)",
        "resolved[item] = min(labels.index(value) + 1, len(labels) - 1)",
    ),
    Mutation(
        "RATER the frozen chronology is not checked",
        "scripts/rater_kit.py",
        'require(chronology == sorted(set(chronology)), "Need frozen < gate-confirmed < unblinded")',
        "pass",
    ),
    Mutation(
        "RATER finalize accepts a protocol changed after the freeze",
        "scripts/rater_kit.py",
        '        frozen.get("digest") == digest({k: v for k, v in frozen.items() if k != "digest"}),',
        "        True,",
    ),
    Mutation(
        "RATER answers saved from another packet are accepted",
        "scripts/rater_kit.py",
        'seen_digest is None or seen_digest == kit["kit_digest"],',
        "True,",
    ),
    Mutation(
        "RATER a form cell is not protected from spreadsheet formulas",
        "scripts/rater_kit.py",
        """    return "'" + value if value[:1] in {"=", "+", "-", "@", "\\t", "\\r"} else value""",
        "    return value",
    ),
    Mutation(
        "RATER the frozen gate is relaxed",
        "scripts/rater_kit.py",
        '"lower_kappa": "0.60",',
        '"lower_kappa": "0.50",',
    ),
    Mutation(
        "RATER the bootstrap resamples items instead of companies",
        "scripts/rater_kit.py",
        '"unit": "group",',
        '"unit": "item",',
    ),
]
OVERNIGHT["rater"] = (RATER_KIT_BACKEND, pytest_runner("Rater kit", "tests/unit/test_rater_kit.py"))


REPORT_BACKEND = [
    Mutation(
        "REPORT a company's rank is swapped with its mirror",
        "src/mcda_studio/services/screening_report_service.py",
        "        cells = [_e(row.rank), _e(row.name), _e(_n(row.value))]",
        "        cells = [_e(len(summary.rows) + 1 - row.rank), _e(row.name), _e(_n(row.value))]",
    ),
    Mutation(
        "REPORT a company's class is replaced by the lowest class",
        "src/mcda_studio/services/screening_report_service.py",
        '            cells.append(_e(f"{row.class_name}{margin}"))',
        '            cells.append(_e(f"{list(classes.values())[-1]}{margin}"))',
    ),
    Mutation(
        "REPORT the margin shows the overall value",
        "src/mcda_studio/services/screening_report_service.py",
        '            margin = f" ({_n(row.margin)})" if row.margin is not None else ""',
        '            margin = f" ({_n(row.value)})" if row.margin is not None else ""',
    ),
    Mutation(
        "REPORT the disclaimer is missing",
        "src/mcda_studio/services/screening_report_service.py",
        "    lines = list(DISCLAIMER)",
        "    lines = []",
    ),
    Mutation(
        "REPORT every profile is read under the first one",
        "src/mcda_studio/services/screening_report_service.py",
        'project, requested.model_copy(update={"weight_profile_id": p}), usable',
        'project, requested.model_copy(update={"weight_profile_id": chosen[0]}), usable',
    ),
    Mutation(
        "REPORT a mandate failure reads as met",
        "src/mcda_studio/services/screening_report_service.py",
        '    if status.status == "pass":\n        return "Meets all"',
        '    if True:\n        return "Meets all"',
    ),
    Mutation(
        "REPORT only one contribution is listed",
        "src/mcda_studio/services/screening_report_service.py",
        'for d in row.drivers) or "none"',
        'for d in row.drivers[:1]) or "none"',
    ),
    Mutation(
        "REPORT the judgement-only count is one too high",
        "src/mcda_studio/services/screening_report_service.py",
        "    judged = len(judged_cells)\n",
        "    judged = 1 + len(judged_cells)\n",
    ),
    Mutation(
        "REPORT the partner comparison repeats the first profile",
        "src/mcda_studio/services/screening_report_service.py",
        "                reading = by[idx][alt]",
        "                reading = by[0][alt]",
    ),
]
REPORT_FRONTEND = [
    Mutation(
        "REPORT the download button stays enabled during a what-if trial",
        "frontend/src/components/results/ScreeningReportButton.tsx",
        "disabled={trial.active || guard.disabled || busy ||",
        "disabled={busy ||",
    ),
    Mutation(
        "REPORT a report requested before a trial can still be saved",
        "frontend/src/components/results/ScreeningReportButton.tsx",
        "if (mine.signal.aborted || !guard.permits(ticket) || controller.current !== mine) return;",
        "if (mine.signal.aborted || controller.current !== mine) return;",
    ),
]
OVERNIGHT["report"] = (
    REPORT_BACKEND,
    pytest_runner(
        "Screening report",
        "tests/regression/test_screening_report_reference.py",
        "tests/api/test_api_screening_report.py",
    ),
)

NEUTRAL_BACKEND = [
    Mutation(
        "NEUTRAL the venture sentence is restored to the engine's fixed text",
        "src/mcda_studio/services/screening_report_service.py",
        '    "This report supports a screening decision. It is not advice and does not recommend any "\n'
        '    "option.",',
        '    "This is not investment advice. It does not value any company or recommend any "\n'
        '    "investment.",',
    ),
    Mutation(
        "NEUTRAL the project's own statement is left out of the box",
        "src/mcda_studio/services/screening_report_service.py",
        '    statement = f\'<p class="statement">{_e(project.description)}</p>\' if project.description else ""',
        '    statement = ""',
    ),
    Mutation(
        "NEUTRAL a note line is not HTML-escaped",
        "src/mcda_studio/services/screening_report_service.py",
        '        + "".join(f"<li>{_e(line)}</li>" for line in lines)\n        + "</ul></div>"',
        '        + "".join(f"<li>{line}</li>" for line in lines)\n        + "</ul></div>"',
    ),
    Mutation(
        "NEUTRAL the twenty-note limit refuses the twentieth note",
        "src/mcda_studio/services/screening_report_service.py",
        "    if len(cleaned) > NOTE_MAX_LINES:",
        "    if len(cleaned) >= NOTE_MAX_LINES:",
    ),
    Mutation(
        "NEUTRAL the twenty-note limit accepts a twenty-first note",
        "src/mcda_studio/services/screening_report_service.py",
        "    if len(cleaned) > NOTE_MAX_LINES:",
        "    if len(cleaned) > NOTE_MAX_LINES + 1:",
    ),
    Mutation(
        "NEUTRAL the 300-character limit refuses a 300-character note",
        "src/mcda_studio/services/screening_report_service.py",
        "    if any(len(note) > NOTE_MAX_CHARS for note in cleaned):",
        "    if any(len(note) >= NOTE_MAX_CHARS for note in cleaned):",
    ),
    Mutation(
        "NEUTRAL the 300-character limit accepts a 301-character note",
        "src/mcda_studio/services/screening_report_service.py",
        "    if any(len(note) > NOTE_MAX_CHARS for note in cleaned):",
        "    if any(len(note) > NOTE_MAX_CHARS + 1 for note in cleaned):",
    ),
    Mutation(
        "NEUTRAL the API accepts a twenty-first note",
        "src/mcda_studio/api/schemas.py",
        "max_length=300)]], Field(max_length=20)]",
        "max_length=300)]], Field(max_length=21)]",
    ),
    Mutation(
        "NEUTRAL the API accepts a 301-character note",
        "src/mcda_studio/api/schemas.py",
        "Field(min_length=1, max_length=300)",
        "Field(min_length=1, max_length=301)",
    ),
    Mutation(
        "NEUTRAL the judgement count swaps its two figures",
        "src/mcda_studio/services/screening_report_service.py",
        '    line = f"{judged} of {scored} scored ratings rest on judgement alone"',
        '    line = f"{scored} of {judged} scored ratings rest on judgement alone"',
    ),
    Mutation(
        "NEUTRAL the qualitative figure swaps its two numbers",
        "src/mcda_studio/services/screening_report_service.py",
        '        line += f" ({judged_labelled} of {labelled} qualitative or ordinal ratings)"',
        '        line += f" ({labelled} of {judged_labelled} qualitative or ordinal ratings)"',
    ),
    Mutation(
        "NEUTRAL numeric ratings count as qualitative or ordinal",
        "src/mcda_studio/services/screening_report_service.py",
        "if node.scale is not None and not node.scale.is_numeric",
        "if node.scale is not None and node.scale.is_numeric",
    ),
]
OVERNIGHT["neutral"] = (
    NEUTRAL_BACKEND,
    pytest_runner(
        "Neutral report",
        "tests/regression/test_screening_report_reference.py",
        "tests/api/test_api_screening_report.py",
    ),
)


ORDERS_BACKEND = [
    Mutation(
        "ORDERS the rotation is applied in the wrong direction",
        "scripts/typed_proposal_runner.py",
        "    return options[shift:] + options[:shift]",
        "    return options[-shift:] + options[:-shift]",
    ),
    Mutation(
        "ORDERS the letters are mapped back to the options off by one",
        "scripts/typed_proposal_runner.py",
        "        probabilities = dict(zip(order, letter_softmax(chosen), strict=True))",
        "        probabilities = dict(zip(rotated(order, 1), letter_softmax(chosen), strict=True))",
    ),
    Mutation(
        "ORDERS the rotations are not applied when mapping back",
        "scripts/typed_proposal_runner.py",
        "        probabilities = dict(zip(order, letter_softmax(chosen), strict=True))",
        "        probabilities = dict(zip(options, letter_softmax(chosen), strict=True))",
    ),
    Mutation(
        "ORDERS the mean is replaced by the first rotation",
        "scripts/typed_proposal_runner.py",
        '    scores = {o: math.fsum(r["probabilities"][o] for r in rotations) / n for o in options}',
        '    scores = {o: rotations[0]["probabilities"][o] for o in options}',
    ),
    Mutation(
        "ORDERS cannot tell is left out of the rotation",
        "scripts/typed_proposal_runner.py",
        "        order = rotated(options, shift)\n        chosen",
        "        order = [*rotated(options[:-1], shift % (n - 1)), options[-1]]\n        chosen",
    ),
    Mutation(
        "ORDERS every rotation counts as agreeing with the average",
        "scripts/typed_proposal_runner.py",
        '    agreement = sum(1 for r in rotations if first_max(options, r["probabilities"]) == top) / n',
        "    agreement = sum(1 for r in rotations if first_max(options, r[\"probabilities\"]) != '') / n",
    ),
    Mutation(
        "ORDERS the single-order path adds a smoothing term",
        "scripts/typed_proposal_runner.py",
        '    total = sum(weights)\n    scores = {o: w / total for o, w in zip(options, weights, strict=True)}\n    return scores, {\n        "letters"',
        '    total = sum(weights) + 1e-9\n    scores = {o: w / total for o, w in zip(options, weights, strict=True)}\n    return scores, {\n        "letters"',
    ),
    Mutation(
        "ORDERS the default stops averaging",
        "scripts/typed_proposal_runner.py",
        '        default="rotations",',
        '        default="none",',
    ),
    Mutation(
        "ORDERS a single-order run is recorded as the averaged scoring version",
        "scripts/typed_proposal_runner.py",
        "    return SCORING_SINGLE, SCORING_TEXT_SINGLE",
        "    return SCORING_AVERAGED, SCORING_TEXT_SINGLE",
    ),
    Mutation(
        "REEXTRACT the three-word threshold is off by one",
        "scripts/typed_proposal_runner.py",
        "len(line.split()) <= SHORT_LINE_WORDS and elsewhere",
        "len(line.split()) < SHORT_LINE_WORDS and elsewhere",
    ),
    Mutation(
        "REEXTRACT the shared-line rule crosses hosts",
        "scripts/typed_proposal_runner.py",
        '        hosts[row["url"]] = host_of(row)',
        '        hosts[row["url"]] = ""',
    ),
    Mutation(
        "REEXTRACT a page counts as its own other page",
        "scripts/typed_proposal_runner.py",
        "            elsewhere = by_host[hosts[url]][line] - {url}",
        "            elsewhere = by_host[hosts[url]][line] - set()",
    ),
    Mutation(
        "REEXTRACT a repeated line within a page is kept",
        "scripts/typed_proposal_runner.py",
        "            if line in seen:\n                continue",
        "            if False:\n                continue",
    ),
    Mutation(
        "REEXTRACT the saved raw bytes are not checked",
        "scripts/typed_proposal_runner.py",
        '        require(sha(raw) == row["raw_sha256"], f"A saved page changed on disk: {row[\'url\']}")',
        "        pass",
    ),
]
OVERNIGHT["orders"] = (
    ORDERS_BACKEND,
    pytest_runner("Option orders and re-extraction", "tests/unit/test_typed_proposal_runner.py"),
)

RUNNER_BACKEND = [
    Mutation(
        "RUNNER an output inside the repository is accepted",
        "scripts/typed_proposal_runner.py",
        "        not resolved.is_relative_to(ROOT),",
        "        True,",
    ),
    Mutation(
        "RUNNER the snapshot client sends another name",
        "scripts/typed_proposal_runner.py",
        'url, headers={"User-Agent": CLIENT, "Accept"',
        'url, headers={"User-Agent": "python-urllib", "Accept"',
    ),
    Mutation(
        "RUNNER a login or paywall page is saved",
        "scripts/typed_proposal_runner.py",
        '            if status in (401, 403):\n                row["outcome"] = "skipped_login_or_paywall"',
        '            if status in (401,):\n                row["outcome"] = "skipped_login_or_paywall"',
    ),
    Mutation(
        "RUNNER robots.txt is ignored",
        "scripts/typed_proposal_runner.py",
        "        if not permitted:",
        "        if False:",
    ),
    Mutation(
        "RUNNER a saved page is fetched again without --refresh",
        "scripts/typed_proposal_runner.py",
        "        if url in kept and not args.refresh:",
        "        if url in kept and False:",
    ),
    Mutation(
        "RUNNER the stored page hash is of nothing",
        "scripts/typed_proposal_runner.py",
        '                row["raw_sha256"] = sha(body)',
        '                row["raw_sha256"] = sha(b"")',
    ),
    Mutation(
        "RUNNER a company's question state uses only its first cited page",
        "scripts/typed_proposal_runner.py",
        '        cited = sorted(identity.get(alt, {}).values(), key=lambda s: s["url"])',
        '        cited = sorted(identity.get(alt, {}).values(), key=lambda s: s["url"])[:1]',
    ),
    Mutation(
        "RUNNER the leftover probability units are not distributed",
        "scripts/typed_proposal_runner.py",
        "    for o in ranked[:left]:",
        "    for o in ranked[:0]:",
    ),
    Mutation(
        "RUNNER an exact tie at the top picks a winner",
        "scripts/typed_proposal_runner.py",
        "    return (winners[0], False) if len(winners) == 1 else (None, True)",
        "    return (winners[0], False)",
    ),
    Mutation(
        "RUNNER cannot tell can become a proposal",
        "scripts/typed_proposal_runner.py",
        "        proposed = top is not None and top != CANNOT_TELL and top_p >= threshold",
        "        proposed = top is not None and top_p >= threshold",
    ),
    Mutation(
        "RUNNER a probability exactly at the threshold abstains",
        "scripts/typed_proposal_runner.py",
        "        proposed = top is not None and top != CANNOT_TELL and top_p >= threshold",
        "        proposed = top is not None and top != CANNOT_TELL and top_p > threshold",
    ),
    Mutation(
        "RUNNER jev sends without --allow-network",
        "scripts/typed_proposal_runner.py",
        '        require(args.allow_network, "The jev backend needs --allow-network")',
        "        pass",
    ),
    Mutation(
        "RUNNER jev drops the bearer key",
        "scripts/typed_proposal_runner.py",
        '                "Authorization": f"Bearer {self._key}",',
        '                "X-Unused": f"Bearer {self._key}",',
    ),
    Mutation(
        "RUNNER jev accepts an answer that names other options",
        "scripts/typed_proposal_runner.py",
        '        if not isinstance(probabilities, dict) or set(probabilities) != set(question["options"]):',
        "        if not isinstance(probabilities, dict):",
    ),
    Mutation(
        "RUNNER a changed question is run",
        "scripts/typed_proposal_runner.py",
        '        require(\n            question["digest"] == digest(body), f"Question {question[\'question_id\']} was changed"\n        )',
        "        pass",
    ),
    Mutation(
        "RUNNER a proposal cites a source that is not in the registry",
        "scripts/typed_proposal_runner.py",
        "                    ids.append(sid)",
        '                    ids.append(sid + "x")',
    ),
    Mutation(
        "RUNNER confidence is reported as certainty",
        "scripts/typed_proposal_runner.py",
        '                "value": float(top_p),',
        '                "value": 1.0,',
    ),
    Mutation(
        "RUNNER a benchmark label is mapped to the wrong level",
        "scripts/typed_proposal_runner.py",
        '                "label": levels[question["labels"].index(top)] if proposed else None,',
        '                "label": levels[-1] if proposed else None,',
    ),
    # The Laya backend, the model allowlist and jev rotations (16 November 2026).
    Mutation(
        "RUNNER a chunk exactly at the token budget is split off by one",
        "scripts/typed_proposal_runner.py",
        "            if count(joined) <= budget:\n                current.update(",
        "            if count(joined) < budget:\n                current.update(",
    ),
    Mutation(
        "RUNNER the chunk mean is replaced by the first chunk",
        "scripts/typed_proposal_runner.py",
        "    return {o: math.fsum(v[o] for v in vectors) / len(vectors) for o in options}",
        "    return {o: vectors[0][o] for o in options}",
    ),
    Mutation(
        "RUNNER cannot tell is dropped from the laya criteria",
        "scripts/typed_proposal_runner.py",
        "        return list(order)",
        "        return [o for o in order if o != CANNOT_TELL]",
    ),
    Mutation(
        "RUNNER a jev rotation is not mapped back to its options",
        "scripts/typed_proposal_runner.py",
        '            return {option: scores[option] for option in question["options"]}',
        '            return dict(zip(question["options"], scores.values(), strict=True))',
    ),
    Mutation(
        "RUNNER a laya rotation is not mapped back to its options",
        "scripts/typed_proposal_runner.py",
        '        return {o: float(probabilities[o]) for o in question["options"]}',
        '        return dict(zip(question["options"], map(float, probabilities.values()), strict=True))',
    ),
    Mutation(
        "RUNNER the laya window is hard-coded to 512",
        "scripts/typed_proposal_runner.py",
        '        self.max_len = int(config["max_len"])',
        "        self.max_len = 512",
    ),
    Mutation(
        "RUNNER the model allowlist is bypassed",
        "scripts/typed_proposal_runner.py",
        "        args.repo in MODEL_ALLOWLIST,",
        "        True,",
    ),
    Mutation(
        "RUNNER a question whose rubric laya would cut is answered anyway",
        "scripts/typed_proposal_runner.py",
        "        if capped != whole:",
        "        if False:",
    ),
]
RUNNER_BACKEND += [
    Mutation(
        "RUNNER the second Laya reading takes the least confident chunk",
        "scripts/typed_proposal_runner.py",
        "    return max(range(len(chunk_means)), key=lambda c: (max(chunk_means[c].values()), -c))",
        "    return min(range(len(chunk_means)), key=lambda c: (max(chunk_means[c].values()), -c))",
    ),
    Mutation(
        "RUNNER a tie for the most confident chunk goes to the later chunk",
        "scripts/typed_proposal_runner.py",
        "key=lambda c: (max(chunk_means[c].values()), -c))",
        "key=lambda c: (max(chunk_means[c].values()), c))",
    ),
    Mutation(
        "RUNNER export reads the mean when asked for the second reading",
        "scripts/typed_proposal_runner.py",
        '    return {qid: row["readings"][key] for qid, row in rows.items()}',
        "    return rows",
    ),
    Mutation(
        "RUNNER proposals from the second reading do not name it in the tool version",
        "scripts/typed_proposal_runner.py",
        '        tool_version += f"+{args.reading}"',
        "        pass",
    ),
    Mutation(
        "RUNNER a local model ignores an NVIDIA GPU",
        "scripts/typed_proposal_runner.py",
        "    if torch.cuda.is_available():\n",
        "    if False:\n",
    ),
    Mutation(
        "RUNNER a local model runs in float32 on an NVIDIA GPU",
        "scripts/typed_proposal_runner.py",
        '        return "cuda", torch.float16',
        '        return "cuda", torch.float32',
    ),
]
OVERNIGHT["runner"] = (
    RUNNER_BACKEND,
    pytest_runner("Typed-proposal runner", "tests/unit/test_typed_proposal_runner.py"),
)


SWAP_BACKEND = [
    Mutation(
        "SWAP longer names are not replaced first",
        "scripts/typed_proposal_runner.py",
        "    ordered = sorted(pairs, key=lambda p: (-len(p[0]), p[0]))",
        "    ordered = sorted(pairs, key=lambda p: (len(p[0]), p[0]))",
    ),
    Mutation(
        "SWAP matches names in any case",
        "scripts/typed_proposal_runner.py",
        '    pattern = re.compile("|".join(re.escape(a) for a, _ in ordered))',
        '    pattern = re.compile("|".join(re.escape(a) for a, _ in ordered), re.I)',
    ),
    Mutation(
        "SWAP a swap file without its header is accepted",
        "scripts/typed_proposal_runner.py",
        '            rows and rows[0] == ["original", "replacement"],',
        "            True,",
    ),
    Mutation(
        "SWAP a name listed twice is accepted",
        "scripts/typed_proposal_runner.py",
        '    require(len({a for a, _ in pairs}) == len(pairs), "A name is listed twice")',
        "    pass",
    ),
    Mutation(
        "COMPARE a changed top label is not detected",
        "scripts/typed_proposal_runner.py",
        '        flip = rows_a[qid]["top"] != rows_b[qid]["top"]',
        "        flip = False",
    ),
    Mutation(
        "COMPARE the probability shift has the wrong sign",
        "scripts/typed_proposal_runner.py",
        "        shifts = {o: pb[o] - pa[o] for o in order}",
        "        shifts = {o: pa[o] - pb[o] for o in order}",
    ),
    Mutation(
        "COMPARE runs of different questions are compared",
        "scripts/typed_proposal_runner.py",
        '    require(set(rows_a) == set(rows_b), "The two runs answered different questions")',
        "    pass",
    ),
    Mutation(
        "COMPARE the largest shifts are listed smallest first",
        "scripts/typed_proposal_runner.py",
        '    largest = sorted(cells, key=lambda c: (-c["largest_shift"], c["question_id"]))[: args.top]',
        '    largest = sorted(cells, key=lambda c: (c["largest_shift"], c["question_id"]))[: args.top]',
    ),
    Mutation(
        "COMPARE the unchanged count ignores changes",
        "scripts/typed_proposal_runner.py",
        '        "top_label_unchanged": len(cells) - changed,',
        '        "top_label_unchanged": len(cells),',
    ),
]
OVERNIGHT["swap"] = (
    SWAP_BACKEND,
    pytest_runner(
        "Name swap",
        "tests/unit/test_typed_proposal_runner.py",
        "-k",
        "swap or compare or injected or identical or different",
    ),
)


IMPACT_BACKEND = [
    Mutation(
        "IMPACT a label of the scale is skipped",
        "src/mcda_studio/services/decision_impact_service.py",
        "        for k, label in enumerate(labels):",
        "        for k, label in enumerate(labels[:-1]):",
    ),
    Mutation(
        "IMPACT a level is counted one off",
        "src/mcda_studio/services/decision_impact_service.py",
        "                    levels=k - position,",
        "                    levels=k - position + 1,",
    ),
    Mutation(
        "IMPACT rank ties use the wrong tolerance sign",
        "src/mcda_studio/methods/mavt/aggregation.py",
        "    return [1 + sum(1 for other in values if other > v + tol) for v in values]",
        "    return [1 + sum(1 for other in values if other > v - tol) for v in values]",
    ),
    Mutation(
        "IMPACT a value on a class boundary takes the lower class",
        "src/mcda_studio/methods/sorting/classes.py",
        "    return sum(1 for b in boundaries if value < b - TIE_TOL)",
        "    return sum(1 for b in boundaries if value < b + TIE_TOL)",
    ),
    Mutation(
        "IMPACT a leader change is seen only when the whole set is replaced",
        "src/mcda_studio/services/decision_impact_service.py",
        "            if now_leaders != leaders:",
        "            if now_leaders.isdisjoint(leaders):",
    ),
    Mutation(
        "IMPACT only a better rank counts as a target rank change",
        "src/mcda_studio/services/decision_impact_service.py",
        "            if ranks[i] != base_ranks[i]:",
        "            if ranks[i] < base_ranks[i]:",
    ),
    Mutation(
        "IMPACT zero-weight cells are analysed",
        "src/mcda_studio/services/decision_impact_service.py",
        "            weights[j] <= 0\n",
        "            weights[j] < 0\n",
    ),
    Mutation(
        "IMPACT cells are ordered with rank changes after no change",
        "src/mcda_studio/services/decision_impact_service.py",
        '    rank_of_tier = {"leader_or_class": 0, "rank": 1, "none": 2}',
        '    rank_of_tier = {"leader_or_class": 0, "rank": 2, "none": 1}',
    ),
    Mutation(
        "IMPACT a class change alone is not a decision change",
        "src/mcda_studio/services/decision_impact_service.py",
        '        decisive = bool(by_change["leader"] or by_change["target_class"])',
        '        decisive = bool(by_change["leader"])',
    ),
    Mutation(
        "IMPACT the smallest change is the largest",
        "src/mcda_studio/services/decision_impact_service.py",
        "        nearest = min((abs(e.levels) for e in moving), default=None)",
        "        nearest = max((abs(e.levels) for e in moving), default=None)",
    ),
    Mutation(
        "IMPACT a rejected claim still counts as support for the cell",
        "src/mcda_studio/services/decision_impact_service.py",
        '    return claim.review is not None and claim.review.status != "rejected"',
        '    return claim.review is not None and claim.review.status != "nonsense"',
    ),
]
IMPACT_FRONTEND = [
    Mutation(
        "IMPACT the toggle starts on",
        "frontend/src/components/QuestionsPanel.tsx",
        "const [byImpact, setByImpact] = useState(false);",
        "const [byImpact, setByImpact] = useState(true);",
    ),
    Mutation(
        "IMPACT the route is called without the toggle",
        "frontend/src/components/QuestionsPanel.tsx",
        "byImpact && project.alternatives.length > 0, loadImpact",
        "project.alternatives.length > 0, loadImpact",
    ),
]
OVERNIGHT["impact"] = (
    IMPACT_BACKEND,
    pytest_runner(
        "Decision impact",
        "tests/regression/test_decision_impact_reference.py",
        "tests/api/test_api_decision_impact.py",
    ),
)


# ----------------------------------------------------------------------------------------------
# Reference cases (12 November 2026): ``--reference_cases-only``.
# ----------------------------------------------------------------------------------------------

REFERENCE_SERVICE = "src/mcda_studio/services/reference_case_service.py"
REFERENCE_CASES_BACKEND = [
    Mutation(
        "REFERENCE an ordinal gap is divided by n instead of n - 1",
        REFERENCE_SERVICE,
        "Fraction(steps, n - 1) if n > 1",
        "Fraction(steps, n) if n > 1",
    ),
    Mutation(
        "REFERENCE a missing rating counts as a gap of 0",
        REFERENCE_SERVICE,
        "            continue  # missing is not compared: never a gap of 0 or 1\n",
        "            gaps.append(Fraction(0))\n            shared_weights.append(weights[leaf])\n"
        "            continue\n",
    ),
    Mutation(
        "REFERENCE a missing rating counts as a gap of 1",
        REFERENCE_SERVICE,
        "            continue  # missing is not compared: never a gap of 0 or 1\n",
        "            gaps.append(Fraction(1))\n            shared_weights.append(weights[leaf])\n"
        "            continue\n",
    ),
    Mutation(
        "REFERENCE exactly the shared threshold is not comparable (<= for <)",
        REFERENCE_SERVICE,
        "if distance is None or fraction < threshold:",
        "if distance is None or fraction <= threshold:",
    ),
    Mutation(
        "REFERENCE the shared-count tie-break is reversed",
        REFERENCE_SERVICE,
        "ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))",
        "ranked.sort(key=lambda item: (-item[0], item[1], item[2]))",
    ),
    Mutation(
        "REFERENCE the case-id tie-break is reversed",
        REFERENCE_SERVICE,
        "ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))",
        "ranked.sort(key=lambda item: (-item[0], -item[1], [-ord(c) for c in item[2]]))",
    ),
    Mutation(
        "REFERENCE similarity is ordered ascending",
        REFERENCE_SERVICE,
        "ranked.sort(key=lambda item: (-item[0], -item[1], item[2]))",
        "ranked.sort(key=lambda item: (item[0], -item[1], item[2]))",
    ),
    Mutation(
        "REFERENCE distances are summed in floats instead of exact fractions",
        REFERENCE_SERVICE,
        "        distance = sum(gaps, Fraction(0)) / len(gaps)",
        "        distance = Fraction(sum(float(g) for g in gaps) / len(gaps))",
    ),
    Mutation(
        "REFERENCE the first gap stands in for the mean",
        REFERENCE_SERVICE,
        "        distance = sum(gaps, Fraction(0)) / len(gaps)",
        "        distance = gaps[0]",
    ),
    Mutation(
        "REFERENCE outcomes are included by default",
        REFERENCE_SERVICE,
        "    include_outcomes: bool = False,\n    exclude_same_id: bool = False,\n) -> ReferenceCasesResult:",
        "    include_outcomes: bool = True,\n    exclude_same_id: bool = False,\n) -> ReferenceCasesResult:",
    ),
    Mutation(
        "REFERENCE outcomes are never included",
        REFERENCE_SERVICE,
        "outcome=case.outcome if include_outcomes else None,",
        "outcome=None,",
    ),
    Mutation(
        "REFERENCE the snapshot guard refuses a source dated on the snapshot (< for <=)",
        REFERENCE_SERVICE,
        "elif source.date > case.snapshot_date:",
        "elif source.date >= case.snapshot_date:",
    ),
    Mutation(
        "REFERENCE the snapshot guard is skipped for undated sources",
        REFERENCE_SERVICE,
        "                if source.date is None:\n",
        "                if source.date is None:\n                    continue\n",
    ),
    Mutation(
        "REFERENCE an outcome dated before the snapshot is accepted",
        REFERENCE_SERVICE,
        "if case.outcome.as_of < case.snapshot_date:",
        "if False and case.outcome.as_of < case.snapshot_date:",
    ),
    Mutation(
        "REFERENCE an outcome on the snapshot day is refused (<= for <)",
        REFERENCE_SERVICE,
        "if case.outcome.as_of < case.snapshot_date:",
        "if case.outcome.as_of <= case.snapshot_date:",
    ),
    Mutation(
        "REFERENCE profile weights are not renormalised over the shared leaves",
        REFERENCE_SERVICE,
        "        distance /= total",
        "        distance /= 1",
    ),
    Mutation(
        "REFERENCE zero-weight leaves are compared",
        REFERENCE_SERVICE,
        "scale.is_labelled and global_weights[leaf] > 0:",
        "scale.is_labelled and global_weights[leaf] >= 0:",
    ),
    Mutation(
        "REFERENCE one too few cases are returned",
        REFERENCE_SERVICE,
        "cases=[item[3] for item in ranked[:k]],",
        "cases=[item[3] for item in ranked[: k - 1]],",
    ),
    Mutation(
        "REFERENCE a label off the scale is accepted",
        REFERENCE_SERVICE,
        "elif rating.label not in scale.labels:",
        "elif rating.label in []:",
    ),
    Mutation(
        "REFERENCE a one-step ordinal gap is grouped as further apart",
        REFERENCE_SERVICE,
        "if row.ordered and row.steps == 1:",
        "if row.ordered and row.steps == 0:",
    ),
    Mutation(
        "REFERENCE the own case is left out by default",
        REFERENCE_SERVICE,
        "    exclude_same_id: bool = False,\n) -> ReferenceCasesResult:",
        "    exclude_same_id: bool = True,\n) -> ReferenceCasesResult:",
    ),
    Mutation(
        "REFERENCE the own case is never left out",
        REFERENCE_SERVICE,
        "            if exclude_same_id and case.id == alt.id:",
        "            if False and case.id == alt.id:",
    ),
    Mutation(
        "REFERENCE every case is left out when asked, not only the own one",
        REFERENCE_SERVICE,
        "            if exclude_same_id and case.id == alt.id:",
        "            if exclude_same_id:",
    ),
    Mutation(
        "REFERENCE a left-out case is not reported",
        REFERENCE_SERVICE,
        "                excluded_case_ids=excluded,",
        "                excluded_case_ids=[],",
    ),
    Mutation(
        "REFERENCE the leave-out switch is not echoed",
        REFERENCE_SERVICE,
        "        exclude_same_id=exclude_same_id,\n    )\n    tree = project.tree()",
        "        exclude_same_id=False,\n    )\n    tree = project.tree()",
    ),
]
REFERENCE_PANEL = "frontend/src/components/ReferenceCasesPanel.tsx"
REFERENCE_CASES_FRONTEND = [
    Mutation(
        "REFERENCE the outcomes switch starts on",
        REFERENCE_PANEL,
        "const [outcomes, setOutcomes] = useState(false);",
        "const [outcomes, setOutcomes] = useState(true);",
    ),
    Mutation(
        "REFERENCE outcomes are requested without the switch",
        REFERENCE_PANEL,
        "referenceSet?.value, alternativeId, outcomes, leaveOut, signal);",
        "referenceSet?.value, alternativeId, true, leaveOut, signal);",
    ),
    Mutation(
        "REFERENCE the analysis runs on a set that failed validation",
        REFERENCE_PANEL,
        "useAnalysisRequest(key, valid && alternativeId !== null, load);",
        "useAnalysisRequest(key, referenceSet !== null && alternativeId !== null, load);",
    ),
    Mutation(
        "REFERENCE the interface reorders the engine's cases",
        REFERENCE_PANEL,
        "{row.cases.map(match =>",
        "{[...row.cases].reverse().map(match =>",
    ),
    Mutation(
        "REFERENCE one-step leaves are shown as further apart",
        REFERENCE_PANEL,
        '["one_step", "One step apart"],',
        '["one_step", "Further apart"],',
    ),
    Mutation(
        "REFERENCE the leave-out switch starts on",
        REFERENCE_PANEL,
        "const [leaveOut, setLeaveOut] = useState(false);",
        "const [leaveOut, setLeaveOut] = useState(true);",
    ),
    Mutation(
        "REFERENCE the own case is left out without the switch",
        REFERENCE_PANEL,
        "referenceSet?.value, alternativeId, outcomes, leaveOut, signal);",
        "referenceSet?.value, alternativeId, outcomes, true, signal);",
    ),
]
OVERNIGHT["reference_cases"] = (
    REFERENCE_CASES_BACKEND,
    pytest_runner(
        "Reference cases",
        "tests/unit/test_reference_cases.py",
        "tests/regression/test_reference_cases_reference.py",
        "tests/api/test_api_reference_cases.py",
    ),
)


# ----------------------------------------------------------------------------------------------
# First-round retrospective (13 November 2026): ``--first_round-only``.
# ----------------------------------------------------------------------------------------------

FIRST_ROUND_BUILD = "examples/nz_first_round_retrospective/build.py"
FIRST_ROUND_BACKEND = [
    Mutation(
        "FIRST ROUND a source before the lower boundary is accepted",
        FIRST_ROUND_BUILD,
        "when < STARTS[alt] and key not in OWN_SITES.get(alt, set())",
        "False",
    ),
    Mutation(
        "FIRST ROUND a source after the upper boundary is accepted",
        FIRST_ROUND_BUILD,
        "when > ENDS[alt] or",
        "False or",
    ),
    Mutation(
        "FIRST ROUND the final allowed day is refused",
        FIRST_ROUND_BUILD,
        "when > ENDS[alt] or",
        "when >= ENDS[alt] or",
    ),
    Mutation(
        "FIRST ROUND the earlier own-site exception is removed",
        FIRST_ROUND_BUILD,
        "key not in OWN_SITES.get(alt, set())",
        "True",
    ),
    Mutation(
        "FIRST ROUND another company's earlier site is accepted",
        FIRST_ROUND_BUILD,
        "key not in OWN_SITES.get(alt, set())",
        "key not in set().union(*OWN_SITES.values())",
    ),
    Mutation(
        "FIRST ROUND a market capture before the window is accepted",
        FIRST_ROUND_BUILD,
        "not STARTS[alt] <= date.fromisoformat(captured) <= ENDS[alt]",
        "date.fromisoformat(captured) > ENDS[alt]",
    ),
    Mutation(
        "FIRST ROUND future market years are accepted",
        FIRST_ROUND_BUILD,
        "if year > ANCHORS[alt].year:",
        "if False:",
    ),
    Mutation(
        "FIRST ROUND duplicate publishers get multiple votes",
        FIRST_ROUND_BUILD,
        "if not estimates or len(set(publishers)) != len(publishers):",
        "if not estimates:",
    ),
    Mutation(
        "FIRST ROUND the first publisher stands in for the median",
        FIRST_ROUND_BUILD,
        "size = float(median([Decimal(e[4]) for e in estimates]))",
        "size = float(Decimal(estimates[0][4]))",
    ),
    Mutation(
        "FIRST ROUND market size uses the mean instead of the median",
        FIRST_ROUND_BUILD,
        "size = float(median([Decimal(e[4]) for e in estimates]))",
        "size = float(sum(Decimal(e[4]) for e in estimates) / len(estimates))",
    ),
    Mutation(
        "FIRST ROUND one partner profile is silently dropped",
        FIRST_ROUND_BUILD,
        "weight_profiles=study.weight_profiles,",
        "weight_profiles=study.weight_profiles[:1],",
    ),
    Mutation(
        "FIRST ROUND mandate requirements are dropped",
        FIRST_ROUND_BUILD,
        "requirements=study.requirements,",
        "requirements=None,",
    ),
    Mutation(
        "FIRST ROUND sorting classes are dropped",
        FIRST_ROUND_BUILD,
        "sorting=study.sorting,",
        "sorting=None,",
    ),
    Mutation(
        "FIRST ROUND rubrics are no longer copied from the study",
        FIRST_ROUND_BUILD,
        '"rubrics.json": (STUDY / "rubrics.json").read_bytes(),',
        '"rubrics.json": b"{}\\n",',
    ),
    Mutation(
        "FIRST ROUND invalid sidecars are written instead of refused",
        FIRST_ROUND_BUILD,
        "if not report.valid:",
        "if False:",
    ),
    Mutation(
        "FIRST ROUND outcomes leak into the project",
        FIRST_ROUND_BUILD,
        'title="Looking back: five NZ first rounds (public information)",',
        "title=str(OUTCOMES),",
    ),
    Mutation(
        "FIRST ROUND an unsupported regulatory gap gets a favourable rating",
        FIRST_ROUND_BUILD,
        '        project = ps.set_performance(project, alt, "market_size", size)',
        '        project = ps.set_performance(project, alt, "regulatory_burden", "No approval required")\n'
        '        project = ps.set_performance(project, alt, "market_size", size)',
    ),
    Mutation(
        "FIRST ROUND the window exception covers every leaf of that source",
        FIRST_ROUND_BUILD,
        "    if leaf is not None and WINDOW_EXCEPTIONS.get((alt, leaf)) == key:",
        '    if WINDOW_EXCEPTIONS.get((alt, "stage")) == key:',
    ),
    Mutation(
        "FIRST ROUND the exception cell enters the reference set",
        FIRST_ROUND_BUILD,
        "            if (alt, leaf) in WINDOW_EXCEPTIONS:\n                continue",
        "            if False:\n                continue",
    ),
    Mutation(
        "FIRST ROUND absence-rule claims lose their basis label",
        FIRST_ROUND_BUILD,
        'PREFIX = {"observed": "", "absence": ABSENCE,',
        'PREFIX = {"observed": "", "absence": "",',
    ),
    Mutation(
        "FIRST ROUND a gap-rule cell silently overwrites a drafted rating",
        FIRST_ROUND_BUILD,
        "        if _leaf in CELLS[_alt]:",
        "        if False:",
    ),
    Mutation(
        "FIRST ROUND the build writes while a cell is missing",
        FIRST_ROUND_BUILD,
        "        if [leaf for leaf in leaves if leaf not in rated]:",
        "        if False:",
    ),
    Mutation(
        "FIRST ROUND the README counts every rating as observed",
        FIRST_ROUND_BUILD,
        '            counts[BASIS.get((alt, leaf), "observed")] += 1',
        '            counts["observed"] += 1',
    ),
]
OVERNIGHT["first_round"] = (
    FIRST_ROUND_BACKEND,
    pytest_runner("First-round study", "tests/regression/test_nz_first_round_retrospective.py"),
)


PORTABLE = "src/mcda_studio/methods/portable.py"
PORTABLE_BACKEND = [
    Mutation(
        "PORTABLE log drops the last polynomial term",
        PORTABLE,
        "r = z * (_LG1 + z * (_LG2 + z * (_LG3 + z * (_LG4 + z * (_LG5 + z * (_LG6 + z * _LG7))))))",
        "r = z * (_LG1 + z * (_LG2 + z * (_LG3 + z * (_LG4 + z * (_LG5 + z * _LG6)))))",
    ),
    Mutation(
        "PORTABLE log skips the reduction to [sqrt(1/2), sqrt(2))",
        PORTABLE,
        "    low = m < _SQRT_HALF\n",
        "    low = m < 0.5\n",
    ),
    Mutation(
        "PORTABLE log1p loses its branch for 1 + x rounding to 1",
        PORTABLE,
        "    exact = d == 0.0  # 1 + x rounded to 1",
        "    exact = d != d  # 1 + x rounded to 1",
    ),
    Mutation(
        "PORTABLE exp truncates x / ln 2 instead of rounding it",
        PORTABLE,
        "b.select(x < 0.0, -0.5, 0.5))",
        "b.select(x < 0.0, 0.0, 0.0))",
    ),
    Mutation(
        "PORTABLE lgamma uses Stirling's series without the upward shift",
        PORTABLE,
        "_STIRLING_FROM = 10.0",
        "_STIRLING_FROM = 1.0",
    ),
    Mutation(
        "PORTABLE lgamma of an integer is off by one factorial",
        PORTABLE,
        "math.factorial(int(value) - 1)",
        "math.factorial(int(value))",
    ),
    Mutation(
        "PORTABLE the interval exponential comes from the C library again",
        "src/mcda_studio/methods/smaa/intervals.py",
        "        return portable.exp(log_front) * _beta_continued_fraction(a, b, x) / a",
        '        return __import__("math").exp(log_front) * _beta_continued_fraction(a, b, x) / a',
    ),
    Mutation(
        "PORTABLE the interval log-gamma comes from the C library again",
        "src/mcda_studio/methods/smaa/intervals.py",
        "        portable.lgamma(a + b)\n",
        '        __import__("math").lgamma(a + b)\n',
    ),
    Mutation(
        "PORTABLE sensitivity sums with a BLAS product again",
        "src/mcda_studio/methods/mavt/sensitivity.py",
        "    return np.array(overall_values(prep.partial, _global_with(prep, node_id, t)), dtype=float)",
        "    return prep.partial @ _global_with(prep, node_id, t)",
    ),
    Mutation(
        "PORTABLE SMAA-2 overall values come from einsum again",
        "src/mcda_studio/methods/smaa/engine.py",
        "    return _columns_sum(\n"
        "        [partial[:, :, leaf] * weights[:, leaf, None] for leaf in range(partial.shape[2])]\n"
        "    )",
        '    return np.einsum("nal,nl->na", partial, weights)',
    ),
    Mutation(
        "PORTABLE SMAA-2 exponential draws use the C library's log1p again",
        "src/mcda_studio/methods/smaa/engine.py",
        "raw = -portable.log1p_array(-u)",
        "raw = -np.log1p(-u)",
    ),
    Mutation(
        "PORTABLE equal closest changes are chosen by rounding noise",
        "src/mcda_studio/services/screening_summary_service.py",
        "or (candidate.weight_change < current.weight_change - TIE_TOL)",
        "or (candidate.weight_change < current.weight_change)",
    ),
    Mutation(
        "PORTABLE the portable manifest still records the real system",
        "scripts/byte_identity.py",
        "    platform.system = lambda: system\n",
        "    pass\n",
    ),
]
OVERNIGHT["portable"] = (
    PORTABLE_BACKEND,
    pytest_runner(
        "Portable outputs",
        "tests/unit/test_portable_math.py",
        "tests/regression/test_portable_outputs.py",
        "tests/unit/test_smaa.py",
        "tests/unit/test_sensitivity.py",
        "tests/regression/test_screening_summary_reference.py",
        "tests/regression/test_smaa_reference.py",
    ),
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
    ap.add_argument("--study-only", action="store_true")
    ap.add_argument("--exemplars-only", action="store_true")
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--cleanup-only", action="store_true")
    ap.add_argument("--gallery-only", action="store_true")
    ap.add_argument("--showcase-only", action="store_true")
    for key in OVERNIGHT:
        ap.add_argument(f"--{key}-only", action="store_true")
    ap.add_argument(
        "--skip-control",
        action="store_true",
        help="skip the unmutated control (run it once, separately, with --control-only)",
    )
    ap.add_argument(
        "--control-only",
        action="store_true",
        help="run only the unmutated control and name every runner that fails",
    )
    ap.add_argument(
        "--shard",
        metavar="K/N",
        help="run only every N-th mutation starting at K (1-based), so N processes can split a "
        "campaign; each shard also runs the unmutated control",
    )
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
        + ([] if args.frontend_only else [(m, run_study) for m in STUDY_BACKEND])
        + ([] if args.frontend_only else [(m, run_exemplars) for m in EXEMPLARS_BACKEND])
        + ([] if args.frontend_only else [(m, run_summary) for m in SUMMARY_BACKEND])
        + (
            []
            if args.frontend_only
            else [(m, run_showcase_questions) for m in SHOWCASE_QUESTIONS_BACKEND]
        )
        + (
            []
            if args.frontend_only
            else [(m, run_fixture_freshness) for m in SHOWCASE_FIXTURE_BACKEND]
        )
        + (
            []
            if args.frontend_only
            else [
                (m, run_showcase_polish) for m in SHOWCASE_POLISH_BACKEND + SHOWCASE_DRAWER_BACKEND
            ]
        )
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
                + SUMMARY_FRONTEND
                + CLEANUP_FRONTEND
                + GALLERY_FRONTEND
                + SHOWCASE_FRONTEND
                + SHOWCASE_POLISH_FRONTEND
                + SHOWCASE_DRAWER_FRONTEND
                + SHOWCASE_VIEW_FRONTEND
                + SCREENING_PROFILES_FRONTEND
                + SCREENING_WHAT_IF_FRONTEND
                + REPORT_FRONTEND
                + IMPACT_FRONTEND
                + REFERENCE_CASES_FRONTEND
            ]
        )
    )
    if not args.frontend_only:
        for group, runner in OVERNIGHT.values():
            todo += [(m, runner) for m in group]  # type: ignore[misc]
        todo += [(m, run_screening_profiles) for m in SCREENING_PROFILES_BACKEND]
        todo += [(m, run_screening_what_if) for m in SCREENING_WHAT_IF_BACKEND]
    if not args.backend_only and not args.frontend_only:
        todo += [(m, run_clean_demo_guard) for m in CLEAN_DEMO_GUARD]
    for key, (group, _runner) in OVERNIGHT.items():
        if getattr(args, f"{key}_only"):
            extra = {
                "report": REPORT_FRONTEND,
                "impact": IMPACT_FRONTEND,
                "reference_cases": REFERENCE_CASES_FRONTEND,
            }.get(key, [])
            todo = [(m, r) for m, r in todo if m in group or m in extra]
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
    if args.study_only:
        todo = [(m, r) for m, r in todo if m in STUDY_BACKEND]
    if args.exemplars_only:
        todo = [(m, r) for m, r in todo if m in EXEMPLARS_BACKEND]
    if args.summary_only:
        todo = [(m, r) for m, r in todo if m in SUMMARY_BACKEND + SUMMARY_FRONTEND]
    if args.cleanup_only:
        todo = [(m, r) for m, r in todo if m in CLEANUP_FRONTEND]
    if args.gallery_only:
        todo = [(m, r) for m, r in todo if m in GALLERY_FRONTEND]
    if args.showcase_only:
        todo = [
            (m, r)
            for m, r in todo
            if m
            in SHOWCASE_QUESTIONS_BACKEND
            + SHOWCASE_FIXTURE_BACKEND
            + SHOWCASE_FRONTEND
            + SHOWCASE_POLISH_BACKEND
            + SHOWCASE_POLISH_FRONTEND
            + SHOWCASE_DRAWER_BACKEND
            + SHOWCASE_DRAWER_FRONTEND
            + SHOWCASE_VIEW_FRONTEND
            + CLEAN_DEMO_GUARD
            + SCREENING_PROFILES_BACKEND
            + SCREENING_PROFILES_FRONTEND
            + SCREENING_WHAT_IF_BACKEND
            + SCREENING_WHAT_IF_FRONTEND
        ]
    if args.models_only:
        todo = [(m, r) for m, r in todo if m in MODELS_BACKEND + MODELS_FRONTEND]
    if args.uncertainty_only:
        todo = [(m, r) for m, r in todo if m in UNCERTAINTY_BACKEND]
    if args.ahp_only:
        todo = [(m, r) for m, r in todo if m in AHP_BACKEND + AHP_FRONTEND]
    if args.promethee_only:
        todo = [(m, r) for m, r in todo if m in PROMETHEE_BACKEND + PROMETHEE_FRONTEND]
    if args.control_only:
        todo = []
    if args.shard:
        k, _, n = args.shard.partition("/")
        if not (k.isdigit() and n.isdigit() and 1 <= int(k) <= int(n)):
            raise SystemExit("--shard needs K/N with 1 <= K <= N")
        todo = todo[int(k) - 1 :: int(n)]
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
        control = {
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
            run_study if not args.frontend_only else None,
            run_exemplars if not args.frontend_only else None,
            run_summary if not args.frontend_only else None,
            run_showcase_questions if not args.frontend_only else None,
            run_fixture_freshness if not args.frontend_only else None,
            run_screening_profiles if not args.frontend_only else None,
            run_screening_what_if if not args.frontend_only else None,
            *([] if args.frontend_only else [runner for _, runner in OVERNIGHT.values()]),
            run_frontend if not args.backend_only else None,
            run_clean_demo_guard if not args.backend_only and not args.frontend_only else None,
        } - {None}
        failed = []
        if args.skip_control:
            control = set()
            print("control skipped (--skip-control)", flush=True)
        for r in sorted(control, key=lambda f: f.__name__):  # run every one: name what fails
            if not r(work):  # type: ignore[operator]
                failed.append(getattr(r, "label", r.__name__))
        base_ok = not failed
        if failed:
            print("control failures: " + ", ".join(failed), flush=True)
        print(f"baseline of the unmutated copy: {'passes' if base_ok else 'FAILS'}")
        print(f"{len(todo) - survivors} of {len(todo)} killed")
        return 0 if survivors == 0 and base_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
