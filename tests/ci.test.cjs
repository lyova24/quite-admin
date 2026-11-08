const assert = require('node:assert/strict');
const {mkdtempSync, readFileSync, renameSync, rmSync, writeFileSync} = require('node:fs');
const {execFileSync} = require('node:child_process');
const {tmpdir} = require('node:os');
const {createRequire} = require('node:module');
const path = require('node:path');
const {test} = require('node:test');
const yaml = require('js-yaml');
const checkCI = require('../scripts/check-ci.cjs');
const validateResults = require('../scripts/ci-ready.cjs');
const {groups, audits, selectJobs, changedPaths} = require('../scripts/select-ci.cjs');

const root = path.resolve(__dirname, '..');
const context = {repo: {owner: 'lyova24', repo: 'quite-admin'}};
const sha = 'a'.repeat(40);
const successfulRun = {
  id: 42, head_sha: sha, head_branch: 'master', event: 'push',
  head_repository: {full_name: 'lyova24/quite-admin'},
  status: 'completed', conclusion: 'success',
};
const ready = {name: 'CI ready', status: 'completed', conclusion: 'success'};
const releaseReady = {name: 'Release ready', status: 'completed', conclusion: 'success'};
const docs = {name: 'quite-admin-docs', expired: false};
const workflow = name => yaml.load(readFileSync(path.join(root, '.github/workflows', name), 'utf8'));

function client({runs = [successfulRun], jobs = [ready, releaseReady], artifacts = [docs]} = {}) {
  const calls = [];
  const github = {
    rest: {actions: {
      listWorkflowRuns: async params => {
        assert.deepEqual(params, {
          ...context.repo, workflow_id: 'ci.yml', head_sha: sha,
          branch: 'master', event: params.event, per_page: 1,
        });
        assert.ok(['push', 'workflow_dispatch'].includes(params.event));
        calls.push('runs');
        return {data: {workflow_runs: runs.filter(run =>
          (run.event === 'workflow_dispatch' ? 'workflow_dispatch' : 'push') === params.event)
          .slice(0, params.per_page)}};
      },
      listJobsForWorkflowRun: async params => {
        assert.ok(runs.some(run => run.id === params.run_id));
        assert.equal(params.filter, 'latest');
        calls.push('jobs');
        return jobs;
      },
      listWorkflowRunArtifacts: async params => {
        assert.ok(runs.some(run => run.id === params.run_id));
        calls.push('artifacts');
        return artifacts;
      },
    }},
    paginate: (method, params) => method(params),
  };
  return {github, calls};
}

test('the release accepts the exact master commit and uses documentation from that CI run', async () => {
  const {github, calls} = client();
  assert.equal(await checkCI({github, context, sha, docs: true}), successfulRun.id);
  assert.deepEqual(calls, ['runs', 'runs', 'jobs', 'artifacts']);
});

test('missing CI, unfinished runs and every unsuccessful conclusion block publication', async () => {
  const states = [
    null,
    {status: 'queued', conclusion: null},
    {status: 'in_progress', conclusion: null},
    {status: 'in_progress', conclusion: 'success'},
    ...['failure', 'cancelled', 'skipped', 'neutral', 'timed_out', 'action_required']
      .map(conclusion => ({status: 'completed', conclusion})),
  ];
  for (const state of states) {
    const {github, calls} = client({runs: state ? [{...successfulRun, ...state}] : []});
    await assert.rejects(checkCI({github, context, sha, docs: true}), /master CI run/);
    assert.deepEqual(calls, ['runs', 'runs']);
  }
});

test('an older green run cannot hide a newer failed or pending run', async () => {
  for (const latest of [
    {...successfulRun, conclusion: 'failure'},
    {...successfulRun, status: 'in_progress', conclusion: null},
  ]) {
    const {github} = client({runs: [latest, {...successfulRun, id: 41}]});
    await assert.rejects(checkCI({github, context, sha}), /master CI run/);
  }
});

test('a different commit, branch, PR trigger or repository cannot authorize a release', async () => {
  for (const mismatch of [
    {head_sha: 'b'.repeat(40)}, {head_branch: 'feature'},
    {event: 'pull_request'}, {event: 'schedule'},
    {head_repository: {full_name: 'fork/quite-admin'}}, {head_repository: null},
  ]) {
    const {github} = client({runs: [{...successfulRun, ...mismatch}]});
    await assert.rejects(checkCI({github, context, sha}), /master CI run/);
  }
});

