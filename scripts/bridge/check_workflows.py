"""Static workflow contract, with Bash parser checks (never runs bodies)."""
import ast,pathlib,re,subprocess
import yaml
root=pathlib.Path(__file__).resolve().parents[2]
workflows={}
for path in sorted((root/'.github/workflows').glob('bridge-*.yml')):
    doc=yaml.load(path.read_text(),Loader=yaml.BaseLoader)
    assert isinstance(doc,dict) and 'on' in doc and 'jobs' in doc,path
    workflows[path.name]=doc
    for job in doc['jobs'].values():
        for step in job.get('steps',[]):
            if 'uses' in step:assert re.fullmatch(r'[^@]+@[0-9a-f]{40}',step['uses']),step['uses']
            if 'run' in step:
                script=re.sub(r'\$\{\{.*?\}\}','expression_placeholder',step['run'])
                subprocess.run(['bash','-n'],input=script,text=True,check=True)
release=workflows['bridge-release.yml']
assert release['permissions']=={'contents':'read','actions':'read','checks':'read','pull-requests':'read'}
assert release['jobs']['verify'].get('environment') is None
assert release['jobs']['verify']['outputs']['workflow_write_required']=='${{ steps.verify.outputs.workflow_write_required }}'
owners=[line.split() for line in (root/'.github/CODEOWNERS').read_text().splitlines() if line.strip() and not line.startswith('#')]
assert owners==[[p,'@Skimbee'] for p in ('/.github/workflows/bridge-*','/scripts/bridge/','/.github/CODEOWNERS','/CODEOWNERS','/docs/CODEOWNERS','/tests/plugins/memory/test_hindsight_pin_contract.py')]
for mode in ['verify','stage','attest','publish']:
    job=release['jobs'][mode]
    assert "github.ref == 'refs/heads/main'" in job['if']
    assert "github.repository == 'Skimbee/hermes-agent'" in job['if']
    if mode!='verify':
        assert "needs.verify.outputs.publishable == 'true'" in job['if']
        assert job['environment']=='bridge-publisher'
        apps=[s['with'] for s in job['steps'] if s.get('uses','').startswith('actions/create-github-app-token@')]
        assert len(apps)==1 and apps[0]['repositories']=='hermes-agent' and apps[0]['skip-token-revoke']=='false'
        assert 'permission-administration' not in apps[0]
        if mode=='attest':assert 'permission-workflows' not in apps[0]
        else:
            assert apps[0]['permission-workflows']=="${{ needs.verify.outputs.workflow_write_required == 'true' && vars.BRIDGE_WORKFLOW_WRITES_ENABLED == 'true' && 'write' || '' }}"
            action=[s for s in job['steps'] if s.get('name')==('stage exact candidate' if mode=='stage' else 'publish exact candidate')][0]
            assert action['env']['BRIDGE_WORKFLOW_WRITES_ENABLED']=='${{ vars.BRIDGE_WORKFLOW_WRITES_ENABLED }}'
        if mode=='attest':assert apps[0].get('permission-checks')=='write' and 'permission-contents' not in apps[0]
        else:assert apps[0].get('permission-contents')=='write' and 'permission-checks' not in apps[0]
assert "vars.BRIDGE_RELEASE_ENABLED == 'true'" in release['jobs']['publish']['if']
assert 'schedule' not in workflows['bridge-hourly-pilot.yml']['on']
assert workflows['bridge-hourly-pilot.yml']['on']['workflow_dispatch']['inputs']['rehearsal']['default']=='normal'
assert workflows['bridge-hourly-pilot.yml']['permissions']=={'contents':'read'}
ordered_names=[step.get('name') for step in workflows['bridge-hourly-pilot.yml']['jobs']['verify']['steps']]
sequence=('Build isolated candidate without credentials','Reconcile missing lock exclusion metadata','Install and verify frozen SDK contract','Run focused regression gates','Preserve exact tested candidate','Upload candidate and receipt')
assert all(ordered_names.count(name)==1 for name in sequence), 'Missing or duplicated candidate step'
positions=[ordered_names.index(name) for name in sequence]
assert positions==sorted(positions), 'Candidate preparation, tests and evidence are out of order'
hourly_steps={step.get('name'):step for step in workflows['bridge-hourly-pilot.yml']['jobs']['verify']['steps']}
for name in ('Reconcile missing lock exclusion metadata','Install and verify frozen SDK contract','Run focused regression gates','Preserve exact tested candidate'):
    assert hourly_steps[name]['if']=="steps.build.outputs.has_candidate != 'false'", 'Missing no-change guard: '+name
    assert 'continue-on-error' not in hourly_steps[name], 'Candidate gates may not ignore failures'
for file in (root/'scripts/bridge').rglob('*.py'):ast.parse(file.read_text(),filename=str(file))
print('WORKFLOW_CONTRACT_VALIDATED',len(workflows))
