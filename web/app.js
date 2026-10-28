// ArchIQ - interface web
// Consome POST /api/audit ({ code_or_prompt }) e POST /api/extract-text (upload).
// Login/header Authorization ficam no auth.js (objeto global Auth).

(() => {
  const cfg = window.API_CONFIG || {};
  const api = (path) => (cfg.baseUrl || '') + path;
  const $ = (id) => document.getElementById(id);
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const DRAFT_KEY = 'archiq_draft';
  const MAX_TEXT_FILE = 500 * 1024;
  const MAX_DOC_FILE = 10 * 1024 * 1024; // limite sincrono do Textract
  const GAUGE_LENGTH = 326.7; // 2 * PI * r(52)

  // Bibliotecas carregadas sob demanda, so quando ha resultado (versoes fixadas)
  const CDN = {
    marked: 'https://cdn.jsdelivr.net/npm/marked@15.0.6/lib/marked.esm.js',
    purify: 'https://cdn.jsdelivr.net/npm/dompurify@3.2.4/dist/purify.es.mjs',
    mermaid: 'https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.esm.min.mjs',
  };
  const libs = {};
  const lib = (name) => (libs[name] ||= import(CDN[name]));

  const SEVERITIES = {
    CRITICAL: { cls: 'critical', label: 'Crítica', icon: 'i-critical', rank: 0 },
    HIGH: { cls: 'high', label: 'Alta', icon: 'i-high', rank: 1 },
    MEDIUM: { cls: 'medium', label: 'Média', icon: 'i-medium', rank: 2 },
    LOW: { cls: 'low', label: 'Baixa', icon: 'i-low', rank: 3 },
  };
  const sevOf = (s) => SEVERITIES[String(s || '').toUpperCase()] || { cls: 'low', label: String(s || 'Info'), icon: 'i-low', rank: 4 };

  const STATUS_LABEL = { EXCELENTE: 'Excelente', BOA: 'Boa', REGULAR: 'Regular', ATENCAO: 'Atenção' };

  // Etapas do grafo LangGraph. A API responde de uma vez so, entao o avanco e estimado por tempo.
  const STEPS = [
    ['Lendo entrada', 'parse_input', 0],
    ['Buscando boas práticas', 'retrieve_context', 1.5],
    ['Auditando segurança', 'audit_security', 4],
    ['Otimizando custos', 'optimize_finops', 6.5],
    ['Gerando relatório', 'synthesize_report', 9],
    ['Explicando', 'explain_for_layperson', 12],
  ];

  const EXAMPLE_TF = `# Exemplo: aplicacao web com alguns problemas comuns
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_security_group" "web" {
  vpc_id = aws_vpc.main.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_instance" "web" {
  ami                    = "ami-0c55b159cbfafe1f0"
  instance_type          = "m5.2xlarge"
  vpc_security_group_ids = [aws_security_group.web.id]
}

resource "aws_s3_bucket" "uploads" {
  bucket = "app-uploads-prod"
  acl    = "public-read"
}

resource "aws_db_instance" "app" {
  engine                  = "postgres"
  instance_class          = "db.r5.xlarge"
  allocated_storage       = 100
  storage_encrypted       = false
  backup_retention_period = 1
  publicly_accessible     = true
  username                = "admin"
  password                = "trocar-depois"
}

resource "aws_iam_policy" "app" {
  name   = "app-full-access"
  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Action = "*", Resource = "*" }]
  })
}
`;

  const els = {
    hero: $('hero'), workspace: $('workspace'), results: $('results'),
    editor: $('codeEditor'), gutter: $('gutter'), editorTab: $('editorTab'), editorMeta: $('editorMeta'),
    fileInput: $('fileInput'), dropzone: $('dropzone'), dropStatus: $('dropStatus'),
    analyzeBtn: $('analyzeBtn'), analyzeHint: $('analyzeHint'), statusPanel: $('statusPanel'),
    scorePanel: $('scorePanel'), gaugeArc: $('gaugeArc'), gaugeNum: $('gaugeNum'),
    diagram: $('diagram'), dialog: $('diagramDialog'), dialogCanvas: $('dialogCanvas'),
  };

  let busy = false;
  let lastResult = null;
  let pipelineTimer = null;
  let zoom = 1;

  /* ----------------------------------------------------------------------
     Helpers de DOM (todo dado da API entra via textContent ou DOMPurify)
     ---------------------------------------------------------------------- */
  function h(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function icon(id, extra) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'icon' + (extra ? ' ' + extra : ''));
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', '#' + id);
    svg.appendChild(use);
    return svg;
  }

  function button(label, iconId, onClick, variant = 'btn-ghost') {
    const b = h('button', 'btn ' + variant);
    b.type = 'button';
    if (iconId) b.appendChild(icon(iconId));
    b.append(label);
    b.addEventListener('click', onClick);
    return b;
  }

  async function renderMarkdown(target, md) {
    try {
      const [{ marked }, { default: DOMPurify }] = await Promise.all([lib('marked'), lib('purify')]);
      target.innerHTML = DOMPurify.sanitize(marked.parse(md)); // conteudo vem de LLM: sempre sanitizado
    } catch (e) {
      target.textContent = md; // CDN indisponivel: mostra o texto cru
    }
  }

  function saveDraft() {
    try { sessionStorage.setItem(DRAFT_KEY, els.editor.value); } catch (_) { /* storage bloqueado */ }
  }

  /* ----------------------------------------------------------------------
     Inicializacao
     ---------------------------------------------------------------------- */
  async function init() {
    try { els.editor.value = sessionStorage.getItem(DRAFT_KEY) || ''; } catch (_) { /* storage bloqueado */ }
    updateEditor();
    bindEvents();
    loadRegion();

    await Auth.ready;
    const loggedIn = !Auth.enabled || Boolean(Auth.headers().Authorization);
    els.hero.hidden = loggedIn;
    els.workspace.hidden = !loggedIn;
    if (Auth.enabled && loggedIn) loadUserEmail();
  }

  function bindEvents() {
    $('heroLogin').addEventListener('click', () => Auth.login());

    els.editor.addEventListener('input', () => { updateEditor(); saveDraft(); });
    els.editor.addEventListener('scroll', () => { els.gutter.scrollTop = els.editor.scrollTop; });

    $('exampleBtn').addEventListener('click', () => {
      setCode(EXAMPLE_TF, 'exemplo.tf');
      setDropStatus('Exemplo carregado no editor.', 'ok');
    });
    els.analyzeBtn.addEventListener('click', analyze);

    els.fileInput.addEventListener('change', () => {
      if (els.fileInput.files[0]) handleFile(els.fileInput.files[0]);
      els.fileInput.value = '';
    });
    ['dragenter', 'dragover'].forEach((type) => els.dropzone.addEventListener(type, (e) => {
      e.preventDefault();
      els.dropzone.classList.add('is-over');
    }));
    ['dragleave', 'drop'].forEach((type) => els.dropzone.addEventListener(type, (e) => {
      e.preventDefault();
      els.dropzone.classList.remove('is-over');
    }));
    els.dropzone.addEventListener('drop', (e) => {
      if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]);
    });

    $('toggleReport').addEventListener('click', toggleReport);
    $('copyReport').addEventListener('click', copyReport);
    $('downloadReport').addEventListener('click', downloadReport);
    $('newAnalysis').addEventListener('click', () => {
      els.workspace.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });
      els.editor.focus({ preventScroll: true });
    });

    $('expandDiagram').addEventListener('click', openDiagram);
    $('closeDialog').addEventListener('click', () => els.dialog.close());
    els.dialog.addEventListener('click', (e) => { if (e.target === els.dialog) els.dialog.close(); });
    els.dialog.querySelectorAll('[data-zoom]').forEach((b) => b.addEventListener('click', () => {
      setZoom(zoom + Number(b.dataset.zoom) * 0.25);
    }));
  }

  async function loadRegion() {
    try {
      const res = await fetch(api(cfg.healthEndpoint || '/health'));
      const data = await res.json();
      if (data.region) {
        $('regionTag').textContent = data.region;
        $('regionTag').hidden = false;
      }
    } catch (_) { /* opcional */ }
  }

  // Email do usuario: o access token nao traz email, entao consulta o userInfo do Cognito
  async function loadUserEmail() {
    try {
      const res = await fetch(`${cfg.cognito.domain}/oauth2/userInfo`, { headers: Auth.headers() });
      if (!res.ok) return;
      const { email } = await res.json();
      if (email) {
        $('authUser').textContent = email;
        $('authUser').hidden = false;
      }
    } catch (_) { /* opcional */ }
  }

  /* ----------------------------------------------------------------------
     Editor e arquivos
     ---------------------------------------------------------------------- */
  function updateEditor() {
    const value = els.editor.value;
    const lines = value ? value.split('\n').length : 1;
    els.gutter.textContent = Array.from({ length: lines }, (_, i) => i + 1).join('\n');
    const kb = new Blob([value]).size / 1024;
    els.editorMeta.textContent = value ? `${lines} linhas · ${kb.toFixed(1)} KB` : 'vazio';
    const hasCode = Boolean(value.trim());
    els.analyzeBtn.disabled = !hasCode || busy;
    els.analyzeHint.textContent = busy
      ? 'Análise em andamento…'
      : hasCode ? 'Pronto. A análise leva de 10 a 30 segundos.' : 'Escreva ou carregue um Terraform para começar.';
  }

  function setCode(text, name) {
    els.editor.value = text;
    els.editorTab.textContent = name || 'main.tf';
    els.editor.scrollTop = 0;
    updateEditor();
    saveDraft();
  }

  function setDropStatus(text, kind) {
    els.dropStatus.textContent = text;
    els.dropStatus.className = 'dz-status mono' + (kind ? ' is-' + kind : '');
  }

  async function handleFile(file) {
    const name = file.name.toLowerCase();

    if (/\.(tf|json)$/.test(name)) {
      if (file.size > MAX_TEXT_FILE) return setDropStatus('Arquivo muito grande (limite: 500 KB).', 'error');
      const text = await file.text();
      if (!text.trim()) return setDropStatus('O arquivo está vazio.', 'error');
      setCode(text, file.name);
      return setDropStatus(`${file.name} carregado.`, 'ok');
    }

    if (!/\.(png|jpe?g|pdf|tiff?)$/.test(name)) {
      return setDropStatus('Formato não suportado. Use .tf, .json, PNG, JPG ou PDF.', 'error');
    }
    if (file.size > MAX_DOC_FILE) return setDropStatus('Imagem/PDF muito grande (limite: 10 MB).', 'error');

    setDropStatus('Extraindo texto com Amazon Textract…', 'busy');
    try {
      await Auth.ready;
      const form = new FormData();
      form.append('file', file);
      const res = await fetch(api('/api/extract-text'), { method: 'POST', headers: Auth.headers(), body: form });
      if (res.status === 401) {
        setDropStatus('', '');
        return showSessionExpired();
      }
      if (!res.ok) {
        const msg = {
          503: 'O Textract não está configurado neste servidor.',
          422: 'Não encontramos texto legível nesse arquivo.',
          400: 'O arquivo enviado está vazio.',
        }[res.status] || 'Não foi possível extrair o texto.';
        return setDropStatus(msg, 'error');
      }
      const { extracted_text: text } = await res.json();
      setCode(text, file.name + '.txt');
      setDropStatus('Texto extraído. Revise no editor antes de analisar.', 'ok');
    } catch (_) {
      setDropStatus('Sem conexão com a API para extrair o texto.', 'error');
    }
  }

  /* ----------------------------------------------------------------------
     Analise
     ---------------------------------------------------------------------- */
  async function analyze() {
    const code = els.editor.value.trim();
    if (!code || busy) return;

    busy = true;
    updateEditor();
    els.results.hidden = true;
    startPipeline();

    try {
      await Auth.ready;
      const res = await fetch(api(cfg.auditEndpoint || '/api/audit'), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Accept: 'application/json', ...Auth.headers() },
        body: JSON.stringify({ code_or_prompt: code }),
      });

      if (res.status === 401) return showSessionExpired();
      if (!res.ok) {
        let detail = '';
        try { detail = (await res.json()).detail || ''; } catch (_) { /* corpo nao-JSON */ }
        return showNotice('error', 'i-high', 'A análise falhou',
          'O servidor não conseguiu concluir a auditoria. Seu Terraform continua no editor.',
          `HTTP ${res.status}${detail ? ' · ' + detail : ''}`,
          [button('Tentar de novo', 'i-retry', analyze, 'btn-primary')]);
      }

      const result = await res.json();
      await finishPipeline();
      els.statusPanel.hidden = true;
      renderResults(result);
    } catch (_) {
      showNotice('error', 'i-offline', 'Sem conexão com a API',
        'Não conseguimos falar com o servidor. Se ele estiver hospedado no Render, pode estar acordando: tente de novo em alguns segundos.',
        cfg.baseUrl || window.location.origin,
        [button('Tentar de novo', 'i-retry', analyze, 'btn-primary')]);
    } finally {
      busy = false;
      clearInterval(pipelineTimer);
      updateEditor();
    }
  }

  function showSessionExpired() {
    if (Auth.enabled) Auth.expired();
    $('authUser').hidden = true;
    saveDraft();
    const actions = Auth.enabled
      ? [button('Entrar novamente', 'i-login', () => Auth.login(), 'btn-primary')]
      : [];
    showNotice('warn', 'i-lock', Auth.enabled ? 'Sua sessão expirou' : 'A API exige login',
      Auth.enabled
        ? 'Entre de novo para continuar. O Terraform que você digitou fica salvo neste navegador e volta para o editor.'
        : 'O servidor exige autenticação, mas o login não está configurado nesta página (cognito em config.js).',
      '', actions);
  }

  function showNotice(kind, iconId, title, text, detail, actions) {
    clearInterval(pipelineTimer);
    const panel = els.statusPanel;
    panel.className = 'status-panel notice-' + kind;
    panel.setAttribute('role', 'alert');
    const wrap = h('div', 'notice');
    const body = h('div');
    body.append(h('h3', null, title), h('p', null, text));
    if (detail) body.appendChild(h('p', 'detail mono', detail));
    if (actions.length) {
      const row = h('div', 'notice-actions');
      row.append(...actions);
      body.appendChild(row);
    }
    wrap.append(icon(iconId), body);
    panel.replaceChildren(wrap);
    panel.hidden = false;
    panel.focus({ preventScroll: true });
    panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'nearest' });
  }

  function startPipeline() {
    const panel = els.statusPanel;
    panel.className = 'status-panel';
    panel.removeAttribute('role');

    const head = h('div', 'pipeline-head');
    const elapsed = h('span', 'mono', '00:00');
    head.append(h('h3', null, 'Analisando sua arquitetura'), elapsed);

    const list = h('ol', 'pipeline');
    const items = STEPS.map(([name, id]) => {
      const li = h('li', 'step');
      li.append(h('span', 'step-node'), h('span', 'step-name', name), h('span', 'step-id mono', id));
      list.appendChild(li);
      return li;
    });
    const live = h('p', 'visually-hidden');
    live.setAttribute('role', 'status');
    const note = h('p', 'pipeline-note', 'O andamento é estimado: o servidor executa todas as etapas e devolve o resultado de uma vez.');

    panel.replaceChildren(head, list, note, live);
    panel.hidden = false;
    panel.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'nearest' });

    const started = Date.now();
    let current = -1;
    const tick = () => {
      const secs = (Date.now() - started) / 1000;
      elapsed.textContent = `${String(Math.floor(secs / 60)).padStart(2, '0')}:${String(Math.floor(secs % 60)).padStart(2, '0')}`;
      const step = STEPS.reduce((acc, s, i) => (secs >= s[2] ? i : acc), 0);
      if (step !== current) {
        current = step;
        items.forEach((li, i) => {
          li.classList.toggle('is-done', i < step);
          li.classList.toggle('is-active', i === step);
        });
        live.textContent = STEPS[step][0];
      }
    };
    tick();
    clearInterval(pipelineTimer);
    pipelineTimer = setInterval(tick, 250);
    panel._items = items;
  }

  function finishPipeline() {
    clearInterval(pipelineTimer);
    (els.statusPanel._items || []).forEach((li) => {
      li.classList.remove('is-active');
      li.classList.add('is-done');
    });
    return new Promise((resolve) => setTimeout(resolve, reduceMotion ? 0 : 450));
  }

  /* ----------------------------------------------------------------------
     Resultado
     ---------------------------------------------------------------------- */
  function renderResults(r) {
    lastResult = r;
    const summary = r.executive_summary || {};
    const score = Math.max(0, Math.min(100, Number(r.score) || 0));
    const findings = (r.security_audit && r.security_audit.findings) || [];
    const optimizations = (r.finops_audit && r.finops_audit.optimizations) || [];
    const savings = (r.finops_audit && r.finops_audit.monthly_savings_pct) || 0;
    const services = (r.parsed_services || []).filter((s) => s !== 'GENERAL_AWS');

    const time = new Date().toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    $('resSession').textContent = `Sessão ${String(r.session_id || '').slice(0, 8)} · ${time}`;

    // Score
    const band = score >= 75 ? 'good' : score >= 50 ? 'mid' : 'bad';
    els.scorePanel.style.setProperty('--score-color', `var(--score-${band})`);
    els.scorePanel.classList.toggle('is-alert', score < 75);
    els.scorePanel.setAttribute('aria-label', `Score ${score} de 100`);
    const status = $('scoreStatus');
    status.textContent = STATUS_LABEL[summary.score_status] || (band === 'good' ? 'Boa' : band === 'mid' ? 'Regular' : 'Atenção');
    const note = $('scoreNote');
    note.textContent = score < 75
      ? 'Abaixo do limite de alerta (75). Comece pelos findings de severidade alta.'
      : 'Acima do limite de alerta (75).';
    els.scorePanel.querySelector('.alert-pill')?.remove();
    if (r.alert_sent) {
      const pill = h('span', 'alert-pill');
      pill.append(icon('i-bell'), 'alerta enviado via SNS');
      note.after(pill);
    }
    $('statServices').textContent = services.length;
    $('statFindings').textContent = findings.length;
    $('statSavings').textContent = `${savings}%`;

    // Explicacao para leigos (primeiro) e relatorio tecnico (sob demanda)
    renderMarkdown($('layperson'), r.layperson_explanation
      || 'A explicação em linguagem simples não foi gerada nesta análise. O relatório técnico abaixo traz todos os detalhes.');
    $('servicesList').replaceChildren(...services.map((s) => h('span', null, s)));
    renderMarkdown($('technicalReport'), r.technical_report || r.final_report || '');
    $('secReport').hidden = true;
    setReportToggle(false);

    renderFindings(findings);
    renderSavings(optimizations, savings);

    els.results.hidden = false;
    reveal();
    animateGauge(score);
    els.results.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });
    renderDiagram(r.final_report || '');
  }

  function reveal() {
    const parts = els.results.querySelectorAll('.summary > *, .block:not([hidden])');
    parts.forEach((el, i) => {
      el.classList.remove('is-in');
      el.classList.add('reveal');
      el.style.transitionDelay = `${Math.min(i, 5) * 70}ms`;
    });
    requestAnimationFrame(() => requestAnimationFrame(() => parts.forEach((el) => el.classList.add('is-in'))));
  }

  function animateGauge(score) {
    const arc = els.gaugeArc;
    const target = GAUGE_LENGTH * (1 - score / 100);
    arc.style.transition = 'none';
    arc.style.strokeDashoffset = GAUGE_LENGTH;
    arc.getBoundingClientRect(); // aplica o estado inicial antes da transicao
    arc.style.transition = '';

    if (reduceMotion) {
      arc.style.strokeDashoffset = target;
      els.gaugeNum.textContent = score;
      return;
    }
    requestAnimationFrame(() => { arc.style.strokeDashoffset = target; });
    const start = performance.now();
    const duration = 1400;
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      els.gaugeNum.textContent = Math.round(score * (1 - Math.pow(1 - t, 3)));
      if (t < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }

  function renderFindings(findings) {
    const list = $('findingsList');
    const filters = $('sevFilters');
    filters.replaceChildren();

    if (!findings.length) {
      const empty = h('div', 'empty');
      empty.append(icon('i-check'), 'Nenhum risco de segurança encontrado pelas regras do ArchIQ.');
      list.replaceChildren(empty);
      return;
    }

    const sorted = [...findings].sort((a, b) => sevOf(a.severity).rank - sevOf(b.severity).rank);
    list.replaceChildren(...sorted.map((f) => {
      const sev = sevOf(f.severity);
      const item = h('details', `finding sev-${sev.cls}`);
      item.dataset.sev = sev.cls;
      const summary = h('summary');
      const badge = h('span', `badge sev-${sev.cls}`);
      badge.append(icon(sev.icon), sev.label);
      const chev = icon('i-chevron', 'chev');
      summary.append(badge, h('span', 'svc', f.service || 'Terraform'), h('span', 'rule', f.rule || ''), chev);
      const fix = h('div', 'fix');
      fix.append(h('strong', null, 'Como corrigir'), f.remediation || 'Sem remediação sugerida.');
      item.append(summary, fix);
      return item;
    }));

    // Filtros: "Todas" + cada severidade presente
    const counts = {};
    sorted.forEach((f) => { const s = sevOf(f.severity); counts[s.cls] = counts[s.cls] || { sev: s, n: 0 }; counts[s.cls].n++; });
    const chips = [];
    const makeChip = (key, label, n, sev) => {
      const chip = h('button', 'chip');
      chip.type = 'button';
      chip.setAttribute('aria-pressed', String(key === 'all'));
      if (sev) {
        chip.style.setProperty('--chip-color', `var(--sev-${sev.cls})`);
        chip.appendChild(icon(sev.icon));
      }
      chip.append(label, ' ', h('span', 'count', String(n)));
      chip.addEventListener('click', () => {
        chips.forEach((c) => c.setAttribute('aria-pressed', String(c === chip)));
        list.querySelectorAll('.finding').forEach((el) => { el.hidden = key !== 'all' && el.dataset.sev !== key; });
      });
      chips.push(chip);
      return chip;
    };
    filters.append(makeChip('all', 'Todas', sorted.length),
      ...Object.values(counts).map(({ sev, n }) => makeChip(sev.cls, sev.label, n, sev)));
  }

  function renderSavings(optimizations, savings) {
    const list = $('optimizationsList');
    $('finMeta').textContent = optimizations.length ? `economia potencial estimada: ${savings}% ao mês` : '';
    if (!optimizations.length) {
      const empty = h('div', 'empty');
      empty.append(icon('i-check'), 'Nenhuma oportunidade de economia identificada. Os recursos parecem bem dimensionados.');
      list.replaceChildren(empty);
      return;
    }
    list.replaceChildren(...optimizations.map((o) => {
      const card = h('article', 'saving');
      card.append(h('span', 'svc', o.service || 'Geral'), h('p', 'action', o.action || ''));
      if (o.impact) card.appendChild(h('p', 'impact', o.impact));
      return card;
    }));
  }

  /* ----------------------------------------------------------------------
     Diagrama Mermaid
     ---------------------------------------------------------------------- */
  function extractMermaid(md) {
    const m = md.match(/```mermaid\s*\n([\s\S]*?)```/) || md.match(/^(graph (?:TD|LR)\n[\s\S]*?)(?:\n\s*\n|$)/m);
    return m ? m[1].trim() : '';
  }

  async function renderDiagram(md) {
    const box = els.diagram;
    const expand = $('expandDiagram');
    const source = extractMermaid(md);
    expand.hidden = true;

    if (!source) {
      const empty = h('div', 'empty');
      empty.append(icon('i-network'), 'Nenhum serviço específico identificado para desenhar.');
      box.replaceChildren(empty);
      return;
    }

    box.replaceChildren(h('p', 'diagram-note mono', 'Desenhando diagrama…'));
    const id = 'archiq-diagram-' + Date.now();
    try {
      const { default: mermaid } = await lib('mermaid');
      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict', // rotulos sanitizados pelo proprio mermaid
        theme: 'base',
        themeVariables: {
          background: '#111A22',
          primaryColor: '#16222D',
          primaryTextColor: '#E6EDF3',
          primaryBorderColor: '#5CC8E0',
          lineColor: '#5CC8E0',
          secondaryColor: '#16222D',
          tertiaryColor: '#111A22',
          edgeLabelBackground: '#0B1117',
          fontFamily: 'IBM Plex Mono, monospace',
          fontSize: '14px',
        },
        flowchart: { curve: 'basis', padding: 14 },
      });
      const { svg } = await mermaid.render(id, source);
      box.innerHTML = svg;
      box.querySelector('svg')?.setAttribute('aria-label', 'Diagrama dos serviços detectados');
      box.querySelector('svg')?.setAttribute('role', 'img');
      expand.hidden = false;
    } catch (_) {
      document.getElementById('d' + id)?.remove(); // mermaid deixa o container de erro no body
      const pre = h('pre', null, source);
      box.replaceChildren(h('p', 'diagram-note', 'Não foi possível desenhar o diagrama. Código Mermaid gerado:'), pre);
    }
  }

  function openDiagram() {
    const svg = els.diagram.querySelector('svg');
    if (!svg) return;
    els.dialogCanvas.replaceChildren(svg.cloneNode(true));
    setZoom(1);
    els.dialog.showModal();
  }

  function setZoom(value) {
    zoom = Math.max(0.5, Math.min(3, value));
    els.dialogCanvas.style.setProperty('--zoom', zoom);
    $('zoomLabel').textContent = `${Math.round(zoom * 100)}%`;
  }

  /* ----------------------------------------------------------------------
     Relatorio tecnico
     ---------------------------------------------------------------------- */
  function reportMarkdown() {
    return (lastResult && (lastResult.technical_report || lastResult.final_report)) || '';
  }

  function setReportToggle(open) {
    const btn = $('toggleReport');
    btn.setAttribute('aria-expanded', String(open));
    btn.lastChild.textContent = open ? 'Ocultar relatório técnico' : 'Ver relatório técnico';
  }

  function toggleReport() {
    const section = $('secReport');
    const open = section.hidden;
    section.hidden = !open;
    setReportToggle(open);
    if (open) {
      section.classList.remove('reveal');
      section.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth' });
    }
  }

  async function copyReport() {
    const btn = $('copyReport');
    try {
      await navigator.clipboard.writeText(reportMarkdown());
      btn.lastChild.textContent = 'Copiado!';
    } catch (_) {
      btn.lastChild.textContent = 'Não foi possível copiar';
    }
    setTimeout(() => { btn.lastChild.textContent = 'Copiar Markdown'; }, 2000);
  }

  function downloadReport() {
    const blob = new Blob([reportMarkdown()], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = h('a');
    a.href = url;
    a.download = `archiq-relatorio-${String(lastResult?.session_id || 'sessao').slice(0, 8)}.md`;
    a.click();
    URL.revokeObjectURL(url);
  }

  init();
})();
