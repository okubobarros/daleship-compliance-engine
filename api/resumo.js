// Vercel Serverless Function (Node.js) — proxy server-side para a API real (Render).
//
// resultado.html (site estático, sem backend próprio) chama /api/resumo?dossie_id=...
// same-origin; esta função injeta o Bearer API_TOKEN (env var do Vercel, nunca enviada
// ao browser) e repassa a resposta. Assim o token nunca aparece no JS do cliente nem no
// devtools de rede do visitante — só a chamada server-to-server carrega o segredo.
//
// Configurar no Vercel: Project Settings -> Environment Variables
//   API_TOKEN      = (mesmo valor configurado no Render)
//   RENDER_API_URL = https://daleship-compliance-engine.onrender.com  (opcional, tem default)
module.exports = async (req, res) => {
  const dossieId = req.query.dossie_id;
  if (!dossieId) {
    res.status(400).json({ error: "dossie_id obrigatório" });
    return;
  }
  const apiBase = process.env.RENDER_API_URL || "https://daleship-compliance-engine.onrender.com";
  const token = process.env.API_TOKEN;
  if (!token) {
    // Fail-closed: sem token configurado no Vercel, o proxy não inventa dado nem some em silêncio.
    res.status(503).json({ error: "proxy sem API_TOKEN configurado" });
    return;
  }
  try {
    const upstream = await fetch(
      `${apiBase}/dossies/${encodeURIComponent(dossieId)}/resumo`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    const body = await upstream.text();
    res.status(upstream.status).setHeader("Content-Type", "application/json").send(body);
  } catch (e) {
    res.status(502).json({ error: "falha ao consultar a API", detail: String(e) });
  }
};
