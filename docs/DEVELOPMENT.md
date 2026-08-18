# Development

## Environment

Python 3.11+ is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python run.py
```

The source run uses in-tree runtime locations by default:

- `data/`
- `cache/`
- `logs/`

Packaged releases override those paths through environment variables.

## Repository layout

- `app/` - Server application.
- `ai_backend/` - independent Local AI Backend source.
- `data/system_packs/` - System Packs intentionally bundled with release builds.
- `pipelines/` - shipped Advanced Ask pipeline presets.
- `packaging/` - Linux/Windows installer and release builders.
- `tests/` - regression scripts and test-only fixtures.
- `tools/` - diagnostics/benchmarks/validators.
- `scripts/` - source/release maintenance helpers.
- `docs/` - user/developer documentation and licensed reference material.

## Tests

Run all retained regression scripts:

```bash
python tests/run_regressions.py
```

Run one or more groups:

```bash
python tests/run_regressions.py --group system_packs --group regression
```

`tests/fixtures/system_packs/ttl_test_minimal` is a **test-only fixture** and is deliberately outside `data/system_packs/`, so it cannot be seeded or included in release payloads.

## Source bundles

Create a clean development handoff bundle with:

```bash
python scripts/create_source_bundle.py
```

The bundler excludes Git metadata, virtual environments, runtime user data, caches, models, build outputs, backups, and generated bundle metadata.

## Runtime path overrides

The Server recognizes:

- `TTL_DATA_DIR`
- `TTL_CACHE_DIR`
- `TTL_LOG_DIR`
- `TTL_HOST`
- `TTL_PORT`

These make packaged installs relocatable while preserving convenient in-tree paths during development.

## Adding a System Pack

See [SYSTEM_PACKS.md](SYSTEM_PACKS.md). Only packs placed under `data/system_packs/` are candidates for release bundling. Development/test fixtures belong under `tests/fixtures/`.
