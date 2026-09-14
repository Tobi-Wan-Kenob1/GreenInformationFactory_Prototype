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
  const MAX_PAGE_SIZE = 50;
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

  // Try hard to find a numeric EUR budget in SEDIA's assorted metadata fields.
  function extractBudgetEUR(meta) {
    if (!meta) return null;
    const direct = first(meta.budget) || first(meta.cftEstimatedTotalProcedureValue);
    const cands = [];
    if (direct != null) cands.push(direct);
    const bo = first(meta.budgetOverview) || first(meta.budgetOverviewJSONItem);
    if (typeof bo === 'string' && bo.indexOf('{') !== -1) {
      try {
        const parsed = JSON.parse(bo);
        const items = parsed.budgetTopicActionMap || parsed;
        JSON.stringify(items).replace(/"(?:budget|totalBudget|plannedOpeningBudget)"\s*:\s*"?([\d.,\s]+)"?/g,
          (_, n) => { cands.push(n); return _; });
      } catch (e) { /* not JSON after all */ }
    }
    for (const c of cands) {
      const n = parseFloat(String(c).replace(/[^\d.]/g, ''));
      if (isFinite(n) && n > 1000) return Math.round(n);
    }
    return null;
  }

  function normalizeGrant(r, source) {
    const meta = r.metadata || {};
    const id = first(meta.identifier) || r.reference || r.url || Math.random().toString(36).slice(2);
    return {
      id: 'g:' + id,
      kind: 'grant',
      title: stripTags(first(meta.title) || r.title || id),
      summary: stripTags(first(meta.description) || first(meta.descriptionByte) || r.summary || r.content || ''),
      date: String(first(meta.startDate) || first(meta.publicationDateLong) || '').slice(0, 10) || null,
      url: 'https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/opportunities/topic-details/' +
           encodeURIComponent(String(id).toLowerCase()),
      budgetEUR: extractBudgetEUR(meta),
      doctype: first(meta.type) === '2' ? 'Tender' : 'Call topic',
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

  async function liveGrants(keywords, flt) {
    const text = keywords.map(k => '"' + k + '"').join(' OR ');
    const statuses = [STATUS.forthcoming, STATUS.open];
    if (flt.includeClosed) statuses.push(STATUS.closed);

    // type 1 = grant call topics. The body must be form-urlencoded: a
    // multipart FormData body makes the API answer 500.
    const body = new URLSearchParams({
      query: JSON.stringify({
        bool: { must: [{ terms: { type: ['1'] } }, { terms: { status: statuses } }] }
      }),
      languages: JSON.stringify(['en']),
      sort: JSON.stringify({ field: 'sortStatus', order: 'DESC' })
    });
    const url = SEDIA_URL + '?apiKey=SEDIA&pageNumber=1&pageSize=' + MAX_PAGE_SIZE +
                '&text=' + encodeURIComponent(text);
    const resp = await timeoutFetch(url, { method: 'POST', body: body });
    if (!resp.ok) throw new Error('SEDIA HTTP ' + resp.status);
    const json = await resp.json();
    return (json.results || [])
      .map(r => normalizeGrant(r, 'live'))
      .filter(d => inWindow(d, flt));
  }

  /* ---------- live: EU policies via CELLAR SPARQL ---------- */

  function sparqlQuery(keywords, flt) {
    flt = normFilters(flt);
    const filters = keywords
      .map(k => 'CONTAINS(LCASE(STR(?title)), "' + k.toLowerCase().replace(/["\\]/g, '') + '")')
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
    return keywords.some(k => hay.indexOf(k.toLowerCase()) !== -1);
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
        const items = (json.items || [])
          .map(d => Object.assign({}, d, { source: isSample ? 'sample' : 'cache' }))
          .filter(d => matchesKeywords(d, keywords) && inWindow(d, flt));
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
      const items = await liveFn(keywords, flt);
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
    _internal: { extractBudgetEUR, normalizeGrant, normalizePolicyBinding, sparqlQuery,
                 matchesKeywords, inWindow }
  };
})();
