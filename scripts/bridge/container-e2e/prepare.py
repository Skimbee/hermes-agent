"""Authenticated input preparation; no candidate execution, no credentials persisted."""
import hashlib,io,json,os,pathlib,re,subprocess,zipfile
ROOT=pathlib.Path.cwd(); INPUT=ROOT/'e2e-input';INPUT.mkdir()
REPO='Skimbee/hermes-agent'
def api(path):return json.loads(subprocess.check_output(['gh','api','repos/'+REPO+'/'+path]))
def git(*a):return subprocess.check_output(['git',*a],text=True).strip()
def main():
    rid=os.environ['CANDIDATE_RUN'];assert re.fullmatch('[1-9][0-9]*',rid)
    run=api('actions/runs/'+rid)
    assert run['status']=='completed' and run['conclusion']=='success'
    assert run['repository']['full_name']==REPO and run['path']=='.github/workflows/bridge-hourly-pilot.yml'
    assert run['event'] in ('workflow_dispatch','schedule')
    raw=api('actions/runs/'+rid+'/artifacts?per_page=100');assert raw['total_count']<100
    rows=[a for a in raw['artifacts'] if a['name']==f'bridge-candidate-{rid}-{run["run_attempt"]}' and not a['expired']]
    assert len(rows)==1
    a=rows[0];assert a['size_in_bytes']<25*1024*1024
    archive=subprocess.check_output(['gh','api',f'repos/{REPO}/actions/artifacts/{a["id"]}/zip'])
    assert 'sha256:'+hashlib.sha256(archive).hexdigest()==a['digest']
    z=zipfile.ZipFile(io.BytesIO(archive))
    if z.namelist()==['no-change.json']:
        assert sum(i.file_size for i in z.infolist())<131072
        import sys
        sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
        from release_evidence import identity
        receipt=json.loads(z.read('no-change.json'))
        assert receipt['schema']==1 and receipt['kind']=='no-change'
        assert receipt['base']==receipt['candidate']==receipt['workflow_sha']==run['head_sha']==api('git/ref/heads/main')['object']['sha']
        assert receipt['run_id']==rid and receipt['run_attempt']==str(run['run_attempt']) and run['head_branch']=='main'
        dashboard=api('actions/runs/'+os.environ['GITHUB_RUN_ID'])
        assert dashboard['head_sha']==os.environ['GITHUB_SHA'] and dashboard['run_attempt']==int(os.environ['GITHUB_RUN_ATTEMPT'])
        result={'schema':3,'state':'no_change','candidate_run':{**identity(run),'status':'completed','conclusion':'success'},'candidate_artifact':{'id':a['id'],'run_id':run['id'],'digest':a['digest'],'expired':False},'dashboard_identity':identity(dashboard)}
        (ROOT/'evidence').mkdir(exist_ok=True)
        (ROOT/'evidence/result.json').write_text(json.dumps(result,indent=2))
        (INPUT/'original-receipt.json').write_bytes(z.read('no-change.json'))
        with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('no_change=true\n')
        print('NO_UPDATE_CANDIDATE');return
    assert sorted(z.namelist())==['candidate.bundle','receipt.json']
    with open(os.environ['GITHUB_OUTPUT'],'a') as f:f.write('no_change=false\n')
    assert sum(i.file_size for i in z.infolist())<25*1024*1024
    receipt=json.loads(z.read('receipt.json'));bundle=z.read('candidate.bundle')
    assert receipt['run_id']==rid and str(receipt['run_attempt'])==str(run['run_attempt'])
    assert receipt['workflow_sha']==run['head_sha']==receipt['base']
    assert api('git/ref/heads/main')['object']['sha']==receipt['base']
    assert re.fullmatch('[0-9a-f]{40}',receipt['candidate'])
    assert hashlib.sha256(bundle).hexdigest()==receipt['bundle_sha256']
    (INPUT/'candidate.bundle').write_bytes(bundle)
    (INPUT/'original-receipt.json').write_bytes(z.read('receipt.json'))
    subprocess.run(['git','clone','--bare','https://github.com/'+REPO+'.git',str(INPUT/'fixture.git')],check=True)
    git('--git-dir='+str(INPUT/'fixture.git'),'bundle','verify',str(INPUT/'candidate.bundle'))
    git('--git-dir='+str(INPUT/'fixture.git'),'fetch',str(INPUT/'candidate.bundle'),'HEAD')
    assert git('--git-dir='+str(INPUT/'fixture.git'),'rev-parse','FETCH_HEAD')==receipt['candidate']
    for ancestor in (receipt['base'],receipt['upstream']):
        subprocess.run(['git','--git-dir='+str(INPUT/'fixture.git'),'merge-base','--is-ancestor',ancestor,receipt['candidate']],check=True)
    base='d131988d53c3b8389801f6cee03b990bd51ac49a'
    git('--git-dir='+str(INPUT/'fixture.git'),'update-ref','refs/heads/main',receipt['candidate'])
    git('--git-dir='+str(INPUT/'fixture.git'),'symbolic-ref','HEAD','refs/heads/main')
    manifest=[]
    output=subprocess.check_output(['git','--git-dir='+str(INPUT/'fixture.git'),'ls-tree','-rz',receipt['candidate']])
    for row in output.split(b'\0'):
        if not row:continue
        attrs,path=row.split(b'\t',1);mode,kind,oid=attrs.decode().split()
        assert kind=='blob', 'Submodule requires explicit inspection'
        name=path.decode('utf-8');assert not name.startswith('/') and '..' not in name.split('/')
        manifest.append({'path':name,'mode':mode,'oid':oid})
    attributes=subprocess.check_output(['git','--git-dir='+str(INPUT/'fixture.git'),'check-attr','--source='+receipt['candidate'],'-z','--stdin','eol','filter','working-tree-encoding'],input=b''.join(e['path'].encode()+b'\0' for e in manifest)).split(b'\0')
    assert attributes[-1]==b'' and (len(attributes)-1)%3==0
    attrs={}
    for i in range(0,len(attributes)-1,3):
        path,key,value=(v.decode() for v in attributes[i:i+3]);attrs.setdefault(path,{})[key]=value
    for entry in manifest:
        values=attrs[entry['path']]
        assert values['filter'] in ('unspecified','unset'), 'External Git filter not permitted'
        assert values['working-tree-encoding'] in ('unspecified','unset'), 'Encoding requires explicit inspector support'
        assert values['eol'] in ('unspecified','unset','lf','crlf')
        entry['eol']=values['eol']
    (INPUT/'manifest.json').write_text(json.dumps(manifest))
    meta={'schema':2,'candidate_run':{'repository':REPO,'id':run['id'],'attempt':run['run_attempt'],'workflow_id':run['workflow_id'],'path':run['path'],'controller':run['head_sha'],'status':run['status'],'conclusion':run['conclusion'],'event':run['event']},'candidate_artifact':{'id':a['id'],'run_id':run['id'],'digest':a['digest'],'expired':a['expired']},'candidate':receipt['candidate'],'bundle_sha256':receipt['bundle_sha256'],'pre_head':base,'publication_enabled':False}
    dashboard=json.loads(subprocess.check_output(['gh','api','repos/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID']]))
    assert dashboard['head_sha']==os.environ['GITHUB_SHA'] and dashboard['run_attempt']==int(os.environ['GITHUB_RUN_ATTEMPT'])
    meta['dashboard_identity']={'repository':os.environ['GITHUB_REPOSITORY'],'id':dashboard['id'],'attempt':dashboard['run_attempt'],'workflow_id':dashboard['workflow_id'],'path':dashboard['path'],'controller':dashboard['head_sha'],'event':dashboard['event']}
    (INPUT/'binding.json').write_text(json.dumps(meta,indent=2))
    print('VERIFIED_INPUT',run['id'],a['id'],receipt['candidate'])
if __name__=='__main__':main()
