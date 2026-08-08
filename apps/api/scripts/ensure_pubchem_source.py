#!/usr/bin/env python3
"""Get-or-create do `ScientificSource` real "PubChem" (Incremento 2.3, Rodada 2, Fase I).

Utilitário mínimo, idempotente: NUNCA cria um segundo registro se um "PubChem"
`ScientificSource` já existir (busca por nome exato antes de inserir). Usado pelo roteiro
Windows (Run-PubChemPilotWindows.ps1) para obter um `source_id` real antes de submeter CIDs --
nunca inventa um `source_id` nem reaproveita o registro fictício de demonstração criado por
`seed_scientific_data.py` (que é explicitamente rotulado como fonte fictícia de demonstração,
nunca PubChem real -- ver docstring daquele módulo).

`redistribution_status=UNKNOWN` é usado deliberadamente (nunca ALLOWED por omissão, mesmo que
a política pública do NIH/PubChem seja permissiva) -- este projeto nunca assume permissão de
redistribuição sem verificação humana explícita e documentada (ver
models/scientific_data.py::RedistributionStatus)."""
from __future__ import annotations

import json

from biomatcad_api.db import SessionLocal
from biomatcad_api.models.scientific_data import RedistributionStatus, ScientificSource, SourceType

PUBCHEM_SOURCE_NAME = "PubChem"


def main() -> int:
    db = SessionLocal()
    try:
        existing = db.query(ScientificSource).filter(ScientificSource.name == PUBCHEM_SOURCE_NAME).first()
        if existing is not None:
            print(json.dumps({"id": existing.id, "created": False, "name": existing.name}))
            return 0

        source = ScientificSource(
            name=PUBCHEM_SOURCE_NAME,
            source_type=SourceType.DATABASE,
            base_url="https://pubchem.ncbi.nlm.nih.gov",
            publisher="National Center for Biotechnology Information (NCBI), NIH.",
            license=(
                "Ver https://pubchem.ncbi.nlm.nih.gov/docs/about -- status de redistribuição "
                "registrado como UNKNOWN neste piloto até verificação humana explícita "
                "(nunca assumido automaticamente)."
            ),
            version="pug-rest",
            terms_of_use="https://pubchem.ncbi.nlm.nih.gov/docs/about",
            redistribution_status=RedistributionStatus.UNKNOWN,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        print(json.dumps({"id": source.id, "created": True, "name": source.name}))
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
