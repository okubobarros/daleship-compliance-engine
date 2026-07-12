// Vercel Serverless Function (Node.js) — proxy server-side para GET /dossies/{id}/estado (Render).
// Clone de resumo.js (mesmo padrão: injeta o Bearer API_TOKEN server-side, nunca vai ao browser).
// Usado pelo polling de loading.html enquanto o dossiê ainda não está consolidado.
const https = require("https");

function buscarEstado(apiBase, dossieId, token) {
  return new Promise((resolve, reject) => {
    const url = new URL(`${apiBase}/dossies/${encodeURIComponent(dossieId)}/estado`);
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
    const upstream = await buscarEstado(apiBase, dossieId, token);
    res.setHeader("Content-Type", "application/json");
    res.status(upstream.status);
    res.send(upstream.body);
  } catch (e) {
    res.status(502).json({ error: "falha ao consultar a API", detail: String((e && e.message) || e) });
  }
};
