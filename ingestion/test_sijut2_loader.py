"""Teste unitário do parser do SIJUT2 (transformação pura, sem rede).

Valida: extração de id_ato/tipo/número/órgão/data/ementa de uma linha de resultado,
limpeza de comentários HTML (que duplicam a ementa), decodificação de entidades,
leitura do total de páginas, e o filtro por 'Assunto:'.

Uso: mcp-server/.venv/Scripts/python.exe ingestion/test_sijut2_loader.py
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from loaders import parse_sijut2_pagina, _ato_para_unidade  # noqa: E402

# HTML sintético espelhando a estrutura real observada na listagem do SIJUT2
# (comentários com link.action antigo, âncoras com sessão, entidades &#xE7;).
HTML = """
<table>
<tr class='linhaResultados'>
  <!-- <td><a href='link.action?idAto=152131'>Solu&#xE7;&#xE3;o de Consulta</a></td> -->
  <td width="10%"><a href='https://normasinternet2.example/#/consulta/externa/152131/vs/X'>Solu&#xE7;&#xE3;o de Consulta</a></td>
  <td width="10%"><!-- <a href='link.action?antigo=1&idAto=152131'> --><a href='#'>107</a></td>
  <td width="10%"><div><a href='#'>Cosit</a></div></td>
  <td width="10%"><a href='#'>01/07/2026</a></td>
  <td width="50%">
    <!-- <a href='link.action?antigo=1&idAto=152131'>Assunto: Classifica&#xE7;&#xE3;o de Mercadorias<br>DUPLICADO NO COMENTARIO</a> -->
    <a href='#'>Assunto: Classifica&#xE7;&#xE3;o de Mercadorias<br>C&#xF3;digo NCM: 8539.51.00<br>Mercadoria: M&#xF3;dulo de LED.<br>Dispositivos Legais: RGI 1 e RGI 6.</a>
  </td>
</tr>
<tr class='linhaResultados'>
  <td><a href='link.action?antigo=1&idAto=152143'>Solu&#xE7;&#xE3;o de Consulta</a></td>
  <td><a href='#'>108</a></td>
  <td><div><a href='#'>Cosit</a></div></td>
  <td><a href='#'>01/07/2026</a></td>
  <td><a href='#'>Assunto: Imposto sobre a Renda Retido na Fonte - IRRF<br>Coisa n&#xE3;o-comex.</a></td>
</tr>
</table>
<select class="paginacao"><option value="1">1</option></select> de 159
<i class="material-icons btnProximaPagina2" id="btnProximaPagina2">seta</i>
"""


def main() -> None:
    atos, total = parse_sijut2_pagina(HTML)
    assert total == 159, f"total de páginas: esperado 159, veio {total}"
    assert len(atos) == 2, f"esperado 2 atos, veio {len(atos)}"

    a = atos[0]
    assert a["id_ato"] == "152131"
    assert a["tipo"] == "Solução de Consulta"
    assert a["numero"] == "107"
    assert a["orgao_emissor"] == "Cosit"
    assert a["data_publicacao"] == "01/07/2026"
    assert a["ementa"].startswith("Assunto: Classificação de Mercadorias")
    assert "Código NCM: 8539.51.00" in a["ementa"]
    assert "DUPLICADO NO COMENTARIO" not in a["ementa"], "comentário HTML vazou para a ementa"

    u = _ato_para_unidade(a)
    assert u.identificador == "Solução de Consulta Cosit nº 107/2026"
    assert u.fonte_url == "http://normas.receita.fazenda.gov.br/sijut2consulta/link.action?idAto=152131"
    print("OK: linha parseada (id, tipo, número, órgão, data, ementa limpa, permalink).")

    # filtro por Assunto (mesma lógica do loader)
    filtro = "classificação de mercadorias"
    mantidos = [x for x in atos if filtro in x["ementa"].splitlines()[0].lower()]
    assert len(mantidos) == 1 and mantidos[0]["id_ato"] == "152131"
    print("OK: filtro por 'Assunto: Classificação de Mercadorias' mantém 1 de 2.")


if __name__ == "__main__":
    main()
