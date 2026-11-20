/* Stage 6: the topic lists must not be led by filler words.
 *
 * The 2026 back-test (paper/results on the validation-paper branch) found the
 * tool's own topic lists headed by "will", "develop", "part" and "aims" —
 * words in nearly every project abstract that say nothing about its subject.
 * This runs the tool's analytics on proposal-style text and checks they are
 * gone while the subject words survive. */
'use strict';

module.exports = {
  name: 'stopwords — proposal boilerplate does not become a topic',

  async run({ page, check, finder }) {
    await finder.open();
    const result = await page.evaluate(() => {
      const abstract = (subject) => ({
        kind: 'grant',
        title: `${subject} pilot`,
        summary: `The research will develop ${subject} methods. As part of the work the ` +
                 `project aims to provide results and an approach that may help farmers.`,
      });
      const docs = ['soil carbon', 'biochar', 'manure biogas', 'soil carbon', 'biochar']
        .map(abstract)
        .concat([{ kind: 'policy', title: 'Soil monitoring law', summary: 'soil carbon will be monitored' },
                 { kind: 'policy', title: 'Biochar fertiliser', summary: 'biochar may be used' }]);
      const a = window.FinderAnalytics.analyze(docs, []);
      return {
        grant: a.grantTopics.map(t => t.term),
        policy: a.policyTopics.map(t => t.term),
        bridge: a.bridge.map(t => t.term),
      };
    });
    const all = [...result.grant, ...result.policy, ...result.bridge];
    for (const filler of ['will', 'develop', 'part', 'aims', 'research', 'results', 'approach', 'may', 'provide']) {
      check.ok(!all.includes(filler), `"${filler}" is boilerplate and must not be offered as a topic`);
    }
    for (const subject of ['soil', 'biochar', 'farmers']) {
      check.ok(all.some(t => t.split(' ').includes(subject)),
        `the subject word "${subject}" must survive the stop list`);
    }
  },
};
