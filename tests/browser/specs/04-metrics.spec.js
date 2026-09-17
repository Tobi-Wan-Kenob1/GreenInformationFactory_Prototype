/* Stages 4-5: scenario building, and the metrics that have to stay honest —
 * funding, indicative abatement that scales with the portfolio, the capped
 * confidence rating, and the one-way sensitivity panel. */
'use strict';

/** "≈ 9.9 MtCO₂e (0.7–146) lifetime" → 9_900_000 tonnes. */
function parseAbatement(cell) {
  const m = /≈\s*([\d.,]+)\s*(kt|Mt)/.exec(cell);
  if (!m) return null;
  return parseFloat(m[1].replace(/,/g, '')) * (m[2] === 'Mt' ? 1e6 : 1e3);
}

module.exports = {
  name: 'metrics — scenarios, scaled abatement, confidence and sensitivity',

  async run({ page, check, finder }) {
    await finder.open();
    await finder.addKeywords(['soil', 'mining', 'circular economy']);
    await finder.search();
    await finder.analyse();
    await finder.selectTopics(3);

    await page.click('#go-scenarios');
    await page.waitForSelector('.bundle-doc');

    // Scenario A: everything the topics bundle.
    const boxes = page.locator('.bundle-doc');
    const total = await boxes.count();
    check.ok(total >= 4, 'the bundles should offer several documents to choose from');
    await finder.saveScenario('Full portfolio');

    // Scenario B: drop one funded grant. It has to be a grant — policies carry
    // no budget, so removing those would leave the funding, and therefore the
    // abatement, untouched. The same topic can appear in several bundles, so
    // every checkbox for that document is cleared.
    const dropId = await page.locator('.doc.grant .bundle-doc').first().getAttribute('data-id');
    check.ok(dropId, 'there should be a grant in the bundles to drop');
    const copies = page.locator(`.bundle-doc[data-id="${dropId}"]`);
    for (let i = 0; i < await copies.count(); i++) await copies.nth(i).uncheck();
    await finder.saveScenario('Without one grant');

    const rows = await finder.metrics();
    check.equal(rows.length, 2, 'both scenarios should be compared');

    const [full, half] = rows;   // "Full portfolio", "Without one grant"
    const COL = { name: 0, policies: 1, grants: 2, funding: 3, savings: 4, co2: 5, abatement: 6, confidence: 7 };

    // --- funding is a band, not a point ---------------------------------
    check.match(full[COL.funding], /\d[\d.,]*–[\d.,]+ M€/,
      'funding should be a 25-100 % band of the summed call budgets');

    // --- abatement depends on the portfolio -----------------------------
    // This is the whole reason it replaced the global sectoral figure, which
    // was identical for every scenario. Note it is deliberately NOT asserted
    // to fall monotonically with size: dropping documents also changes the
    // matched topic mix, and therefore the blended €/tCO₂e the funding is
    // divided by, so a smaller portfolio on cheaper topics can score higher.
    check.notMatch(full[COL.abatement], /Gt/,
      'the global GtCO₂e/yr figure must not be presented as a scenario metric');
    const abFull = parseAbatement(full[COL.abatement]);
    const abHalf = parseAbatement(half[COL.abatement]);
    check.ok(abFull !== null && abHalf !== null,
      `both scenarios should have an abatement estimate (got "${full[COL.abatement]}", "${half[COL.abatement]}")`);
    check.ok(abFull > 0 && abHalf > 0, 'a funded scenario should produce a positive estimate');
    check.ok(abFull !== abHalf,
      'two different portfolios must not produce the same figure — that was the flaw in the global sectoral number');
    check.match(full[COL.abatement], /lifetime/,
      'the figure is a lifetime total, not an annual rate, and should say so');

    // funding, unlike abatement, is a plain sum and must respect the subset
    const money = cell => parseFloat(/([\d.,]+)–/.exec(cell)[1].replace(/,/g, ''));
    check.ok(money(half[COL.funding]) <= money(full[COL.funding]),
      'a subset of the documents cannot carry more funding than the whole');

    // --- confidence stays capped ----------------------------------------
    for (const row of rows) {
      check.match(row[COL.confidence], /\/75/, 'confidence should be reported out of its cap');
      check.notMatch(row[COL.confidence], /\b100\b/, 'a perfect score must not be reachable');
      const score = parseInt(/(\d+)\/75/.exec(row[COL.confidence])[1], 10);
      check.ok(score <= 75, `confidence ${score} should never exceed the cap`);
    }

    // --- one-way sensitivity --------------------------------------------
    await page.locator('.sens > summary').click();
    const shares = await page.locator('.sensrow .sv').allInnerTexts();
    check.ok(shares.length > 0, 'the sensitivity panel should list contributing assumptions');
    const first = parseInt(shares[0], 10);
    check.ok(first > 0 && first <= 100, 'each contribution should be a percentage share');
    const swing = await page.locator('.sensblock .swing').first().innerText();
    check.match(swing, /funding \(×\d+\)/, 'the swing should be decomposed into funding');
    check.match(swing, /deployment factor \(×\d+\)/, 'and the deployment factor');
    check.match(swing, /€\/tCO₂e/, 'and the abatement cost that was blended');

    // --- recommendations name the composition ---------------------------
    const reco = await page.locator('.reco').innerText();
    check.match(reco, /Where to start/, 'a best scenario should be recommended');
    check.match(reco, /Exemplary first operational steps/,
      'the recommendation should include concrete operational steps');

    // --- assumptions are disclosed --------------------------------------
    const box = await page.locator('#assumptions-box').innerText();
    check.match(box, /Indicative abatement/, 'the abatement method should be documented');
    check.match(box, /deployment factor/i, 'including the deployment factor');
    check.match(box, /keyword screening/i, 'and the honesty caveat on the confidence rating');

    // --- a policy-only scenario makes no funding claim -------------------
    await finder.open();
    await finder.addKeywords(['soil']);
    await finder.search();
    const grantBoxes = page.locator('#list-grants input[type=checkbox]');
    const grantCount = await grantBoxes.count();
    check.ok(grantCount > 0, 'there should be grants to deselect');
    for (let i = 0; i < grantCount; i++) await grantBoxes.nth(i).uncheck();

    await finder.analyse();
    check.equal(await page.locator('#topic-scope .scopebtn.on').getAttribute('data-scope'), 'policy',
      'a policy-only selection should land on the policy scope, since no bridge topic can exist');
    await finder.selectTopics(2);
    await page.click('#go-scenarios');
    await page.waitForSelector('.bundle-doc');
    await finder.saveScenario('Policy-only baseline');

    const policyRows = await finder.metrics();
    const row = policyRows[0];
    check.match(row[COL.funding], /n\/a/, 'a policy-only scenario should report funding as n/a, not zero');
    check.match(row[COL.abatement], /n\/a/, 'and no abatement, since it carries no budget');
    const policyReco = await page.locator('.reco').innerText();
    check.match(policyReco, /Policy-only scenario/,
      'the recommendation should address a policy-only scenario on its own terms');
  },
};
