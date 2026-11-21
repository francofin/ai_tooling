from pipelines.verify_stable import sanitise


def test_strips_urls_and_keys():
    text = "boom https://example.com/stable/x?symbol=A&apikey=SECRET123 end"
    out = sanitise(text)
    assert "http" not in out and "SECRET123" not in out
    assert "<url>" in out and out.endswith("end")


def test_redacts_bare_apikey_and_keeps_plain_text():
    assert sanitise("bad apikey=abc&x=1") == "bad apikey=<redacted>&x=1"
    assert sanitise("no problem") == "no problem"
