Tabletop Librarian Windows release builder
==========================================

Build-machine prerequisites:
- Windows x64
- Python 3.12 x64 from python.org (Python Launcher / py.exe enabled)
- Inno Setup 6 or 7
- 7-Zip x64
- Tesseract OCR x64
- Internet access while build environments download Python dependencies

Build both independent products from the repository root:

  powershell -ExecutionPolicy Bypass -File .\packaging\windows\build_releases.ps1

Outputs are written to:

  dist\windows\

The Server installer contains Tabletop Librarian Server, TTL Server Manager,
the Generic D20 System Pack, Windows OCR/CBR runtime dependencies, and release
license/documentation files. It does not contain the TTL Local AI Backend or a
llama.cpp model/runtime.

The AI Backend installer contains only the Backend Manager plus project
license/documentation files. The Manager downloads llama.cpp runtimes and GGUF
models after installation.
