/* Record what the finder says about a frozen corpus.
 *
 *   node tests/browser/record.js --corpus path/to/corpus --out run.json \
 *        [--queries soil,mining] [--from 1990] [--to 2009] [--label A1]
 *
 * Not a test. The browser suite checks that the app behaves; this drives the
 * same app over a frozen corpus and writes down its answers, so the answers
 * exist before anyone looks at what happened next. That ordering is the whole
 * basis of a back-test, and it only means something if the output is recorded
 * and fixed rather than regenerated later from a corpus that has since moved.
 *
 * Queries come from `gif codebook-queries` when not given explicitly, so the
 * terms are chosen by rule rather than by whoever ran this.
 *
 * The run is hermetic: outbound requests are blocked, so the app falls back to
 * the snapshot tier and reads exactly the frozen files — never the live EU
 * endpoints, which would silently answer with today's data.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const { startServer } = require('./server');

const ROOT = path.resolve(__dirname, '..', '..');
const DOCS = path.join(ROOT, 'docs');

function arg(name, fallback = null) {
  const i = process.argv.indexOf('--' + name);
  return i === -1 ? fallback : process.argv[i + 1];
}

function chromiumPath() {
  if (process.env.FINDER_TEST_CHROMIUM) return process.env.FINDER_TEST_CHROMIUM;
  const preinstalled = '/opt/pw-browsers/chromium';
  return fs.existsSync(preinstalled) ? preinstalled : null;
}

/** Topic chips for one scope, with the scope's own count. */
async function readScope(page, scope) {
  const button = page.locator(`#topic-scope .scopebtn[data-scope="${scope}"]`);
  if (!await button.count()) return null;
  const label = (await button.innerText()).replace(/\s+/g, ' ').trim();
  await button.click();
  // The chip carries the term in data-t and its frequencies in <small>. Taking
  // innerText instead gives "soil3p · 4g", and the ranking is the thing being
  // recorded — it has to come out as data, not as a label to re-parse later.
  const topics = await page.$$eval('#topic-chips .tchip', chips => chips.map((c, i) => {
    const counts = /(\d+)p\s*·\s*(\d+)g/.exec(c.querySelector('small')?.textContent || '');
    return {
      rank: i + 1,
      term: c.dataset.t,
      dfPolicy: counts ? Number(counts[1]) : null,
      dfGrant: counts ? Number(counts[2]) : null,
    };
  }));
  return { scope, label, topics };
}

/** The codebook panel: what is addressed on both sides, and what is a gap. */
async function readCodebook(page) {
  const panel = page.locator('.codebook');
  if (!await panel.count()) return null;
  const clean = rows => rows.map(t => t.trim()).filter(Boolean);
  return {
    summary: (await panel.locator('> summary').innerText()).replace(/\s+/g, ' ').trim(),
    both: clean(await page.locator('.cbtable tr.cb-both td:first-child').allInnerTexts()),
    gaps: clean(await page.locator('.cbtable tr.cb-gap td:first-child').allInnerTexts()),
  };
}

async function recordQuery(page, baseUrl, query, from, to) {
  await page.goto(baseUrl + '/finder/index.html');
  await page.evaluate(() => localStorage.clear());
  await page.goto(baseUrl + '/finder/index.html');
  await page.waitForFunction(
    () => document.querySelector('#kw-expansion') !== null &&
          !document.getElementById('kw-synonyms').disabled,
    null, { timeout: 15000 });

  await page.fill('#kw-input', query);
  await page.press('#kw-input', 'Enter');
  await page.fill('#win-from', String(from));
  await page.fill('#win-to', String(to));
  await page.locator('#win-to').dispatchEvent('change');

  await page.click('#go-search');
  await page.waitForFunction(
    () => document.querySelectorAll('#src-status .srcpill').length >= 3,
    null, { timeout: 60000 });

  const counts = {
    policies: await page.locator('#list-policies .doc').count(),
    grants: await page.locator('#list-grants .doc').count(),
  };
  const tiers = (await page.locator('#src-status .srcpill').allInnerTexts())
    .map(t => t.replace(/\s+/g, ' ').trim());

  const record = { query, window: { from, to }, counts, sources: tiers };
  if (counts.policies + counts.grants === 0) {
    record.note = 'no documents matched; nothing further to record';
    return record;
  }

  await page.click('#go-topics');
  // Wait for the stage, not for a chart. A query can match grants and no
  // policies — single-source results are a feature, not an edge case — and
  // then #chart-policies renders an empty state with no <svg> in it, so
  // waiting on the chart hangs for exactly the corpora this is built for.
  await page.waitForSelector('#topic-scope .scopebtn', { timeout: 30000 });

  // Every scope, not just the active one: H3 compares bridge topics against
  // single-corpus ones, so both have to be on the record before outcomes are
  // seen. Reading them afterwards would let the comparison be chosen.
  record.scopes = [];
  for (const scope of ['bridge', 'policy', 'grant']) {
    const read = await readScope(page, scope);
    if (read) record.scopes.push(read);
  }
  record.codebook = await readCodebook(page);

  // A scenario over the top topics, so the metrics the tool would show are
  // recorded too — not to validate them (the protocol is explicit that they
  // are not under test) but so the paper can report what the tool said.
  const chips = page.locator('#topic-chips .tchip');
  const take = Math.min(3, await chips.count());
  for (let i = 0; i < take; i++) await chips.nth(i).click();
  record.selectedTopics = take;

  if (take > 0) {
    await page.click('#go-scenarios');
    await page.waitForSelector('.bundle-doc', { timeout: 30000 });
    await page.fill('#scenario-name', `recorded: ${query}`);
    await page.click('#save-scenario');
    await page.waitForSelector('.scenario-card', { timeout: 30000 });
    await page.click('#go-metrics');
    await page.waitForSelector('.metrics-table tbody tr', { timeout: 30000 });
    record.metrics = await page.$$eval('.metrics-table tbody tr', rows => rows.map(r =>
      [...r.querySelectorAll('td')].map(td => td.innerText.replace(/\s+/g, ' ').trim())));
    const rec = page.locator('#recommendations');
    if (await rec.count()) {
      record.recommendation = (await rec.innerText()).replace(/\s+/g, ' ').trim();
    }
  }
  return record;
}

