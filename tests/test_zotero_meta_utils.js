const assert = require('node:assert/strict');

const { getRawPaperSections } = require('../app/zotero-meta-utils.js');

const sample = `---
title: Attention Is All You Need
---

## Chinese Abstract
这是中文摘要。

## 📝 TLDR
这是 tldr。

## Abstract
This is the original abstract in English.

## Detailed Summary (AI-generated)
This is ai summary.
`;

const sections = getRawPaperSections(sample);

assert.equal(sections.chineseAbstractText, '这是中文摘要。');
assert.equal(sections.tldrText, '这是 tldr。');
assert.equal(sections.originalAbstractText, 'This is the original abstract in English.');
assert.equal(sections.aiSummaryText, 'This is ai summary.');

console.log('zotero meta utils tests passed');
