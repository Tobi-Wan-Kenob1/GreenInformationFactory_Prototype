/* Stage 1-2: keyword search, source labelling, ranking, and the time window
 * that makes historical benchmarking possible. */
'use strict';

module.exports = {
  name: 'search — results, labelling, ranking and the time window',

  async run({ page, check, finder }) {
    await finder.open();
    await finder.addKeywords(['soil', 'mining']);
    await finder.search();

    // --- the corpus the fixtures define ---------------------------------
    // The default window starts in 2015, so the two pre-2015 acts are out.
    const recent = await finder.counts();
    check.equal(recent.policies, 3,
      'the default 2015+ window should match soil 2024, fertiliser 2019 and carbon farming 2018');
    check.equal(recent.grants, 2,
      'the default 2015+ window should match the soil 2024 and mining 2023 grants');

    await page.click('.stepper .step[data-stage="1"]');
    await finder.setWindow(2004, 2026);
    await finder.search();
    const all = await finder.counts();
    check.equal(all.policies, 5,
      'widening to 2004 should add the 2012 mining decision and the 2005 quarrying directive');
    check.equal(all.grants, 3, 'and the 2011 supply-chain grant');

    const titles = (await finder.titles()).join(' | ');
    check.match(titles, /soil monitoring and resilience/i, 'the soil directive should be found');
    check.notMatch(titles, /climate neutrality/i,
      'the climate act matches neither keyword and must not appear');
    check.notMatch(titles, /Background information note/i,
      'the background note matches neither keyword and must not appear');

    // --- sources are labelled honestly ----------------------------------
    const pills = (await page.locator('#src-status .srcpill').allInnerTexts()).join(' | ');
    check.match(pills, /window 2004–2026/, 'the active window should be shown');
    check.match(pills, /EUR-Lex: snapshot/,
      'with the live tier unreachable the app must fall back to the snapshot and say so');
    check.notMatch(pills, /DEMO SAMPLE/,
      'real snapshot data must not be labelled as bundled demo data');
    const detail = await page.locator('#src-status .srcpill').nth(1).getAttribute('title');
    check.match(detail, /live unreachable|snapshot/,
      'the pill tooltip should explain where the results came from');

    // --- ranking: a title hit outranks a summary-only hit ----------------
    const policyTitles = await page.locator('#list-policies .doc .t').allInnerTexts();
    const titleHit = policyTitles.findIndex(t => /soil monitoring and resilience/i.test(t));
    const summaryHit = policyTitles.findIndex(t => /carbon farming and soil carbon/i.test(t));
    check.ok(titleHit !== -1 && summaryHit !== -1, 'both soil policies should be listed');
    check.ok(titleHit < summaryHit,
      'a document with the keyword in its title should rank above one matching further down');

    // --- grant cards carry the decisive facts ---------------------------
    const grantMeta = (await page.locator('#list-grants .doc .m').allInnerTexts()).join(' | ');
    check.match(grantMeta, /deadline 2026-02-18/, 'an open deadline should be shown');
    check.match(grantMeta, /deadline 2023-09-12/, 'a passed deadline should still be shown');
    const passed = await page.locator('#list-grants .doc .tag.past').count();
    check.ok(passed >= 1, 'a deadline in the past should be marked as such');
    check.match(grantMeta, /12 M€/, 'a known budget should be shown on the card');

    // --- the time window narrows to a past setting ----------------------
    await page.click('.stepper .step[data-stage="1"]');
    await finder.setWindow(2004, 2013);
    await finder.search();
    const historical = await finder.counts();
    check.equal(historical.policies, 2,
      '2004-2013 should leave the 2012 mining decision and the 2005 quarrying directive');
    check.equal(historical.grants, 1, '2004-2013 should leave the 2011 supply-chain grant');
    const oldTitles = (await finder.titles()).join(' | ');
    check.match(oldTitles, /quarrying operations/i, 'the 2005 act should survive the window');
    check.notMatch(oldTitles, /2024\/9002/, 'a 2024 act must not survive a 2004-2013 window');

    // --- a window with no data explains itself --------------------------
    await page.click('.stepper .step[data-stage="1"]');
    await finder.setWindow(1990, 1995);
    await finder.search();
    const empty = await finder.counts();
    check.equal(empty.policies + empty.grants, 0, '1990-1995 has no fixture documents');
    const message = await page.locator('#list-grants .empty').first().innerText();
    check.match(message, /1990–1995/,
      'an empty result should name the window rather than implying no such documents exist');
  },
};
