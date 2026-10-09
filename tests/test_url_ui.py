from pathlib import Path

from streamlit.testing.v1 import AppTest

from app import url_documents


def button(app, label):
    return next(item for item in app.button if item.label == label)


def test_url_preview_save_and_duplicate_feedback(tmp_path, monkeypatch):
    snapshot = {
        "version": 1,
        "source_url": "https://docs.example.com/vpn",
        "resolved_url": "https://docs.example.com/vpn",
        "fetched_at": "2026-10-09T12:00:00+00:00",
        "text": "Synthetic prerequisites: approved account and MFA.",
    }
    monkeypatch.setattr(url_documents, "fetch_page", lambda url: snapshot)
    save = url_documents.save_snapshot
    monkeypatch.setattr(
        url_documents, "save_snapshot", lambda value, directory: save(value, tmp_path)
    )
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app/ui.py").run()
    assert not app.exception
    app.text_input[0].set_value(snapshot["source_url"]).run()
    button(app, "Fetch preview").click().run()
    assert any(snapshot["text"] == item.value for item in app.text)
    assert not list(tmp_path.rglob("*.url.json"))
    button(app, "Save URL snapshot").click().run()
    assert len(list(tmp_path.rglob("*.url.json"))) == 1
    assert any("Rebuild the index" in item.value for item in app.warning)
    button(app, "Fetch preview").click().run()
    button(app, "Save URL snapshot").click().run()
    assert any("already saved" in item.value for item in app.error)
    assert not app.exception


def test_changed_url_and_fetch_failure_clear_stale_preview(monkeypatch):
    def fail_fetch(url):
        raise ValueError("No readable documentation")

    monkeypatch.setattr(url_documents, "fetch_page", fail_fetch)
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app/ui.py").run()
    app.session_state["url_preview"] = (
        "https://docs.example.com/old",
        {"text": "Old evidence"},
    )
    app.text_input[0].set_value("https://docs.example.com/new").run()
    assert all(item.label != "Save URL snapshot" for item in app.button)
    button(app, "Fetch preview").click().run()
    assert "url_preview" not in app.session_state
    assert any("No readable documentation" in item.value for item in app.error)
    assert not app.exception
