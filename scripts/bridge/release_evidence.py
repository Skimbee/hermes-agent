"""Read-only GitHub evidence verification. Never checks out or executes candidate code."""
import hashlib,io,json,os,pathlib,subprocess,tempfile,zipfile
from typing import Any
from release_policy import require,sha,protected_paths,validate_candidate
REPO='Skimbee/hermes-agent'
CANDIDATE_PATH='.github/workflows/bridge-hourly-pilot.yml'
DASHBOARD_PATH='.github/workflows/bridge-dashboard-e2e.yml'
CLIENT_BASE='d131988d53c3b8389801f6cee03b990bd51ac49a'
LIMIT=25*1024*1024

def api(path,method='GET',data=None,app=False,raw=False) -> Any:
    require(not path.startswith('/') and '://' not in path,'Unsafe API path')
    command=['gh','api','--method',method,'repos/'+REPO+'/'+path]
    if data is not None:command+=['--input','-']
    env=os.environ.copy()
    if app:env['GH_TOKEN']=os.environ['APP_TOKEN']
    result=subprocess.run(command,input=json.dumps(data).encode() if data is not None else None,stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=env,timeout=90)
    require(result.returncode==0,'GitHub request failed: '+method+' '+path+'; '+result.stderr.decode(errors='replace')[:2000])
    return result.stdout if raw else json.loads(result.stdout)

def identity(run):
    return {'repository':run['repository']['full_name'],'id':run['id'],'attempt':run['run_attempt'],'workflow_id':run['workflow_id'],'path':run['path'],'controller':run['head_sha'],'event':run['event']}

def verify_bindings(c,d,a,r,bundle,binding,result,base):
    sha(base)
    for run,path,events in ((c,CANDIDATE_PATH,('schedule','workflow_dispatch')),(d,DASHBOARD_PATH,('workflow_run','workflow_dispatch'))):
        require(run['repository']['full_name']==REPO and run['head_branch']=='main','Repository/branch')
        require(run['status']=='completed' and run['conclusion']=='success','Run status')
        require(run['path']==path and run['event'] in events and run['head_sha']==base,'Controller/path/event')
    require(type(r['schema']) is int and r['schema']==1,'Receipt schema')
    require(r['run_id']==str(c['id']) and r['run_attempt']==str(c['run_attempt']),'Receipt run identity')
    require(r['base']==base==r['workflow_sha'],'Receipt base')
    for key in ('candidate','upstream','base'):sha(r[key])
    require(hashlib.sha256(bundle).hexdigest()==r['bundle_sha256'],'Bundle digest')
    expected_run={**identity(c),'status':'completed','conclusion':'success'}
    expected_artifact={'id':a['id'],'run_id':c['id'],'digest':a['digest'],'expired':False}
    require(a['expired'] is False,'Expired candidate artifact')
    for observed in (binding,result):
        require(type(observed['schema']) is int and observed['schema']==2,'E2E schema')
        require(observed['candidate_run']==expected_run and observed['candidate_artifact']==expected_artifact,'Original run/artifact binding')
        require(observed['candidate']==r['candidate'] and observed['bundle_sha256']==r['bundle_sha256'],'Original candidate/bundle binding')
        require(observed['dashboard_identity']==identity(d),'Original dashboard identity')
    require(result['dashboard_run']==identity(d),'Dashboard run binding')
    for flag in ('passed','reconnected','tracked_tree_matches','candidate_stopped','browser_sandbox_requested'):
        require(result.get(flag) is True,'Missing positive E2E observation: '+flag)
    require('PID namespaces Yes' in result['browser_sandbox_status'] and 'Seccomp-BPF sandbox Yes' in result['browser_sandbox_status'],'Browser sandbox')
    require(result['pre_head']==CLIENT_BASE and result['post_head']==r['candidate'],'Inspected heads')
    require(type(result['tracked_files_verified']) is int and result['tracked_files_verified']>0,'Inspected file count')
    require(result['observed_receipt']=={'pre_sha':CLIENT_BASE,'post_sha':r['candidate'],'outcome':'success'},'Observed receipt')

