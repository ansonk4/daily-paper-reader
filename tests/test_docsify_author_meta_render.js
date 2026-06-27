const assert = require('node:assert/strict');

global.window = {
  marked: null,
  location: { origin: 'https://example.test' },
};
global.document = {
  documentElement: { clientWidth: 1280 },
  body: {
    classList: {
      remove() {},
    },
  },
  addEventListener() {},
};

require('../app/docsify-plugin.js');

const hook = {
  beforeEachHandler: null,
  doneEachHandler: null,
  beforeEach(fn) {
    this.beforeEachHandler = fn;
  },
  doneEach(fn) {
    this.doneEachHandler = fn;
  },
};
const vm = {
  route: {
    file: '202606/24/test-paper.md',
    path: '/202606/24/test-paper',
  },
};

window.$docsify.plugins[0](hook, vm);

const markdown = `---
title: Test Paper
authors: "Ada Lovelace, Alan Turing"
author_affiliations: "Ada Lovelace (first_author): OpenAI; Alan Turing (last_author): Stanford University"
date: 20260624
pdf: "https://example.test/paper.pdf"
tags: ["query:agents"]
score: 8.4
relevance_score: 8.0
author_score: 9.0
author_metrics_json: '[{"name":"Ada Lovelace","role":"first_author","citation_count":1234,"paper_count":56},{"name":"Alan Turing","role":"last_author","citation_count":"98765","paper_count":"432"}]'
author_rating_explanation: "Verified elite AI lab and school affiliations."
evidence: relevant
tldr: concise tldr
---

## Abstract
Body.
`;

const rendered = hook.beforeEachHandler(markdown);

assert.ok(rendered.includes('<div class="paper-author-list">Ada Lovelace, Alan Turing</div>'));
assert.ok(rendered.includes('<div class="paper-affiliation-author">Ada Lovelace<span class="paper-author-role">first_author</span></div><div class="paper-affiliation-text">OpenAI</div>'));
assert.ok(rendered.includes('<div class="paper-affiliation-author">Alan Turing<span class="paper-author-role">last_author</span></div><div class="paper-affiliation-text">Stanford University</div>'));
assert.ok(rendered.includes('<span class="paper-author-metric"><span class="paper-author-metric-label">Citations</span>1,234</span>'));
assert.ok(rendered.includes('<span class="paper-author-metric"><span class="paper-author-metric-label">Papers</span>56</span>'));
assert.ok(rendered.includes('<span class="paper-author-metric"><span class="paper-author-metric-label">Citations</span>98,765</span>'));
assert.ok(rendered.includes('<span class="paper-author-metric"><span class="paper-author-metric-label">Papers</span>432</span>'));
assert.ok(rendered.includes('<strong>Score</strong>: 8.4'));
assert.ok(rendered.includes('<strong>Relevance Score</strong>: 8.0'));
assert.ok(rendered.includes('<strong>Author Score</strong>: 9.0'));
assert.ok(rendered.includes('<strong>Author Rating</strong>: Verified elite AI lab and school affiliations.'));

const labelOnlyRendered = hook.beforeEachHandler(markdown.replace(
  'Ada Lovelace (first_author): OpenAI; Alan Turing (last_author): Stanford University',
  'Ada Lovelace (first_author); Alan Turing (last_author): Stanford University'
));
assert.ok(labelOnlyRendered.includes('<div class="paper-affiliation-author">Ada Lovelace<span class="paper-author-role">first_author</span></div>'));
assert.ok(!labelOnlyRendered.includes('<div class="paper-affiliation-author">Affiliation</div><div class="paper-affiliation-text">Ada Lovelace (first_author)</div>'));

console.log('docsify author meta render tests passed');
