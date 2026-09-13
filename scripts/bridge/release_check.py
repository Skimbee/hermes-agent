"""Independent GitHub evidence gate. Read-only; never executes candidate code."""
import hashlib, io, json, os, pathlib, re, subprocess, zipfile
REPO='Skimbee/hermes-agent'

def api(path):
    return json.loads(subprocess.check_output(['gh','api',f'repos/{REPO}/{path}']))
def git(*args):
    return subprocess.check_output(['git',*args],text=True).strip()
def artifact(run, name):
    rows=api(f'actions/runs/{run["id"]}/artifacts?per_page=100')['artifacts']
    rows=[a for a in rows if a['name']==name and not a['expired']]
    assert len(rows)==1, 'Missing or ambiguous artifact'
    a=rows[0]
    assert a['size_in_bytes']<25*1024*1024, 'Artifact too large'
    data=subprocess.check_output(['gh','api',f'repos/{REPO}/actions/artifacts/{a["id"]}/zip'])
    assert 'sha256:'+hashlib.sha256(data).hexdigest()==a['digest'], 'Artifact digest mismatch'
    z=zipfile.ZipFile(io.BytesIO(data))
    assert sum(i.file_size for i in z.infolist())<25*1024*1024, 'Archive expansion limit'
    return z

def main():
    run_id=os.environ['CANDIDATE_RUN']
    assert re.fullmatch('[0-9]+',run_id), 'Invalid run ID'
    run=api(f'actions/runs/{run_id}')
    assert run['repository']['full_name']==REPO
    assert run['path']=='.github/workflows/bridge-hourly-pilot.yml'
    assert run['status']=='completed' and run['conclusion']=='success'
    assert run['event'] in ('schedule','workflow_dispatch')
    z=artifact(run,f'bridge-candidate-{run_id}-{run["run_attempt"]}')
    assert set(z.namelist())=={'candidate.bundle','receipt.json'}
    r=json.loads(z.read('receipt.json'))
    assert r['run_id']==run_id and int(r['run_attempt'])==run['run_attempt']
    assert r['workflow_sha']==run['head_sha']==r['base']
    main_sha=api('git/ref/heads/main')['object']['sha']
    assert main_sha==r['base'], 'Stale candidate base: rerun hourly integration'
    bundle=z.read('candidate.bundle')
    assert hashlib.sha256(bundle).hexdigest()==r['bundle_sha256']
    p=pathlib.Path(os.environ['RUNNER_TEMP'])/'verified-candidate.bundle'; p.write_bytes(bundle)
    subprocess.run(['git','bundle','verify',str(p)],check=True)
    subprocess.run(['git','fetch',str(p),'HEAD'],check=True)
    assert git('rev-parse','FETCH_HEAD')==r['candidate']
    for ancestor in (r['base'],r['upstream']):
        subprocess.run(['git','merge-base','--is-ancestor',ancestor,r['candidate']],check=True)
    approved=json.loads(pathlib.Path('scripts/bridge/approved-controls.json').read_text())
    blocked=[]
    for path in git('diff','--name-only',r['base'],r['candidate']).splitlines():
        if path.startswith(('.github/','scripts/')):
            blob=subprocess.run(['git','rev-parse',f'{r["candidate"]}:{path}'],capture_output=True,text=True)
            value=blob.stdout.strip() if blob.returncode==0 else 'DELETED'
            if approved.get(path)!=value: blocked.append(path)
    assert not blocked, f'Unreviewed control changes: {blocked}'
    e2e=None
    runs=api('actions/workflows/bridge-dashboard-e2e.yml/runs?status=success&per_page=30')['workflow_runs']
    for candidate in runs:
        if candidate['event']!='workflow_dispatch' or candidate['head_sha']!=main_sha:
            continue
        ez=artifact(candidate,f'dashboard-e2e-{candidate["id"]}')
        if 'result.json' not in ez.namelist(): continue
        result=json.loads(ez.read('result.json'))
        if result.get('passed') is True and result.get('target')==r['candidate'] and result.get('post_head')==r['candidate'] and result.get('reconnected') is True:
            e2e=candidate['id']; break
    assert e2e, 'No successful exact-candidate Dashboard E2E on current controller'
    assert api('git/ref/heads/main')['object']['sha']==main_sha, 'Main changed during verification'
    pathlib.Path('gate-result.json').write_text(json.dumps(dict(candidate=r['candidate'],base=main_sha,run_id=run_id,dashboard_run=e2e,evidence_verified=True,publication_enabled=False),indent=2)+'\n')
    print('EVIDENCE_VERIFIED_NOT_PUBLISHED',r['candidate'])

if __name__=='__main__': main()
