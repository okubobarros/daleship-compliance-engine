"""Teste de fumaça do guardrail de grounding: com a base `normas` vazia,
buscar_norma deve retornar {'encontrado': False} e nunca inventar citação.

Uso (da raiz do repo):
    mcp-server/.venv/Scripts/python.exe mcp-server/test_rag_grounding.py
"""
import asyncio
import pathlib
import sys

from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent / "src"))

from tools.rag_search import buscar_norma  # noqa: E402


async def main() -> None:
    resultado = await buscar_norma("exigência de LPCO para importação de vinho", orgao="MAPA")
    print("Resultado:", resultado)
    assert resultado["encontrado"] is False, "Base vazia deveria retornar encontrado=False"
    assert resultado["motivo"] == "sem base normativa localizada"
    print("OK: grounding respeitado — sem citação inventada com base vazia.")


if __name__ == "__main__":
    asyncio.run(main())
