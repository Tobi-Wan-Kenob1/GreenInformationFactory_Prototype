/* Policy & Grant Finder — data access layer.
 *
 * Two tiers per source:
 *   live   — browser fetch() against the public EU endpoints
 *   cache  — JSON snapshots under data/ (written by the finder-data GitHub
 *            Action, or the bundled sample_*.json shipped with the repo)
 *
 * Every document is normalised to:
 *   { id, kind: 'policy'|'grant', title, summary, date, url, budgetEUR|null,
 *     doctype, source: 'live'|'cache' }
 */
(function () {
  'use strict';

  const SEDIA_URL = 'https://api.tech.ec.europa.eu/search-api/prod/rest/search';
  const CELLAR_URL = 'https://publications.europa.eu/webapi/rdf/sparql';
  const FETCH_TIMEOUT_MS = 12000;

  // The search API answers 400 ("Result size limit 100mb has been reached")
  // above this page size, and 500 for multipart bodies — send form-urlencoded.
  const PAGE_SIZE = 25;
  const STATUS = { forthcoming: '31094501', open: '31094502', closed: '31094503' };

  // Default window: everything from 2015 to today, closed calls included.
  function normFilters(f) {
    const now = new Date().getFullYear();
    f = f || {};
    return {
      from: Math.min(Math.max(parseInt(f.from, 10) || 2015, 1958), now),
      to: Math.min(Math.max(parseInt(f.to, 10) || now, 1958), now),
      includeClosed: f.includeClosed !== false
    };
  }

  function inWindow(doc, flt) {
    if (!doc.date) return true;                 // undated records are never hidden
    const y = parseInt(String(doc.date).slice(0, 4), 10);
    return !y || (y >= flt.from && y <= flt.to);
  }

  /* ---------- keyword expansion ----------
   * EUR-Lex matching is a raw substring test, so "bioeconomy" alone misses
   * "bio-economy" and "bio economy". Expand each keyword into the spellings
   * EU documents actually use. Deliberately conservative: orthographic
   * variants and a naive plural, never semantic synonyms — those would widen
   * recall in ways the user did not ask for. */
  const COMPOUND_PREFIXES = ['bio', 'agro', 'eco', 'geo', 'micro', 'nano', 'multi'];

  function expandKeyword(keyword) {
    const base = String(keyword || '').toLowerCase().trim();
    if (!base) return [];
    const out = [base];
    const add = v => { if (v && out.indexOf(v) === -1) out.push(v); };

    if (base.indexOf('-') !== -1) {
      add(base.replace(/-/g, ' '));
      add(base.replace(/-/g, ''));
    }
    if (base.indexOf(' ') !== -1) {
      add(base.replace(/ /g, '-'));
      add(base.replace(/ /g, ''));
    }
    // a solid compound is often written split or hyphenated: bioeconomy →
    // bio-economy / bio economy
    for (const p of COMPOUND_PREFIXES) {
      if (base.indexOf(p) === 0 && base.length > p.length + 3) {
        add(p + '-' + base.slice(p.length));
        add(p + ' ' + base.slice(p.length));
      }
    }
    if (/[^aeiours]s$/.test(base)) add(base.slice(0, -1));   // biofuels → biofuel
    else if (!/s$/.test(base)) add(base + 's');
    return out;
  }

  function expandAll(keywords) {
    const out = [];
    (keywords || []).forEach(k => expandKeyword(k).forEach(v => {
      if (out.indexOf(v) === -1) out.push(v);
    }));
    return out;
  }

  /* ---------- relevance ----------
   * Results arrive in the API's own order (SEDIA by status, CELLAR by date),
   * which is not relevance to *these* keywords. Score client-side: a title hit
   * outweighs a body hit, matching several keywords outweighs matching one,
   * and recency only breaks ties. */
  function scoreDoc(doc, keywords) {
    const title = String(doc.title || '').toLowerCase();
    const body = (title + ' ' + String(doc.summary || '')).toLowerCase();
    const matched = [];
    let score = 0;
    for (const k of keywords || []) {
      const variants = expandKeyword(k);
      if (variants.some(v => title.indexOf(v) !== -1)) { score += 3; matched.push(k); }
      else if (variants.some(v => body.indexOf(v) !== -1)) { score += 1; matched.push(k); }
    }
    if (matched.length > 1) score += 2;
    const year = parseInt(String(doc.date || '').slice(0, 4), 10);
    if (year) score += Math.max(0, Math.min(1, (year - 2000) / 30));
    return { score: score, matched: matched };
  }

  function rankDocs(docs, keywords) {
    docs.forEach(d => {
      const r = scoreDoc(d, keywords);
      d.relevance = r.score;
      d.matchedKeywords = r.matched;
    });
    return docs.sort((a, b) => b.relevance - a.relevance ||
                               String(b.date || '').localeCompare(String(a.date || '')));
  }

  function timeoutFetch(url, opts) {
    const ctrl = new AbortController();
    const t = setTimeout(() => ctrl.abort(), FETCH_TIMEOUT_MS);
    return fetch(url, Object.assign({}, opts, { signal: ctrl.signal }))
      .finally(() => clearTimeout(t));
  }

  /* ---------- helpers ---------- */

  function stripTags(s) {
    return String(s == null ? '' : s).replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim();
  }

  function first(v) { return Array.isArray(v) ? v[0] : v; }

  // The API ignores the type filter we send, so support FAQs and tenders
  // arrive mixed in. Type 1 alone is not enough — some FAQs are indexed as
  // type 1 too; real call topics always carry a topic identifier.
  function isCallTopic(r) {
    const meta = r.metadata || {};
    return String(first(meta.type) || '') === '1' &&
           !!first(meta.identifier) &&
           !first(meta.esST_question);
  }

  // SEDIA nests the money as budgetOverview.budgetTopicActionMap.<id>[].
  // budgetYearMap = {"2016": 188650000}. Sum years within a map, then take the
  // largest map — the same call budget repeats per action and would otherwise
  // be double-counted.
  function budgetYearTotals(node, out) {
    out = out || [];
    if (Array.isArray(node)) {
      node.forEach(n => budgetYearTotals(n, out));
    } else if (node && typeof node === 'object') {
      for (const k of Object.keys(node)) {
        const v = node[k];
        if (k === 'budgetYearMap' && v && typeof v === 'object') {
          const years = Object.values(v).filter(x => typeof x === 'number');
          if (years.length) out.push(years.reduce((a, b) => a + b, 0));
        } else {
          budgetYearTotals(v, out);
        }
      }
    }
    return out;
  }

  function extractBudgetEUR(meta) {
    if (!meta) return null;
    const bo = first(meta.budgetOverview) || first(meta.budgetOverviewJSONItem);
    if (typeof bo === 'string' && bo.indexOf('{') !== -1) {
      try {
        const totals = budgetYearTotals(JSON.parse(bo));
        if (totals.length) return Math.round(Math.max.apply(null, totals));
      } catch (e) { /* not JSON after all */ }
    }
    const cands = [];
    const direct = first(meta.budget) || first(meta.cftEstimatedTotalProcedureValue);
    if (direct != null) cands.push(direct);
    if (typeof bo === 'string') {
      bo.replace(/"(?:budget|totalBudget|plannedOpeningBudget)"\s*:\s*"?([\d.,\s]+)"?/g,
        (_, n) => { cands.push(n); return _; });
    }
    for (const c of cands) {
      const n = parseFloat(String(c).replace(/[^\d.]/g, ''));
      if (isFinite(n) && n > 1000) return Math.round(n);
    }
    // Last resort: free-text "Indicative budget: 188.65 Million Euros".
    const infos = stripTags(first(meta.additionalInfos) || '');
    const m = /budget[^0-9]{0,40}([\d]+(?:[.,][\d]+)?)\s*(million|m\b|bn|billion)?/i.exec(infos);
    if (m) {
      let amount = parseFloat(m[1].replace(',', '.'));
      const unit = (m[2] || '').toLowerCase();
      if (unit.charAt(0) === 'm') amount *= 1e6;
      else if (unit.charAt(0) === 'b') amount *= 1e9;
      if (isFinite(amount) && amount > 1000) return Math.round(amount);
    }
    return null;
  }

  function normalizeGrant(r, source) {
    const meta = r.metadata || {};
    const id = first(meta.identifier) || r.reference || r.url || Math.random().toString(36).slice(2);
    const description = stripTags(first(meta.description) || first(meta.descriptionByte) ||
                                  r.summary || r.content || '');
    const terms = [].concat(meta.keywords || [], meta.tags || []).map(String);
    const uniqTerms = terms.filter((t, i) => terms.indexOf(t) === i);
    return {
      id: 'g:' + id,
      kind: 'grant',
      title: stripTags(first(meta.title) || r.title || id),
      summary: (description.slice(0, 600) +
                (uniqTerms.length ? ' · ' + uniqTerms.join(', ') : '')).trim(),
      date: String(first(meta.startDate) || first(meta.es_SortDate) ||
                   first(meta.publicationDateLong) || '').slice(0, 10) || null,
      deadline: String(first(meta.deadlineDate) || '').slice(0, 10) || null,
      status: String(first(meta.status) || '') || null,
      callId: stripTags(first(meta.callIdentifier) || '') || null,
      programmePeriod: stripTags(first(meta.programmePeriod) || '') || null,
      url: 'https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/' +
           encodeURIComponent(String(id).toLowerCase()),
      budgetEUR: extractBudgetEUR(meta),
      doctype: 'Call topic',
      source: source
    };
  }

  function normalizePolicyBinding(b, source) {
    const uri = b.work ? b.work.value : '';
    const celex = b.celex ? b.celex.value : null;
    return {
      id: 'p:' + (celex || uri || Math.random().toString(36).slice(2)),
      kind: 'policy',
      title: stripTags(b.title ? b.title.value : uri),
      summary: '',
      date: b.date ? String(b.date.value).slice(0, 10) : null,
      url: celex
        ? 'https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:' + encodeURIComponent(celex)
        : uri,
      budgetEUR: null,
      doctype: b.type ? String(b.type.value).split('/').pop() : 'Act',
      source: source
    };
  }

  /* ---------- live: Horizon grants via SEDIA search API ---------- */

  // One request per keyword: the API caps the whole matched result set at
  // 100 MB, and a broad "a OR b OR c…" query exceeds it (HTTP 400) whatever
  // the page size. The body must be form-urlencoded — multipart returns 500.
  async function sediaSearch(keyword, statuses) {
    const body = new URLSearchParams({
      query: JSON.stringify({
        bool: { must: [{ terms: { type: ['1'] } }, { terms: { status: statuses } }] }
      }),
      languages: JSON.stringify(['en']),
      sort: JSON.stringify({ field: 'sortStatus', order: 'DESC' })
    });
    const url = SEDIA_URL + '?apiKey=SEDIA&pageNumber=1&pageSize=' + PAGE_SIZE +
                '&text=' + encodeURIComponent('"' + keyword + '"');
    const resp = await timeoutFetch(url, { method: 'POST', body: body });
    if (!resp.ok) throw new Error('SEDIA HTTP ' + resp.status);
    return (await resp.json()).results || [];
  }

  async function liveGrants(keywords, flt) {
    const statuses = [STATUS.forthcoming, STATUS.open];
    if (flt.includeClosed) statuses.push(STATUS.closed);

    const settled = await Promise.all(keywords.map(k =>
      sediaSearch(k, statuses).then(
        results => ({ k: k, results: results }),
        err => ({ k: k, err: err }))));

    const failed = settled.filter(s => s.err);
    if (failed.length === settled.length) {
      throw new Error(failed[0].err.message);      // every keyword failed
    }
    const seen = new Set();
    const out = [];
    for (const s of settled) {
      for (const r of s.results || []) {
        if (!isCallTopic(r)) continue;            // drop FAQs / tenders
        const d = normalizeGrant(r, 'live');
        if (seen.has(d.id) || !inWindow(d, flt)) continue;
        seen.add(d.id);
        d.matchedKeyword = s.k;
        out.push(d);
      }
    }
    return out;
  }

  /* ---------- live: EU policies via CELLAR SPARQL ---------- */

  function sparqlQuery(keywords, flt) {
    flt = normFilters(flt);
    // Substring match, so feed it every spelling variant of each keyword.
    const filters = expandAll(keywords)
      .map(v => 'CONTAINS(LCASE(STR(?title)), "' + v.replace(/["\\]/g, '') + '")')
      .join(' || ');
    return `
PREFIX cdm: <http://publications.europa.eu/ontology/cdm#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT DISTINCT ?work ?title ?date ?type ?celex WHERE {
  ?work cdm:work_date_document ?date .
  ?work cdm:work_has_resource-type ?type .
  FILTER(?type IN (
    <http://publications.europa.eu/resource/authority/resource-type/REG>,
    <http://publications.europa.eu/resource/authority/resource-type/DIR>,
    <http://publications.europa.eu/resource/authority/resource-type/DEC>,
    <http://publications.europa.eu/resource/authority/resource-type/COM>))
  OPTIONAL { ?work cdm:resource_legal_id_celex ?celex . }
  ?exp cdm:expression_belongs_to_work ?work .
  ?exp cdm:expression_uses_language <http://publications.europa.eu/resource/authority/language/ENG> .
  ?exp cdm:expression_title ?title .
  FILTER(${filters})
  FILTER(?date >= "${flt.from}-01-01"^^xsd:date)
  FILTER(?date <= "${flt.to}-12-31"^^xsd:date)
} ORDER BY DESC(?date) LIMIT 75`;
  }

  async function livePolicies(keywords, flt) {
    const url = CELLAR_URL + '?query=' + encodeURIComponent(sparqlQuery(keywords, flt)) +
                '&format=' + encodeURIComponent('application/sparql-results+json');
    const resp = await timeoutFetch(url, { headers: { Accept: 'application/sparql-results+json' } });
    if (!resp.ok) throw new Error('CELLAR HTTP ' + resp.status);
    const json = await resp.json();
    const rows = (json.results && json.results.bindings) || [];
    const seen = new Set();
    const out = [];
    for (const b of rows) {
      const d = normalizePolicyBinding(b, 'live');
      if (!seen.has(d.id)) { seen.add(d.id); out.push(d); }
    }
    return out;
  }

  /* ---------- cache tier ---------- */

  async function loadJson(path) {
    const resp = await timeoutFetch(path, { cache: 'no-cache' });
    if (!resp.ok) throw new Error(path + ' HTTP ' + resp.status);
    return resp.json();
  }

  function matchesKeywords(doc, keywords) {
    const hay = (doc.title + ' ' + doc.summary).toLowerCase();
    return expandAll(keywords).some(v => hay.indexOf(v) !== -1);
  }

  async function cachedDocs(kind, keywords, flt) {
    // Snapshot written by the GitHub Action first, bundled demo sample last.
    const paths = kind === 'grant'
      ? ['data/grants.json', 'data/sample_grants.json']
      : ['data/policies.json', 'data/sample_policies.json'];
    for (const p of paths) {
      try {
        const json = await loadJson(p);
        const isSample = p.indexOf('sample_') !== -1;
        const items = rankDocs((json.items || [])
          .map(d => Object.assign({}, d, { source: isSample ? 'sample' : 'cache' }))
          .filter(d => matchesKeywords(d, keywords) && inWindow(d, flt)), keywords);
        return { items, snapshot: p, isSample, generated: json.generated || null };
      } catch (e) { /* try next path */ }
    }
    return { items: [], snapshot: null, isSample: false, generated: null };
  }

  /* ---------- public API: live with cache fallback ---------- */

  async function search(kind, keywords, filters) {
    const flt = normFilters(filters);
    const liveFn = kind === 'grant' ? liveGrants : livePolicies;
    const window_ = flt.from + '–' + flt.to;
    try {
      const items = rankDocs(await liveFn(keywords, flt), keywords);
      if (items.length > 0) {
        return { items, tier: 'live', detail: 'live API, ' + window_ };
      }
      // Live worked but returned nothing — offer cached matches as a hint.
      const c = await cachedDocs(kind, keywords, flt);
      return c.items.length
        ? { items: c.items, tier: c.isSample ? 'sample' : 'cache',
            detail: 'live returned 0 for ' + window_ + ', showing ' +
                    (c.isSample ? 'bundled demo data' : 'snapshot') + ' (' + c.snapshot + ')' }
        : { items: [], tier: 'live', detail: 'live API, no matches in ' + window_ };
    } catch (err) {
      const c = await cachedDocs(kind, keywords, flt);
      return {
        items: c.items,
        tier: c.snapshot ? (c.isSample ? 'sample' : 'cache') : 'err',
        detail: c.snapshot
          ? 'live unreachable (' + err.message + ') — ' +
            (c.isSample ? 'bundled DEMO data, not real EU records' : 'snapshot ' + c.snapshot) +
            (c.generated ? ', ' + String(c.generated).slice(0, 10) : '') + ', ' + window_
          : 'live unreachable and no cached data (' + err.message + ')'
      };
    }
  }

  window.FinderAPI = {
    search,
    loadJson,
    normFilters,
    expandKeyword,
    _internal: { extractBudgetEUR, normalizeGrant, normalizePolicyBinding, sparqlQuery,
                 matchesKeywords, inWindow, isCallTopic, budgetYearTotals,
                 expandAll, scoreDoc, rankDocs }
  };
})();
