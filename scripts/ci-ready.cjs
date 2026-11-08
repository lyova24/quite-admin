const {groups, audits} = require('./select-ci.cjs');

module.exports = function validateResults(needs) {
  if (needs.changes?.result !== 'success' || needs.metadata?.result !== 'success') {
    throw new Error('Change detection and release metadata checks must succeed.');
  }
  const plan = JSON.parse(needs.changes.outputs.plan);
  if ([...groups, ...audits].some(group => typeof plan[group] !== 'boolean') ||
      plan.security !== (plan['python-audit'] || plan['node-audit']) ||
      needs.changes.outputs.full !== String([...groups, ...audits].every(group => plan[group]))) {
    throw new Error('Invalid CI selection plan.');
  }
  const failures = groups.filter(group => needs[group]?.result !== (plan[group] ? 'success' : 'skipped'));
  if (failures.length) throw new Error('Required checks did not pass as planned: ' + failures.join(', '));
};

if (require.main === module) module.exports(JSON.parse(process.env.CI_RESULTS));
