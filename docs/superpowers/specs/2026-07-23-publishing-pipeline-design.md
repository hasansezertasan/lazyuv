# Publishing pipeline (PyPI) + hatch-vcs + MIT — Design Spec

**Date:** 2026-07-23
**Status:** Draft
**Follows:** the CI workflow (#10). First of three staged PRs adopting
`hasansezertasan/cobo`'s release setup; this one delivers the **publishing pipeline**
(the ROADMAP "Distribution → 1.0" gate). Toolchain (PR 2) and community config (PR 3)
follow.

## Problem

lazyuv is feature-complete for the project surface and CI-gated, but not installable —
there is no way to `uv tool install lazyuv` from PyPI, and no automated release. This PR
makes lazyuv build- and release-ready with an automated, review-gated pipeline mimicking
cobo: conventional-commit-driven release PRs, PyPI **trusted publishing** (OIDC, no
stored token), and GitHub releases.

## Decision & scope

Inherit cobo's release machinery, adapted to lazyuv, **dropping the Docker jobs** (lazyuv
is a CLI/TUI tool, not a GitHub Action). In scope:

1. **hatch-vcs versioning** — the version is derived from the git tag at build time (as
   cobo does), so release-please owns the number and the build reads it. `pyproject`
   becomes `dynamic = ["version"]`; a `_version.py` is generated (gitignored).
2. **Publish metadata** — `license = "MIT"`, authors/maintainers, keywords, classifiers,
   and `[project.urls]`, so the PyPI page is complete.
3. **MIT LICENSE** file.
4. **release-please** config + manifest (`release-type: python`, drafts, force-tag).
5. **`release.yml`** — release-please → build → publish-pypi → publish-release →
   reconcile (all action SHAs pinned; the Docker + prerelease-Docker jobs removed).
6. **`check-pr-title.yml`** — conventional PR-title lint (matches the repo's norm and
   what release-please consumes).

The existing `ci.yml` (`lint + test`) is **unchanged** here.

**Non-goals (deferred to PR 2/3):** the tox/prek/multi-tool lint+type toolchain, the
multi-OS CI matrix, coverage gates, renovate/codecov, and community templates.

## Versioning (`pyproject.toml`)

```toml
[build-system]
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[project]
# version removed; now dynamic
dynamic = ["version"]

[tool.hatch.version]
source = "vcs"
fallback-version = "0.0.0"          # covers a checkout with no tags (e.g. fresh CI)

[tool.hatch.version.raw-options]
version_scheme = "only-version"     # use the tag as-is (release-please owns bumps)
local_scheme = "no-local-version"   # PyPI rejects local versions

[tool.hatch.build]
hooks.vcs.version-file = "src/lazyuv/_version.py"
```

`src/lazyuv/_version.py` is generated at build time → add to `.gitignore`. lazyuv's own
`__init__`/runtime does not import it (the tool never displays its *own* version except
via the uv-version subtitle, which is uv's version, unrelated), so no runtime change.

## Publish metadata (`pyproject.toml`)

`license = "MIT"`; `authors`/`maintainers` = Hasan Sezer Taşan
<hasansezertasan@gmail.com>; `keywords` (uv, tui, terminal, textual, cli,
developer-tools, dependency-management, packaging, …); `classifiers` (Environment ::
Console, Intended Audience :: Developers, License :: OSI Approved :: MIT License,
Programming Language :: Python :: 3.14, Typing :: Typed, Topic :: Software Development,
Topic :: System :: Installation/Setup, Topic :: Utilities); `[project.urls]`
homepage/source/issues/changelog/releasenotes/documentation → the lazyuv repo.

## LICENSE

MIT text at repo root, copyright Hasan Sezer Taşan.

## release-please

- `.github/release-please-config.json`: `release-type: python`, `draft: true`,
  `force-tag-creation: true`, `include-component-in-tag: false`,
  `bump-minor-pre-major: true` — identical shape to cobo.
- `.github/.release-please-manifest.json`: `{".": "0.1.0"}` (lazyuv's current version).

With `release-type: python`, release-please tracks/bumps the version in the manifest and
creates the tag; hatch-vcs reads that tag to stamp the build. No file has a static
version to edit (pyproject is dynamic).

## Workflows (`.github/workflows/`, all actions SHA-pinned)

- **`release.yml`** — adapted from cobo verbatim in structure, minus `publish-docker`:
  `release-please` → `build-package` (`actions/checkout` `fetch-depth: 0` so hatch-vcs
  sees the tag; `uv build --no-sources`; upload `dist-pypi` artifact) →
  `publish-pypi` (`id-token: write`, `environment: publish`, `uv publish
  --trusted-publishing always`) → `publish-release` (download artifacts, `gh release
  upload` + un-draft, prerelease/latest flags) → `reconcile` (close the phantom
  next-release PR and re-dispatch). The prerelease `is_prerelease` gate is kept (inert
  until a beta channel is enabled), minus its Docker consumer.
- **`check-pr-title.yml`** — `amannn/action-semantic-pull-request` + sticky comment,
  verbatim from cobo.

## Testing / verification

No application code changes, so the existing suite is unaffected. Verify:
- `uv sync --locked` still clean; `uv run --no-sync pytest -q` → **233 pass**; `uvx
  ruff@0.15.22 check src tests` clean.
- `uvx validate-pyproject pyproject.toml` passes (metadata well-formed).
- `uv build` produces `dist/lazyuv-<version>-py3-none-any.whl` + sdist; inspect that the
  wheel carries the metadata (name, license, entry point `lazyuv`). With no tag it uses
  `fallback-version`; a throwaway `git tag v0.1.0` build stamps `0.1.0` (proves hatch-vcs
  reads tags) — tag deleted after.
- `actionlint` (via `uvx actionlint`) on the two new workflows — clean.

## Manual steps (owner; documented in the PR, required before a real publish)

1. **PyPI trusted publisher** for project `lazyuv`: owner `hasansezertasan`, repo
   `lazyuv`, workflow filename `release.yml`, environment `publish`.
2. **GitHub Environment** named `publish` on the repo.

Until both exist, the pipeline builds and drafts correctly but the publish step is a
no-op-that-would-fail — safe, since it only runs on a release-please release commit.

## Open questions

- First real release: tag `v0.1.0` (current) or graduate straight to `v1.0.0`? Draft
  keeps `0.1.0` in the manifest; the 1.0 decision is a follow-up once PR 2/3 land.
