// Diplodoc 5.64 uses the extensionless CommonJS paths from markdown-it 13.
// Keep its consumers compatible with the patched markdown-it 14 ESM files on Node 24.
// This adapter changes module paths/interop only, never parser behavior or advisory checks.
const Module = require('node:module');
const path = require('node:path');
const load = Module._load;

Module._load = function (request, parent, isMain) {
  if (request.startsWith('markdown-it/lib/') && !request.endsWith('.mjs')) {
    const target = request.replace(/\.js$/, '');
    let filename;
    try {
      filename = Module._resolveFilename(target + '.mjs', parent);
    } catch (error) {
      if (error.code !== 'MODULE_NOT_FOUND') throw error;
      filename = Module._resolveFilename(target + '/index.mjs', parent);
    }
    const exported = load.call(this, filename, parent, isMain);
    return exported.default ?? exported;
  }
  return load.call(this, request, parent, isMain);
};

const manifest = require.resolve('@diplodoc/cli/package');
const entry = path.resolve(path.dirname(manifest), require(manifest).bin.yfm);
process.argv[1] = entry;
Module._load(entry, null, true);
