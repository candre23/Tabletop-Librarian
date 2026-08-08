# Tabletop Librarian v0.3.5

Self-hosted tabletop RPG library, rules helper, and character resource server.

## Phase 0.3 work

- RAG context chunks with page/source metadata
- OpenVINO CPU semantic embeddings
- all-MiniLM-L6-v2 embedding model
- Locally saved converted OpenVINO model
- Hybrid lexical + semantic retrieval
- Folder- and file-scoped hybrid retrieval
- Stopword filtering, rare-term lexical reranking, and stronger exact-match scoring
- Permission-aware retrieval for GM/player access

## Run

```bash
source .venv/bin/activate
python run.py
```

For first-time semantic setup:

1. Open Knowledgebase Tools and build/refresh Extracted Text.
2. Build the RAG corpus.
3. Build Semantic Embeddings from Knowledgebase Tools.

The first embedding build requires internet access to obtain the model.

- Selectable embedding models: Fast, Balanced, and Quality


## Knowledgebase maintenance

GM navigation includes a single **Knowledgebase** tool page for extracted text, context chunks, semantic embeddings, retrieval testing, and local AI provider settings. Knowledgebase Tools tracks these stages in dependency order and warns when library contents have changed since the last complete build.


### Recursive physical sources

Adding a directory as a physical library source automatically registers that
directory and each descendant directory as an independent physical source.
This makes nested documents available immediately while still allowing any
subfolder source to be removed separately later.


### Physical source scan progress

Adding a physical directory now displays an immediate progress overlay while
TTL discovers descendant source folders and scans the resulting library
contents. The indicator is intentionally indeterminate because source-folder
discovery and document inspection do not have a reliable total-work estimate
before the scan begins.
