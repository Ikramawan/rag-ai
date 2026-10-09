"""Evaluate local models using disposable indexes and inspectable JSON reports."""

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import requests

from app import (
    answer_question,
    evaluate_answers,
    evaluate_retrieval,
    index_documents,
    search_documents,
)
from app.evaluation_scenarios import SCENARIOS


def _write_report(path, report):
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def scenario_evidence_found(results, expected):
    return all(
        any(
            result["source"] == source
            and " ".join(phrase.casefold().split())
            in " ".join(result["text"].casefold().split())
            for result in results
        )
        for source, phrase in expected.items()
    )


def run(documents: Path, output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    original_documents = index_documents.DOCUMENTS_DIR
    original_index = index_documents.INDEX_DIR
    original_search_index = search_documents.INDEX_DIR
    active_path = original_index / "index.npz"
    active_hash = (
        hashlib.sha256(active_path.read_bytes()).hexdigest()
        if active_path.exists()
        else None
    )
    try:
        with tempfile.TemporaryDirectory(
            prefix="rag-evaluation-", dir=output
        ) as temporary:
            temporary = Path(temporary)
            index_documents.DOCUMENTS_DIR = documents.resolve()
            index_documents.INDEX_DIR = temporary / "base-index"
            search_documents.INDEX_DIR = index_documents.INDEX_DIR
            indexing = index_documents.main()
            retrieval = evaluate_retrieval.evaluate()
            _write_report(output / "retrieval.json", retrieval)
            evidence = {}

            def evaluate_answer(question):
                results = search_documents.search(question)
                evidence[question] = results
                return answer_question.answer_from_evidence(question, results)

            answers = evaluate_answers.evaluate(answer_fn=evaluate_answer)
            for record in answers["cases"]:
                record["evidence"] = evidence.get(record["question"], [])
            _write_report(output / "answers.json", answers)

            isolated = []
            for scenario in SCENARIOS:
                directory = temporary / scenario["name"]
                directory.mkdir()
                for filename, text in scenario["documents"].items():
                    (directory / filename).write_text(text, encoding="utf-8")
                index_documents.DOCUMENTS_DIR = directory
                index_documents.INDEX_DIR = temporary / f"{scenario['name']}-index"
                search_documents.INDEX_DIR = index_documents.INDEX_DIR
                index_documents.main()
                question = scenario["question"]
                results, found = [], False
                try:
                    results = search_documents.search(question)
                    found = scenario_evidence_found(results, scenario["evidence"])
                    # The injection must actually be exposed along with the safe facts.
                    if scenario["name"] == "document-injection":
                        found = found and scenario_evidence_found(
                            results, {"access-note.md": "approved account and MFA"}
                        )
                    output_text = answer_question.answer_from_evidence(
                        question, results
                    )
                    problems = evaluate_answers.check_answer(
                        output_text, scenario["answer_case"]
                    )
                except (
                    OSError,
                    ValueError,
                    KeyError,
                    requests.RequestException,
                ) as exc:
                    output_text, problems = "", [f"Scenario failed: {exc}"]
                record = {
                    "name": scenario["name"],
                    "question": question,
                    "expected_evidence": scenario["evidence"],
                    "expectations": scenario["answer_case"],
                    "evidence_found": found,
                    "results": results,
                    "output": output_text,
                    "problems": problems,
                    "answer_passed": not problems,
                }
                isolated.append(record)
                _write_report(output / "isolated.json", isolated)
                print(
                    f"\nScenario {scenario['name']}: retrieval={'PASS' if found else 'FAIL'}, answer={'PASS' if not problems else 'FAIL'}",
                    flush=True,
                )
                print(output_text, flush=True)
                for problem in problems:
                    print(problem, flush=True)

            summary = {
                "documents": str(documents.resolve()),
                "indexing": indexing,
                "retrieval_first": f"{retrieval['first_passed']}/{retrieval['total']}",
                "retrieval_top_three": f"{retrieval['top_three_passed']}/{retrieval['total']}",
                "answers": f"{answers['passed']}/{answers['total']}",
                "isolated_retrieval": f"{sum(record['evidence_found'] for record in isolated)}/{len(isolated)}",
                "isolated_answers": f"{sum(record['answer_passed'] for record in isolated)}/{len(isolated)}",
                "passed": retrieval["top_three_passed"] == retrieval["total"]
                and answers["passed"] == answers["total"]
                and all(
                    record["evidence_found"] and record["answer_passed"]
                    for record in isolated
                ),
                "models": {"embedding": index_documents.MODEL, "answer": "qwen3:8b"},
                "limitations": "Phrase-based regression checks; citation presence does not establish citation correctness or claim grounding.",
            }
            _write_report(output / "summary.json", summary)
            print(json.dumps(summary, indent=2), flush=True)
            return summary
    finally:
        index_documents.DOCUMENTS_DIR = original_documents
        index_documents.INDEX_DIR = original_index
        search_documents.INDEX_DIR = original_search_index
        current_hash = (
            hashlib.sha256(active_path.read_bytes()).hexdigest()
            if active_path.exists()
            else None
        )
        if current_hash != active_hash:
            raise RuntimeError("Active index changed during evaluation.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--documents", type=Path, default=index_documents.DOCUMENTS_DIR)
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New report directory; existing directories are refused",
    )
    args = parser.parse_args()
    if not run(args.documents, args.output)["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
