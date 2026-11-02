import assert from 'node:assert/strict';
import {readFile, readdir, rm, writeFile} from 'node:fs/promises';

const output = new URL('../build/docs/', import.meta.url);
if (process.argv[2] === '--clean') {
  // Remove only generated output; old pages must not survive a new site build.
  await rm(output, {recursive: true, force: true});
  console.log('Cleared generated documentation output.');
  process.exit(0);
}
for (const page of ['index.html', 'en/index.html', 'ru/index.html']) {
  const html = await readFile(new URL(page, output), 'utf8');
  assert.match(html, /<!doctype html>/i, `${page}: missing generated HTML`);
}
// The static viewer defaults to light and has no configuration for its initial mode.
// Move our supported custom resource before the content and deferred viewer bundles.
// Resolve it through the generated <base> so repository prefixes and both languages work.
async function prepareTheme(directory) {
  let count = 0;
  for (const entry of await readdir(directory, {withFileTypes: true})) {
    const file = new URL(entry.name, directory);
    if (entry.isDirectory()) {
      if (entry.name !== 'demo') count += await prepareTheme(new URL(entry.name + '/', directory));
    } else if (entry.name.endsWith('.html')) {
      let html = await readFile(file, 'utf8');
      if (!html.includes('id="diplodoc-state"')) continue;
      const resource = /<script\b[^>]*\bsrc="_assets\/script\/quite-admin-theme\.js"[^>]*><\/script>/g;
      assert.equal([...html.matchAll(resource)].length, 1, `${file.pathname}: missing theme initializer`);
      html = html.replace(resource, '');
      assert.match(html, /<body class="g-root g-root_theme_(?:light|dark)">/, `${file.pathname}: unexpected viewer root`);
      html = html.replace(
        /<body class="g-root g-root_theme_(?:light|dark)">/,
        '<body class="g-root g-root_theme_dark">\n        <script src="_assets/script/quite-admin-theme.js"></script>',
      );
      await writeFile(file, html);
      count++;
    }
  }
  return count;
}
const themedPages = await prepareTheme(output);
assert.ok(themedPages >= 3, 'Documentation pages must receive the theme initializer');
// Serve generated HTML and _bundle assets directly, never through Jekyll/Liquid.
await writeFile(new URL('.nojekyll', output), '');
console.log(`GitHub Pages artifact prepared (${themedPages} themed Diplodoc pages, Jekyll disabled).`);
