import assert from 'node:assert/strict';
import {readFile, writeFile} from 'node:fs/promises';

const output = new URL('../build/docs/', import.meta.url);
for (const page of ['index.html', 'en/index.html', 'ru/index.html']) {
  const html = await readFile(new URL(page, output), 'utf8');
  assert.match(html, /<!doctype html>/i, `${page}: missing generated HTML`);
}
// Serve generated HTML and _bundle assets directly, never through Jekyll/Liquid.
await writeFile(new URL('.nojekyll', output), '');
console.log('GitHub Pages artifact prepared (Diplodoc HTML, Jekyll disabled).');
