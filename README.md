# Tabletop Librarian v0.3.3

Self-hosted tabletop RPG library, rules helper, and character resource server.

## Phase 0.3 work

- RAG context chunks with page/source metadata
- OpenVINO CPU semantic embeddings
- all-MiniLM-L6-v2 embedding model
- Locally saved converted OpenVINO model
- Hybrid lexical + semantic retrieval
- Folder- and file-scoped hybrid retrieval
- Permission-aware retrieval for GM/player access

## Run

```bash
source .venv/bin/activate
python run.py
```

For first-time semantic setup:

1. Build the Search Index text cache.
2. Build the RAG corpus.
3. Build Embeddings from the RAG Corpus page.

The first embedding build requires internet access to obtain the model.
