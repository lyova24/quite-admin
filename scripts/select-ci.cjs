// Keep path selection local: no API pagination limits, credentials or third-party filters.
const {execFileSync} = require('node:child_process');
const {appendFileSync, readFileSync} = require('node:fs');

const groups = ['tests', 'docs', 'javascript', 'browser', 'databases', 'compatibility', 'security'];
const audits = ['python-audit', 'node-audit'];
const runtime = ['tests', 'docs', 'javascript', 'browser', 'databases', 'compatibility'];

function selectJobs(paths, {full = false} = {}) {
  const plan = Object.fromEntries([...groups, ...audits].map(group => [group, full]));
  const enable = (...names) => names.forEach(name => { plan[name] = true; });
  for (const path of paths) {
    if (path.startsWith('.github/workflows/') ||
        ['scripts/select-ci.cjs', 'scripts/ci-ready.cjs', 'scripts/check-ci.cjs',
          'tests/ci.test.cjs'].includes(path)) {
      enable(...groups, ...audits);
    } else if (['pyproject.toml', 'uv.lock'].includes(path)) {
      enable(...runtime, 'python-audit');
    } else if (['package.json', 'package-lock.json', '.npmrc', '.node-version', '.nvmrc'].includes(path)) {
      enable('docs', 'javascript', 'browser', 'node-audit');
    } else if (path.startsWith('docs/') || /\.(md|rst)$/.test(path) || path === 'LICENSE') {
      enable('docs');
    } else if (path.startsWith('src/quite_admin/static/') || path.startsWith('src/quite_admin/templates/')) {
      enable('tests', 'docs', 'javascript', 'browser', 'compatibility');
    } else if (path.startsWith('src/') || path.startsWith('examples/') || path === 'scripts/build_demo.py') {
      enable(...runtime);
    } else if (path.startsWith('demo/')) {
      enable('docs', 'javascript', 'browser');
    } else if (path.startsWith('tests/browser/') || path === 'playwright.config.mjs') {
      enable('browser');
    } else if (path.startsWith('tests/') && /\.(mjs|cjs)$/.test(path)) {
      enable('javascript');
    } else if (path.startsWith('tests/') && path.endsWith('.py')) {
      enable('tests', 'databases', 'compatibility');
      if (['tests/browser_app.py', 'tests/helpers.py', 'tests/__init__.py'].includes(path)) enable('browser');
    } else if (path.startsWith('api/') || ['scripts/check_api.py', 'scripts/test_compatibility.py'].includes(path)) {
      enable('tests', 'compatibility');
    } else if (['scripts/check-docs.mjs', 'scripts/diplodoc.cjs', 'scripts/prepare-pages.mjs'].includes(path)) {
      enable('docs');
    } else if (['scripts/check_release.py', 'scripts/check_distributions.py'].includes(path)) {
      enable('tests');
    } else if (!['.gitignore', '.editorconfig'].includes(path)) {
      // New/unclassified inputs must never silently lose validation.
      enable(...groups, ...audits);
    }
  }
  plan.security = plan['python-audit'] || plan['node-audit'];
  return plan;
}

function changedPaths(eventName, event, git = args => execFileSync('git', args, {maxBuffer: 16 * 1024 * 1024})) {
  if (eventName === 'workflow_dispatch') return null;
  const base = eventName === 'pull_request' ? event.pull_request?.base?.sha : event.before;
  const head = eventName === 'pull_request' ? event.pull_request?.head?.sha : event.after;
  const valid = sha => /^[a-f0-9]{40,64}$/.test(sha || '') && !/^0+$/.test(sha);
  if (!['push', 'pull_request'].includes(eventName) || !valid(base) || !valid(head)) return null;
  try {
    const range = `${base}${eventName === 'pull_request' ? '...' : '..'}${head}`;
    // Disabling rename detection includes both the old and new path, including deletions.
    return git(['diff', '--name-only', '--no-renames', '-z', range, '--']).toString('utf8').split('\0').filter(Boolean);
  } catch {
    // A force-push can make the old commit unavailable. Run everything in that case.
    return null;
  }
}

if (require.main === module) {
  const event = JSON.parse(readFileSync(process.env.GITHUB_EVENT_PATH, 'utf8'));
  const paths = changedPaths(process.env.GITHUB_EVENT_NAME, event);
  const plan = selectJobs(paths || [], {full: paths === null});
  const full = [...groups, ...audits].every(group => plan[group]);
  appendFileSync(process.env.GITHUB_OUTPUT,
    Object.entries({...plan, full, plan: JSON.stringify(plan)}).map(([key, value]) => `${key}=${value}\n`).join(''));
  appendFileSync(process.env.GITHUB_STEP_SUMMARY,
    `## CI selection\n\n${paths === null ? 'Full validation (manual run or unavailable diff).' : `${paths.length} changed paths.`}\n\n` +
    '| Check | Selected |\n| --- | --- |\n' +
    Object.entries(plan).map(([name, selected]) => `| ${name} | ${selected ? 'yes' : 'no'} |\n`).join(''));
}

module.exports = {groups, audits, selectJobs, changedPaths};
