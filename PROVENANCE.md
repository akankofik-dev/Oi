# PROVENANCE.md — oi-agent source reconstruction

## What this repository is

This is a **reconstruction** of the `oi-agent` 1.0.2 source tree, created as
Fase 1 ("Source of Truth") of the OI Standalone 1.0.0 effort. It is NOT the
original development repository.

## Source material

- **Artifact**: `oi_agent-1.0.2.tar.gz` (PyPI sdist)
- **SHA-256**: `ae5898c4e0f373bd73ba47ac4aea1620256540214534a61ca64401c357f46509`
- **Size**: 16,432,958 bytes
- **Downloaded**: 2026-10-10 from `https://pypi.org/pypi/oi-agent/json`
  (`files.pythonhosted.org` distribution URL)
- **Declared upstream repository** (per sdist `pyproject.toml` / `PKG-INFO`):
  `https://github.com/akankofik-dev/Oi` — returns HTTP 404 (publicly
  unreachable as of 2026-10-10; not a rename, since GitHub issues no
  redirect; cannot distinguish private vs deleted without owner credentials)

## Verification method

1. The sdist tarball was extracted and committed as the single root commit (tag `v1.0.2`). Excluding this `PROVENANCE.md` file (the only
   addition), the committed tree is byte-identical to the tarball contents
   (verified with `diff -r` against a fresh extraction).
2. A wheel was rebuilt from this tree with `python -m build --wheel
   --no-isolation` (hatchling backend, as declared in `pyproject.toml`).
3. The rebuilt wheel was compared file-by-file (SHA-256 per file, excluding
   `dist-info` metadata) against the published
   `oi_agent-1.0.2-py3-none-any.whl` from PyPI: **2154 files, 0 missing,
   0 differing**. The published wheel is fully reproducible from this tree.

### Note on `src/oi/dashboard/`

The sdist's own `.gitignore` excludes `src/oi/dashboard/**` — evidence that
upstream treated the dashboard as a **generated build artifact**, not
versioned source (hatch ships it via `[tool.hatch.build] artifacts`).
To keep this reconstruction byte-identical to the *shipped* sdist, the
dashboard assets were force-added (`git add -f`) despite the ignore rule.

## What was NOT recovered

The following existed in the original development repository (evidenced by
references inside the sdist) but are **absent** here and were not fabricated:

- Git history (commits, branches, tags beyond the `v1.0.2` tag created here)
- `tests/` (pytest config in `pyproject.toml` references `testpaths = ["tests"]`)
- `docs/` (including `docs/installation-audit-issues.md`, referenced in a
  `pyproject.toml` comment)
- CI / release workflow configuration
- Issue tracker, pull requests, and review history

## Explicit non-claims

- This reconstruction is **not claimed to be identical in all aspects** to
  the lost repository — only the shipped source tree is preserved.
- No git history was invented; the single reconstruction commit is authored
  as `oi-standalone-reconstruction`, not as the original authors.
- License and upstream attribution are preserved unchanged (`LICENSE`:
  MIT, Copyright (c) 2026 OrcaKit / Oi contributors (akankofik-dev)).

## Sibling components (not reconstructed — original git repos retained)

- `oi-harness` 1.0.1 — tag `v1.0.1` (`41e29593997c26fb7aba7b59d7d66b7f78b465fc`)
- `oi-gateway` 1.0.0 — tag `v1.0.0` (`fd488d25adef81e987d6966e42c8d45833d2d5f4`)
- `oi-memory` 1.0.0 — tag `v1.0.0` (`904af43fe8493b8b5149f7f1085145a09360f190`)
- `oi-browser` 1.0.0 — tag `v1.0.0` (`cc752ee2fbbb306f7d6b4d139b1044ae0c1372c1`)

See `../SOURCES.md` for the full source-of-truth record.
