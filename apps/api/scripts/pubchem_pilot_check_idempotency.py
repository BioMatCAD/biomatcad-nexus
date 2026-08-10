#!/usr/bin/env python3
"""Compara duas execuções REAIS (mesma lista de CIDs, submetidas duas vezes) e decide se a
idempotência foi de fato comprovada -- correção do falso positivo confirmado na Run 2 do piloto
PubChem Windows (`INVALID_FALSE_POSITIVE`).

Bug real da Run 2 (`Run-PubChemPilotWindows.ps1`): o loop de comparação por CID já marcava cada
item individual de `.extra` como `ok=false` quando faltava `RawSourceRecord`, mas esquecia de
também marcar a variável agregada `$idempotencyOk = $false` antes do `continue` -- resultado:
`idempotency_proof.ok=true` mesmo com TODOS os 3 CIDs mostrando `ok=false` em `.extra`. Este
script substitui aquele loop por `scripts/pubchem_pilot_validation.py::validate_idempotency`
(testado isoladamente), sempre consultando os DOIS relatórios de novo a partir do banco (nunca
reaproveitando os objetos já impressos pelos passos anteriores do roteiro -- elimina qualquer
dúvida sobre estado obsoleto)."""
from __future__ import annotations

import argparse
import json
import sys

from pubchem_pilot_report import build_pilot_report  # type: ignore[import-not-found]
from pubchem_pilot_validation import validate_idempotency  # type: ignore[import-not-found]

from biomatcad_api.db import SessionLocal


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Compara duas execuções reais do piloto PubChem e decide se a idempotência foi comprovada."
    )
    parser.add_argument("--request-id-1", required=True)
    parser.add_argument("--request-id-2", required=True)
    parser.add_argument("--expected-cid", action="append", required=True, dest="expected_cids")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        report1 = build_pilot_report(db, args.request_id_1)
        report2 = build_pilot_report(db, args.request_id_2)
        if report1 is None:
            print(json.dumps({"ok": False, "reason": f"solicitação '{args.request_id_1}' não encontrada.", "details": []}, ensure_ascii=False))
            return 2
        if report2 is None:
            print(json.dumps({"ok": False, "reason": f"solicitação '{args.request_id_2}' não encontrada.", "details": []}, ensure_ascii=False))
            return 2

        result = validate_idempotency(report1, report2, args.expected_cids)
        reason = (
            "idempotência comprovada para todos os CIDs esperados."
            if result.ok
            else "idempotência NÃO comprovada -- ver 'details' por CID."
        )
        print(json.dumps({"ok": result.ok, "reason": reason, "details": result.details}, ensure_ascii=False))
        return 0 if result.ok else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
