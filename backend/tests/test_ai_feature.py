"""
backend/tests/test_ai_feature.py

Tests the AI feature's fallback guarantee -- the operator-facing summary
must NEVER raise or return something unusable, regardless of API key
presence, network failures, or malformed responses.
"""

from app.services.ai_feature import _template_fallback, summarize_ticket

SAMPLE_SPAN_TICKET = {
    "incident_type": "span", "upstream_pole": "P-1", "downstream_pole": "P-2",
    "affected_pole_count": 5, "pincode": "560001",
    "topology_status": "VERIFIED", "confidence": 0.95,
}

SAMPLE_DT_TICKET = {
    "incident_type": "dt", "dt_id": "D-0001",
    "affected_pole_count": 36, "pincode": None,
    "topology_status": "INFERRED", "confidence": 0.60,
}


def test_template_fallback_never_raises_for_span():
    result = _template_fallback(SAMPLE_SPAN_TICKET)
    assert "P-1" in result
    assert "P-2" in result
    assert "5" in result


def test_template_fallback_handles_missing_pincode():
    result = _template_fallback(SAMPLE_DT_TICKET)
    assert "D-0001" in result
    assert "PIN" not in result  # no pincode present, must not fabricate one


def test_summarize_ticket_falls_back_without_api_key(monkeypatch):
    monkeypatch.setattr("app.services.ai_feature.ANTHROPIC_API_KEY", None)
    result = summarize_ticket(SAMPLE_SPAN_TICKET)
    assert result["source"] == "template"
    assert len(result["summary"]) > 0


def test_summarize_ticket_falls_back_on_network_error(monkeypatch):
    monkeypatch.setattr("app.services.ai_feature.ANTHROPIC_API_KEY", "fake-key-for-test")

    def raise_connection_error(*args, **kwargs):
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr("app.services.ai_feature.requests.post", raise_connection_error)

    result = summarize_ticket(SAMPLE_SPAN_TICKET)
    assert result["source"] == "template"
    assert "P-1" in result["summary"]


def test_summarize_ticket_falls_back_on_malformed_response(monkeypatch):
    monkeypatch.setattr("app.services.ai_feature.ANTHROPIC_API_KEY", "fake-key-for-test")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"unexpected": "shape"}  # missing "content" key entirely

    monkeypatch.setattr("app.services.ai_feature.requests.post", lambda *a, **k: FakeResponse())

    result = summarize_ticket(SAMPLE_SPAN_TICKET)
    assert result["source"] == "template"


def test_summarize_ticket_uses_ai_on_success(monkeypatch):
    monkeypatch.setattr("app.services.ai_feature.ANTHROPIC_API_KEY", "fake-key-for-test")

    class FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"content": [{"text": "Span fault, 5 poles dark, high confidence."}]}

    monkeypatch.setattr("app.services.ai_feature.requests.post", lambda *a, **k: FakeResponse())

    result = summarize_ticket(SAMPLE_SPAN_TICKET)
    assert result["source"] == "ai"
    assert result["summary"] == "Span fault, 5 poles dark, high confidence."