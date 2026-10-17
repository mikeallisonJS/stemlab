# Changelog fragments

Every PR that touches the engine (`stemlab/`), the app (`app/src/`, `app/scripts/`,
`app/electron-builder.cjs`, `app/package.json`), `recipes/`, `third_party/` or
`pyproject.toml` must add one file here. CI enforces it (`changelog-check`).
The full flow is in the README under Releases.

- **Name**: `<issue>.<type>.md`, e.g. `12.feature.md`, or `+<slug>.<type>.md` for a
  change with no issue, e.g. `+rocm-detect.bugfix.md`.
- **Types**: `breaking`, `feature`, `bugfix` render into the changelog. `chore` and
  `docs` do not render; they exist so housekeeping PRs pass the check without
  polluting the release notes.
- **Body**: one or two sentences, user-facing voice, present tense: what changed
  for the person running the app, not how.

Fragments are consumed (deleted) by the release PR that ships them.
