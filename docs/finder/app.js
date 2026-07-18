/* Policy & Grant Finder — main application (stages 1–5).
 * Pure browser JS, no build step: state lives in `S`, scenarios persist in
 * localStorage. Data access is in api.js, text analytics in analytics.js.
 */
(function () {
  'use strict';

  const LS_KEY = 'gif_finder_scenarios_v1';

  const S = {
    keywords: [],
    docs: [],                 // normalised docs from the last search
    selected: new Set(),      // doc ids included in the analysis
    topics: [],               // bridge topics from analytics
    selectedTopics: new Set(),
    scenarios: [],            // [{name, created, topics:[], docs:[{id,kind,title,url,budgetEUR,text}]}]
    co2: null,                // co2_assumptions.json content
    metrics: []
  };

  const $ = id => document.getElementById(id);
  const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
    c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  /* ─────────── stage navigation ─────────── */

  function goto(n) {
    document.querySelectorAll('.stage-panel').forEach(p => p.classList.add('hidden'));
    $('stage-' + n).classList.remove('hidden');
    document.querySelectorAll('.stepper .step').forEach(b => {
      const k = +b.dataset.stage;
      b.classList.toggle('on', k === n);
      b.classList.toggle('done', k < n);
    });
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  document.querySelectorAll('.stepper .step').forEach(b =>
    b.addEventListener('click', () => goto(+b.dataset.stage)));

  /* ─────────── stage 1: keywords ─────────── */

  const SUGGESTIONS = ['bioeconomy', 'circular economy', 'biomass', 'just transition',
    'carbon farming', 'soil', 'renewable energy', 'carbon capture', 'biorefinery',
    'nature-based solutions', 'recycling', 'climate neutrality'];

  function renderKeywords() {
    $('kw-chips').innerHTML = S.keywords.map((k, i) =>
      `<span class="chip">${esc(k)}<button aria-label="Remove ${esc(k)}" data-i="${i}">×</button></span>`).join('') ||
      '<span class="empty">No keywords yet — add at least one.</span>';
    $('kw-chips').querySelectorAll('button').forEach(b =>
      b.addEventListener('click', () => { S.keywords.splice(+b.dataset.i, 1); renderKeywords(); }));
    $('kw-suggest').innerHTML = SUGGESTIONS.map(s =>
      `<button class="opt" ${S.keywords.includes(s) ? 'disabled' : ''}>${esc(s)}</button>`).join('');
    $('kw-suggest').querySelectorAll('.opt').forEach(b =>
      b.addEventListener('click', () => addKeyword(b.textContent)));
    $('go-search').disabled = S.keywords.length === 0;
  }

  function addKeyword(raw) {
    const k = String(raw || '').trim().toLowerCase().replace(/\s+/g, ' ');
    if (k && k.length >= 2 && !S.keywords.includes(k)) S.keywords.push(k);
    $('kw-input').value = '';
    renderKeywords();
  }

  $('kw-add').addEventListener('click', () => addKeyword($('kw-input').value));
  $('kw-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); addKeyword($('kw-input').value); }
  });

  /* ─────────── stage 2: search ─────────── */

  function docCard(d) {
    const checked = S.selected.has(d.id) ? 'checked' : '';
    const budget = d.budgetEUR
      ? `<span class="tag budget">≈ ${(d.budgetEUR / 1e6).toLocaleString('en', { maximumFractionDigits: 1 })} M€</span>` : '';
    return `<label class="doc ${d.kind}">
      <input type="checkbox" data-id="${esc(d.id)}" ${checked}>
      <span>
        <span class="t"><a href="${esc(d.url)}" target="_blank" rel="noopener">${esc(d.title)}</a></span>
        <span class="m">${esc(d.doctype || '')}${d.date ? ' · ' + esc(d.date) : ''} ${budget}</span>
        ${d.summary ? `<span class="s">${esc(d.summary)}</span>` : ''}
      </span>
    </label>`;
  }

  function renderDocs() {
    for (const kind of ['policy', 'grant']) {
      const docs = S.docs.filter(d => d.kind === kind);
      const el = $(kind === 'policy' ? 'list-policies' : 'list-grants');
      el.innerHTML = docs.length ? docs.map(docCard).join('')
        : '<div class="empty">No matches for these keywords.</div>';
      $(kind === 'policy' ? 'cnt-policies' : 'cnt-grants').textContent = String(docs.length);
    }
    document.querySelectorAll('.doclist input[type=checkbox]').forEach(cb =>
      cb.addEventListener('change', () => {
        cb.checked ? S.selected.add(cb.dataset.id) : S.selected.delete(cb.dataset.id);
        $('go-topics').disabled = S.selected.size === 0;
      }));
    $('go-topics').disabled = S.selected.size === 0;
  }

  function srcPill(kind, res) {
    const label = kind === 'policy' ? 'EUR-Lex' : 'Funding & Tenders';
    const cls = res.tier === 'live' ? 'live' : res.tier === 'cache' ? 'cache' : 'err';
    const word = res.tier === 'live' ? 'live' : res.tier === 'cache' ? 'snapshot' : 'unavailable';
    return `<span class="srcpill ${cls}" title="${esc(res.detail)}">${label}: ${word} · ${res.items.length} docs</span>`;
  }

  async function runSearch() {
    goto(2);
    $('src-status').innerHTML = '<span class="srcpill"><span class="spin"></span> querying EUR-Lex and the Funding &amp; Tenders API …</span>';
    $('list-policies').innerHTML = $('list-grants').innerHTML = '<div class="empty">Searching…</div>';
    const [pol, gra] = await Promise.all([
      FinderAPI.search('policy', S.keywords),
      FinderAPI.search('grant', S.keywords)
    ]);
    S.docs = pol.items.concat(gra.items);
    S.selected = new Set(S.docs.map(d => d.id));   // everything included by default
    $('src-status').innerHTML = srcPill('policy', pol) + srcPill('grant', gra);
    renderDocs();
  }

  $('go-search').addEventListener('click', runSearch);
  $('back-1').addEventListener('click', () => goto(1));
  $('sel-all').addEventListener('click', () => { S.selected = new Set(S.docs.map(d => d.id)); renderDocs(); });
  $('sel-none').addEventListener('click', () => { S.selected = new Set(); renderDocs(); });

  /* ─────────── stage 3: topic analysis ─────────── */

  function selectedDocs() { return S.docs.filter(d => S.selected.has(d.id)); }

  function renderTopicChips() {
    const el = $('topic-chips');
    el.innerHTML = S.topics.length ? S.topics.map(t =>
      `<button class="tchip ${S.selectedTopics.has(t.term) ? 'sel' : ''}" data-t="${esc(t.term)}">
         ${esc(t.term)}<small>${t.dfPolicy}p · ${t.dfGrant}g</small></button>`).join('')
      : '<div class="empty">No terms appear in both corpora — select more documents.</div>';
    el.querySelectorAll('.tchip').forEach(b => b.addEventListener('click', () => {
      const t = b.dataset.t;
      S.selectedTopics.has(t) ? S.selectedTopics.delete(t) : S.selectedTopics.add(t);
      renderTopicChips();
      $('go-scenarios').disabled = S.selectedTopics.size === 0;
    }));
    $('go-scenarios').disabled = S.selectedTopics.size === 0;
  }

  function runAnalysis() {
    goto(3);
    const docs = selectedDocs();
    const res = FinderAnalytics.analyze(docs, S.keywords);
    S.topics = res.bridge;
    for (const t of S.selectedTopics)              // drop stale selections
      if (!S.topics.some(x => x.term === t)) S.selectedTopics.delete(t);
    const nP = docs.filter(d => d.kind === 'policy').length;
    const nG = docs.filter(d => d.kind === 'grant').length;
    $('note-policies').textContent = `Share of the ${nP} selected policy documents containing the term.`;
    $('note-grants').textContent = `Share of the ${nG} selected grant documents containing the term.`;
    $('chart-policies').innerHTML = FinderAnalytics.barChartSVG(res.policyTerms, '#0A6B65', nP);
    $('chart-grants').innerHTML = FinderAnalytics.barChartSVG(res.grantTerms, '#B67F27', nG);
    renderTopicChips();
  }

  $('go-topics').addEventListener('click', runAnalysis);
  $('back-2').addEventListener('click', () => goto(2));

  /* ─────────── stage 4: scenarios ─────────── */

  function docText(d) { return (d.title + ' ' + d.summary).toLowerCase(); }

  function renderBundles() {
    const docs = selectedDocs();
    const topics = [...S.selectedTopics];
    $('bundle-area').innerHTML = topics.map(t => {
      const hits = docs.filter(d => docText(d).includes(t));
      const pol = hits.filter(d => d.kind === 'policy');
      const gra = hits.filter(d => d.kind === 'grant');
      const row = d => `<label class="doc ${d.kind}">
          <input type="checkbox" class="bundle-doc" data-id="${esc(d.id)}" checked>
          <span><span class="t">${esc(d.title)}</span>
          <span class="m">${d.budgetEUR ? '≈ ' + (d.budgetEUR / 1e6).toFixed(1) + ' M€' : esc(d.doctype || '')}</span></span>
        </label>`;
      return `<div class="chart" style="margin-top:12px">
        <h3>Topic: “${esc(t)}” <small style="color:var(--faint)">(${pol.length} policies · ${gra.length} grants)</small></h3>
        <div class="cols">
          <div>${pol.map(row).join('') || '<div class="empty">no policies</div>'}</div>
          <div>${gra.map(row).join('') || '<div class="empty">no grants</div>'}</div>
        </div>
      </div>`;
    }).join('') || '<div class="empty">No topics selected.</div>';
  }

  function loadScenarios() {
    try { S.scenarios = JSON.parse(localStorage.getItem(LS_KEY) || '[]'); }
    catch (e) { S.scenarios = []; }
  }
  function saveScenarios() { localStorage.setItem(LS_KEY, JSON.stringify(S.scenarios)); }

  function renderScenarios() {
    $('scenario-list').innerHTML = S.scenarios.map((sc, i) => {
      const nP = sc.docs.filter(d => d.kind === 'policy').length;
      const nG = sc.docs.filter(d => d.kind === 'grant').length;
      return `<div class="scenario-card">
        <h3>${esc(sc.name)} <button data-i="${i}" title="Delete scenario">✕ delete</button></h3>
        <p class="meta">Topics: ${sc.topics.map(esc).join(', ')} · ${nP} policies · ${nG} grants · saved ${esc(String(sc.created).slice(0, 10))}</p>
        <ul>${sc.docs.slice(0, 6).map(d => `<li>${esc(d.title)}</li>`).join('')}
            ${sc.docs.length > 6 ? `<li>… and ${sc.docs.length - 6} more</li>` : ''}</ul>
      </div>`;
    }).join('') || '<div class="empty">No scenarios saved yet.</div>';
    $('scenario-list').querySelectorAll('h3 button').forEach(b =>
      b.addEventListener('click', () => { S.scenarios.splice(+b.dataset.i, 1); saveScenarios(); renderScenarios(); }));
    $('go-metrics').disabled = S.scenarios.length === 0;
  }

  $('go-scenarios').addEventListener('click', () => { goto(4); renderBundles(); renderScenarios(); });
  $('back-3').addEventListener('click', () => goto(3));

  $('save-scenario').addEventListener('click', () => {
    const name = $('scenario-name').value.trim() || ('Scenario ' + (S.scenarios.length + 1));
    const ids = new Set([...document.querySelectorAll('.bundle-doc:checked')].map(cb => cb.dataset.id));
    if (ids.size === 0) { alert('Tick at least one policy or grant for this scenario.'); return; }
    const byId = new Map(S.docs.map(d => [d.id, d]));
    // Embed a slim copy of each doc so saved scenarios survive page reloads.
    const docs = [...ids].map(id => byId.get(id)).filter(Boolean).map(d => ({
      id: d.id, kind: d.kind, title: d.title, url: d.url,
      budgetEUR: d.budgetEUR, src: d.source, text: docText(d)
    }));
    S.scenarios.push({ name, created: new Date().toISOString(), topics: [...S.selectedTopics], docs });
    saveScenarios();
    $('scenario-name').value = '';
    renderScenarios();
  });

  /* ─────────── stage 5: metrics ─────────── */

  async function loadCo2() {
    if (S.co2) return S.co2;
    S.co2 = await FinderAPI.loadJson('data/co2_assumptions.json');
    return S.co2;
  }

  function scenarioMetrics(sc, co2) {
    const grants = sc.docs.filter(d => d.kind === 'grant');
    const known = grants.filter(g => g.budgetEUR);
    const funding = known.reduce((a, g) => a + g.budgetEUR, 0);
    const text = sc.docs.map(d => d.text).join(' ') + ' ' + sc.topics.join(' ').toLowerCase();
    // whole-word matching, so "fuel" does not fire on "biofuels"
    const hasTerm = t => new RegExp('\\b' + t.toLowerCase().replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '\\b').test(text);
    const matched = (co2.assumptions || []).filter(a => a.match_terms.some(hasTerm));
    const co2Index = matched.reduce((a, m) => a + m.score, 0);
    const sectoral = matched.filter(m => m.gtco2e_yr[1] > 0);
    const savers = (co2.cost_saving_assumptions || []).filter(a => a.match_terms.some(hasTerm));

    // Confidence rating (data completeness, not a statistical CI) — capped at
    // 75/100 because keyword screening on generic assumptions can never be
    // fully certain. Deductions documented in co2_assumptions.json →
    // method_uncertainty.
    let conf = 75;
    const missingShare = grants.length ? (grants.length - known.length) / grants.length : 1;
    conf -= Math.round(40 * missingShare);
    if (sc.docs.length < 3) conf -= 25; else if (sc.docs.length < 6) conf -= 10;
    if (matched.length && sectoral.length / matched.length < 0.5) conf -= 10;
    if (sc.docs.some(d => d.src !== 'live')) conf -= 5;   // snapshot/sample data may be stale
    conf = Math.min(75, Math.max(5, conf));

    return {
      name: sc.name,
      nPolicies: sc.docs.filter(d => d.kind === 'policy').length,
      nGrants: grants.length,
      fundingEUR: funding,
      // a call-topic budget usually funds several projects → 25–100 % band
      fundingLowEUR: Math.round(funding * 0.25),
      fundingHighEUR: funding,
      fundingUnknown: grants.length - known.length,
      saveRangeEUR: [
        savers.reduce((a, s) => a + s.save_eur_yr[0], 0),
        savers.reduce((a, s) => a + s.save_eur_yr[1], 0)
      ],
      matchedSavers: savers.map(s => s.driver),
      co2Index,
      co2RangeGt: [
        matched.reduce((a, m) => a + m.gtco2e_yr[0], 0),
        matched.reduce((a, m) => a + m.gtco2e_yr[1], 0)
      ],
      matchedTopics: matched.map(m => m.topic),
      sectoralTopics: sectoral.map(m => m.topic),
      exampleTasks: sectoral
        .filter(m => m.example_tasks && m.example_tasks.length)
        .sort((a, b) => b.score - a.score)
        .slice(0, 2)
        .map(m => ({ topic: m.topic, tasks: m.example_tasks.slice(0, 2) })),
      confidence: conf,
      confidenceLabel: conf >= 60 ? 'High' : conf >= 40 ? 'Medium' : 'Low'
    };
  }

  const fmtM = eur => (eur / 1e6).toLocaleString('en', { maximumFractionDigits: 1 });

  /* One actionable "how to proceed" sentence block per scenario, plus an
   * overall pick. Deterministic text built from the computed metrics. */
  function recommendation(m) {
    const parts = [];
    if (m.nGrants > 0) {
      parts.push(`To realise the funding potential, prepare consortium proposals for the ` +
        `${m.nGrants} Horizon topic${m.nGrants > 1 ? 's' : ''} in this scenario — realistically ` +
        `€${fmtM(m.fundingLowEUR)}–${fmtM(m.fundingHighEUR)} M of the published call budgets` +
        (m.fundingUnknown ? ` (plus ${m.fundingUnknown} topic${m.fundingUnknown > 1 ? 's' : ''} without budget data as upside)` : '') + `.`);
    } else {
      parts.push(`This scenario contains no grants yet — add matching Horizon topics before pursuing it.`);
    }
    if (m.nPolicies > 0) {
      parts.push(`Anchor the work explicitly in the ${m.nPolicies} matching ` +
        `polic${m.nPolicies > 1 ? 'ies' : 'y'} to demonstrate EU policy alignment in the proposal.`);
    }
    if (m.sectoralTopics.length) {
      parts.push(`The CO₂ mitigation potential is carried by ${m.sectoralTopics.slice(0, 3).join(', ')}` +
        ` — make ${m.sectoralTopics.length > 1 ? 'these' : 'this'} the technical core of the work plan.`);
    }
    for (const et of m.exampleTasks) {
      parts.push(`Exemplary first operational steps for ${et.topic.toLowerCase()}: ` +
        `(1) ${et.tasks[0]}${et.tasks[1] ? `; (2) ${et.tasks[1]}` : ''}.`);
    }
    if (m.matchedSavers.length) {
      parts.push(`Cost savings would come mainly from ${m.matchedSavers.slice(0, 3).join('; ').toLowerCase()}` +
        ` (indicative €${fmtM(m.saveRangeEUR[0])}–${fmtM(m.saveRangeEUR[1])} M/yr for a typical actor)` +
        ` — quantify these with site-specific data before any investment decision.`);
    }
    parts.push(`Confidence: ${m.confidenceLabel} (${m.confidence}/75 — capped, this is a keyword screening)` +
      (m.confidence < 60
        ? ` — firm up by ${m.fundingUnknown ? 'adding budget data for the open topics' : 'including more matching documents'} and by verifying the linked source documents.`
        : `; verify against the linked source documents before committing resources.`));
    return parts.join(' ');
  }

  function bestScenarioIndex(M) {
    if (M.length < 2) return 0;
    // rank-sum over funding mid, CO2 index and savings mid (lower rank = better)
    const rank = key => {
      const order = [...M.keys()].sort((a, b) => key(M[b]) - key(M[a]));
      const r = new Array(M.length);
      order.forEach((idx, pos) => { r[idx] = pos; });
      return r;
    };
    const rf = rank(m => (m.fundingLowEUR + m.fundingHighEUR) / 2);
    const rc = rank(m => m.co2Index);
    const rs = rank(m => (m.saveRangeEUR[0] + m.saveRangeEUR[1]) / 2);
    let best = 0, bestSum = Infinity;
    M.forEach((m, i) => {
      const s = rf[i] + rc[i] + rs[i];
      if (s < bestSum) { bestSum = s; best = i; }
    });
    return best;
  }

  function renderMetrics() {
    const M = S.metrics;
    $('metrics-chart').innerHTML =
      '<div class="charts"><div class="chart"><h3>Potential funding (M€, 25–100 % of call budgets)</h3>' +
      FinderAnalytics.barChartSVG(M.map(m => ({
        label: m.name, value: (m.fundingLowEUR + m.fundingHighEUR) / 2e6,
        lo: m.fundingLowEUR / 1e6, hi: m.fundingHighEUR / 1e6 })), '#B67F27') +
      '</div><div class="chart"><h3>Potential cost savings (M€/yr, indicative)</h3>' +
      FinderAnalytics.barChartSVG(M.map(m => ({
        label: m.name, value: (m.saveRangeEUR[0] + m.saveRangeEUR[1]) / 2e6,
        lo: m.saveRangeEUR[0] / 1e6, hi: m.saveRangeEUR[1] / 1e6 })), '#3D7A75') +
      '</div><div class="chart"><h3>CO<sub>2</sub> mitigation index (indicative)</h3>' +
      FinderAnalytics.barChartSVG(M.map(m => ({ label: m.name, value: m.co2Index })), '#0A6B65') +
      '</div></div>';
    $('metrics-table').innerHTML = `<table class="metrics-table"><thead><tr>
      <th>Scenario</th><th>Policies</th><th>Grants</th><th>Funding potential</th>
      <th>Cost savings /yr</th><th>CO₂ index</th><th>Global sectoral potential*</th><th>Confidence</th>
      </tr></thead><tbody>` + M.map(m => `<tr>
        <td>${esc(m.name)}</td>
        <td class="num">${m.nPolicies}</td>
        <td class="num">${m.nGrants}</td>
        <td class="num">${fmtM(m.fundingLowEUR)}–${fmtM(m.fundingHighEUR)} M€${m.fundingUnknown ? ` <small>(+${m.fundingUnknown} without budget data)</small>` : ''}</td>
        <td class="num">${fmtM(m.saveRangeEUR[0])}–${fmtM(m.saveRangeEUR[1])} M€</td>
        <td class="num">${m.co2Index}</td>
        <td class="num">${m.co2RangeGt[0].toFixed(1)}–${m.co2RangeGt[1].toFixed(1)} GtCO₂e/yr</td>
        <td><span class="conf ${m.confidenceLabel.toLowerCase()}" title="Data-completeness rating, capped at 75/100 — see assumptions box">${m.confidenceLabel} · ${m.confidence}/75</span></td>
      </tr>`).join('') + '</tbody></table>';
    renderRecommendations(M);
  }

  function renderRecommendations(M) {
    if (!M.length) { $('recommendations').innerHTML = ''; return; }
    const best = bestScenarioIndex(M);
    const overall = M.length > 1
      ? `<p class="reco-overall"><strong>Where to start:</strong> “${esc(M[best].name)}” ranks best across
         funding, CO₂ potential and cost savings — pursue it first, and keep the others as fallback
         options for later calls.</p>` : '';
    $('recommendations').innerHTML = `<div class="reco">
      <h3>How to proceed</h3>${overall}
      ${M.map((m, i) => `<p><strong>${esc(m.name)}${i === best && M.length > 1 ? ' ★' : ''}:</strong>
        ${esc(recommendation(m))}</p>`).join('')}
    </div>`;
  }

  function renderAssumptions(co2) {
    $('assumptions-box').innerHTML = `<h3>How these figures are computed — read this first</h3>
      <p><strong>Uncertainty.</strong> ${esc(co2.method_uncertainty || '')}</p>
      <p><strong>CO₂ index.</strong> ${esc(co2.method || '')}</p>
      <p><strong>Cost savings.</strong> ${esc(co2.method_cost_savings || '')}</p>
      <details><summary>Show CO₂ assumption entries (${(co2.assumptions || []).length}) — edit
      <code>docs/finder/data/co2_assumptions.json</code> to change them</summary>
      <table><thead><tr><th>Topic</th><th>Match terms</th><th>Score</th><th>GtCO₂e/yr (global, 2030)</th><th>Basis</th></tr></thead>
      <tbody>${(co2.assumptions || []).map(a => `<tr>
        <td>${esc(a.topic)}</td><td>${a.match_terms.map(esc).join(', ')}</td>
        <td>${a.score}</td><td>${a.gtco2e_yr[0]}–${a.gtco2e_yr[1]}</td><td>${esc(a.basis)}</td>
      </tr>`).join('')}</tbody></table></details>
      <details><summary>Show cost-saving drivers (${(co2.cost_saving_assumptions || []).length})</summary>
      <table><thead><tr><th>Driver</th><th>Match terms</th><th>€/yr (typical actor)</th><th>Basis</th></tr></thead>
      <tbody>${(co2.cost_saving_assumptions || []).map(a => `<tr>
        <td>${esc(a.driver)}</td><td>${a.match_terms.map(esc).join(', ')}</td>
        <td>${fmtM(a.save_eur_yr[0])}–${fmtM(a.save_eur_yr[1])} M</td><td>${esc(a.basis)}</td>
      </tr>`).join('')}</tbody></table></details>`;
  }

  async function runMetrics() {
    goto(5);
    try {
      const co2 = await loadCo2();
      S.metrics = S.scenarios.map(sc => scenarioMetrics(sc, co2));
      renderMetrics();
      renderAssumptions(co2);
    } catch (e) {
      $('metrics-table').innerHTML = `<div class="empty">Could not load CO₂ assumptions: ${esc(e.message)}</div>`;
    }
  }

  $('go-metrics').addEventListener('click', runMetrics);
  $('back-4').addEventListener('click', () => goto(4));

  /* export */
  function download(name, mime, content) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([content], { type: mime }));
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }
  $('export-json').addEventListener('click', () =>
    download('finder_scenarios.json', 'application/json',
      JSON.stringify({ generated: new Date().toISOString(), keywords: S.keywords,
                       scenarios: S.scenarios, metrics: S.metrics }, null, 2)));
  $('export-csv').addEventListener('click', () => {
    const head = 'scenario,policies,grants,funding_eur_low,funding_eur_high,grants_without_budget,' +
      'cost_saving_eur_yr_low,cost_saving_eur_yr_high,co2_index,co2_gt_low,co2_gt_high,' +
      'confidence,confidence_label,matched_topics,matched_saving_drivers';
    const rows = S.metrics.map(m => [
      '"' + m.name.replace(/"/g, '""') + '"', m.nPolicies, m.nGrants,
      m.fundingLowEUR, m.fundingHighEUR, m.fundingUnknown,
      m.saveRangeEUR[0], m.saveRangeEUR[1], m.co2Index, m.co2RangeGt[0], m.co2RangeGt[1],
      m.confidence, m.confidenceLabel,
      '"' + m.matchedTopics.join('; ') + '"',
      '"' + m.matchedSavers.join('; ') + '"'
    ].join(','));
    download('finder_metrics.csv', 'text/csv', [head].concat(rows).join('\n'));
  });

  /* ─────────── init ─────────── */
  loadScenarios();
  renderKeywords();
  renderScenarios();
})();
