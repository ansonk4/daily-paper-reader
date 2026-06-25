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
author_rating_explanation: "Verified elite AI lab and school affiliations."
evidence: relevant
tldr: concise tldr
---

## Abstract
Body.
`;

const rendered = hook.beforeEachHandler(markdown);

assert.ok(rendered.includes('<strong>Authors</strong>: Ada Lovelace, Alan Turing'));
assert.ok(rendered.includes('<strong>Author Affiliations</strong>: Ada Lovelace (first_author): OpenAI; Alan Turing (last_author): Stanford University'));
assert.ok(rendered.includes('<strong>Score</strong>: 8.4'));
assert.ok(rendered.includes('<strong>Relevance Score</strong>: 8.0'));
assert.ok(rendered.includes('<strong>Author Score</strong>: 9.0'));
assert.ok(rendered.includes('<strong>Author Rating</strong>: Verified elite AI lab and school affiliations.'));

console.log('docsify author meta render tests passed');
