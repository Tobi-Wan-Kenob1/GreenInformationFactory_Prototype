/* Stage 3: topic analytics, the scope selector that allows single-source
 * scenarios, and the WP1/D1.2 codebook coverage panel. */
'use strict';

module.exports = {
  name: 'topics — analytics, scope selector and WP1 codebook coverage',

  async run({ page, check, finder }) {
    await finder.open();
    await finder.addKeywords(['soil', 'mining', 'circular economy']);
    await finder.search();
    await finder.analyse();

    // --- analytics run on EuroVoc subjects, not just titles -------------
    const policyTerms = await page.locator('#chart-policies text[text-anchor="end"]').allInnerTexts();
    check.ok(policyTerms.length > 0, 'the policy corpus should produce topic bars');
    const joined = policyTerms.join(' ').toLowerCase();
    check.notMatch(joined, /\bdocument\b|\beea\b|\brelevance\b/,
      'EUR-Lex title boilerplate should be filtered out of the topics');

    // --- every scope is offered, with counts ----------------------------
    const scopes = await page.locator('#topic-scope .scopebtn').allInnerTexts();
    check.equal(scopes.length, 3, 'bridge, policy and grant scopes should all be offered');
    const active = await page.locator('#topic-scope .scopebtn.on').getAttribute('data-scope');
    check.ok(['bridge', 'policy', 'grant'].includes(active), 'a scope should be selected');
    const chips = await page.locator('#topic-chips .tchip').count();
    check.ok(chips > 0, 'the selected scope should offer topics');

    // switching scope re-renders the chips
    await page.locator('#topic-scope .scopebtn[data-scope="grant"]').click();
    check.equal(await page.locator('#topic-scope .scopebtn.on').getAttribute('data-scope'), 'grant',
      'clicking a scope should select it');
    check.ok(await page.locator('#topic-chips .tchip').count() > 0,
      'the grant corpus alone should still offer topics — that is what makes a grant-only scenario possible');

    // --- codebook coverage ----------------------------------------------
    const panel = page.locator('.codebook');
    check.equal(await panel.count(), 1, 'the WP1 codebook panel should be rendered');
    const summary = await page.locator('.codebook > summary').innerText();
    check.match(summary, /\d+ of \d+ codes on both sides/, 'coverage should be summarised');
    check.match(summary, /\d+ not addressed/, 'blind spots should be counted');

    const dimensions = await page.locator('.cbblock h4').allInnerTexts();
    check.ok(dimensions.length >= 4,
      'barriers, drivers, stakeholders and the sector dimensions should each get a block');

    // "water" is in both fixture corpora → addressed on both sides.
    const both = (await page.locator('.cbtable tr.cb-both td:first-child').allInnerTexts())
      .map(t => t.trim());
    check.ok(both.includes('water'),
      '"water" appears in both fixture corpora and should read as addressed by policy and funding');

    // "biochar" appears in neither → a blind spot, which is the panel's point.
    const gaps = (await page.locator('.cbtable tr.cb-gap td:first-child').allInnerTexts())
      .map(t => t.trim());
    check.ok(gaps.includes('biochar'),
      '"biochar" appears in neither corpus and should read as a blind spot');
    check.ok(!gaps.includes('water'), 'a code found in the corpus must not be listed as a gap');

    // --- the panel states its provenance and method ---------------------
    const body = await panel.innerText();
    check.match(body, /zenodo\.20744025/, 'the codebook should cite its source record');
    check.match(body, /verify/i, 'and say that hits are verifiable in the source document');
  },
};
