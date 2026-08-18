# Tabletop Librarian

Tabletop Librarian (TTL) is a self-hosted tabletop RPG library, rules reference, character manager, and AI-assisted game resource server.

Version 1.0.0 consists of two independent applications:

- **Tabletop Librarian Server**: hosts the library, readers, users, characters, System Packs, search, OCR, knowledgebase, and AI/RAG interface.
- **TTL Local AI Backend**: an optional llama.cpp server to provide local inference, packaged with a basic GUI for ease of operation.

The Server can also use Gemini or OpenAI-compatible APIs for cloud inference instead of the Local AI Backend.

## Highlights

- Browser-based bookshelf with physical library sources and uploads.
- PDF, CBZ, CBR, image, TXT, and Markdown readers.
- Persistent OCR derivatives for scanned PDFs and comic archives.
- Incremental extracted-text, chunk, and semantic-embedding knowledgebase.
- Basic and Advanced Ask modes with citations to retrieved source material.
- Player and GM accounts with visibility-aware library and character access.
- Guided character creation, calculated rules, limits, advancement, temporary effects, and `.ttlchar` import/export.
- Independent local llama.cpp Backend Manager with hardware-aware CUDA/Vulkan/CPU choices and curated model/runtime downloads.
- System-neutral character engine driven by portable `.ttlsys` System Packs.
- Bundled generic D20 system pack derived from SRD 5.2.1 under CC BY 4.0.
- Additional system packs published here: https://github.com/candre23/TTL_System_Packs


## Supported release platforms

- **Windows x64**: Native installers
- **Linux x86_64**: Automated install scripts tested on Ubuntu 26.04. Other versions or distros may or may not work without some manual fiddling on your part.

A GPU is strongly recommended for local LLM inference. CPU mode exists as a functional fallback but will be very slow.

## Quick start

Download the Server release for your platform from GitHub Releases and install it. The Server defaults to port **8080** and the Local AI Backend defaults to **8081**; both installers allow alternate ports when needed.

After first launch:

1. Create the initial GM account.
2. Add one or more physical library folders or upload documents.
3. Open **Knowledgebase** and build extracted text, chunks, and semantic embeddings if you want RAG/AI answers.
4. Configure an AI provider. This can be the separate TTL Local AI Backend on the same machine/LAN or a hosted provider.
5. Create characters from the built-in Generic D20 System Pack or import additional `.ttlsys` packs.

See [Installation](docs/INSTALLATION.md) and the [User Guide](docs/USER_GUIDE.md) for details.

## Documentation

- [Installation](docs/INSTALLATION.md)
- [User Guide](docs/USER_GUIDE.md)
- [Local AI Backend](docs/AI_BACKEND.md)
- [System Pack specification](docs/SYSTEM_PACKS.md)
- [Advanced Ask pipeline presets](docs/PIPELINES.md)
- [OCR workflow](docs/OCR.md)
- [Development](docs/DEVELOPMENT.md)
- [Building releases](docs/BUILDING_RELEASES.md)
- [Release checklist](docs/RELEASE_CHECKLIST.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## Built-in Generic D20 reference

The repository includes the original SRD 5.2.1 (CC BY 4.0) PDF in [`docs/reference/`](docs/reference/).  The Generic D20 system pack is based on this document and installed by default.  It is presented as a generic 5E-compatible example pack and is not an official Dungeons & Dragons product.

## Source development

Python 3.11+ is required. A normal development setup is:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
python run.py
```

The development server defaults to `http://127.0.0.1:8080`/all interfaces on port 8080. Runtime data lives under `data/`, logs under `logs/`, and caches under `cache/` unless overridden by environment variables.

Run the regression suite with:

```bash
python tests/run_regressions.py
```

## AI & Safety Disclaimer
The code and documentation included in this project is primarily vibeslop. The human writing this sentence in particular can barely code and doesn't really understand how any of this works. It Works On My Machine and hasn't caused my genitals to explode, but your mileage may vary. I make absolutely no guarantee as to the safety or security of the contents of this project. Use at your own risk. Or don't.  The TTL web server utilizes fairly basic authentication and is not hardened against attacks.  It has not been tested in any way for proper security.  This software is intended for LAN or secure proxy use only.


## License

Tabletop Librarian source code and original project material are released under the **Unlicense**. See [LICENSE](LICENSE).

The SRD 5.2.1, Generic D20's SRD-derived material, and third-party dependencies retain their own licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).


