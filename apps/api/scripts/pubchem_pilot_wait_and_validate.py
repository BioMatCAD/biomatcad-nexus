#!/usr/bin/env python3
"""Combina `pubchem_pilot_wait_for_terminal.py` (acompanha uma solicitação até estado terminal,
com timeout explícito, reivindicando SOMENTE essa solicitação -- nunca a fila inteira) com
`pubchem_pilot_validation.py` (exige o estado terminal CERTO e, para o dry run, ausência de
delta de RawSourceRecord em vez de contagem absoluta) -- ponto de entrada único que
`scripts/Run-PubChemPilotWindows.ps1` chama para cada passo de dry run/execução real.

Para `--kind dry_run`, roda DOIS validadores sobre o MESMO relatório (um único acompanhamento,
uma única leitura de rede -- nunca uma segunda consulta ao PubChem): `validate_network_reachability`
(a resposta oficial foi mesmo obtida e é válida) e `validate_dry_run_report` (nenhum
RawSourceRecord novo apareceu durante a janela do dry run, comparado contra `--baseline-file`,
um JSON produzido por `pubchem_pilot_capture_baseline.py` ANTES da submissão -- correção do
`QUEUE_CONTAMINATION` da Run 3, ver docs/data/connectors/PUBCHEM_CONNECTOR.md). `--baseline-file`
é obrigatório para `--kind dry_run` (nunca opcional -- sem ele não há como distinguir
"contaminação real" de "registro antigo legítimo").

Para `--kind real`, roda apenas `validate_real_report` (a rede já foi confirmada pelo dry run
anterior na mesma execução do piloto).

Imprime um único objeto JSON em stdout e sai 0 se tudo `ok`, 1 caso contrário (timeout ou
validação reprovada), 2 se a solicitação não existir. Nunca imprime segredos -- o relatório não
contém credenciais.

Formato de saída (`--kind dry_run`):
    {"ok": bool, "reason": str, "report": {...} | null,
     "network_reachability": {"ok": bool, "reason": str, "reason_code": str},
     "dry_run_validation": {"ok": bool, "reason": str, "reason_code": str}}

Formato de saída (`--kind real`):
    {"ok": bool, "reason": str, "reason_code": str, "report": {...} | null}"""
from __future__ import annotations

import argparse
import json
import sys

from pubchem_pilot_validation import (  # type: ignore[import-not-found]
    validate_dry_run_report,
    validate_network_reachability,
    validate_real_report,
)
from pubchem_pilot_wait_for_terminal import (  # type: ignore[import-not-found]
    RequestNotFoundError,
    RequestTerminalTimeoutError,
    wait_for_request_terminal,
)

from biomatcad_api.db import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Espera uma solicitação de ingestão PubChem atingir estado terminal e valida o resultado."
    )
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--kind", required=True, choices=["dry_run", "real"])
    parser.add_argument("--expected-cid", action="append", required=True, dest="expected_cids")
    parser.add_argument("--poll-interval-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--dispatcher-id", default=None)
    parser.add_argument(
        "--baseline-file",
        default=None,
        help="Caminho do JSON de baseline (produzido por pubchem_pilot_capture_baseline.py) -- "
        "OBRIGATÓRIO para --kind dry_run, ignorado para --kind real.",
    )
    args = parser.parse_args()

    if args.kind == "dry_run" and not args.baseline_file:
        print(
            json.dumps(
                {
                    "ok": False,
                    "reason": "--baseline-file é obrigatório para --kind dry_run (correção QUEUE_CONTAMINATION da Run 3).",
                    "report": None,
                },
                ensure_ascii=False,
            )
        )
        return 2

    db = SessionLocal()
    try:
        try:
            report = wait_for_request_terminal(
                db,
                request_id=args.request_id,
                dispatcher_id=args.dispatcher_id,
                poll_interval_seconds=args.poll_interval_seconds,
                timeout_seconds=args.timeout_seconds,
            )
        except RequestNotFoundError as exc:
            print(json.dumps({"ok": False, "reason": str(exc), "report": None}, ensure_ascii=False))
            return 2
        except RequestTerminalTimeoutError as exc:
            print(json.dumps({"ok": False, "reason": str(exc), "report": exc.last_report}, ensure_ascii=False))
            return 1

        if args.kind == "real":
            result = validate_real_report(report, args.expected_cids)
            print(
                json.dumps(
                    {
                        "ok": result.ok,
                        "reason": result.reason,
                        "reason_code": result.reason_code,
                        "report": report,
                    },
                    ensure_ascii=False,
                )
            )
            return 0 if result.ok else 1

        # kind == "dry_run"
        with open(args.baseline_file, encoding="utf-8") as f:
            baseline = json.load(f)
        network_result = validate_network_reachability(report, args.expected_cids)
        dry_run_result = validate_dry_run_report(report, args.expected_cids, baseline)
        overall_ok = network_result.ok and dry_run_result.ok
        if not network_result.ok:
            reason = network_result.reason
        elif not dry_run_result.ok:
            reason = dry_run_result.reason
        else:
            reason = "dry run e network_reachability aprovados."
        print(
            json.dumps(
                {
                    "ok": overall_ok,
                    "reason": reason,
                    "report": report,
                    "network_reachability": {
                        "ok": network_result.ok,
                        "reason": network_result.reason,
                        "reason_code": network_result.reason_code,
                    },
                    "dry_run_validation": {
                        "ok": dry_run_result.ok,
                        "reason": dry_run_result.reason,
                        "reason_code": dry_run_result.reason_code,
                    },
                },
                ensure_ascii=False,
            )
        )
        return 0 if overall_ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
