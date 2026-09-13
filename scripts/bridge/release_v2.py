"""Trusted release orchestration. No candidate checkout, merge or execution."""
import argparse,base64,json,os,pathlib,subprocess,tempfile
from release_policy import require,sha,validate_candidate,validate_check,owner_approved,CHECK,APP_ID
from release_evidence import REPO,api,artifact,canonical_hash,verify
WORKFLOW='.github/workflows/bridge-release.yml'
BOT='skimbee-hermes-bridge[bot]'

def run_context():
    require(os.environ['GITHUB_REPOSITORY']==REPO and os.environ['GITHUB_REF']=='refs/heads/main','Trusted main only')
    rid=int(os.environ['GITHUB_RUN_ID']);attempt=int(os.environ['GITHUB_RUN_ATTEMPT'])
    run=api('actions/runs/'+str(rid))
    require(run['path']==WORKFLOW and run['head_sha']==os.environ['GITHUB_SHA'] and run['head_branch']=='main' and run['run_attempt']==attempt,'Release runtime identity')
    require(api('actions/workflows/'+str(run['workflow_id']))['path']==WORKFLOW,'Release workflow ID')
    return run

def completed_job(run,name):
    listing=api(f'actions/runs/{run["id"]}/attempts/{run["run_attempt"]}/jobs?per_page=100')
    require(listing['total_count']==len(listing['jobs']) and listing['total_count']<100,'Job pagination')
    jobs=[j for j in listing['jobs'] if j['name']==name]
    require(len(jobs)==1 and jobs[0]['status']=='completed' and jobs[0]['conclusion']=='success','Missing completed trusted job: '+name)

def source_proof(run):
    completed_job(run,'verify')
    a,z=artifact(run,f'bridge-proof-{run["id"]}-{run["run_attempt"]}')
    require(set(z.namelist())=={'proof.json'},'Proof archive')
    document=json.loads(z.read('proof.json'))
    require(document['release_run']==run['id'] and document['release_attempt']==run['run_attempt'] and document['controller']==run['head_sha'],'Proof runtime')
    require(document['proof_sha256']==canonical_hash(document['proof']),'Proof hash')
    return document,a

def exact_pr(proof):
    branch='bridge/candidate/'+sha(proof['candidate'])
    prs=api('pulls?state=open&base=main&head=Skimbee:'+branch+'&per_page=100')
    require(len(prs)==1,'Missing or ambiguous exact-candidate PR')
    pr=api('pulls/'+str(prs[0]['number']))
    require(pr['state']=='open' and pr['draft'] is False and pr['base']['ref']=='main' and pr['base']['repo']['full_name']==REPO,'PR state/base')
    require(pr['head']['ref']==branch and pr['head']['sha']==proof['candidate'] and pr['head']['repo']['full_name']==REPO,'PR head')
    require(pr['user']['type']=='Bot' and pr['user']['login']==BOT,'PR author')
    return pr

