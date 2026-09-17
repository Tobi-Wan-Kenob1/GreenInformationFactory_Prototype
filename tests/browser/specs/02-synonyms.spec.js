/* The plain-language bridge: everyday wording has to reach documents written
 * in EU/academic register, visibly and reversibly. */
'use strict';

module.exports = {
  name: 'synonyms — plain language reaches bureaucratic wording',

  async run({ page, check, finder }) {
    /** Search one keyword with expansion on or off, return the hit count. */
    async function countFor(keyword, useSynonyms) {
      await finder.open();
      if (!useSynonyms) await page.uncheck('#kw-synonyms');
      await finder.addKeywords([keyword]);
      await finder.search();
      const { policies, grants } = await finder.counts();
      return { total: policies + grants, titles: (await finder.titles()).join(' | ') };
    }

    // --- the headline case: nobody searches for "organic fertiliser" -----
    const muckOn = await countFor('muck', true);
    const muckOff = await countFor('muck', false);
    check.equal(muckOff.total, 0, '"muck" appears nowhere in the corpus verbatim');
    check.ok(muckOn.total > 0, '"muck" should still reach the documents that mean it');
    check.match(muckOn.titles, /organic fertilisers from biogas digestate/i,
      '"muck" should reach the organic-fertiliser grant');
    check.match(muckOn.titles, /organic fertilisers and soil improvers/i,
      '"muck" should reach the organic-fertiliser regulation');

    // --- and the same in the other direction ----------------------------
    const warmingOn = await countFor('global warming', true);
    const warmingOff = await countFor('global warming', false);
    check.equal(warmingOff.total, 0, '"global warming" is not EU wording');
    check.match(warmingOn.titles, /climate neutrality/i,
      '"global warming" should reach the climate act via its EuroVoc subjects');

    const diggingOn = await countFor('digging', true);
    check.match(diggingOn.titles, /extractive|quarrying|mining/i,
      '"digging" should reach the mining documents');

    // --- expansion never reduces recall ---------------------------------
    for (const kw of ['soil', 'mining', 'circular economy']) {
      const on = await countFor(kw, true);
      const off = await countFor(kw, false);
      check.ok(on.total >= off.total,
        `expansion must not lose results for "${kw}" (on ${on.total} < off ${off.total})`);
    }

    // --- the user can see, and undo, what was added ---------------------
    await finder.open();
    await finder.addKeywords(['muck']);
    await page.waitForSelector('#kw-expansion .exrow');
    const shown = await page.locator('#kw-expansion').innerText();
    check.match(shown, /manure/, 'the expansion should be listed for the user');
    check.match(shown, /organic fertiliser/, 'including the jargon it will search for');

    await page.uncheck('#kw-synonyms');
    const off = await page.locator('#kw-expansion').innerText();
    check.notMatch(off, /manure/, 'switching expansion off should clear the expansion list');
    check.match(off, /spelling variants only/i, 'and say what is still being searched');

    // --- a keyword with no relatives says so rather than looking broken --
    await page.check('#kw-synonyms');
    await finder.addKeywords(['zzzqqq']);
    const unknown = await page.locator('#kw-expansion').innerText();
    check.match(unknown, /no related wording known/i,
      'an unknown keyword should be explained, not silently unexpanded');

    // --- precision: short thesaurus terms must not match inside words ----
    // "ground" and "earth" were once synonyms of soil, which pulled in
    // "groundwater" and "earth observation" — both common in this corpus and
    // nothing to do with soil. They were removed; this pins that decision.
    const earthObservation = {
      title: 'Land use monitoring with digital tools',
      summary: 'Digital monitoring of land use change using data spaces and earth observation.',
    };
    check.equal(await finder.matches(earthObservation, ['soil'], true), false,
      '"soil" must not reach "earth observation" through a synonym');

    const background = {
      title: 'Background information note on appeal procedures',
      summary: 'administrative procedure, unearthed archive material',
    };
    check.equal(await finder.matches(background, ['ground'], false), false,
      '"ground" must not match inside "Background"');
    check.equal(await finder.matches(background, ['earth'], false), false,
      '"earth" must not match inside "unearthed"');
    check.equal(await finder.matches({ title: 'Grounds for refusal', summary: '' }, ['ground'], false),
      true, '"ground" should still match the plural "Grounds" when searched directly');
    check.equal(await finder.matches({ title: 'Earthworks permit', summary: '' }, ['earth'], false),
      true, '"earth" should still match at a word start when searched directly');
  },
};
