const {execFileSync} = require('node:child_process');

// Documentation may follow the latest published package without another package release.
// Keep this list narrow: runtime, demo and package inputs still need the release route.
const documentationFiles = new Set([
  'README.md',
  'AGENTS.md',
  '.github/workflows/pages.yml',
  'scripts/check-docs-deployment.cjs',
  'scripts/capture_screenshots.mjs',
  'scripts/screenshot_app.py',
  'tests/ci.test.cjs',
]);

module.exports = async function checkDocsDeployment({github, context, sha,
  git = args => execFileSync('git', args, {maxBuffer: 16 * 1024 * 1024}),
  info = () => {}}) {
  if (!/^[a-f0-9]{40,64}$/.test(sha || '')) throw new Error('A full commit SHA is required.');

  const {data: master} = await github.rest.git.getRef({...context.repo, ref: 'heads/master'});
  if (master.object?.sha !== sha) {
    info('Skipping documentation deployment: master has advanced past this CI run.');
    return false;
  }

  const {data: release} = await github.rest.repos.getLatestRelease(context.repo);
  if (release.draft || release.prerelease || !release.published_at ||
      !/^v\d+\.\d+\.\d+$/.test(release.tag_name || '')) {
    throw new Error('Documentation deployment needs a finalized published version tag.');
  }
  const base = git(['rev-parse', '--verify', `refs/tags/${release.tag_name}^{commit}`]).toString().trim();
  if (!/^[a-f0-9]{40,64}$/.test(base)) throw new Error('The published release tag could not be resolved.');
  try {
    git(['merge-base', '--is-ancestor', base, sha]);
  } catch (error) {
    if (error.status !== 1) throw error;
    info('Skipping documentation deployment: master does not descend from the published release.');
    return false;
  }

  // Full local history avoids API file-count limits. Disabled rename detection checks
  // both paths, so moving a runtime file into docs cannot disguise a package change.
  const paths = git(['diff', '--name-only', '--no-renames', '-z', base, sha, '--'])
    .toString('utf8').split('\0').filter(Boolean);
  if (!paths.length || paths.some(path => !path.startsWith('docs/') && !documentationFiles.has(path))) {
    info('Skipping documentation deployment: the commit is released already or includes package changes.');
    return false;
  }
  return true;
};
