import os

from app.config import load_env_file


def test_load_env_file_parses_and_respects_existing(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "\n"
        "NVDT_PLAIN=abc123\n"
        "export NVDT_EXPORTED=yes\n"
        'NVDT_DOUBLE="/certs/cert.pem /certs/key.pem"\n'
        "NVDT_SINGLE='has # hash'\n"
        "NVDT_INLINE=value # trailing comment\n"
        "NVDT_EMPTY=\n"
        "NVDT_KEEP=from-file\n"
        "not a valid line\n"
        "BAD-KEY=x\n",
        encoding="utf-8",
    )
    for key in ("NVDT_PLAIN", "NVDT_EXPORTED", "NVDT_DOUBLE", "NVDT_SINGLE", "NVDT_INLINE", "NVDT_EMPTY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("NVDT_KEEP", "from-shell")

    loaded = load_env_file(env)

    assert os.environ["NVDT_PLAIN"] == "abc123"
    assert os.environ["NVDT_EXPORTED"] == "yes"
    assert os.environ["NVDT_DOUBLE"] == "/certs/cert.pem /certs/key.pem"
    assert os.environ["NVDT_SINGLE"] == "has # hash"
    assert os.environ["NVDT_INLINE"] == "value"
    assert os.environ["NVDT_EMPTY"] == ""
    assert os.environ["NVDT_KEEP"] == "from-shell"  # real environment wins
    assert "NVDT_KEEP" not in loaded and "BAD-KEY" not in os.environ
    for key in loaded:
        monkeypatch.delenv(key)


def test_missing_file_is_ignored(tmp_path):
    assert load_env_file(tmp_path / "nope.env") == []
