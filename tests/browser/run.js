/* Tiny test runner for the Policy & Grant Finder browser suite.
 *
 *   node tests/browser/run.js            # every spec
 *   node tests/browser/run.js synonyms   # only specs whose name matches
 *
 * No test framework on purpose: the repo's only JS is the finder itself, and a
 * runner small enough to read in one sitting is cheaper to keep working than a
 * framework nobody here maintains. Playwright drives a real Chromium because
 * the things worth testing (ranking, localStorage, SVG charts) only exist once
 * the page has run.
 */
'use strict';

const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const { startServer } = require('./server');

const ROOT = path.resolve(__dirname, '..', '..');
const DOCS = path.join(ROOT, 'docs');
const FIXTURES = path.join(__dirname, 'fixtures');
const SPEC_DIR = path.join(__dirname, 'specs');

/** Resolve a Chromium binary, preferring an explicit path over a managed one. */
function chromiumPath() {
  if (process.env.FINDER_TEST_CHROMIUM) return process.env.FINDER_TEST_CHROMIUM;
  // Pre-installed in some sandboxes, where Playwright's own copy is absent.
  const preinstalled = '/opt/pw-browsers/chromium';
  if (fs.existsSync(preinstalled)) return preinstalled;
  return null;                       // let Playwright find the browser it manages
}

class AssertionError extends Error {}

/** Assertions, kept deliberately few: a message that says what was expected. */
const check = {
  ok(cond, message) {
    if (!cond) throw new AssertionError(message);
  },
  equal(actual, expected, message) {
    if (actual !== expected) {
      throw new AssertionError(`${message}\n    expected: ${expected}\n    actual:   ${actual}`);
    }
  },
  match(text, re, message) {
    if (!re.test(text)) {
      throw new AssertionError(`${message}\n    expected to match ${re}\n    in: ${String(text).slice(0, 300)}`);
    }
  },
  notMatch(text, re, message) {
    if (re.test(text)) {
      throw new AssertionError(`${message}\n    expected NOT to match ${re}\n    in: ${String(text).slice(0, 300)}`);
    }
  },
};

async function main() {
  const filter = process.argv[2];
  const specs = fs.readdirSync(SPEC_DIR)
    .filter(f => f.endsWith('.spec.js'))
    .filter(f => !filter || f.includes(filter))
    .sort()
    .map(f => require(path.join(SPEC_DIR, f)));

  if (!specs.length) {
    console.error(filter ? `no specs match "${filter}"` : 'no specs found');
    process.exit(1);
  }

  const server = await startServer(DOCS, {
    '/finder/data/policies.json': path.join(FIXTURES, 'policies.json'),
    '/finder/data/grants.json': path.join(FIXTURES, 'grants.json'),
  });
  const exe = chromiumPath();
  const browser = await chromium.launch(exe ? { executablePath: exe } : {});

  let failed = 0;
  for (const spec of specs) {
    const started = Date.now();
    const context = await browser.newContext({ viewport: { width: 1280, height: 1400 } });

    // Hermetic: nothing leaves the machine. The finder tries its live tier
    // first (EUR-Lex and the Funding & Tenders API) and falls back to the
    // snapshot, so on a runner with real internet it would answer with live EU
    // data and no fixture assertion would hold. Blocking outbound requests
    // pins the suite to the fallback path — which is also the path real
    // browsers take for policies, since CELLAR sends no CORS headers.
    await context.route('**/*', route => {
      const url = route.request().url();
      if (url.startsWith(server.baseUrl)) return route.continue();
      return route.abort();
    });

    const page = await context.newPage();

    // A page error is a failure even if every assertion passes.
    const pageErrors = [];
    page.on('pageerror', e => pageErrors.push(e.message));
    page.on('console', m => {
      if (m.type() === 'error' && !/net::|Failed to load resource/.test(m.text())) {
        pageErrors.push(m.text());
      }
    });

    try {
      await spec.run({ page, baseUrl: server.baseUrl, check, finder: helpers(page, server.baseUrl) });
      if (pageErrors.length) throw new AssertionError('page errors: ' + pageErrors.join(' | '));
      console.log(`  PASS  ${spec.name}  (${Date.now() - started}ms)`);
    } catch (err) {
      failed += 1;
      const label = err instanceof AssertionError ? 'FAIL' : 'ERROR';
      console.log(`  ${label}  ${spec.name}  (${Date.now() - started}ms)`);
      console.log('        ' + String(err.message).split('\n').join('\n        '));
    } finally {
      await context.close();
    }
  }

  await browser.close();
  await server.close();

  console.log(failed ? `\n${failed} of ${specs.length} spec(s) failed` : `\nall ${specs.length} spec(s) passed`);
  process.exit(failed ? 1 : 0);
}

/** Page helpers shared by the specs — the finder's own vocabulary. */
function helpers(page, baseUrl) {
  const api = {
    /** Load the finder with a clean slate (scenarios live in localStorage). */
    async open() {
      await page.goto(baseUrl + '/finder/index.html');
      await page.evaluate(() => localStorage.clear());
      await page.goto(baseUrl + '/finder/index.html');
      // The thesaurus loads asynchronously; searching before it lands would
      // silently test the un-expanded path.
      await page.waitForFunction(
        () => document.querySelector('#kw-expansion') !== null &&
              !document.getElementById('kw-synonyms').disabled,
        null, { timeout: 15000 });
    },
    async addKeywords(keywords) {
      for (const k of keywords) {
        await page.fill('#kw-input', k);
        await page.press('#kw-input', 'Enter');
      }
    },
    async setWindow(from, to) {
      await page.fill('#win-from', String(from));
      await page.fill('#win-to', String(to));
      await page.locator('#win-to').dispatchEvent('change');
    },
    async search() {
      await page.click('#go-search');
      // Three pills: the window, plus one per source.
      await page.waitForFunction(
        () => document.querySelectorAll('#src-status .srcpill').length >= 3,
        null, { timeout: 30000 });
    },
    async counts() {
      return {
        policies: await page.locator('#list-policies .doc').count(),
        grants: await page.locator('#list-grants .doc').count(),
      };
    },
    async titles() {
      return (await page.locator('#list-policies .doc .t, #list-grants .doc .t').allInnerTexts())
        .map(t => t.trim());
    },
    /** Run keywords through the app's own matcher, without the UI. */
    matches(doc, keywords, useSynonyms) {
      return page.evaluate(([d, k, s]) =>
        window.FinderAPI._internal.matchesKeywords(d, k, s), [doc, keywords, useSynonyms]);
    },
    async analyse() {
      await page.click('#go-topics');
      await page.waitForSelector('#chart-policies svg', { timeout: 15000 });
    },
    async selectTopics(n) {
      const chips = page.locator('#topic-chips .tchip');
      const available = Math.min(n, await chips.count());
      for (let i = 0; i < available; i++) await chips.nth(i).click();
      return available;
    },
    async saveScenario(name) {
      await page.fill('#scenario-name', name);
      await page.click('#save-scenario');
      await page.waitForSelector('.scenario-card', { timeout: 10000 });
    },
    async metrics() {
      await page.click('#go-metrics');
      await page.waitForSelector('.metrics-table tbody tr', { timeout: 15000 });
      return page.$$eval('.metrics-table tbody tr', rows => rows.map(r =>
        [...r.querySelectorAll('td')].map(td => td.innerText.replace(/\s+/g, ' ').trim())));
    },
  };
  return api;
}

main().catch(err => {
  console.error('runner crashed:', err);
  process.exit(1);
});
