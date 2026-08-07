from __future__ import annotations

import platform
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ai.provider import chat_completion, provider_settings_for_ui
from app.rag.embeddings import embedding_status
from app.rag.retrieve import available_rag_scope, retrieve_chunks

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

FOLDER_NAME = "Eldritch"
DOCUMENT_NAMES = {
    "Eldritch Core Rules Book",
    "Eldritch Eldritch Monsters",
    "Eldritch The Crypt of Kur-Ka",
}

SYSTEM_PROMPT = (
    "You are Tabletop Librarian, a tabletop RPG rules and reference assistant. "
    "Answer the user's question using only the supplied source passages. "
    "Do not invent rules, facts, names, or interpretations not supported by them. "
    "If the passages are insufficient, say what cannot be established. "
    "When making factual claims, cite the supporting passages using bracketed "
    "source numbers such as [1] or [2]. Keep the answer focused and practical."
)


def build_scope() -> list[str]:
    scope = available_rag_scope(
        "gm",
        selected_folder=FOLDER_NAME,
        selected_documents=[],
    )

    selected = [
        item["path"]
        for item in scope["documents"]
        if item["display_name"] in DOCUMENT_NAMES
    ]

    found = {
        item["display_name"]
        for item in scope["documents"]
        if item["display_name"] in DOCUMENT_NAMES
    }

    missing = sorted(DOCUMENT_NAMES - found)

    if missing:
        raise RuntimeError(
            "Could not find required benchmark document(s): "
            + ", ".join(missing)
        )

    return selected


def format_source(index: int, source: dict) -> str:
    page = source.get("page")
    page_label = f", page {page}" if page else ""
    return (
        f"[{index}] {source['display_name']}{page_label}\n"
        f"{source.get('text', '').strip()}"
    )


def main() -> int:
    ai = provider_settings_for_ui()

    if not ai.get("configured"):
        print("AI provider is not configured.", file=sys.stderr)
        return 1

    document_paths = build_scope()
    embedding = embedding_status()

    started_all = time.perf_counter()
    generated = datetime.now()

    report = []
    report.append("TABLETOP LIBRARIAN RAG + LLM ANSWER BENCHMARK")
    report.append("=" * 88)
    report.append(f"Generated: {generated.isoformat(timespec='seconds')}")
    report.append(f"Python: {platform.python_version()}")
    report.append(f"Platform: {platform.platform()}")
    report.append("")
    report.append("SCOPE")
    report.append("-" * 88)
    report.append(f"Virtual folder: {FOLDER_NAME}")
    for name in sorted(DOCUMENT_NAMES):
        report.append(f"  - {name}")
    report.append("")
    report.append("AI PROVIDER")
    report.append("-" * 88)
    report.append(f"Base URL: {ai.get('base_url')}")
    report.append(f"Model: {ai.get('model')}")
    report.append(f"Temperature: {ai.get('temperature')}")
    report.append(f"Max output tokens: {ai.get('max_tokens')}")
    report.append("")
    report.append("EMBEDDINGS")
    report.append("-" * 88)
    report.append(f"Model: {embedding.get('model_label')}")
    report.append(f"Backend: {embedding.get('backend')}")
    report.append(f"Vectors: {embedding.get('vectors')}")
    report.append(f"Dimensions: {embedding.get('dimensions')}")
    report.append("")

    successes = 0
    failures = 0
    total_retrieval = 0.0
    total_generation = 0.0

    for number, question in enumerate(QUESTIONS, start=1):
        print(f"[{number:02d}/{len(QUESTIONS)}] {question}", flush=True)

        report.append("")
        report.append("=" * 88)
        report.append(f"QUESTION {number}")
        report.append("=" * 88)
        report.append(question)
        report.append("")

        try:
            retrieval_started = time.perf_counter()
            sources = retrieve_chunks(
                question,
                "gm",
                limit=8,
                folder_scope=FOLDER_NAME,
                document_paths=document_paths,
            )
            retrieval_time = time.perf_counter() - retrieval_started
            total_retrieval += retrieval_time

            report.append(f"Retrieval time: {retrieval_time:.3f} sec")
            report.append(f"Sources returned: {len(sources)}")
            report.append("")

            if not sources:
                raise RuntimeError("No source passages returned.")

            source_blocks = [
                format_source(index, source)
                for index, source in enumerate(sources, start=1)
            ]

            user_prompt = (
                f"Question:\n{question}\n\n"
                "Source passages:\n\n"
                + "\n\n".join(source_blocks)
            )

            generation_started = time.perf_counter()
            completion = chat_completion(
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ]
            )
            generation_time = time.perf_counter() - generation_started
            total_generation += generation_time

            successes += 1

            report.append(f"Generation time: {generation_time:.3f} sec")
            report.append(f"Model returned: {completion.get('model')}")
            usage = completion.get("usage") or {}
            if usage:
                report.append(
                    "Usage: "
                    f"prompt={usage.get('prompt_tokens', 'n/a')}, "
                    f"completion={usage.get('completion_tokens', 'n/a')}, "
                    f"total={usage.get('total_tokens', 'n/a')}"
                )

            report.append("")
            report.append("ANSWER")
            report.append("-" * 88)
            report.append(completion["content"])
            report.append("")
            report.append("RETRIEVED SOURCES")
            report.append("-" * 88)

            for index, source in enumerate(sources, start=1):
                page = source.get("page")
                score = source.get("hybrid_score")
                report.append(
                    f"[{index}] {source['display_name']} | "
                    f"page {page if page is not None else 'n/a'} | "
                    f"hybrid {score:.6f}" if isinstance(score, float)
                    else f"[{index}] {source['display_name']} | "
                         f"page {page if page is not None else 'n/a'}"
                )
                excerpt = " ".join(source.get("text", "").split())
                report.append(excerpt[:650])
                report.append("")

        except Exception as exc:
            failures += 1
            report.append("ERROR")
            report.append("-" * 88)
            report.append(str(exc))
            report.append("")
            print(f"    ERROR: {exc}", flush=True)

    elapsed_all = time.perf_counter() - started_all

    report.append("")
    report.append("=" * 88)
    report.append("SUMMARY")
    report.append("=" * 88)
    report.append(f"Questions: {len(QUESTIONS)}")
    report.append(f"Successful answers: {successes}")
    report.append(f"Failures: {failures}")
    report.append(f"Total retrieval time: {total_retrieval:.3f} sec")
    report.append(f"Total generation time: {total_generation:.3f} sec")
    report.append(f"Total benchmark time: {elapsed_all:.3f} sec")

    if successes:
        report.append(
            f"Average generation time: {total_generation / successes:.3f} sec"
        )

    stamp = generated.strftime("%Y%m%d_%H%M%S")
    output = Path(f"rag_answer_benchmark_eldritch_{stamp}.txt")
    output.write_text("\n".join(report) + "\n", encoding="utf-8")

    print("")
    print(f"Benchmark complete: {successes} successful, {failures} failed.")
    print(f"Report: {output.resolve()}")

    return 0 if failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
