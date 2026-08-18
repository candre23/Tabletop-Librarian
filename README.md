# Tabletop Librarian

Tabletop Librarian (TTL) is a self-hosted tabletop RPG library, rules reference, character manager, and AI-assisted game resource server.

Version 1.0.0 consists of two independent products:

- **Tabletop Librarian Server**: hosts the library, readers, users, characters, System Packs, search, OCR, knowledgebase, and AI/RAG interface.
- **TTL Local AI Backend**: a separate llama.cpp manager that can run on the same computer or another machine on the LAN.

The Server can also use hosted OpenAI-compatible providers instead of the Local AI Backend.

## Highlights

- Browser-based bookshelf with physical library sources and uploads.
- PDF, CBZ, CBR, image, TXT, and Markdown readers.
- Persistent OCR derivatives for scanned PDFs and comic archives.
- Incremental extracted-text, chunk, and semantic-embedding knowledgebase.
- Basic and Advanced Ask modes with citations to retrieved source material.
- Player and GM accounts with visibility-aware library and character access.
- System-neutral character engine driven by portable `.ttlsys` System Packs.
- Guided character creation, calculated rules, limits, advancement, temporary effects, and `.ttlchar` import/export.
- Built-in **Generic D20** System Pack derived from SRD 5.2.1 under CC BY 4.0.
- Independent local llama.cpp Backend Manager with hardware-aware CUDA/Vulkan/CPU choices and curated model/runtime downloads.
- Windows x64 and Linux x86_64 release tooling.

## Supported release platforms

### Server

- **Windows x64**: native installer; tested during the 1.0 release cycle.
- **Linux x86_64**: officially tested on **Ubuntu 26.04 LTS**. Other distributions are community-supported and may require adaptation.

### Local AI Backend

- Windows x64.
- Linux x86_64, officially tested on Ubuntu 26.04 LTS.

A GPU is strongly recommended for local LLM inference. CPU mode exists as a functional fallback but can be very slow.

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

The repository includes the original SRD 5.2.1 PDF and a generic cover image under [`docs/reference/`](docs/reference/). Generic D20 is intentionally named and presented as a generic 5E-compatible System Pack rather than an official Dungeons & Dragons product.

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

## License

Tabletop Librarian source code and original project material are released under the **Unlicense**. See [LICENSE](LICENSE).

The SRD 5.2.1, Generic D20's SRD-derived material, and third-party dependencies retain their own licenses. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Repository

https://github.com/candre23/Tabletop-Librarian
