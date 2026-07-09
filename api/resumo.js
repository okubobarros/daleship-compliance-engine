// Vercel Serverless Function (Node.js) — proxy server-side para a API real (Render).
//
// resultado.html (site estático, sem backend próprio) chama /api/resumo?dossie_id=...
// same-origin; esta função injeta o Bearer API_TOKEN (env var do Vercel, nunca enviada
// ao browser) e repassa a resposta. Assim o token nunca aparece no JS do cliente nem no
// devtools de rede do visitante — só a chamada server-to-server carrega o segredo.
//
// Usa o módulo `https` nativo (não `fetch`) de propósito: o runtime Node do Vercel varia
// por projeto/config, e `fetch` global só existe a partir do Node 18 — `https` funciona em
// qualquer versão, sem dependência externa (sem package.json/npm install para este arquivo).
//
// Configurar no Vercel: Project Settings -> Environment Variables
//   API_TOKEN      = (mesmo valor configurado no Render)
//   RENDER_API_URL = https://daleship-compliance-engine.onrender.com  (opcional, tem default)
const https = require("https");

function buscarResumo(apiBase, dossieId, token) {
  return new Promise((resolve, reject) => {
    const url = new URL(`${apiBase}/dossies/${encodeURIComponent(dossieId)}/resumo`);
    const req = https.request(
      url,
      { method: "GET", headers: { Authorization: `Bearer ${token}` } },
      (upstream) => {
        let data = "";
        upstream.on("data", (chunk) => { data += chunk; });
        upstream.on("end", () => resolve({ status: upstream.statusCode, body: data }));
      }
    );
    req.on("error", reject);
    req.setTimeout(15000, () => req.destroy(new Error("timeout consultando a API")));
    req.end();
  });
}

module.exports = async (req, res) => {
  console.log("api/resumo iniciado");
  // Handler inteiro blindado: NENHUMA exceção deve escapar como 500 sem corpo JSON —
  // sempre uma resposta explicável (fail-closed, nunca silencioso).
  try {
    const dossieId = req.query && req.query.dossie_id;
    if (!dossieId) {
      res.status(400).json({ error: "dossie_id obrigatório" });
      return;
    }
    const apiBase = process.env.RENDER_API_URL || "https://daleship-compliance-engine.onrender.com";
    const token = process.env.API_TOKEN;
    if (!token) {
      res.status(503).json({ error: "proxy sem API_TOKEN configurado" });
      return;
    }
    const upstream = await buscarResumo(apiBase, dossieId, token);
    // Sem encadear .setHeader() no meio: é o método NATIVO do Node (não um helper do Vercel
    // como .status()/.json()), nem sempre retorna `this` de forma consistente entre runtimes —
    // encadear pode quebrar silenciosamente e, pior, deixar a resposta em estado parcial (o que
    // faria o catch abaixo falhar de novo ao tentar responder, virando um 500 sem corpo).
    res.setHeader("Content-Type", "application/json");
    res.status(upstream.status);
    res.send(upstream.body);
  } catch (e) {
    res.status(502).json({ error: "falha ao consultar a API", detail: String((e && e.message) || e) });
  }
};
