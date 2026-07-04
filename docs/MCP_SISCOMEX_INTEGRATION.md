# Estrutura Técnica — MCP Server + RAG + Integração PUCOMEX/Órgãos

**Referência:** ARCHITECTURE.md, DATA_SOURCES.md
**Objetivo:** guia de início imediato — o que instalar, configurar e codificar hoje.

---

## 1. Duas integrações diferentes — não tratem como a mesma coisa

**PUCOMEX (Portal Único Siscomex)** — API REST oficial, documentada, com autenticação por certificado digital. Isso existe e é acessível hoje.

**MAPA / Anvisa / Ibama (registro de defensivos)** — **não têm API pública equivalente** conhecida. O SISPA é recém-lançado sem API documentada até o momento. Para essa vertical, a integração continua sendo scraping/mapeamento manual, como já está no `DATA_SOURCES.md`.

Se a intenção agora é retomar a frente de comex (PUCOMEX) em paralelo à vertical de defensivos, seção 2 abaixo é o caminho. Se é só para entender o padrão de autenticação de API governamental brasileira (útil como referência de arquitetura, já que MAPA/Anvisa podem lançar API no mesmo padrão), a seção 2 também serve de blueprint.

## 2. Autenticação PUCOMEX — o que a documentação oficial exige

- API REST, formatos **XML e JSON** (alguns serviços só em XML com schema XSD), toda em UTF-8.
- Segurança obrigatória via **SSL/TLS com certificado digital ICP-Brasil** (A1 ou A3) — não existe autenticação por chave simples/API key tradicional na porta principal.
- Fluxo de autenticação:
  1. Cliente inicia handshake SSL apresentando o certificado.
  2. `POST /portal/api/autenticar` com header `Role-Type` (perfil de atuação — importador, despachante, depositário etc.).
  3. Servidor retorna `Set-Token`, `X-CSRF-Token` e `X-CSRF-Expiration` no header.
  4. Requisições seguintes usam esses tokens (`Authorization` = valor de `Set-Token`, mais `X-CSRF-Token`).
  5. Token tem validade de 60 minutos; a API recomenda reutilizar o token válido, não reautenticar a cada chamada.

- **Mecanismo crítico para o produto de vocês: "Chaves de Acesso".** O usuário final (cliente de vocês, dono do certificado digital) pode gerar uma chave de acesso dentro do próprio Portal Único e compartilhar com um sistema terceiro — ou seja, **o cliente autoriza a aplicação de vocês a consumir a API em nome dele, sem vocês precisarem deter o certificado digital dele**. Isso é o modelo certo para SaaS multi-cliente: cada cliente gera a própria chave e conecta ao seu sistema.

- Ambiente de validação (teste): `val.portalunico.siscomex.gov.br` — usem esse antes de produção.

## 3. Estrutura do MCP Server

O MCP (Model Context Protocol) expõe ferramentas que o Claude Code (ou qualquer host MCP) pode chamar diretamente. A ideia: em vez de o agente precisar "adivinhar" como consultar a norma ou o Siscomex, ele chama uma ferramenta com contrato bem definido.

```
mcp-server/
├── src/
│   ├── server.py              # entrypoint do MCP server
│   ├── tools/
│   │   ├── rag_search.py      # busca na base normativa (pgvector)
│   │   ├── siscomex_client.py # cliente autenticado PUCOMEX
│   │   ├── agrofit_lookup.py  # consulta a precedentes do Agrofit
│   │   └── dossie_tools.py    # criação/consulta de dossiê no Postgres
│   ├── auth/
│   │   └── pucomex_auth.py    # handshake SSL + gestão de token
│   └── db/
│       └── connection.py      # conexão Postgres/pgvector
├── requirements.txt
└── README.md
```

### Esqueleto do servidor (Python, usando o SDK oficial `mcp`)

```python
# src/server.py
from mcp.server import Server
from mcp.server.stdio import stdio_server
from tools.rag_search import buscar_norma
from tools.siscomex_client import consultar_ncm_siscomex
from tools.agrofit_lookup import consultar_precedente_agrofit

server = Server("compliance-engine")

@server.tool()
async def buscar_norma_regulatoria(query: str, orgao: str = None) -> dict:
    """Busca trecho normativo relevante na base indexada (RAG),
    retornando texto, fonte e data de vigência."""
    return await buscar_norma(query, orgao)

@server.tool()
async def consultar_ncm(codigo_ncm: str, chave_acesso: str) -> dict:
    """Consulta dados de NCM no Portal Único Siscomex usando a
    chave de acesso fornecida pelo cliente final."""
    return await consultar_ncm_siscomex(codigo_ncm, chave_acesso)

@server.tool()
async def consultar_precedente(ingrediente_ativo: str) -> dict:
    """Consulta precedentes de registro no Agrofit para um
    ingrediente ativo."""
    return await consultar_precedente_agrofit(ingrediente_ativo)

async def main():
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Cliente PUCOMEX (esqueleto de autenticação)

```python
# src/auth/pucomex_auth.py
import httpx

