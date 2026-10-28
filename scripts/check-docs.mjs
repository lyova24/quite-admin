import assert from 'node:assert/strict';
import {readFile, readdir, stat} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('../docs/', import.meta.url));
const languages = ['en', 'ru'];

async function pages(directory, prefix = '') {
  const result = [];
  for (const entry of await readdir(directory, {withFileTypes: true})) {
    const relative = path.posix.join(prefix, entry.name);
    if (entry.isDirectory()) {
      result.push(...await pages(path.join(directory, entry.name), relative));
    } else if (entry.name.endsWith('.md')) {
      result.push(relative);
    }
  }
  return result.sort();
}

let primaryPages;
let primaryNavigation;
for (const language of languages) {
  const directory = path.join(root, language);
  const files = await pages(directory);
  const toc = await readFile(path.join(directory, 'toc.yaml'), 'utf8');
  // Diplodoc validates the YAML itself. Compare every local href in navigation order.
  const navigation = [...toc.matchAll(/^\s*href:\s*(\S+)\s*$/gm)].map(match => match[1]);
  assert.deepEqual([...new Set(navigation)].sort(), files, `${language}: TOC coverage differs`);
  if (primaryPages) {
    assert.deepEqual(files, primaryPages, `${language}: translated page coverage differs`);
    assert.deepEqual(navigation, primaryNavigation, `${language}: navigation order differs`);
  } else {
    primaryPages = files;
    primaryNavigation = navigation;
  }
  for (const file of files) {
    const filename = path.join(directory, file);
    const content = await readFile(filename, 'utf8');
    assert.match(content, /^# .+/m, `${language}/${file}: missing page title`);
    const prose = content.replace(/^```[^\n]*\n[\s\S]*?^```\s*$/gm, '');
    for (const match of prose.matchAll(/\[[^\]]*\]\(([^)\s]+)\)/g)) {
      const href = match[1];
      if (/^(?:[a-z][a-z0-9+.-]*:|\/|#)/i.test(href)) continue;
      const target = decodeURIComponent(href.split(/[?#]/)[0]);
      if (!target) continue;
      const resolved = path.resolve(path.dirname(filename), target);
      assert.ok(resolved.startsWith(root), `${language}/${file}: link escapes docs: ${href}`);
      assert.ok((await stat(resolved)).isFile(), `${language}/${file}: missing link target: ${href}`);
    }
  }
}
console.log(`Documentation checked: ${primaryPages.length} matching pages per language (en, ru).`);