def verify_no_change(c,d,a,r,result,base):
    for run,path,events in ((c,CANDIDATE_PATH,('schedule','workflow_dispatch')),(d,DASHBOARD_PATH,('workflow_run','workflow_dispatch'))):
        require(run['repository']['full_name']==REPO and run['head_branch']=='main' and run['head_sha']==base,'No-change controller')
        require(run['status']=='completed' and run['conclusion']=='success' and run['path']==path and run['event'] in events,'No-change run')
    require(r['schema']==1 and r['kind']=='no-change' and r['candidate']==r['base']==r['workflow_sha']==base,'No-change receipt')
    require(r['run_id']==str(c['id']) and r['run_attempt']==str(c['run_attempt']),'No-change source identity')
    sha(r['upstream'])
    require(a['expired'] is False,'No-change expired artifact')
    require(result['schema']==3 and result['state']=='no_change' and result['candidate_run']=={**identity(c),'status':'completed','conclusion':'success'},'No-change binding')
    require(result['candidate_artifact']=={'id':a['id'],'run_id':c['id'],'digest':a['digest'],'expired':False} and result['dashboard_identity']==identity(d),'No-change artifact/dashboard binding')

def artifact(run,name):
    rows=api('actions/runs/'+str(run['id'])+'/artifacts?per_page=100')
    require(rows['total_count']==len(rows['artifacts']) and rows['total_count']<100,'Artifact pagination')
    matches=[a for a in rows['artifacts'] if a['name']==name and a['expired'] is False]
    require(len(matches)==1,'Missing or ambiguous artifact');a=matches[0]
    require(a['size_in_bytes']<LIMIT,'Artifact size')
    data=api('actions/artifacts/'+str(a['id'])+'/zip',raw=True)
    require(len(data)<LIMIT and 'sha256:'+hashlib.sha256(data).hexdigest()==a['digest'],'Artifact digest')
    z=zipfile.ZipFile(io.BytesIO(data));names=z.namelist()
    require(len(names)==len(set(names)) and sum(i.file_size for i in z.infolist())<LIMIT,'Archive bounds/duplicate entries')
    return a,z

def canonical_hash(data):return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def verify_first_parent(base,candidate,git):
    sha(base);sha(candidate)
    chain=git('rev-list','--first-parent',candidate).decode('ascii').splitlines()
    require(chain and chain[0]==candidate and base in chain,'Base absent from actual first-parent chain')

def verify_official_upstream(upstream,git):
    sha(upstream)
    git('fetch','--no-tags','https://github.com/NousResearch/hermes-agent.git','refs/heads/main')
    git('merge-base','--is-ancestor',upstream,'FETCH_HEAD')


def classify_control_changes(base,candidate,upstream,git):
    """Exempt only exact upstream changes that overwrite no fork customization.

    Git mode/type/object identity includes deletions and mode changes. The caller
    must independently establish that upstream is on the official main history.
    No checkout, filters, candidate imports or candidate-supplied path lists.
    """
    for value in (base,candidate,upstream):sha(value)
    ancestor=git('merge-base',base,upstream).decode().strip();sha(ancestor)
    def tree(commit):
        entries={}
        for entry in git('ls-tree','-rz',commit).split(b'\0'):
            if entry:
                metadata,path=entry.split(b'\t',1)
                entries[path.decode('utf-8')]=metadata
        return entries
    before,after,original,incoming=map(tree,(base,candidate,ancestor,upstream))
    paths=sorted(p for p in before.keys()|after.keys() if before.get(p)!=after.get(p))
    protected=set(protected_paths(paths))
    workflows=[];upstream_workflows=[]
    for path in paths:
        if not path.startswith(('.github/','scripts/')):continue
        upstream_owned=(path not in protected and before.get(path)==original.get(path)
                        and after.get(path)==incoming.get(path))
        if not upstream_owned:protected.add(path)
        if path.startswith('.github/workflows/'):
            workflows.append(path)
            if upstream_owned:upstream_workflows.append(path)
    return {'protected_paths':sorted(protected),'workflow_changes':workflows,
            'upstream_workflow_changes':upstream_workflows}