test('a green workflow with no successful aggregate validation gate is rejected', async () => {
  for (const jobs of [[], [{...ready, conclusion: 'skipped'}],
    [{...ready, conclusion: 'failure'}], [{...ready, name: 'pytest'}]]) {
    const {github, calls} = client({jobs});
    await assert.rejects(checkCI({github, context, sha, docs: true}), /CI ready/);
    assert.deepEqual(calls, ['runs', 'runs', 'jobs']);
  }
});

test('missing or expired documentation blocks the release before any publishing job', async () => {
  for (const artifacts of [[], [{...docs, expired: true}], [{name: 'unrelated', expired: false}]]) {
    const {github} = client({artifacts});
    await assert.rejects(checkCI({github, context, sha, docs: true}), /quite-admin-docs artifact/);
  }
});

test('a PyPI retry validates CI without requiring an old documentation artifact', async () => {
  const {github, calls} = client({artifacts: []});
  assert.equal(await checkCI({github, context, sha}), successfulRun.id);
  assert.deepEqual(calls, ['runs', 'runs', 'jobs']);
});

test('GitHub API errors fail closed', async () => {
  const {github} = client();
  github.rest.actions.listWorkflowRuns = async () => { throw new Error('GitHub unavailable'); };
  await assert.rejects(checkCI({github, context, sha}), /GitHub unavailable/);
});

test('release, Pages and PyPI workflow scripts execute the shared gate before publication', async () => {
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  const release = workflow('release.yml');
  const pypi = workflow('pypi.yml');
  const pages = workflow('pages.yml');
  const oldSha = process.env.RELEASE_SHA;
  process.env.RELEASE_SHA = sha;
  try {
    for (const steps of [release.jobs.metadata.steps, pages.jobs.verify.steps, pypi.jobs.build.steps]) {
      const step = steps.find(step => step.with?.script?.includes('check-ci.cjs'));
      assert.ok(step, 'Publication must use the CI gate');
      const execute = new AsyncFunction('require', 'github', 'context', step.with.script);
      const requireFromRoot = createRequire(path.join(root, 'package.json'));
      await execute(requireFromRoot, client().github, context);
      await assert.rejects(execute(requireFromRoot, client({runs: []}).github, context), /master CI run/);
    }
  } finally {
    if (oldSha === undefined) delete process.env.RELEASE_SHA;
    else process.env.RELEASE_SHA = oldSha;
  }

  assert.deepEqual(release.jobs.publish.needs, 'metadata');
  assert.equal(release.jobs.publish.steps[0].with.ref, '${{ needs.metadata.outputs.sha }}');
  assert.ok(!Object.values(release.jobs).some(job => job.uses?.endsWith('/ci.yml')));
  const buildSteps = pypi.jobs.build.steps;
  assert.ok(buildSteps.findIndex(step => step.with?.script?.includes('check-ci.cjs')) <
    buildSteps.findIndex(step => step.run === 'uv build'));
  assert.deepEqual(pypi.jobs.publish.needs, 'build');
});

test('Pages deploys the selected CI artifact without rebuilding or testing it', () => {
  const pages = workflow('pages.yml');
  assert.deepEqual(pages.on.workflow_run, {workflows: ['release'], types: ['completed']});
  assert.match(pages.jobs.verify.if, /conclusion == 'success'/);
  assert.match(pages.jobs.verify.if, /head_repository.full_name == github.repository/);
  assert.equal(pages.jobs.verify.steps[0].with.ref, '${{ github.event.workflow_run.head_sha }}');
  assert.deepEqual(pages.jobs.prepare.needs, 'verify');
  const steps = pages.jobs.prepare.steps;
  const download = steps.find(step => step.uses?.startsWith('actions/download-artifact@'));
  assert.equal(download.with.name, 'quite-admin-docs');
  assert.equal(download.with['run-id'], '${{ needs.verify.outputs.ci-run-id }}');
  assert.ok(download.with['github-token']);
  assert.ok(!steps.some(step => step.run));
  assert.deepEqual(pages.jobs.deploy.needs, 'prepare');

  const ci = workflow('ci.yml');
  assert.deepEqual(ci.on.push.branches, ['master']);
  assert.ok(!('workflow_call' in ci.on));
  const artifact = workflow('docs.yml').jobs.docs.steps
    .find(step => step.uses?.startsWith('actions/upload-artifact@'));
  assert.equal(artifact.with['include-hidden-files'], true, 'Keep .nojekyll in the CI artifact');
});

