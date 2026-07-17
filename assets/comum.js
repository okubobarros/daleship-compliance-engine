// Infra compartilhada do Cockpit do Despachante: sessão (Supabase Auth via localStorage,
// mesmo formato já usado por simulacao/loading/resultado), chamadas à API real e o shell
// (sidebar + topbar) idêntico em todas as telas logadas.
//
// Princípio (dono, 11/07/2026): nenhum botão decorativo — tudo que aparece aqui funciona.
(function () {
  // Override de desenvolvimento: localStorage 'daleship.api_base' aponta para uma API local
  // (ex.: http://127.0.0.1:8787) sem tocar no código. Em produção, fica o Render.
  const API_BASE = window.__API_BASE__ || localStorage.getItem('daleship.api_base') ||
    'https://daleship-compliance-engine.onrender.com';
  const CHAVE_SESSAO = 'daleship.sessao';

  // ---------- Sessão ----------
  function sessao() {
    try {
      const s = JSON.parse(localStorage.getItem(CHAVE_SESSAO) || 'null');
      if (s && s.token && s.expira_em && s.expira_em > Date.now() / 1000) return s;
    } catch { /* sessão corrompida = sem sessão */ }
    return null;
  }

  function exigirLogin() {
    const s = sessao();
    if (!s) {
      const destino = location.pathname + location.search;
      location.href = '/login.html?next=' + encodeURIComponent(destino);
      throw new Error('sem sessão');
    }
    return s;
  }

  function sair() {
    localStorage.removeItem(CHAVE_SESSAO);
    location.href = '/login.html';
  }

  // ---------- API ----------
  async function api(caminho, opcoes = {}) {
    const s = exigirLogin();
    const resposta = await fetch(API_BASE + caminho, {
      ...opcoes,
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer ' + s.token,
        ...(opcoes.headers || {}),
      },
    });
    if (resposta.status === 401) { sair(); throw new Error('sessão expirada'); }
    const corpo = await resposta.json().catch(() => ({}));
    if (!resposta.ok) {
      throw new Error(corpo.detail || corpo.mensagem || ('Erro ' + resposta.status));
    }
    return corpo;
  }

  async function apiPublica(caminho) {
    const resposta = await fetch(API_BASE + caminho);
    if (!resposta.ok) throw new Error('Erro ' + resposta.status);
    return resposta.json();
  }

  // ---------- Formatação / segurança ----------
  function esc(texto) {
    return String(texto ?? '').replace(/[&<>"']/g, (c) => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));
  }
  const fmtBRL = (v) => (v == null ? '—'
    : v.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' }));
  const fmtPct = (v) => (v == null ? '—' : v.toLocaleString('pt-BR') + '%');
  function fmtData(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (isNaN(d)) return esc(iso);
    const soData = /^\d{4}-\d{2}-\d{2}$/.test(iso);
    return d.toLocaleDateString('pt-BR', soData ? { timeZone: 'UTC' } : undefined) +
      (soData ? '' : ' ' + d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }));
  }

  // Badge de situação do dossiê (estado_pipeline + status) — mesmas cores em todas as telas.
  function badgeDossie(d) {
    const st = d.status || '';
    if (st === 'travado') return ['Travado', 'bg-red-100 text-red-700', 'bg-red-500'];
    if (st === 'escalado') return ['Escalado', 'bg-purple-100 text-purple-700', 'bg-purple-500'];
    const e = d.estado_pipeline || 'recebido';
    if (e === 'concluido') return ['Concluído', 'bg-green-100 text-green-700', 'bg-green-500'];
    if (e === 'concluido_com_excecoes')
      return ['Com exceções', 'bg-yellow-100 text-yellow-800', 'bg-yellow-500'];
    return ['Em processamento', 'bg-blue-100 text-blue-700', 'bg-blue-500'];
  }

  // ---------- Shell (sidebar + topbar) ----------
  const ITENS_NAV = [
    { id: 'cockpit', rotulo: 'Cockpit', icone: 'dashboard', href: '/cockpit.html' },
    { id: 'classificacao', rotulo: 'Classificação Fiscal', icone: 'find_in_page', href: '/classificacao.html' },
    { id: 'custeio', rotulo: 'Custeio (VMLD)', icone: 'calculate', href: '/custeio.html' },
    { id: 'feed', rotulo: 'Feed Normativo', icone: 'newspaper', href: '/feed.html' },
    { id: 'processos', rotulo: 'Processos', icone: 'rule_settings', href: '/processos.html' },
  ];

  function montarShell(ativo, opcoes = {}) {
    const s = exigirLogin();
    const alvoSidebar = document.getElementById('sidebar');
    const alvoTopbar = document.getElementById('topbar');

    alvoSidebar.outerHTML = `
      <aside class="w-64 h-screen border-r border-outline-variant bg-surface-container-low flex-col py-6 hidden md:flex shrink-0">
        <div class="px-6 mb-8">
          <a href="/cockpit.html" class="flex items-center gap-3">
            <img src="/logo.png" alt="Despachante de Bolso" class="w-9 h-9 rounded-lg border border-outline-variant bg-white object-contain" />
            <div>
              <h1 class="text-[15px] font-bold text-on-surface leading-tight">Despachante de Bolso</h1>
              <p class="text-[10px] uppercase tracking-widest text-on-surface-variant font-bold">Cockpit do Despachante</p>
            </div>
          </a>
        </div>
        <nav class="flex-1 px-3 space-y-1">
          ${ITENS_NAV.map((item) => item.id === ativo
            ? `<a href="${item.href}" class="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-secondary-container text-on-secondary-container font-semibold text-sm">
                 <span class="material-symbols-outlined preenchido">${item.icone}</span><span>${item.rotulo}</span></a>`
            : `<a href="${item.href}" class="flex items-center gap-3 px-3 py-2.5 rounded-lg text-on-surface-variant hover:bg-surface-container-high transition-colors text-sm">
                 <span class="material-symbols-outlined">${item.icone}</span><span>${item.rotulo}</span></a>`).join('')}
        </nav>
        <div class="px-3 mt-4">
          <a href="/simulacao.html" class="w-full py-3 bg-secondary text-white rounded-lg font-bold flex items-center justify-center gap-2 hover:opacity-90 transition-opacity text-sm">
            <span class="material-symbols-outlined text-sm">add</span><span>Nova operação</span>
          </a>
        </div>
        <div class="mt-auto px-3 border-t border-outline-variant pt-4 space-y-1">
          <a href="/" class="flex items-center gap-3 px-3 py-2 rounded-lg text-on-surface-variant hover:bg-surface-container-high transition-colors text-sm">
            <span class="material-symbols-outlined">language</span><span>Site público</span>
          </a>
          <button id="botao-sair-side" class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-on-surface-variant hover:bg-surface-container-high transition-colors text-sm">
            <span class="material-symbols-outlined">logout</span><span>Sair</span>
          </button>
        </div>
      </aside>`;

    const temBusca = Boolean(opcoes.busca);
    alvoTopbar.outerHTML = `
      <header class="h-16 flex justify-between items-center gap-4 px-6 lg:px-8 w-full bg-surface border-b border-outline-variant shrink-0">
        <div class="flex-1 max-w-md">${temBusca ? `
          <div class="relative">
            <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant">search</span>
            <input id="busca-topbar" type="text" placeholder="${esc(opcoes.busca.placeholder || 'Pesquisar...')}"
              class="w-full bg-surface-container-low border-none rounded-full pl-10 pr-4 py-1.5 focus:ring-2 focus:ring-secondary text-sm transition-all outline-none" />
          </div>` : `<p class="text-sm font-semibold text-on-surface-variant">${esc(opcoes.titulo || '')}</p>`}
        </div>
        <div class="flex items-center gap-3">
          <div class="text-right hidden sm:block">
            <p class="font-bold text-[13px] text-on-surface leading-tight">${esc(s.email || 'Conta autenticada')}</p>
            <p class="text-[10px] text-on-surface-variant">Sessão Supabase ativa</p>
          </div>
          <div class="w-9 h-9 rounded-full bg-secondary-container text-white flex items-center justify-center font-bold text-sm uppercase">
            ${esc((s.email || 'C').charAt(0))}
          </div>
          <button id="botao-sair-top" title="Sair"
            class="p-2 rounded-full text-on-surface-variant hover:bg-surface-container transition-all">
            <span class="material-symbols-outlined">logout</span>
          </button>
        </div>
      </header>`;

    document.getElementById('botao-sair-top').addEventListener('click', sair);
    document.getElementById('botao-sair-side').addEventListener('click', sair);
    if (temBusca && opcoes.busca.aoFiltrar) {
      document.getElementById('busca-topbar').addEventListener('input', (ev) =>
        opcoes.busca.aoFiltrar(ev.target.value.trim().toLowerCase()));
    }
    return s;
  }

  window.Cockpit = {
    API_BASE, sessao, exigirLogin, sair, api, apiPublica,
    esc, fmtBRL, fmtPct, fmtData, badgeDossie, montarShell,
  };
})();