PUCOMEX_BASE_URL = "https://val.portalunico.siscomex.gov.br"  # ambiente de validação

async def autenticar(chave_acesso: str, role_type: str, cert_path: str, cert_key: str):
    """Autentica no PUCOMEX usando certificado digital + chave de acesso
    do cliente (gerada por ele mesmo no portal)."""
    async with httpx.AsyncClient(cert=(cert_path, cert_key)) as client:
        response = await client.post(
            f"{PUCOMEX_BASE_URL}/portal/api/autenticar",
            headers={"Role-Type": role_type},
        )
        response.raise_for_status()
        return {
            "token": response.headers["Set-Token"],
            "csrf_token": response.headers["X-CSRF-Token"],
            "expiration": response.headers["X-CSRF-Expiration"],
        }
```

**Nota crítica de segurança**: nunca armazenem o certificado digital do cliente no backend de vocês além do tempo estritamente necessário da sessão — a própria documentação do PUCOMEX recomenda que o sistema terceiro não armazene localmente a chave de acesso do usuário. Tratem isso como segredo efêmero, idealmente mantido em memória ou cofre de segredos (Vault/AWS Secrets Manager), nunca em log ou banco em texto claro.

## 4. Como o MCP se conecta ao RAG e ao LangGraph

O MCP server não substitui o LangGraph — ele é a **camada de ferramentas** que os nós do grafo chamam. Fluxo:

```
LangGraph (orquestração do raciocínio)
   │
   ├── Nó de recuperação normativa  → chama tool `buscar_norma_regulatoria` (MCP)
   ├── Nó de consulta a precedente  → chama tool `consultar_precedente` (MCP)
   └── Nó de consulta Siscomex      → chama tool `consultar_ncm` (MCP, só se
                                        a vertical de comex estiver ativa)
```

Isso permite que o mesmo MCP server seja reutilizado tanto por uma sessão de Claude Code (durante desenvolvimento/debug) quanto pelo próprio agente de produção do LangGraph — um único ponto de verdade para "como consultar essas fontes", sem duplicar lógica.

## 5. O que fazer hoje, em ordem

1. `pip install mcp httpx asyncpg pgvector` — dependências mínimas.
2. Subir Postgres + pgvector local (Docker é suficiente para começar).
3. Implementar `rag_search.py` reaproveitando o schema já definido em `ARCHITECTURE.md`.
4. Implementar o esqueleto do MCP server acima e testar localmente com Claude Code apontando para ele via stdio (configuração de servidor MCP local no `claude_desktop_config.json` ou equivalente do Claude Code).
5. Só implementar `siscomex_client.py` de verdade quando tiverem um certificado de teste e um cliente disposto a gerar uma Chave de Acesso no ambiente de validação (`val.portalunico.siscomex.gov.br`) — não vale a pena mockar autenticação por certificado, é melhor testar contra o ambiente real de validação desde cedo.
6. Para a vertical MAPA/Anvisa/Ibama, sigam a ordem já definida em `DATA_SOURCES.md` e `ROADMAP.md` — captura manual/scraping, sem cliente de API dedicado por enquanto.

## 6. Pontos de atenção específicos

- **Sem SDK/exemplo pronto para MAPA/Anvisa/Ibama** — diferente do PUCOMEX, que tem documentação pública madura, essas agências ainda não têm padrão de API aberto. Não percam tempo tentando "adivinhar" uma API que não existe; tratem como ingestão de conteúdo público via scraping controlado, versionado por data de vigência (já desenhado em `ARCHITECTURE.md`).
- **Ambiente de validação primeiro, sempre**: PUCOMEX deixa claro que o ambiente foi implementado recentemente e pode ter instabilidades — validem toda integração em `val.portalunico.siscomex.gov.br` antes de qualquer chamada em produção.
- **Role-Type importa**: a documentação lista perfis específicos (ex: DEPOSIT, OPERPORT, e outros conforme o serviço) que determinam o que a autenticação permite consultar — mapeiem exatamente qual perfil o cliente final precisa autorizar antes de desenhar a tool do MCP.
