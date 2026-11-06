// Shared publication gate. A previous green run must not hide a failed or pending rerun.
module.exports = async function checkCI({github, context, sha, docs = false}) {
  const {data} = await github.rest.actions.listWorkflowRuns({
    ...context.repo,
    workflow_id: 'ci.yml',
    head_sha: sha,
    branch: 'master',
    event: 'push',
    per_page: 1,
  });
  const run = data.workflow_runs[0];
  if (!run || run.head_sha !== sha || run.head_branch !== 'master' ||
      run.event !== 'push' ||
      run.head_repository?.full_name !== `${context.repo.owner}/${context.repo.repo}` ||
      run.status !== 'completed' || run.conclusion !== 'success') {
    throw new Error(`Commit ${sha} needs a successful completed master push run of ci.yml. ` +
      'Finish or rerun that CI, then rerun the release.');
  }

  const jobs = await github.paginate(github.rest.actions.listJobsForWorkflowRun, {
    ...context.repo, run_id: run.id, filter: 'latest', per_page: 100,
  });
  if (!jobs.some(job => job.name === 'CI ready' &&
      job.status === 'completed' && job.conclusion === 'success')) {
    throw new Error(`CI run ${run.id} has no successful CI ready validation gate.`);
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
