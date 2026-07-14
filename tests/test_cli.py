from pathlib import Path
from typer.testing import CliRunner
from nxopen_mcp.cli import app

runner = CliRunner()
FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_index_with_bad_path_fails_helpfully(tmp_path):
    result = runner.invoke(app, ["index", "--nx-path", str(tmp_path)])
    assert result.exit_code == 1
    assert "NXOpen" in result.output  # 告訴使用者在找什麼


def test_index_with_fake_embedder(tmp_path, monkeypatch):
    # 用環境變數讓 CLI 換成 fake embedder,避免測試下載 BGE-M3
    monkeypatch.setenv("NXOPEN_MCP_FAKE_EMBEDDER", "1")
    # fixture 目錄裡的 sample_doc.xml 改名規則不符,放一份符合的
    (tmp_path / "NXOpen.xml").write_bytes(
        (FIXTURE_DIR / "sample_doc.xml").read_bytes())
    db = tmp_path / "index.db"
    result = runner.invoke(
        app, ["index", "--nx-path", str(tmp_path), "--db", str(db)])
    assert result.exit_code == 0, result.output
    assert db.exists()


def test_index_with_workers_option(tmp_path, monkeypatch):
    monkeypatch.setenv("NXOPEN_MCP_FAKE_EMBEDDER", "1")
    (tmp_path / "NXOpen.xml").write_bytes(
        (FIXTURE_DIR / "sample_doc.xml").read_bytes())
    db = tmp_path / "index.db"
    result = runner.invoke(
        app, ["index", "--nx-path", str(tmp_path), "--db", str(db),
              "--workers", "2"])
    assert result.exit_code == 0, result.output
    from nxopen_mcp.retrieval.store import Store
    store = Store(db)
    cnt = store.conn.execute("SELECT count(*) c FROM dense_vec").fetchone()["c"]
    assert cnt == 3


def test_serve_without_index_gives_guidance(tmp_path):
    result = runner.invoke(app, ["serve", "--db", str(tmp_path / "nope.db")])
    assert result.exit_code == 1
    assert "nxopen-mcp index" in result.output  # 指引先跑 index


def test_fake_embedder_hook_missing_module_fails_helpfully(tmp_path, monkeypatch):
    monkeypatch.setenv("NXOPEN_MCP_FAKE_EMBEDDER", "1")
    import builtins
    real_import = builtins.__import__
    def block_tests_fakes(name, *a, **k):
        if name == "tests.fakes":
            raise ImportError("No module named 'tests'")
        return real_import(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", block_tests_fakes)
    (tmp_path / "NXOpen.xml").write_text("<doc><members/></doc>")
    result = runner.invoke(app, ["index", "--nx-path", str(tmp_path),
                                 "--db", str(tmp_path / "i.db")])
    assert result.exit_code == 1
    assert "NXOPEN_MCP_FAKE_EMBEDDER" in result.output
