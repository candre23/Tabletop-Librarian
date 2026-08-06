from __future__ import annotations

import argparse
import platform
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.rag.chunks import chunk_cache_status
from app.rag.embeddings import embedding_status
from app.rag.retrieve import retrieve_chunks

QUESTIONS = [
    "How many Character Points does a starting character get, and what are the restrictions on Masteries at character creation?",
    "Can a character try a skill they never purchased?",
    "How does Extra Weapon Attack work if I'm fighting with two weapons?",
    "What does the game call the maximum possible result of an ability's dice?",
    "How are Spell Points calculated?",
    "How do I calculate hit points and Resilience for a non-full-fledged monster?",
    "How do I keep a monster from having so many hit points that combat becomes tedious?",
    "What happens if I hit a Limbo Espirit with an ordinary sword?",
    "Which is more dangerous in a straight fight, Xoraxai or an Arch-Demon, and what makes each threatening?",
    "What are the PCs actually supposed to accomplish in The Crypt of Kur-Ka?",
    "Why is Borakr pretending to be injured in the fountain room?",
    "What happens if the party drank from the pond earlier in the adventure?",
    "What should the GM remember about marching order before running the crypt?",
    "If the PCs encounter the giant spider in Kur-Ka, what rules information would I need to run that fight?",
]

def fmt_score(value, digits=3):
    if value is None:
        return "n/a"
    return f"{value:.{digits}f}"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = args.output or Path(f"rag_diagnostic_results_{timestamp}.txt")

    chunks = chunk_cache_status()
    embeddings = embedding_status()

    lines = [
        "TABLETOP LIBRARIAN HYBRID RAG DIAGNOSTIC",
        "=" * 72,
        f"Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"Python: {sys.version.split()[0]}",
        f"Platform: {platform.platform()}",
        "",
        "CORPUS STATUS",
        "-" * 72,
        f"Documents: {chunks.get('documents', 0)}",
        f"Pages: {chunks.get('pages', 0)}",
        f"Chunks: {chunks.get('chunks', 0)}",
        f"Embedding model: {embeddings.get('model', 'unknown')}",
        f"Embedding backend: {embeddings.get('backend', 'unknown')}",
        f"Vectors: {embeddings.get('vectors', 0)}",
        f"Dimensions: {embeddings.get('dimensions', 0)}",
        "",
    ]

    total_start = time.perf_counter()

    for number, question in enumerate(QUESTIONS, start=1):
        start = time.perf_counter()
        try:
            results = retrieve_chunks(question, user_role="gm", limit=args.limit)
            error = None
        except Exception as exc:
            results = []
            error = f"{type(exc).__name__}: {exc}"

        elapsed = time.perf_counter() - start
        lines += [
            "",
            "=" * 72,
            f"QUESTION {number}",
            "=" * 72,
            question,
            "",
            f"Retrieval time: {elapsed:.3f} seconds",
            f"Results returned: {len(results)}",
        ]

        if error:
            lines += ["", f"ERROR: {error}"]
            continue

        if not results:
            lines += ["", "NO RESULTS"]
            continue

        for rank, result in enumerate(results, start=1):
            lines += [
                "",
                "-" * 72,
                f"RESULT {rank}",
                "-" * 72,
                f"Document: {result.get('display_name', '')}",
                f"Virtual folder: {result.get('folder_name', '')}",
                f"Page: {result.get('page', '')}",
                f"Chunk ID: {result.get('id', '')}",
                f"Hybrid score: {fmt_score(result.get('hybrid_score'), 6)}",
                f"Semantic score: {fmt_score(result.get('semantic_score'), 3)}",
                f"Lexical score: {fmt_score(result.get('lexical_score'), 3)}",
                "",
                result.get("text", "").strip(),
            ]

    total_elapsed = time.perf_counter() - total_start
    lines += [
        "",
        "=" * 72,
        "SUMMARY",
        "=" * 72,
        f"Questions: {len(QUESTIONS)}",
        f"Results requested per question: {args.limit}",
        f"Total diagnostic time: {total_elapsed:.3f} seconds",
        "",
    ]

    output.write_text("\n".join(lines), encoding="utf-8")
    print(f"Diagnostic complete: {output.resolve()}")
    print(f"Questions tested: {len(QUESTIONS)}")
    print(f"Total time: {total_elapsed:.1f} seconds")
    print("Upload the generated .txt file back to ChatGPT for analysis.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
