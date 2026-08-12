from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import sys

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import app.rag.chunks as chunks_mod
import app.rag.embeddings as emb_mod


class FakeModel:
    def __init__(self):
        self.encoded_texts: list[str] = []

    def encode(self, texts, **kwargs):
        rows = []
        for text in texts:
            text = str(text)
            self.encoded_texts.append(text)
            seed = sum(ord(ch) for ch in text)
            vector = np.asarray([
                (seed % 97) + 1,
                (seed % 89) + 2,
                (seed % 83) + 3,
                (seed % 79) + 4,
            ], dtype=np.float32)
            vector /= np.linalg.norm(vector)
            rows.append(vector)
        return np.vstack(rows)


def main() -> None:
    with TemporaryDirectory() as temp_text:
        temp = Path(temp_text)
        rag_dir = temp / "rag"
        rag_dir.mkdir()
        chunk_file = rag_dir / "chunks.json"
        embedding_file = rag_dir / "embeddings.npy"
        meta_file = rag_dir / "embeddings.json"

        doc_a = str((temp / "a.pdf").resolve())
        doc_b = str((temp / "b.pdf").resolve())
        for path in (Path(doc_a), Path(doc_b)):
            path.write_bytes(b"pdf")

        cached = {
            doc_a: {
                "filename": "a.pdf", "display_name": "A", "type": "PDF",
                "pages": [{"page": 1, "text": "Alpha rules text " * 20}],
            },
            doc_b: {
                "filename": "b.pdf", "display_name": "B", "type": "PDF",
                "pages": [{"page": 1, "text": "Beta rules text " * 20}],
            },
        }

        chunks_mod.CHUNK_CACHE_FILE = chunk_file
        chunks_mod.RAG_CACHE_DIR = rag_dir
        chunks_mod.list_folders = lambda: [{"name": "Test"}]
        chunks_mod.scan_folder = lambda folder, generate_covers=False: {
            "documents": [
                {"path": doc_a, "type": "PDF"},
                {"path": doc_b, "type": "PDF"},
            ]
        }
        chunks_mod.load_cached_text = lambda path: cached.get(str(path.resolve()))
        chunks_mod.mark_chunks_current = lambda: None
        chunks_mod.invalidate_chunks = lambda: None

        first = chunks_mod.build_chunk_cache(force=True)
        assert first["documents"] == 2
        old_chunks = chunks_mod.load_chunks()
        old_b = [chunk for chunk in old_chunks if chunk["path"] == doc_b]
        assert old_b

        emb_mod.RAG_CACHE_DIR = rag_dir
        emb_mod.EMBEDDINGS_FILE = embedding_file
        emb_mod.EMBEDDING_META_FILE = meta_file
        emb_mod.load_chunks = chunks_mod.load_chunks
        emb_mod.mark_embeddings_current = lambda: None
        emb_mod.invalidate_embeddings = lambda: None
        emb_mod.selected_model = lambda: {
            "key": "test", "label": "Test", "model": "fake/model", "description": "test"
        }
        model = FakeModel()
        emb_mod._load_model = lambda: model

        full = emb_mod.build_embeddings(force=True)
        assert full["full_rebuild"] is True
        full_vectors = np.load(embedding_file).copy()
        full_meta = json.loads(meta_file.read_text())
        b_ids = {chunk["id"] for chunk in old_b}
        b_vectors_before = {
            chunk_id: full_vectors[index].copy()
            for index, chunk_id in enumerate(full_meta["chunk_ids"])
            if chunk_id in b_ids
        }

        model.encoded_texts.clear()
        cached[doc_a] = {
            "filename": "a.pdf", "display_name": "A", "type": "PDF",
            "pages": [{"page": 1, "text": "Alpha CHANGED rules text " * 20}],
        }
        delta = chunks_mod.build_chunk_cache(changed_paths={doc_a})
        assert delta["full_rebuild"] is False
        new_chunks = chunks_mod.load_chunks()
        new_b = [chunk for chunk in new_chunks if chunk["path"] == doc_b]
        assert [chunk["id"] for chunk in new_b] == [chunk["id"] for chunk in old_b]

        inc = emb_mod.build_embeddings(
            changed_paths={doc_a},
            removed_chunk_ids=set(delta["removed_chunk_ids"]),
            force=False,
        )
        assert inc["full_rebuild"] is False
        assert inc["reused"] == len(new_b)
        assert inc["embedded_new"] == len([chunk for chunk in new_chunks if chunk["path"] == doc_a])
        assert model.encoded_texts
        assert all("Beta rules text" not in text for text in model.encoded_texts)

        inc_vectors = np.load(embedding_file)
        inc_meta = json.loads(meta_file.read_text())
        for index, chunk_id in enumerate(inc_meta["chunk_ids"]):
            if chunk_id in b_vectors_before:
                np.testing.assert_allclose(inc_vectors[index], b_vectors_before[chunk_id])

        model.encoded_texts.clear()
        deletion = chunks_mod.build_chunk_cache(removed_paths={doc_a})
        remaining = chunks_mod.load_chunks()
        assert remaining and all(chunk["path"] == doc_b for chunk in remaining)
        delete_emb = emb_mod.build_embeddings(
            changed_paths=set(),
            removed_chunk_ids=set(deletion["removed_chunk_ids"]),
            force=False,
        )
        assert delete_emb["embedded_new"] == 0
        assert delete_emb["reused"] == len(remaining)
        assert not model.encoded_texts

    print("incremental knowledgebase tests passed")


if __name__ == "__main__":
    main()
