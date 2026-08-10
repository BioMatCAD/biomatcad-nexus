#!/usr/bin/env python3
"""Combina `pubchem_pilot_wait_for_terminal.py` (acompanha uma solicitação até estado terminal,
com timeout explícito) com `pubchem_pilot_validation.py` (exige o estado terminal CERTO, nunca
apenas "diferente de failed") -- ponto de entrada único que
`scripts/Run-PubChemPilotWindows.ps1` chama para cada passo de dry run/execução real, em vez do
padrão antigo "chama o dispatcher uma vez, confia na contagem" que produziu o falso positivo da
Run 2 (`INVALID_FALSE_POSITIVE`).

Imprime um único objeto JSON `{"ok": bool, "reason": str, "report": {...} | null}` em stdout e
sai 0 se `ok`, 1 caso contrário (timeout ou validação reprovada), 2 se a solicitação não existir.
Nunca imprime segredos -- o relatório não contém credenciais."""
from __future__ import annotations

import argparse
import json
import sys

from pubchem_pilot_validation import (  # type: ignore[import-not-found]
    validate_dry_run_report,
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
    args = parser.parse_args()

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

        validator = validate_dry_run_report if args.kind == "dry_run" else validate_real_report
        result = validator(report, args.expected_cids)
        print(json.dumps({"ok": result.ok, "reason": result.reason, "report": report}, ensure_ascii=False))
        return 0 if result.ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
