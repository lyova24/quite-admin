// A selective green run authorizes a merge; publication needs complete validation.
// Never let an older green run hide a newer failed, pending or selective run.
module.exports = async function checkCI({github, context, sha, docs = false}) {
  const responses = await Promise.all(['push', 'workflow_dispatch'].map(event =>
    github.rest.actions.listWorkflowRuns({
      ...context.repo, workflow_id: 'ci.yml', head_sha: sha,
      branch: 'master', event, per_page: 1,
    })));
  const run = responses.flatMap(({data}) => data.workflow_runs)
    .sort((left, right) => right.id - left.id)[0];
  if (!run || run.head_sha !== sha || run.head_branch !== 'master' ||
      !['push', 'workflow_dispatch'].includes(run.event) ||
      run.head_repository?.full_name !== `${context.repo.owner}/${context.repo.repo}` ||
      run.status !== 'completed' || run.conclusion !== 'success') {
    throw new Error(`Commit ${sha} needs a successful completed master CI run of ci.yml. ` +
      'Run ci.yml manually on master at that exact commit for full validation, then retry publication.');
  }

  const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
    ...context.repo, run_id: run.id, filter: 'latest', per_page: 100,
  });
  for (const name of ['CI ready', 'Release ready']) {
    if (!jobs.some(job => job.name === name &&
        job.status === 'completed' && job.conclusion === 'success')) {
      throw new Error(`CI run ${run.id} has no successful ${name} validation gate. ` +
        'Run ci.yml manually on master at the exact release commit for full validation, then retry publication.');
    }
  }

  if (docs) {
    const artifacts = await github.paginate(github.rest.actions.listWorkflowRunArtifacts, {
      ...context.repo, run_id: run.id, per_page: 100,
    });
    if (!artifacts.some(artifact => artifact.name === 'quite-admin-docs' && !artifact.expired)) {
      throw new Error(`CI run ${run.id} has no available quite-admin-docs artifact. ` +
        'Rerun that CI to rebuild the release documentation, then rerun the release.');
    }
  }
  return run.id;
};