test('selective green CI cannot authorize a release, even with a documentation artifact', async () => {
  for (const jobs of [[ready], [ready, {...releaseReady, conclusion: 'skipped'}],
    [ready, {...releaseReady, conclusion: 'failure'}],
    [ready, {...releaseReady, status: 'in_progress'}]]) {
    const {github, calls} = client({jobs});
    await assert.rejects(checkCI({github, context, sha, docs: true}), /Release ready/);
    assert.ok(!calls.includes('artifacts'));
  }
});

test('a full manual master run validates the exact release SHA and supplies its docs', async () => {
  const manual = {...successfulRun, id: 43, event: 'workflow_dispatch'};
  const {github} = client({runs: [manual, successfulRun]});
  assert.equal(await checkCI({github, context, sha, docs: true}), manual.id);
});

test('the latest push or manual attempt wins, without falling back to an older full run', async () => {
  for (const event of ['push', 'workflow_dispatch']) {
    for (const latest of [
      {conclusion: 'failure'}, {status: 'in_progress', conclusion: null},
    ]) {
      const {github} = client({runs: [
        {...successfulRun, id: 43, event, ...latest},
        {...successfulRun, event: event === 'push' ? 'workflow_dispatch' : 'push'},
      ]});
      await assert.rejects(checkCI({github, context, sha}), /master CI run/);
    }
  }
  const {github} = client({runs: [
    {...successfulRun, id: 43}, {...successfulRun, event: 'workflow_dispatch'},
  ], jobs: [ready]});
  await assert.rejects(checkCI({github, context, sha}), /Release ready/);
});

const selected = plan => Object.entries(plan).filter(([, enabled]) => enabled).map(([name]) => name).sort();

test('documentation, Python, UI, browser tests and dependency changes select their consumers', () => {
  const runtime = ['tests', 'docs', 'javascript', 'browser', 'databases', 'compatibility'];
  const cases = [
    [['docs/en/releases.md', 'docs/ru/releases.md', 'README.md'], ['docs']],
    [['docs/_assets/script/quite-admin-theme.js'], ['docs']],
    [['scripts/prepare-pages.mjs'], ['docs']],
    [['pyproject.toml'], [...runtime, 'security', 'python-audit']],
    [['uv.lock'], [...runtime, 'security', 'python-audit']],
    [['package-lock.json'], ['docs', 'javascript', 'browser', 'security', 'node-audit']],
    [['package.json'], ['docs', 'javascript', 'browser', 'security', 'node-audit']],
    [['src/quite_admin/admin.py'], runtime],
    [['src/quite_admin/static/admin.css'], runtime.filter(name => name !== 'databases')],
    [['src/quite_admin/templates/quite_admin/base.html'], runtime.filter(name => name !== 'databases')],
    [['demo/app.js'], ['docs', 'javascript', 'browser']],
    [['tests/browser/bulk.spec.mjs'], ['browser']],
    [['playwright.config.mjs'], ['browser']],
    [['tests/forms.test.cjs'], ['javascript']],
    [['tests/test_filters.py'], ['tests', 'databases', 'compatibility']],
    [['tests/helpers.py'], ['tests', 'databases', 'compatibility', 'browser']],
    [['api/modern-0.4.json'], ['tests', 'compatibility']],
    [['.gitignore'], []],
    [[], []],
  ];
  for (const [paths, expected] of cases) {
    assert.deepEqual(selected(selectJobs(paths)), expected.sort(), paths.join(', '));
  }
});

test('mixed changes select the union; CI changes, unknown paths and manual runs select everything', () => {
  assert.deepEqual(selected(selectJobs(['README.md', 'tests/browser/bulk.spec.mjs'])), ['browser', 'docs']);
  assert.deepEqual(selected(selectJobs(['pyproject.toml', 'package.json'])), [...groups, ...audits].sort());
  for (const paths of [['.github/workflows/ci.yml'], ['scripts/select-ci.cjs'],
    ['scripts/ci-ready.cjs'], ['scripts/check-ci.cjs'], ['tests/ci.test.cjs'], ['new-build-input']]) {
    assert.ok(Object.values(selectJobs(paths)).every(Boolean), paths.join(', '));
  }
  assert.ok(Object.values(selectJobs([], {full: true})).every(Boolean));
});