async function main() {
  const corpus = arg('corpus');
  const out = arg('out');
  if (!corpus || !out) {
    console.error('usage: record.js --corpus DIR --out FILE [--queries a,b] '
                  + '[--from YYYY] [--to YYYY] [--label NAME]');
    process.exit(2);
  }
  const corpusDir = path.resolve(corpus);
  const from = parseInt(arg('from', '1990'), 10);
  const to = parseInt(arg('to', String(new Date().getFullYear())), 10);
  const label = arg('label', path.basename(corpusDir));

  let queries = (arg('queries') || '').split(',').map(s => s.trim()).filter(Boolean);
  if (!queries.length) {
    // Prefer a selection file written by `gif codebook-queries` beside the
    // corpus, so the terms are the rule's output rather than this script's.
    const selectionPath = path.join(corpusDir, 'queries.json');
    if (!fs.existsSync(selectionPath)) {
      console.error(`no --queries given and no ${selectionPath};`
                    + ' run `gif codebook-queries --corpus … --out …/queries.json` first');
      process.exit(2);
    }
    queries = JSON.parse(fs.readFileSync(selectionPath, 'utf8')).queries || [];
  }
  if (!queries.length) {
    console.error('the selection produced no queries — nothing to record');
    process.exit(2);
  }

  // Point the app's snapshot paths at the frozen corpus — and leave nothing
  // unmapped. The app falls back to its bundled demo files when a snapshot is
  // missing, and reports the result as a "snapshot" rather than as demo data,
  // so a corpus lacking one source would be quietly topped up with invented
  // documents that then look real in the record. A missing source is mapped to
  // an empty file instead, which says what is true: that source has nothing.
  // The demo files are mapped empty too, so the fallback cannot fire at all.
  const stub = path.join(fs.mkdtempSync(path.join(require('os').tmpdir(), 'rec-')),
                         'empty.json');
  fs.writeFileSync(stub, JSON.stringify({ generated: null, items: [] }));

  const overrides = {};
  let present = 0;
  for (const name of ['policies.json', 'grants.json', 'projects.json']) {
    const file = path.join(corpusDir, name);
    const found = fs.existsSync(file);
    if (found) present += 1;
    overrides['/finder/data/' + name] = found ? file : stub;
  }
  for (const name of ['sample_policies.json', 'sample_grants.json']) {
    overrides['/finder/data/' + name] = stub;
  }
  if (!present) {
    console.error(`no corpus files found in ${corpusDir}`);
    process.exit(2);
  }

  const manifestPath = path.join(corpusDir, 'manifest.json');
  const manifest = fs.existsSync(manifestPath)
    ? JSON.parse(fs.readFileSync(manifestPath, 'utf8')) : null;

  const server = await startServer(DOCS, overrides);
  const exe = chromiumPath();
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});
  const context = await browser.newContext({ viewport: { width: 1280, height: 1400 } });
  await context.route('**/*', route =>
    route.request().url().startsWith(server.baseUrl) ? route.continue() : route.abort());
  const page = await context.newPage();

  const pageErrors = [];
  page.on('pageerror', e => pageErrors.push(e.message));

  const records = [];
  for (const query of queries) {
    process.stdout.write(`  recording "${query}" … `);
    const record = await recordQuery(page, server.baseUrl, query, from, to);
    // Belt and braces over the mapping above: if anything ever reaches the
    // demo files again, the run must fail rather than be written down.
    const tiers = (record.sources || []).join(' | ');
    if (/demo|sample/i.test(tiers)) {
      throw new Error(`demo data reached a recorded run for "${query}": ${tiers}`);
    }
    records.push(record);
    console.log(`${record.counts.policies} policies, ${record.counts.grants} grants`);
  }

  await context.close();
  await browser.close();
  await server.close();

  const payload = {
    label,
    recorded: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
    corpus: {
      dir: path.relative(ROOT, corpusDir),
      // Carry the corpus's identity into the recording: an output that cannot
      // be tied to the input it came from is not evidence of anything.
      manifest: manifest && {
        label: manifest.label, created: manifest.created,
        documents: manifest.documents, complete: manifest.complete,
        window: manifest.window, tool: manifest.tool,
        files: (manifest.files || []).map(f => ({
          name: f.name, items: f.items, sha256: f.sha256,
          content_sha256: f.content_sha256,
        })),
      },
    },
    window: { from, to },
    queries,
    runs: records,
    pageErrors,
  };
  fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
  fs.writeFileSync(path.resolve(out), JSON.stringify(payload, null, 1) + '\n');
  console.log(`\nwrote ${out} — ${records.length} query run(s)`);
  if (pageErrors.length) {
    console.error(`${pageErrors.length} page error(s): ${pageErrors.join(' | ')}`);
    process.exit(1);
  }
}

main().catch(err => {
  console.error('recorder failed:', err);
  process.exit(1);
});
