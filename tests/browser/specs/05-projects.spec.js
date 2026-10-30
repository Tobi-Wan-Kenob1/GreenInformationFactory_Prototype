/* CORDIS funded projects: a third source, merged into the grant results.
 *
 * The point of the source is reach. The Funding & Tenders API indexes Horizon
 * 2020 onward, so before this the tool could not see a 2004 award at all —
 * which is also what made it useless for comparing a past setting against what
 * followed. These assertions are about that reach, and about the records being
 * labelled as the past awards they are rather than passed off as open calls. */
'use strict';

module.exports = {
  name: 'projects — CORDIS awards extend the window below 2014',

  async run({ page, check, finder }) {
    await finder.open();
    await finder.addKeywords(['soil', 'mining']);

    // --- reach: a window no call topic can cover -------------------------
    await finder.setWindow(2004, 2009);
    await finder.search();
    const old = await finder.titles();
    check.match(old.join(' | '), /Rehabilitation of abandoned mining sites/i,
      'a 2004 FP6 award should be findable, which the call-topic API cannot do');
    check.match(old.join(' | '), /Soil carbon accounting for arable land/i,
      'and a 2009 FP7 award');
    check.notMatch(old.join(' | '), /Soil health monitoring at scale/i,
      'a 2023 project must not appear in a 2004-2009 window');

    // --- labelled as awards, not invitations ----------------------------
    const meta = (await page.locator('#list-grants .doc .m').allInnerTexts()).join(' | ');
    check.match(meta, /Funded project/,
      'a CORDIS record must say it is a funded project');
    check.notMatch(meta, /deadline/,
      'an award already made has no deadline to apply to');
    check.match(meta, /1\.5 M€|1\.4 M€/,
      "the EC contribution should be shown like any other record's budget");

    // --- the source is named, so the reader can tell the mix apart -------
    const pills = (await page.locator('#src-status .srcpill').allInnerTexts()).join(' | ');
    const tips = await Promise.all(
      (await page.locator('#src-status .srcpill').all()).map(p => p.getAttribute('title')));
    check.match(pills + ' | ' + tips.join(' | '), /CORDIS/,
      'the status line should disclose that some results are CORDIS projects');

    // --- they flow through the rest of the pipeline ----------------------
    // A source the analytics cannot see would be decoration. In this window
    // the only grant-side records that exist are CORDIS awards, so reaching
    // metrics at all proves they are carried the whole way.
    await finder.analyse();
    const chips = await page.locator('#topic-chips .tchip').count();
    check.ok(chips > 0, 'topics should be extracted from project objectives');
    await finder.selectTopics(3);

    await page.click('#go-scenarios');
    await page.waitForSelector('.bundle-doc');
    await finder.saveScenario('FP6/FP7 awards');

    const rows = await finder.metrics();
    check.ok(rows.length > 0, 'a scenario built on awards should produce metrics');
    check.match(rows[0].join(' '), /M€|k€|€/,
      'and the EC contributions should reach the funding column');
  },
};
