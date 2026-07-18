/* Policy & Grant Finder — client-side text analytics.
 * Document-frequency analysis over the selected documents: which terms appear
 * in how many policy vs. grant documents, and which "bridge topics" appear in
 * both corpora. All computation happens in the browser.
 */
(function () {
  'use strict';

  // Standard English stopwords + EU document boilerplate that would otherwise
  // dominate every chart without telling the user anything.
  const STOP = new Set(('a,about,above,after,again,against,all,am,an,and,any,are,as,at,be,because,' +
    'been,before,being,below,between,both,but,by,can,could,did,do,does,doing,down,during,each,few,' +
    'for,from,further,had,has,have,having,he,her,here,hers,him,his,how,i,if,in,into,is,it,its,' +
    'itself,let,more,most,my,no,nor,not,of,off,on,once,only,or,other,our,ours,out,over,own,same,' +
    'she,should,so,some,such,than,that,the,their,theirs,them,then,there,these,they,this,those,' +
    'through,to,too,under,until,up,very,was,we,were,what,when,where,which,while,who,whom,why,with,' +
    'would,you,your,yours,' +
    // EU / funding boilerplate
    'european,europe,eu,union,commission,council,parliament,regulation,directive,decision,' +
    'communication,proposal,amending,final,com,annex,article,shall,member,states,state,horizon,' +
    'call,topic,topics,action,actions,activities,project,projects,proposal,proposals,programme,' +
    'work,new,including,well,also,related,relevant,based,use,used,using,support,supporting,' +
    'ensure,ensuring,measures,framework,strategy,plan,sample').split(','));

  function tokenize(text) {
    const words = String(text || '').toLowerCase()
      .replace(/[^a-zà-ÿ0-9\s-]/g, ' ')
      .split(/[\s]+/)
      .map(w => w.replace(/^-+|-+$/g, ''))
      .filter(w => w.length >= 3 && !/^\d+$/.test(w));
    const kept = [];
    const terms = [];
    for (const w of words) {
      if (STOP.has(w)) { kept.push(null); continue; }
      kept.push(w);
      terms.push(w);
    }
    // bigrams over adjacent non-stopword tokens ("circular economy", "carbon capture")
    for (let i = 0; i < kept.length - 1; i++) {
      if (kept[i] && kept[i + 1]) terms.push(kept[i] + ' ' + kept[i + 1]);
    }
    return terms;
  }

  // Document frequency per unique term for one corpus of docs.
  function docFreq(docs) {
    const df = new Map();
    for (const d of docs) {
      const uniq = new Set(tokenize(d.title + ' ' + d.summary));
      for (const t of uniq) df.set(t, (df.get(t) || 0) + 1);
    }
    return df;
  }

  // Prefer bigrams over the single words they contain when equally frequent
  // (keep "circular economy", drop "circular" if it only shows up there).
  function pruneSubterms(items) {
    const bigrams = items.filter(x => x.term.includes(' '));
    return items.filter(x => {
      if (x.term.includes(' ')) return true;
      return !bigrams.some(b => b.value >= x.value && b.term.split(' ').includes(x.term));
    });
  }

  function topTerms(df, n, minDf) {
    const items = [...df.entries()]
      .filter(([, v]) => v >= minDf)
      .map(([term, value]) => ({ term, value }))
      .sort((a, b) => b.value - a.value || a.term.localeCompare(b.term));
    return pruneSubterms(items).slice(0, n);
  }

  /* analyze(docs, keywords) →
   *   { policyTerms:[{label,value}], grantTerms:[...], bridge:[{term,dfPolicy,dfGrant,score}] } */
  function analyze(docs, keywords) {
    const pols = docs.filter(d => d.kind === 'policy');
    const gras = docs.filter(d => d.kind === 'grant');
    const dfP = docFreq(pols);
    const dfG = docFreq(gras);
    const minDf = docs.length > 12 ? 2 : 1;

    const policyTerms = topTerms(dfP, 15, minDf).map(x => ({ label: x.term, value: x.value }));
    const grantTerms = topTerms(dfG, 15, minDf).map(x => ({ label: x.term, value: x.value }));

    const bridge = [];
    for (const [term, vP] of dfP.entries()) {
      const vG = dfG.get(term);
      if (!vG || vP < minDf || vG < minDf) continue;
      const pctP = pols.length ? vP / pols.length : 0;
      const pctG = gras.length ? vG / gras.length : 0;
      bridge.push({ term, dfPolicy: vP, dfGrant: vG, score: Math.min(pctP, pctG) });
    }
    bridge.sort((a, b) => b.score - a.score || (b.dfPolicy + b.dfGrant) - (a.dfPolicy + a.dfGrant));
    const prunedBridge = pruneSubterms(bridge.map(b => Object.assign({ value: b.score }, b)))
      .slice(0, 14);
    // user keywords always selectable if they matched anything
    for (const k of keywords || []) {
      if (!prunedBridge.some(b => b.term === k) && dfP.get(k) && dfG.get(k)) {
        prunedBridge.push({ term: k, dfPolicy: dfP.get(k), dfGrant: dfG.get(k), score: 0 });
      }
    }
    return { policyTerms, grantTerms, bridge: prunedBridge };
  }

  /* Horizontal bar chart as inline SVG. items: [{label, value}]. */
  function barChartSVG(items, color, totalDocs) {
    if (!items || !items.length) return '<div class="empty">Nothing to chart.</div>';
    const W = 460, rowH = 26, labelW = 180, pad = 6;
    const H = items.length * rowH + pad * 2;
    const maxV = Math.max(...items.map(i => i.value)) || 1;
    const rows = items.map((it, i) => {
      const y = pad + i * rowH;
      const w = Math.max(2, (W - labelW - 60) * (it.value / maxV));
      const label = it.label.length > 26 ? it.label.slice(0, 25) + '…' : it.label;
      const val = Number.isInteger(it.value) ? it.value : it.value.toFixed(1);
      const pct = totalDocs ? ' (' + Math.round(100 * it.value / totalDocs) + '%)' : '';
      return `<g>
        <title>${it.label}: ${val}${pct}</title>
        <text x="${labelW - 8}" y="${y + rowH / 2 + 4}" text-anchor="end" font-size="12" fill="#5c6662">${label}</text>
        <rect x="${labelW}" y="${y + 5}" width="${w.toFixed(1)}" height="${rowH - 10}" rx="4" fill="${color}" opacity="0.85"></rect>
        <text x="${labelW + w + 6}" y="${y + rowH / 2 + 4}" font-size="11.5" fill="#8a938f">${val}${pct}</text>
      </g>`;
    }).join('');
    return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Bar chart">${rows}</svg>`;
  }

  window.FinderAnalytics = { tokenize, analyze, barChartSVG, _internal: { docFreq, topTerms, STOP } };
})();
