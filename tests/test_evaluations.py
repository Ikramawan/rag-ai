import pytest
import requests

from app import evaluate_answers, evaluate_retrieval
from app.evaluation_scenarios import SCENARIOS
from scripts.run_evaluations import scenario_evidence_found


def test_source_list_cannot_satisfy_answer_requirements_or_citation():
    case = {"required": ["MFA"], "forbidden": [], "citation": True}
    problems = evaluate_answers.check_answer(
        "Unknown.\n\nRetrieved sources:\n[1] MFA guide", case
    )
    assert "Missing: MFA" in problems
    assert "Missing citation" in problems


def test_numbered_procedure_must_preserve_order():
    case = {
        "required": [],
        "forbidden": [],
        "citation": False,
        "ordered_steps": ["approval", "request", "provision", "mfa"],
    }
    good = "1. Obtain approval.\n2. Submit request.\n3. Wait for provisioning.\n4. Enable MFA."
    assert not evaluate_answers.check_answer(good, case)
    bad = "1. Enable MFA.\n2. Submit request.\n3. Obtain approval.\n4. Wait for provisioning."
    assert evaluate_answers.check_answer(bad, case)


def test_retrieval_distinguishes_first_result_from_top_three_evidence():
    results = [
        {"source": "wrong.md", "chunk_id": "wrong.md:0:0", "text": "Other evidence"},
        {
            "source": "right.md",
            "chunk_id": "right.md:0:0",
            "text": "Target: 1 business\nhour",
        },
    ]
    report = evaluate_retrieval.evaluate(
        cases=[("Target?", "right.md", "1 business hour")],
        search_fn=lambda *args, **kwargs: results,
    )
    assert report["first_passed"] == 0
    assert report["top_three_passed"] == 1
    assert report["cases"][0]["results"] == results


def test_evaluation_errors_are_recorded_as_failures_and_do_not_stop_later_cases():
    calls = 0

    def fake_answer(question):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise requests.Timeout("Simulated timeout")
        return "MFA [1]"

    cases = [
        {"question": "Question", "required": ["MFA"], "forbidden": [], "citation": True}
    ] * 2
    report = evaluate_answers.evaluate(cases=cases, answer_fn=fake_answer)
    assert report["passed"] == 1
    assert report["total"] == 2
    assert "Simulated timeout" in report["cases"][0]["problems"][0]


def test_conflict_scenario_requires_both_evidence_sources():
    expected = {"a.md": "7 days", "b.md": "21 days"}
    results = [{"source": "a.md", "text": "7 days"}]
    assert not scenario_evidence_found(results, expected)
    results.append({"source": "b.md", "text": "21 days"})
    assert scenario_evidence_found(results, expected)


def test_ambiguity_check_accepts_scoped_paraphrase_but_rejects_unscoped_answer():
    case = next(
        scenario["answer_case"]
        for scenario in SCENARIOS
        if scenario["name"] == "ambiguous-role"
    )
    valid = "A Viewer can read release records or incident summaries, depending on the specific role (Harbor Viewer or Beacon Viewer) [1]. The application has not been specified."
    assert not evaluate_answers.check_answer(valid, case)
    invalid = "The default application is Harbor. A Viewer reads release records [1]."
    problems = evaluate_answers.check_answer(invalid, case)
    assert "Missing: Beacon" in problems
    assert "Missing: incident summaries" in problems
    assert "Unexpected: default application is Harbor" in problems


def test_runner_restores_directories_and_cleans_temporary_indexes_on_error(
    tmp_path, monkeypatch
):
    from app import index_documents, search_documents
    from scripts import run_evaluations

    original_documents = tmp_path / "original-documents"
    original_index = tmp_path / "original-index"
    original_search = tmp_path / "original-search"
    monkeypatch.setattr(index_documents, "DOCUMENTS_DIR", original_documents)
    monkeypatch.setattr(index_documents, "INDEX_DIR", original_index)
    monkeypatch.setattr(search_documents, "INDEX_DIR", original_search)

    def fail_index():
        raise requests.ConnectionError("Ollama unavailable")

    monkeypatch.setattr(index_documents, "main", fail_index)
    output = tmp_path / "reports"
    with pytest.raises(requests.ConnectionError, match="Ollama unavailable"):
        run_evaluations.run(tmp_path / "evaluation-documents", output)
    assert index_documents.DOCUMENTS_DIR == original_documents
    assert index_documents.INDEX_DIR == original_index
    assert search_documents.INDEX_DIR == original_search
    assert list(output.iterdir()) == []


def test_answer_timeout_does_not_erase_successful_scenario_retrieval(
    tmp_path, monkeypatch
):
    import json
    from types import SimpleNamespace

    from app import answer_question, index_documents
    from scripts import run_evaluations

    documents = tmp_path / "documents"
    documents.mkdir()
    (documents / "ordinary.md").write_text(
        "Synthetic ordinary evidence.", encoding="utf-8"
    )

    def fake_embed(url, *, json, timeout):
        inputs = json["input"]
        count = len(inputs) if isinstance(inputs, list) else 1
        return SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"embeddings": [[1.0, 2.0] for _ in range(count)]},
        )

    def fail_answer(*args, **kwargs):
        raise requests.Timeout("Answer timed out")

    monkeypatch.setattr(index_documents.requests, "post", fake_embed)
    monkeypatch.setattr(answer_question, "answer_from_evidence", fail_answer)
    output = tmp_path / "reports"
    summary = run_evaluations.run(documents, output)
    isolated = json.loads((output / "isolated.json").read_text())
    assert summary["isolated_retrieval"] == "3/3"
    assert summary["isolated_answers"] == "0/3"
    assert all(record["results"] and record["evidence_found"] for record in isolated)
    assert all("Answer timed out" in record["problems"][0] for record in isolated)
    assert not any(path.is_dir() for path in output.iterdir())
