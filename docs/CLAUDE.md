<!--
[INPUT]: stable designs, reference constraints, and execution-phase plans under docs/
[OUTPUT]: lean, actionable documentation governance rules and navigation
[POS]: docs/ collaboration standard

[PROTOCOL]: Update this file only when docs structure, governance rules, or entry responsibilities change; never record timelines.
-->

# docs/ directory guide

## Directory responsibilities

- `docs/CLAUDE.md`: the single navigation and governance entry for docs.
- `docs/AGENTS.md`: a symbolic link to `docs/CLAUDE.md` for agents.md compatibility.
- `docs/reference/*`: stable platform constraints, collaboration rules, and verification procedures.
- `docs/design/*`: adopted, stable product, architecture, and feature design facts.
- `docs/plans/*`: execution-phase design docs, implementation plans, and current to-dos.

## Structure constraints

- The first level of `docs/` contains only `CLAUDE.md`, `AGENTS.md`, `reference/`, `design/`, and `plans/`.
- `docs/reference` stays a flat set of Markdown documents.
- `docs/design` currently organizes long-lived core designs under `core/`; add subdirectories only when a clearly new domain appears.
- `docs/plans` is the execution workspace; before completion, adopted stable facts must be written back to `docs/design` or `docs/reference`.
- No `archive/` directories or duplicated index files; prefer deleting outdated content — history lives in Git.

## Lifecycle and write-back

- Allowed statuses: `draft`, `active`, `in_progress`, `completed`.
- `completed` documents are de-logged by default, keeping only final conclusions, constraints, and the verification baseline.
- Prefer one fact source per topic; avoid sibling documents describing the same thing.
- Before deleting a plan document, confirm its still-valid facts have been written back.

## Current navigation

- Repository positioning and boundaries: `reference/repository-context.md`
- Collaboration, commits, and delivery: `reference/collaboration-and-delivery.md`
- Weekly progress management core design: `design/core/weekly-progress-management.md`
- Initial design and next-phase to-dos: `plans/2026-07-16-initial-skill-design.md`