function results(plan) {
  return {
    changes: {result: 'success', outputs: {
      plan: JSON.stringify(plan), full: String(Object.values(plan).every(Boolean)),
    }},
    metadata: {result: 'success'},
    ...Object.fromEntries(groups.map(group => [group, {result: plan[group] ? 'success' : 'skipped'}])),
  };
}

test('CI ready accepts planned skips but rejects selected skipped, failed or cancelled checks', () => {
  for (const plan of [selectJobs(['README.md']), selectJobs([]), selectJobs([], {full: true})]) {
    assert.doesNotThrow(() => validateResults(results(plan)));
    for (const group of groups.filter(group => plan[group])) {
      for (const result of ['skipped', 'failure', 'cancelled', undefined]) {
        const needs = results(plan);
        needs[group].result = result;
        assert.throws(() => validateResults(needs), /Required checks/);
      }
    }
  }
});

test('selection, metadata failures and incomplete/inconsistent plans fail closed', () => {
  for (const job of ['changes', 'metadata']) {
    for (const state of ['failure', 'cancelled', 'skipped']) {
      const needs = results(selectJobs(['README.md']));
      needs[job].result = state;
      assert.throws(() => validateResults(needs), /must succeed/);
    }
  }
  for (const plan of [{}, {docs: true}, {...selectJobs([]), tests: 'false'},
    {...selectJobs([]), security: true}]) {
    assert.throws(() => validateResults(results(plan)), /Invalid CI selection/);
  }
  const needs = results(selectJobs(['README.md']));
  needs.changes.outputs.full = 'true';
  assert.throws(() => validateResults(needs), /Invalid CI selection/);
  const unexpected = results(selectJobs(['README.md']));
  unexpected.tests.result = 'success';
  assert.throws(() => validateResults(unexpected), /Required checks/);
});

test('manual runs, new branches and missing/invalid diff bases request full validation', () => {
  const unexpectedGit = () => { throw new Error('Git should not be called'); };
  for (const [event, data] of [
    ['workflow_dispatch', {}], ['schedule', {}], ['push', {}],
    ['push', {before: '0'.repeat(40), after: sha}],
    ['push', {before: '--invalid', after: sha}], ['pull_request', {}],
  ]) assert.equal(changedPaths(event, data, unexpectedGit), null);
  assert.equal(changedPaths('push', {before: sha, after: sha}, () => {
    throw new Error('Missing old commit after force push');
  }), null);
});

test('real Git diffs cover multi-commit pushes, deletions, both rename paths and PR merge bases', () => {
  const directory = mkdtempSync(path.join(tmpdir(), 'quite-admin-ci-'));
  const git = args => execFileSync('git', ['-C', directory,
    '-c', 'core.hooksPath=/dev/null', '-c', 'commit.gpgsign=false',
    '-c', 'user.name=CI Tests', '-c', 'user.email=ci@example.invalid', ...args]);
  const commit = () => {
    git(['add', '.']);
    git(['commit', '-qm', 'fixture']);
    return git(['rev-parse', 'HEAD']).toString().trim();
  };
  try {
    git(['init', '-q', '--initial-branch=master']);
    for (const name of ['guide.md', 'old-name.md', 'removed.py']) writeFileSync(path.join(directory, name), 'initial');
    const base = commit();
    writeFileSync(path.join(directory, 'guide.md'), 'updated');
    commit();
    renameSync(path.join(directory, 'old-name.md'), path.join(directory, 'new name\nwith newline.py'));
    rmSync(path.join(directory, 'removed.py'));
    const head = commit();
    const paths = changedPaths('push', {before: base, after: head}, git);
    assert.deepEqual(paths.sort(), ['guide.md', 'old-name.md', 'removed.py', 'new name\nwith newline.py'].sort());

    git(['checkout', '-qb', 'feature', base]);
    writeFileSync(path.join(directory, 'guide.md'), 'feature docs');
    const feature = commit();
    git(['checkout', '-q', 'master']);
    writeFileSync(path.join(directory, 'target-only.py'), 'master change');
    const target = commit();
    assert.deepEqual(changedPaths('pull_request', {
      pull_request: {base: {sha: target}, head: {sha: feature}},
    }, git), ['guide.md']);

    const event = path.join(directory, 'event.json');
    const output = path.join(directory, 'output');
    const summary = path.join(directory, 'summary');
    writeFileSync(event, JSON.stringify({pull_request: {base: {sha: target}, head: {sha: feature}}}));
    execFileSync(process.execPath, [path.join(root, 'scripts/select-ci.cjs')], {
      cwd: directory, env: {...process.env, GITHUB_EVENT_NAME: 'pull_request',
        GITHUB_EVENT_PATH: event, GITHUB_OUTPUT: output, GITHUB_STEP_SUMMARY: summary},
    });
    const outputs = Object.fromEntries(readFileSync(output, 'utf8').trim().split('\n').map(line => {
      const index = line.indexOf('=');
      return [line.slice(0, index), line.slice(index + 1)];
    }));
    assert.equal(outputs.full, 'false');
    assert.deepEqual(JSON.parse(outputs.plan), selectJobs(['guide.md']));
    assert.match(readFileSync(summary, 'utf8'), /\| docs \| yes \|/);
  } finally {
    rmSync(directory, {recursive: true, force: true});
  }
});

