#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]

import sys
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import app.knowledgebase as kb


def test_revision_tracker() -> None:
    original_dir = kb.STATE_DIR
    original_file = kb.STATE_FILE
    original_text = kb.TEXT_CACHE_DIR
    original_chunks = kb.CHUNK_CACHE_FILE
    original_vectors = kb.EMBEDDINGS_FILE
    original_meta = kb.EMBEDDING_META_FILE

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        kb.STATE_DIR = base / "kb"
        kb.STATE_FILE = kb.STATE_DIR / "state.json"
        kb.TEXT_CACHE_DIR = base / "text"
        kb.CHUNK_CACHE_FILE = base / "rag" / "chunks.json"
        kb.EMBEDDINGS_FILE = base / "rag" / "embeddings.npy"
        kb.EMBEDDING_META_FILE = base / "rag" / "embeddings.json"

        state = kb.knowledgebase_status()
        assert state["needs_update"] is True

        kb.mark_library_changed("Test document added")
        changed = kb.knowledgebase_status()
        assert changed["library_changed"] is True
        revision = changed["library_revision"]

        kb.mark_text_current()
        state = kb.knowledgebase_status()
        assert state["text_revision"] == revision
        assert state["chunks_current"] is False

        kb.mark_chunks_current()
        state = kb.knowledgebase_status()
        assert state["chunk_revision"] == revision
        assert state["chunks_current"] is True
        assert state["embeddings_current"] is False

        kb.mark_embeddings_current()
        clean = kb.knowledgebase_status()
        assert clean["embeddings_current"] is True
        assert clean["needs_update"] is False
        assert clean["library_changed"] is False

    kb.STATE_DIR = original_dir
    kb.STATE_FILE = original_file
    kb.TEXT_CACHE_DIR = original_text
    kb.CHUNK_CACHE_FILE = original_chunks
    kb.EMBEDDINGS_FILE = original_vectors
    kb.EMBEDDING_META_FILE = original_meta



def test_orphan_pruning() -> None:
    import app.search.extract as extract

    original_cache_dir = extract.TEXT_CACHE_DIR
    original_list_folders = extract.list_folders
    original_state_dir = kb.STATE_DIR
    original_state_file = kb.STATE_FILE
    original_kb_text = kb.TEXT_CACHE_DIR
    original_chunks = kb.CHUNK_CACHE_FILE
    original_vectors = kb.EMBEDDINGS_FILE
    original_meta = kb.EMBEDDING_META_FILE

    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cache_dir = base / "text"
        cache_dir.mkdir(parents=True)
        orphan = cache_dir / "orphan.json"
        orphan.write_text(json.dumps({
            "cache_version": 1,
            "path": "/removed/book.pdf",
            "pages": [],
            "characters": 0,
        }))

        extract.TEXT_CACHE_DIR = cache_dir
        extract.list_folders = lambda: []
        kb.STATE_DIR = base / "kb"
        kb.STATE_FILE = kb.STATE_DIR / "state.json"
        kb.TEXT_CACHE_DIR = cache_dir
        kb.CHUNK_CACHE_FILE = base / "rag" / "chunks.json"
        kb.EMBEDDINGS_FILE = base / "rag" / "embeddings.npy"
        kb.EMBEDDING_META_FILE = base / "rag" / "embeddings.json"

        summary = extract.build_text_cache()
        assert summary["documents_seen"] == 0
        assert not orphan.exists()

    extract.TEXT_CACHE_DIR = original_cache_dir
    extract.list_folders = original_list_folders
    kb.STATE_DIR = original_state_dir
    kb.STATE_FILE = original_state_file
    kb.TEXT_CACHE_DIR = original_kb_text
    kb.CHUNK_CACHE_FILE = original_chunks
    kb.EMBEDDINGS_FILE = original_vectors
    kb.EMBEDDING_META_FILE = original_meta

def test_structure() -> None:
    main = (ROOT / "app/main.py").read_text()
    nav = (ROOT / "app/templates/_global_nav.html").read_text()
    base = (ROOT / "app/templates/base.html").read_text()
    page = (ROOT / "app/templates/admin_knowledgebase.html").read_text()
    manager = (ROOT / "app/library/manager.py").read_text()
    extract = (ROOT / "app/search/extract.py").read_text()

    assert '@app.get("/admin/knowledgebase"' in main
    assert '@app.post("/admin/knowledgebase/update")' in main
    assert 'RedirectResponse("/admin/knowledgebase"' in main
    assert '<a href="/admin/knowledgebase">Knowledgebase</a>' in nav
    assert '>RAG</a>' not in nav
    assert '>Index</a>' not in nav

    assert "Library contents have changed - knowledgebase will need to be updated." in base
    assert "1. Text" in page
    assert "2. Chunks" in page
    assert "3. Embeddings" in page
    assert "Update Knowledgebase" in page
    assert 'initialUrl.searchParams.delete("message")' in page
    assert "sawEmbeddingRunning" in page
    assert "completedAfterUpdate" in page
    assert "window.location.reload()" in page
    assert "Extracted Text" in page
    assert "Context Chunks" in page
    assert "Semantic Embeddings" in page

    assert manager.count("mark_library_changed(") >= 4
    assert "mark_text_current()" in extract
    assert "cached_path not in seen_paths" in extract


def main() -> int:
    test_revision_tracker()
    test_orphan_pruning()
    test_structure()
    print("PASS: Knowledgebase Tools regression test")
    print("  consolidated GM navigation: OK")
    print("  library-change revision tracking: OK")
    print("  ordered text/chunks/embeddings stages: OK")
    print("  persistent global warning: OK")
    print("  orphaned text-cache pruning: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
