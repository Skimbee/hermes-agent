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
for mode in ['verify','stage','attest','publish']:
    job=release['jobs'][mode]
    assert "github.ref == 'refs/heads/main'" in job['if']
    assert "github.repository == 'Skimbee/hermes-agent'" in job['if']
    if mode!='verify':
        assert "needs.verify.outputs.publishable == 'true'" in job['if']
        assert job['environment']=='bridge-publisher'
        apps=[s['with'] for s in job['steps'] if s.get('uses','').startswith('actions/create-github-app-token@')]
        assert len(apps)==1 and apps[0]['repositories']=='hermes-agent' and apps[0]['skip-token-revoke']=='false'
        assert 'permission-administration' not in apps[0] and 'permission-workflows' not in apps[0]
        if mode=='attest':assert apps[0].get('permission-checks')=='write' and 'permission-contents' not in apps[0]
        else:assert apps[0].get('permission-contents')=='write' and 'permission-checks' not in apps[0]
assert "vars.BRIDGE_RELEASE_ENABLED == 'true'" in release['jobs']['publish']['if']
assert workflows['bridge-hourly-pilot.yml']['on']['schedule']==[{'cron':'17 * * * *'}]
assert workflows['bridge-hourly-pilot.yml']['permissions']=={'contents':'read'}
for file in (root/'scripts/bridge').rglob('*.py'):ast.parse(file.read_text(),filename=str(file))
print('WORKFLOW_CONTRACT_VALIDATED',len(workflows))
