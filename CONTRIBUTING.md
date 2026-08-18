# Contributing

Contributions are welcome.

- Keep the Server and Local AI Backend independently installable.
- Do not commit runtime user data, models, caches, logs, or release build outputs.
- Put test-only System Packs under `tests/fixtures/system_packs/`, not `data/system_packs/`.
- Run `python tests/run_regressions.py` and `python scripts/validate_release.py` before submitting changes.
- Update documentation when changing user-facing behavior, System Pack format, installer behavior, or release prerequisites.

By contributing original material to this repository, you agree that your contribution may be distributed under the repository's Unlicense dedication. Do not contribute third-party material unless you have the right to do so and preserve any required license/attribution notices.
