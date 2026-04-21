# Python Agent Perfect Parity Contract (v1)

## Contract ID
- `2026-04-18-perfect-parity-v1`

## Purpose
- Freeze the parity report schema used for final capability reconciliation against local Claude Code.
- Enforce a stable scoring and failure taxonomy contract to prevent metric drift.

## Top-Level Required Fields
- `contract_version`
- `generated_at`
- `total`
- `passed`
- `failed`
- `success_rate`
- `capability_success_rate`
- `average_score`
- `quality_metrics`
- `quality_dimension_matrix`
- `capability_matrix`
- `failure_breakdown`
- `failure_taxonomy`
- `environment_failure_rate`
- `runtime_failure_rate`
- `capability_failure_rate`
- `details`
- `unresolved_gaps`

## Quality Metrics Contract
- `quality_metrics.decision_quality_score`
- `quality_metrics.edit_correctness_score`
- `quality_metrics.verification_pass_rate`
- `quality_metrics.weighted_quality_score`

### Quality Dimension Matrix
- `quality_dimension_matrix.decision_quality`
- `quality_dimension_matrix.edit_correctness`
- `quality_dimension_matrix.verification`
- `quality_dimension_matrix.weighted_quality`

Each dimension must expose:
- `score`
- `threshold`
- `passed`

Default threshold policy:
- All dimensions use `0.90`.

## Capability Matrix Contract
Required domains:
- `tooling`
- `orchestration`
- `recovery`
- `verification`
- `subagent`
- `semantic_navigation`
- `semantic_refactor`
- `mcp`

Each domain must expose:
- `covered`
- `passed`
- `failed`
- `success_rate`

## Failure Taxonomy Contract
Required taxonomy categories:
- `model`
- `tool`
- `orchestration`
- `semantic`
- `verification`
- `environment`

Per failed detail:
- Must include `failure_taxonomy_category`.

## Acceptance Gates
- Parity suite:
  - `success_rate >= 0.90`
  - `weighted_quality_score >= 0.90`
- Stability:
  - Three consecutive parity runs satisfy both thresholds.
  - Three consecutive full test runs remain green.