def check_identity(run,document,proof_artifact):
    external=f'bridge-v2:{run["id"]}:{run["run_attempt"]}:{proof_artifact["id"]}:{document["proof_sha256"]}'
    return external,'https://github.com/'+REPO+'/actions/runs/'+str(run['id'])

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['verify','stage','attest','publish']);p.add_argument('--dashboard-run',type=int);args=p.parse_args()
    run=run_context()
    if args.mode=='verify':
        require(args.dashboard_run is not None,'Dashboard run required')
        with tempfile.TemporaryDirectory(prefix='bridge-verify-',dir=os.environ['RUNNER_TEMP']) as temp:
            proof,_=verify(args.dashboard_run,pathlib.Path(temp)/'verified')
        document={'release_run':run['id'],'release_attempt':run['run_attempt'],'controller':run['head_sha'],'proof':proof,'proof_sha256':canonical_hash(proof)}
        pathlib.Path('proof.json').write_text(json.dumps(document,indent=2))
        with open(os.environ['GITHUB_OUTPUT'],'a') as out:out.write('publishable='+('false' if proof.get('no_change') else 'true')+'\n')
        print('NO_CHANGE_VERIFIED' if proof.get('no_change') else 'EVIDENCE_VERIFIED',proof['candidate']);return
    document,proof_artifact=source_proof(run);proof=document['proof']
    require(proof.get('no_change') is not True,'No-change proof cannot authorize publication')
    with tempfile.TemporaryDirectory(prefix='bridge-release-',dir=os.environ['RUNNER_TEMP']) as temp:
        fresh,repo=verify(proof['dashboard_run']['id'],pathlib.Path(temp)/'verified')
        require(fresh==proof,'Evidence changed since verifier job')
        require(api('branches/main')['protected'] is True,'Branch protection absent')
        validate_candidate(proof['base'],api('git/ref/heads/main')['object']['sha'],proof['candidate'],proof['parents'],first_parent_contains_base=proof['first_parent_contains_base'])
        branch='bridge/candidate/'+proof['candidate']
        if args.mode=='stage':
            refs=api('git/matching-refs/heads/'+branch)
            require(len(refs)<=1,'Ambiguous candidate ref')
            if refs:
                require(refs[0]['ref']=='refs/heads/'+branch and refs[0]['object']['sha']==proof['candidate'],'Existing branch differs')
            else:
                workflow_changes=[p for p in proof['protected_paths'] if p.startswith('.github/workflows/')]
                require(not workflow_changes,'MANUAL_WORKFLOW_BRANCH_UPLOAD_REQUIRED: App has deliberately no Workflows write permission. Upload the verified bundle to '+branch+' using the authorized owner path; main stays unchanged.')
                env=os.environ.copy()
                env.update({'GIT_CONFIG_COUNT':'3','GIT_CONFIG_KEY_0':'http.https://github.com/.extraheader','GIT_CONFIG_VALUE_0':'AUTHORIZATION: basic '+base64.b64encode(('x-access-token:'+os.environ['APP_TOKEN']).encode()).decode(),'GIT_CONFIG_KEY_1':'core.hooksPath','GIT_CONFIG_VALUE_1':'/dev/null','GIT_CONFIG_KEY_2':'credential.helper','GIT_CONFIG_VALUE_2':''})
                subprocess.run(['git','--git-dir='+str(repo),'push','https://github.com/'+REPO+'.git',proof['candidate']+':refs/heads/'+branch],env=env,check=True,timeout=180)
            require(api('git/ref/heads/'+branch)['object']['sha']==proof['candidate'],'Candidate branch readback')
            prs=api('pulls?state=open&base=main&head=Skimbee:'+branch+'&per_page=100')
            if not prs:
                api('pulls','POST',{'head':branch,'base':'main','title':'Bridge: verified candidate '+proof['candidate'][:12],'body':'Exact tested candidate: `'+proof['candidate']+'`.\n\nProtected paths: '+json.dumps(proof['protected_paths'])+'\n\nReview this exact head when requested. Do not use a merge mode that changes its SHA. Evidence: https://github.com/'+REPO+'/actions/runs/'+str(run['id']),'draft':False,'maintainer_can_modify':False},app=True)
            pr=exact_pr(proof);print('EXACT_CANDIDATE_PR',pr['html_url']);return
        completed_job(run,'stage');pr=exact_pr(proof)
        external,url=check_identity(run,document,proof_artifact)
        if args.mode=='attest':
            check=api('check-runs','POST',{'name':CHECK,'head_sha':proof['candidate'],'status':'completed','conclusion':'success','external_id':external,'details_url':url,'output':{'title':'Exact candidate evidence verified','summary':'Completed candidate + isolated Dashboard runs; archive digests, original bindings and tracked snapshot independently verified. Owner review remains mandatory for protected paths. Proof artifact '+str(proof_artifact['id'])+'.'}},app=True)
            validate_check(api('check-runs/'+str(check['id'])),proof['candidate'],external,url)
            print('EXACT_APP_CHECK',check['id']);return
        require(os.environ.get('BRIDGE_RELEASE_ENABLED')=='true','Publication not enabled')
        completed_job(run,'attest')
        reviews=api('pulls/'+str(pr['number'])+'/reviews?per_page=100');require(len(reviews)<100,'Review pagination')
        if proof['protected_paths'] and not owner_approved(reviews,proof['candidate']):
            pathlib.Path('publication.json').write_text(json.dumps({'exact_sha_published':False,'state':'waiting_owner_review','candidate':proof['candidate'],'pr':pr['number']},indent=2))
            print('WAITING_FOR_EXACT_HEAD_OWNER_REVIEW',pr['html_url']);return
        all_checks=api('commits/'+proof['candidate']+'/check-runs?filter=latest&per_page=100')
        require(all_checks['total_count']<100,'Check pagination')
        checks=[c for c in all_checks['check_runs'] if c['name']==CHECK and c['app']['id']==APP_ID]
        require(len(checks)==1,'Check count');validate_check(checks[0],proof['candidate'],external,url)
        require(api('git/ref/heads/main')['object']['sha']==proof['base'],'Main moved before publication')
        exact_pr(proof)
        api('git/refs/heads/main','PATCH',{'sha':proof['candidate'],'force':False},app=True)
        require(api('git/ref/heads/main')['object']['sha']==proof['candidate'],'Publication readback mismatch')
        require(api('branches/main')['protected'] is True,'Protection readback absent')
        pathlib.Path('publication.json').write_text(json.dumps({'candidate':proof['candidate'],'base':proof['base'],'proof_artifact_id':proof_artifact['id'],'proof_artifact_digest':proof_artifact['digest'],'proof_sha256':document['proof_sha256'],'release_run':run['id'],'release_attempt':run['run_attempt'],'check_id':checks[0]['id'],'pr':pr['number'],'exact_sha_published':True},indent=2))
        print('EXACT_SHA_PUBLISHED',proof['candidate'])
if __name__=='__main__':main()
