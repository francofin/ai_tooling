"""The pipeline must not call the retired FMP v3/v4 APIs."""
import pathlib


def test_no_v3_or_v4_urls():
    root = pathlib.Path(__file__).resolve().parent.parent
    files = [p for p in root.glob("*.py")]
    assert files
    for p in files:
        text = p.read_text(encoding="utf-8")
        assert "api/v3" not in text, p.name
        assert "api/v4" not in text, p.name
