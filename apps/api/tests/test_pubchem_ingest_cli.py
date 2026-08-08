"""Testes do CLI de operação da ingestão PubChem (Incremento 2.3, Rodada 2, Fase H).

Chama `scripts.pubchem_ingest_cli.main()` diretamente (mesmo padrão de
test_geometry_dispatcher_continuous.py para scripts/geometry_dispatcher.py) com sys.argv
monkeypatchado. O CLI usa `SessionLocal` (conexão própria, nova) em produção -- mas nos
testes, `SessionLocal` é monkeypatchado para devolver a MESMA sessão/transação de `db_session`
(mesmo espírito do dependency override `get_db -> db_session` usado pela fixture `client`):
dados criados via `db_session`/factories só são visíveis DENTRO da mesma transação/conexão --
uma conexão verdadeiramente independente NUNCA veria dados ainda não comitados de forma durável
ao banco (ver docstring de test_geometry_job_concurrency.py, que por isso usa
`biomatcad_api.db.SessionLocal` direto para provar exclusão mútua REAL entre conexões
distintas -- o padrão inverso do que se quer aqui)."""
from __future__ import annotations

import json

import scripts.pubchem_ingest_cli as cli_mod
from biomatcad_api.models.scientific_data import RedistributionStatus, ScientificSource, SourceType
from biomatcad_api.models.scientific_ingestion import (
    IngestionRequestStatus,
    ScientificIngestionRequest,
)
from tests.factories import create_admin, create_researcher


class _NoCloseSessionProxy:
    """Encaminha tudo para a sessão real, exceto `close()` -- o teste (via fixture
    `db_session`) continua dono do ciclo de vida da conexão/transação."""

    def __init__(self, session):
        self._session = session

    def __getattr__(self, name):
        return getattr(self._session, name)

    def close(self) -> None:
        pass


def _make_source(db_session) -> ScientificSource:
    source = ScientificSource(
        name="PubChem", source_type=SourceType.DATABASE, redistribution_status=RedistributionStatus.UNKNOWN
    )
    db_session.add(source)
    db_session.commit()
    return source


def _run_cli(monkeypatch, db_session, args: list[str]) -> int:
    monkeypatch.setattr(cli_mod, "SessionLocal", lambda: _NoCloseSessionProxy(db_session))
    monkeypatch.setattr("sys.argv", ["pubchem_ingest_cli.py"] + args)
    return cli_mod.main()


def test_cli_rejects_more_than_10_cids(monkeypatch, capsys, db_session):
    admin = create_admin(db_session, email="cli-admin1@biomatcad.example")
    source = _make_source(db_session)
    args = ["--requested-by-email", admin.email, "--source-id", source.id]
    for i in range(1, 12):
        args += ["--cid", str(i)]
    rc = _run_cli(monkeypatch, db_session, args)
    assert rc == 2
    captured = capsys.readouterr()
    assert "máximo" in captured.err


def test_cli_rejects_unknown_user(monkeypatch, capsys, db_session):
    source = _make_source(db_session)
    rc = _run_cli(
        monkeypatch, db_session,
        ["--requested-by-email", "nao-existe@biomatcad.example", "--source-id", source.id, "--cid", "2244"],
    )
    assert rc == 2
    assert "não encontrado" in capsys.readouterr().err


def test_cli_rejects_non_admin_user(monkeypatch, capsys, db_session):
    researcher = create_researcher(db_session, email="cli-researcher1@biomatcad.example")
    source = _make_source(db_session)
    rc = _run_cli(
        monkeypatch, db_session,
        ["--requested-by-email", researcher.email, "--source-id", source.id, "--cid", "2244"],
    )
    assert rc == 2
    assert "papel" in capsys.readouterr().err


def test_cli_rejects_unknown_connector(monkeypatch, capsys, db_session):
    admin = create_admin(db_session, email="cli-admin2@biomatcad.example")
    source = _make_source(db_session)
    rc = _run_cli(
        monkeypatch, db_session,
        [
            "--requested-by-email", admin.email, "--source-id", source.id, "--cid", "2244",
            "--connector-id", "chebi",
        ],
    )
    assert rc == 2
    assert "unknown_connector" in capsys.readouterr().err


def test_cli_submits_valid_request_and_prints_json(monkeypatch, capsys, db_session):
    admin = create_admin(db_session, email="cli-admin3@biomatcad.example")
    source = _make_source(db_session)
    rc = _run_cli(
        monkeypatch, db_session,
        ["--requested-by-email", admin.email, "--source-id", source.id, "--cid", "2244", "--cid", "702"],
    )
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "queued"
    assert output["dry_run"] is False
    assert output["external_ids"] == ["2244", "702"]

    persisted = db_session.get(ScientificIngestionRequest, output["id"])
    assert persisted is not None
    assert persisted.status == IngestionRequestStatus.QUEUED


def test_cli_dry_run_flag_is_honored(monkeypatch, capsys, db_session):
    admin = create_admin(db_session, email="cli-admin4@biomatcad.example")
    source = _make_source(db_session)
    rc = _run_cli(
        monkeypatch, db_session,
        ["--requested-by-email", admin.email, "--source-id", source.id, "--cid", "2244", "--dry-run"],
    )
    assert rc == 0
    output = json.loads(capsys.readouterr().out)
    assert output["dry_run"] is True


def test_cli_wait_times_out_gracefully_when_never_claimed(monkeypatch, capsys, db_session):
    """Sem nenhum dispatcher rodando, a solicitação nunca sai de `queued` -- `--wait` deve
    retornar código 3 (nunca travar indefinidamente, nunca ser tratado como erro fatal)."""
    admin = create_admin(db_session, email="cli-admin5@biomatcad.example")
    source = _make_source(db_session)
    rc = _run_cli(
        monkeypatch, db_session,
        [
            "--requested-by-email", admin.email, "--source-id", source.id, "--cid", "2244",
            "--wait", "--wait-timeout-seconds", "1", "--wait-poll-interval-seconds", "0.3",
        ],
    )
    assert rc == 3
    assert "tempo limite" in capsys.readouterr().err
