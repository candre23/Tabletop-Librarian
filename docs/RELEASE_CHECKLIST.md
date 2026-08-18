# Release Checklist

Before publishing a release:

1. Confirm Server and AI Backend versions match the intended release.
2. Run `python scripts/validate_release.py`.
3. Run `python tests/run_regressions.py`.
4. Run `python scripts/validate_packaging.py`.
5. Validate the built-in Generic D20 System Pack with `python tools/validate_system_packs.py`.
6. Build Linux artifacts and verify checksums.
7. Build Windows artifacts on Windows and verify checksums.
8. Smoke-test install, upgrade, normal uninstall, and data preservation.
9. Verify Windows Server Manager start/stop behavior.
10. Verify CBR reading, OCR, initial embeddings, incremental embedding updates, and Server-to-Backend communication.
11. Confirm `LICENSE` and `THIRD_PARTY_NOTICES.md` are present in published artifacts.
12. Tag the release only after the tested artifacts are final.