test('workflow routing matches the selection plan and release gate waits for all checks', () => {
  const ci = workflow('ci.yml');
  for (const group of groups) {
    assert.equal(ci.jobs[group].needs, 'changes');
    assert.equal(ci.jobs[group].if, `needs.changes.outputs.${group} == 'true'`);
    assert.equal(ci.jobs.changes.outputs[group], '${{ steps.select.outputs.' + group + ' }}');
    assert.ok(ci.jobs.ready.needs.includes(group));
    assert.ok(workflow(ci.jobs[group].uses.split('/').at(-1)).on.includes?.('workflow_call') ||
      'workflow_call' in workflow(ci.jobs[group].uses.split('/').at(-1)).on);
  }
  assert.equal(ci.jobs.changes.steps[0].with['fetch-depth'], 0);
  assert.equal(ci.jobs.ready.if, 'always()');
  assert.equal(ci.jobs.ready.steps.at(-1).run, 'node scripts/ci-ready.cjs');
  assert.equal(ci.jobs['release-ready'].name, 'Release ready');
  assert.deepEqual(ci.jobs['release-ready'].needs, ['changes', 'ready']);
  assert.match(ci.jobs['release-ready'].if, /always\(\).*outputs.full == 'true'.*ready.result == 'success'/);
  assert.ok(!('paths' in ci.on.push) && !('paths-ignore' in ci.on.push));
  assert.ok(ci.jobs.metadata.steps.some(step => step.run === 'python scripts/check_release.py'));
  assert.ok(workflow('javascript.yml').jobs.javascript.steps.some(step => step.run === 'node --test tests/ci.test.cjs'));
  assert.ok(workflow('docs.yml').jobs.docs.steps.some(step => step.run === 'npm run demo:build'));
  for (const audit of audits) {
    assert.equal(ci.jobs.security.with[audit], '${{ needs.changes.outputs.' + audit + " == 'true' }}");
  }
});

test('dependency audits are separated by ecosystem while scheduled scans retain both', () => {
  const security = workflow('security.yml');
  const condition = (job, event, python, node) => new Function('github', 'inputs',
    `return ${security.jobs[job].if.replaceAll('inputs.python-audit', 'inputs.python')
      .replaceAll('inputs.node-audit', 'inputs.node')}`)(
    {event_name: event}, {python, node});
  for (const event of ['push', 'pull_request']) {
    assert.equal(condition('python-audit', event, true, false), true);
    assert.equal(condition('documentation-audit', event, true, false), false);
    assert.equal(condition('python-audit', event, false, true), false);
    assert.equal(condition('documentation-audit', event, false, true), true);
  }
  for (const event of ['schedule', 'workflow_dispatch']) {
    assert.equal(condition('python-audit', event, false, false), true);
    assert.equal(condition('documentation-audit', event, false, false), true);
  }
  assert.equal(security.on.schedule.length, 1);
});
