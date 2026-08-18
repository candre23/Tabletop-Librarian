# Building Release Artifacts

Server and Local AI Backend are built as independent products.

## Linux

The supported/tested release target is Ubuntu 26.04 LTS x86_64.

From the repository root:

```bash
python3 packaging/linux/build_releases.py
```

Outputs are written under `dist/linux/`:

- `TTL-Server-Linux-x86_64-<version>.tar.gz`
- `TTL-AI-Linux-x86_64-<version>.tar.gz`
- `SHA256SUMS.txt`
- `LINUX_RELEASE_MANIFEST.txt`

## Windows

Windows artifacts must be built on Windows; PyInstaller is not used as a cross-compiler.

Build-machine prerequisites:

- Python 3.12 x64;
- Inno Setup 6/7;
- 7-Zip x64 (copied into the Server payload for CBR/RAR support);
- Tesseract OCR x64 (copied into the Server payload).

Build both products:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_releases.ps1
```

Expected outputs under `dist\windows\`:

- `TTL-Server-Windows-x64-<version>.exe`
- `TTL-AI-Windows-x64-<version>.exe`
- `SHA256SUMS.txt`
- `WINDOWS_RELEASE_MANIFEST.txt`

Rebuild only the Server with:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\rebuild_server.ps1
```

Recompile only installer wrappers with:

```powershell
powershell -ExecutionPolicy Bypass -File .\packaging\windows\recompile_installers.ps1
```

## Release contents

The Server release includes the built-in `generic_d20` System Pack. Test fixtures under `tests/fixtures/` are never included.

Release artifacts must carry the project license and third-party notices. The Windows Server also carries upstream license material for redistributed runtime components.
