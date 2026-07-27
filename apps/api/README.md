# apps/api — API e domínio (FastAPI)

**Status: Incremento 1 implementado e testado (2026-07-27).** Health/ready/version, auth JWT
mínima, contrato de chave mestra para estados operacionais, modelos + migração Alembic, seed
sintético — 10 testes pytest passando contra PostgreSQL real. Ver `IMPLEMENTATION_STATUS.md` na
raiz para evidências completas. CAD/FEM/materiais/ML/otimização e o envelope clínico/
laboratorial ainda não implementados.

## Propósito

Backend Python: FastAPI, Pydantic, SQLAlchemy + Alembic, OpenAPI versionado, PostgreSQL como banco principal, Redis para cache/locks/fila, worker assíncrono, storage S3-compatível (MinIO local).

## Fonte no Prompt Mestre

Seção 6.2

## Como executar

Ver seção "Backend" em `README.md` (raiz do repositório).

## Próximo passo

Ver `REQUIREMENTS_MATRIX.md` e `docs/adr/` para requisitos e decisões associadas antes do
próximo incremento.
