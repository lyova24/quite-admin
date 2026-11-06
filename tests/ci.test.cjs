const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {createRequire} = require('node:module');
const path = require('node:path');
const {test} = require('node:test');
const yaml = require('js-yaml');
const checkCI = require('../scripts/check-ci.cjs');

const root = path.resolve(__dirname, '..');
const context = {repo: {owner: 'lyova24', repo: 'quite-admin'}};
const sha = 'a'.repeat(40);
const successfulRun = {
  id: 42, head_sha: sha, head_branch: 'master', event: 'push',
  head_repository: {full_name: 'lyova24/quite-admin'},
  status: 'completed', conclusion: 'success',
};
const ready = {name: 'CI ready', status: 'completed', conclusion: 'success'};
const docs = {name: 'quite-admin-docs', expired: false};
const workflow = name => yaml.load(readFileSync(path.join(root, '.github/workflows', name), 'utf8'));

function client({runs = [successfulRun], jobs = [ready], artifacts = [docs]} = {}) {
  const calls = [];
  const github = {
    rest: {actions: {
      listWorkflowRuns: async params => {
        assert.deepEqual(params, {
          ...context.repo, workflow_id: 'ci.yml', head_sha: sha,
          branch: 'master', event: 'push', per_page: 1,
        });
        calls.push('runs');
        return {data: {workflow_runs: runs.slice(0, params.per_page)}};
      },
      listJobsForWorkflowRun: async params => {
        assert.equal(params.run_id, successfulRun.id);
        assert.equal(params.filter, 'latest');
        calls.push('jobs');
        return jobs;
      },
      listWorkflowRunArtifacts: async params => {
        assert.equal(params.run_id, successfulRun.id);
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
  assert.deepEqual(calls, ['runs', 'jobs', 'artifacts']);
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
    await assert.rejects(checkCI({github, context, sha, docs: true}), /master push run/);
    assert.deepEqual(calls, ['runs']);
  }
});

test('an older green run cannot hide a newer failed or pending run', async () => {
  for (const latest of [
    {...successfulRun, conclusion: 'failure'},
    {...successfulRun, status: 'in_progress', conclusion: null},
  ]) {
    const {github} = client({runs: [latest, {...successfulRun, id: 41}]});
    await assert.rejects(checkCI({github, context, sha}), /master push run/);
  }
});

test('a different commit, branch, trigger or repository cannot authorize a release', async () => {
  for (const mismatch of [
    {head_sha: 'b'.repeat(40)}, {head_branch: 'feature'},
    {event: 'pull_request'}, {event: 'workflow_dispatch'},
    {head_repository: {full_name: 'fork/quite-admin'}}, {head_repository: null},
  ]) {
    const {github} = client({runs: [{...successfulRun, ...mismatch}]});
    await assert.rejects(checkCI({github, context, sha}), /master push run/);
  }
});

test('a green workflow with no successful aggregate validation gate is rejected', async () => {
  for (const jobs of [[], [{...ready, conclusion: 'skipped'}],
    [{...ready, conclusion: 'failure'}], [{...ready, name: 'pytest'}]]) {
    const {github, calls} = client({jobs});
    await assert.rejects(checkCI({github, context, sha, docs: true}), /CI ready/);
    assert.deepEqual(calls, ['runs', 'jobs']);
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
  assert.deepEqual(calls, ['runs', 'jobs']);
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
      await assert.rejects(execute(requireFromRoot, client({runs: []}).github, context), /master push run/);
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
  const artifact = workflow('tests.yml').jobs.docs.steps
    .find(step => step.uses?.startsWith('actions/upload-artifact@'));
  assert.equal(artifact.with['include-hidden-files'], true, 'Keep .nojekyll in the CI artifact');
});