def verify(dashboard_id,workdir):
    require(type(dashboard_id) is int and dashboard_id>0,'Dashboard ID')
    base=api('git/ref/heads/main')['object']['sha']
    require(os.environ['GITHUB_SHA']==base,'Verifier not from current main')
    d=api('actions/runs/'+str(dashboard_id))
    require(d['status']=='completed' and d['conclusion']=='success' and d['head_sha']==base and d['path']==DASHBOARD_PATH,'Dashboard provenance before download')
    require(api('actions/workflows/'+str(d['workflow_id']))['path']==DASHBOARD_PATH,'Dashboard workflow ID')
    da,dz=artifact(d,f'container-dashboard-{d["id"]}-{d["run_attempt"]}')
    result=json.loads(dz.read('evidence/result.json'))
    cid=result['candidate_run']['id'];require(type(cid) is int and cid>0,'Candidate ID')
    c=api('actions/runs/'+str(cid))
    require(api('actions/workflows/'+str(c['workflow_id']))['path']==CANDIDATE_PATH,'Candidate workflow ID')
    ca,cz=artifact(c,f'bridge-candidate-{c["id"]}-{c["run_attempt"]}')
    if set(cz.namelist())=={'no-change.json'}:
        require(result.get('state')=='no_change','Mismatched no-change artifact')
        r=json.loads(cz.read('no-change.json'))
        require(dz.read('e2e-input/original-receipt.json')==cz.read('no-change.json'),'Original no-change receipt')
        verify_no_change(c,d,ca,r,result,base)
        for ancestor in (r['upstream'],'2f542d949e5729586c6163d027d54c8931fd7cf6'):
            compare=api('compare/'+ancestor+'...'+base)
            require(compare['status'] in ('ahead','identical'),'No-change ancestry')
        require(api('git/ref/heads/main')['object']['sha']==base,'No-change stale base')
        return {'schema':3,'repository':REPO,'candidate':base,'base':base,'no_change':True,'candidate_run':identity(c),'candidate_artifact':{'id':ca['id'],'digest':ca['digest']},'dashboard_run':identity(d),'dashboard_artifact':{'id':da['id'],'digest':da['digest']},'evidence_verified':True},None
    binding=json.loads(dz.read('e2e-input/binding.json'))
    require(set(cz.namelist())=={'receipt.json','candidate.bundle'},'Candidate archive names')
    require(dz.read('e2e-input/original-receipt.json')==cz.read('receipt.json'),'Original receipt bytes')
    r=json.loads(cz.read('receipt.json'));bundle=cz.read('candidate.bundle')
    verify_bindings(c,d,ca,r,bundle,binding,result,base)
    workdir=pathlib.Path(workdir);workdir.mkdir(parents=True,exist_ok=False)
    bpath=workdir/'candidate.bundle';bpath.write_bytes(bundle)
    repo=workdir/'objects.git'
    subprocess.run(['git','clone','--bare','https://github.com/'+REPO+'.git',str(repo)],check=True,timeout=300)
    def git(*args):return subprocess.check_output(['git','-c','core.hooksPath=/dev/null','--git-dir='+str(repo),*args],timeout=120)
    git('bundle','verify',str(bpath));git('fetch',str(bpath),'HEAD')
    require(git('rev-parse','FETCH_HEAD').decode().strip()==r['candidate'],'Bundle head')
    parents=git('show','-s','--format=%P',r['candidate']).decode().split()
    require(parents, 'Candidate has no parents')
    verify_first_parent(base,r['candidate'],git)
    validate_candidate(base,base,r['candidate'],parents,first_parent_contains_base=True)
    for ancestor in (base,r['upstream']):git('merge-base','--is-ancestor',ancestor,r['candidate'])
    verify_official_upstream(r['upstream'],git)
    classification=classify_control_changes(base,r['candidate'],r['upstream'],git)
    tracked=git('ls-tree','-rz',r['candidate']).split(b'\0')
    require(result['tracked_files_verified']==len([x for x in tracked if x]),'Independent tree count')
    require(api('git/ref/heads/main')['object']['sha']==base,'Main moved')
    proof={'schema':3,'repository':REPO,'base':base,'candidate':r['candidate'],'upstream':r['upstream'],'parents':parents,'first_parent_contains_base':True,'candidate_run':identity(c),'candidate_artifact':{'id':ca['id'],'digest':ca['digest']},'dashboard_run':identity(d),'dashboard_artifact':{'id':da['id'],'digest':da['digest']},'bundle_sha256':r['bundle_sha256'],'receipt_sha256':hashlib.sha256(cz.read('receipt.json')).hexdigest(),**classification,'tracked_files_verified':result['tracked_files_verified'],'evidence_verified':True}
    return proof,repo
