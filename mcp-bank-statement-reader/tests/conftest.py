import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every test gets its own empty data folder, never the real ~/.bank-reader."""
    home = tmp_path / "bank-reader-home"
    monkeypatch.setenv("BANK_READER_HOME", str(home))
    return home


@pytest.fixture
def sample_pdf(tmp_path):
    from bank_reader.sample import make_sample_statement

    return make_sample_statement(tmp_path / "sample_statement.pdf")
