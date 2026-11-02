# Analysis context and request safety

Every analytical view (Weights, Sensitivity, Scenarios, Results and the previews) works from one
shared **analysis context**. This page explains what the context contains, how it resolves the
weight profile and scenario, and how the frontend makes sure an answer is never shown under the
wrong context.

## What the context holds

`EditorStore.analysis` owns the viewed **scenario**, the explicitly chosen **profile** (if any) and
the selected **criterion**. It is separate from the editing session state.

- **Selections persist across tabs.** If an edit or undo removes a referenced object, the selection
  is reconciled.
- **Loading resets the view.** Loading or reloading a project returns to the base model with
  automatic profile resolution.
- **Base view is explicit.** It sends `null` scenario and profile IDs, so it never inherits a saved
  scenario default by accident.
- **The rest comes from the project.** The method and its nested parameters are taken from the
  project's analysis configuration.

### Profile precedence

The precedence is defined in `Project.resolve_profile`:

1. an explicitly selected profile;
2. otherwise the viewed scenario's profile, if it names one;
3. otherwise the project's first profile.

An ID that does not exist is an error (`UNKNOWN_REFERENCE`). It never silently falls back to
another profile.

## Request identity and stale responses

`resolveContext` combines the view with the current draft's fingerprint. `analysisKey` then covers:

- the entire configuration
- the revision
- the selected criterion
- the kind of analysis
- extra parameters such as a probe weight or a value-function candidate

Keys use canonical ordering, so property order alone never changes identity.

`useAnalysisRequest` protects the screen from stale answers:

- It debounces requests.
- It aborts superseded fetches.
- It rejects late successes and errors, even from a transport that ignores cancellation.
- After a failure it offers `retry`, which re-sends the same key with a fresh signal and shows
  loading meanwhile. A retry captured under an older key does nothing, so it can never revive an
  obsolete context. Retrying never edits the project, its fingerprint or its undo history.

Each response is also checked against what was asked for: fingerprint, configuration, scenario and
**resolved** profile. The resolved profile is checked on its own because, under automatic
resolution, the configuration can match while a different profile was resolved. While the context
changes, previous results are hidden, never relabelled as current.

## Looking never edits

None of these actions changes project data, undo history or the saved revision:

- selecting objects
- expanding explanations
- moving between tabs
- acknowledging a local-anchor review

Typed text and numbers stay in their input controls until committed. Measurement controls are
disabled while an edit is in flight, so overlapping whole-scale updates cannot restore an older
bound.

## Local anchors and swing review

If the set of alternatives changes in a model with `LOCAL_ANCHORS` warnings, the editor shows a
transient reminder. Swing judgements were made over ranges that may now have moved. You can jump to
Weights and acknowledge that you reviewed them.

- **Session-only.** The acknowledgement is not saved in the project.
- **The underlying warning stays.** The engine's local-anchor diagnostics remain after reload.
- **Nothing is supplied for you.** Every fingerprint change invalidates current analyses. No
  weights or missing measurements are ever filled in to make a model evaluable.

The in-app explanations cover scale types, swing ranges, hierarchical weights, local versus fixed
anchors, compensation and preferential independence. They describe the documented additive MAVT
model, not observed DECERNS behaviour.
