"""External controller for actual Dashboard update in unprivileged container."""
import json,os,pathlib,subprocess,time,urllib.request,threading
from playwright.sync_api import sync_playwright
ROOT=pathlib.Path.cwd(); OUT=ROOT/'evidence';OUT.mkdir(exist_ok=True)
META=json.loads((ROOT/'e2e-input/binding.json').read_text())
NAME='bridge-e2e-'+os.environ['GITHUB_RUN_ID'];VOL=NAME+'-data';NET=NAME+'-net';IMAGE='bridge-e2e-toolchain:local'
def cmd(args,**kw):return subprocess.run(args,check=True,timeout=kw.pop('timeout',120),**kw)
def capture(args,**kw):return subprocess.check_output(args,text=True,timeout=kw.pop('timeout',30),**kw)
def logged(args,path,timeout):
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    def drain():
        with open(path,'wb') as f:
            remaining=2*1024*1024
            while True:
                chunk=process.stdout.read(8192)
                if not chunk:break
                f.write(chunk[:remaining]);remaining=max(0,remaining-len(chunk))
    thread=threading.Thread(target=drain,daemon=True);thread.start()
    try:
        code=process.wait(timeout=timeout);thread.join(timeout=10)
        if code:raise RuntimeError('Container installation failed: '+str(code))
    finally:
        if process.poll() is None:process.kill()

def main():
    assert os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted' and os.environ['GITHUB_REPOSITORY']=='Skimbee/hermes-agent'
    assert os.environ['GITHUB_REF']=='refs/heads/main'
    result={**META,'passed':False,'dashboard_run':{'repository':os.environ['GITHUB_REPOSITORY'],'id':int(os.environ['GITHUB_RUN_ID']),'attempt':int(os.environ['GITHUB_RUN_ATTEMPT']),'controller':os.environ['GITHUB_SHA'],'path':'.github/workflows/bridge-dashboard-e2e.yml','event':os.environ['GITHUB_EVENT_NAME']},'isolation':'nonroot-container-external-controller','publication_enabled':False}
    result['dashboard_run']=META['dashboard_identity']
    assert result['dashboard_run']['controller']==os.environ['GITHUB_SHA']
    assert result['dashboard_run']['id']==int(os.environ['GITHUB_RUN_ID'])
    started=False
    try:
        cmd(['docker','network','create','--subnet','172.30.220.0/24',NET])
        # Allow replies to external controller; deny candidate-initiated host access.
        cmd(['sudo','iptables','-I','INPUT','1','-s','172.30.220.0/24','-j','DROP'])
        cmd(['sudo','iptables','-I','INPUT','1','-s','172.30.220.0/24','-m','conntrack','--ctstate','ESTABLISHED,RELATED','-j','ACCEPT'])
        blocked=['0.0.0.0/8','10.0.0.0/8','100.64.0.0/10','127.0.0.0/8','169.254.0.0/16','172.16.0.0/12','192.0.0.0/24','192.168.0.0/16','198.18.0.0/15','224.0.0.0/4','240.0.0.0/4']
        for dest in blocked:cmd(['sudo','iptables','-I','DOCKER-USER','1','-s','172.30.220.0/24','-d',dest,'-j','REJECT'])
        cmd(['sudo','iptables','-I','DOCKER-USER','1','-s','172.30.220.0/24','-m','conntrack','--ctstate','ESTABLISHED,RELATED','-j','ACCEPT'])
        cmd(['docker','volume','create',VOL])
        cmd(['docker','create','--name',NAME,'--init','--user','10001:10001','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges:true','--pids-limit=512','--memory=5g','--cpus=2','--log-driver=local','--log-opt=max-size=2m','--log-opt=max-file=2','--network',NET,'--publish','127.0.0.1:19119:19120','--mount','type=volume,source='+VOL+',target=/work','--tmpfs=/tmp:rw,nosuid,nodev,size=512m,mode=1777',IMAGE])
        config=json.loads(capture(['docker','inspect',NAME]))[0]
        assert config['HostConfig']['ReadonlyRootfs'] and config['HostConfig']['CapDrop']==['ALL']
        assert not config['HostConfig']['Privileged'] and config['Config']['User']=='10001:10001'
        assert len(config['Mounts'])==1 and config['Mounts'][0]['Name']==VOL
        cmd(['docker','cp',str(ROOT/'e2e-input/fixture.git'),NAME+':/work/fixture.git'],timeout=240)
        cmd(['docker','start',NAME]);started=True
        # No candidate code has run yet. Probe actual outbound policy.
        probe="import socket; targets=['172.30.220.1','169.254.169.254','10.0.0.1'];\nfor t in targets:\n s=socket.socket();s.settimeout(2)\n try:s.connect((t,80));raise RuntimeError('Private destination accessible')\n except OSError:pass\n finally:s.close()\nprint('PRIVATE_EGRESS_BLOCKED')"
        cmd(['docker','exec',NAME,'python3','-I','-c',probe])
        setup='mkdir -p /work/home/.hermes && printf "memory:\\n  provider: none\\ncurator:\\n  enabled: false\\n" > /work/home/.hermes/config.yaml && git config --global --add safe.directory /work/fixture.git && git clone --bare --no-hardlinks /work/fixture.git /work/origin.git && git clone --no-hardlinks /work/origin.git /work/client && cd /work/client && git reset --hard '+META['pre_head']+' && uv sync --frozen --python 3.11 --extra web --extra hindsight && npm ci && npm run build --workspace web'
        logged(['docker','exec',NAME,'sh','-c',setup],OUT/'install-untrusted.log',1200)
        advertised=capture(['docker','exec','--workdir','/work/client',NAME,'env','GIT_CONFIG_GLOBAL=/dev/null','GIT_CONFIG_NOSYSTEM=1','git','ls-remote','origin','refs/heads/main'])
        assert advertised.split()[0]==META['candidate'], 'Origin unreachable under isolated Git configuration'
        cmd(['docker','exec','--detach','--workdir','/work/client',NAME,'sh','-c','exec /work/client/.venv/bin/python -m hermes_cli.main dashboard --host 127.0.0.1 --port 19119 --no-open --isolated --skip-build > /proc/1/fd/1 2>/proc/1/fd/2'])
        cmd(['docker','exec','--detach',NAME,'socat','TCP-LISTEN:19120,bind=0.0.0.0,reuseaddr,fork','TCP:127.0.0.1:19119'])
        url='http://127.0.0.1:19119/system';deadline=time.monotonic()+180
        while True:
            try:
                with urllib.request.urlopen(url,timeout=3) as r:assert r.status==200
                break
            except Exception:
                if time.monotonic()>deadline:raise RuntimeError('Dashboard readiness timeout')
                time.sleep(2)
        with sync_playwright() as p:
            executable=p.chromium.executable_path
            assert executable.startswith('/home/runner/.cache/ms-playwright/chromium-') and executable.endswith('/chrome-linux/chrome')
            # Chromium's documented narrow Ubuntu userns allowance: exact
            # trusted browser path, never a global AppArmor/sysctl disable.
            profile=OUT/'browser-userns.profile'
            profile.write_text('abi <abi/4.0>,\ninclude <tunables/global>\nprofile bridge-browser '+executable+' flags=(unconfined) {\n  userns,\n}\n')
            cmd(['sudo','apparmor_parser','-r',str(profile)])
            browser=p.chromium.launch(headless=True,executable_path=executable,chromium_sandbox=True)
            result['browser_version']=browser.version
            result['browser_sandbox_requested']=True
            sandbox_page=browser.new_page()
            sandbox_page.goto('chrome://sandbox')
            sandbox_text=' '.join(sandbox_page.locator('body').inner_text().split())
            assert 'PID namespaces Yes' in sandbox_text and 'Seccomp-BPF sandbox Yes' in sandbox_text, sandbox_text
            result['browser_sandbox_status']=sandbox_text
            sandbox_page.close()
            context=browser.new_context(service_workers='block',accept_downloads=False)
            context.route('**/*',lambda route:route.continue_() if route.request.url.startswith('http://127.0.0.1:19119/') else route.abort())
            context.route_web_socket('**/*',lambda ws:ws.connect_to_server() if ws.url.startswith('ws://127.0.0.1:19119/') else ws.close())
            page=context.new_page();page.goto(url,wait_until='domcontentloaded')
            with page.expect_response(lambda r:'/api/hermes/update/check' in r.url,timeout=90000) as checked:
                page.get_by_role('button',name='Check for updates',exact=True).click(timeout=90000)
            update_info=checked.value.json()
            result['update_check']={k:v for k,v in update_info.items() if k in ('available','update_available','error','message','reason','managed_externally','install_method','current_sha','latest_sha','behind','ahead')}
            result['system_page_text']=page.locator('body').inner_text()[-6000:]
            page.get_by_role('button',name='Update now',exact=True).click(timeout=90000)
            with page.expect_response(lambda r:r.request.method=='POST' and r.url.endswith('/api/hermes/update'),timeout=60000) as response:
                page.get_by_role('button',name='Update now',exact=True).last.click()
            assert response.value.ok;result['post_accepted']=True
            deadline=time.monotonic()+900;receipt=None
            while time.monotonic()<deadline:
                try:
                    page.goto(url,wait_until='domcontentloaded',timeout=10000)
                    data=page.evaluate("""async()=>{const r=await fetch('/api/hermes/update/receipt',{headers:{'X-Hermes-Session-Token':window.__HERMES_SESSION_TOKEN__}});if(!r.ok)return null;const t=await r.text();if(t.length>131072)throw Error('receipt size');return JSON.parse(t)}""")
                    summary=(data or {}).get('summary') or {}
                    if summary.get('finished_at'):receipt=summary;break
                except Exception:pass
                time.sleep(5)
            assert receipt is not None,'No final receipt'
            result['observed_receipt']={k:receipt.get(k) for k in ('pre_sha','post_sha','outcome')}
            assert receipt['pre_sha']==META['pre_head'] and receipt['post_sha']==META['candidate'] and receipt['outcome']=='success'
            page.get_by_role('button',name='Check for updates',exact=True).wait_for(timeout=60000)
            result['reconnected']=True
            result['observed_receipt']={k:receipt[k] for k in ('pre_sha','post_sha','outcome')}
            browser.close()
        cmd(['docker','stop','--time','10',NAME]);started=False
        assert not json.loads(capture(['docker','inspect','--format','{{json .State}}',NAME]))['Running']
        payload=json.dumps({'candidate':META['candidate'],'manifest':json.loads((ROOT/'e2e-input/manifest.json').read_text())})
        inspection=capture(['docker','run','--rm','--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges:true','--user','10001:10001','--pids-limit=32','--memory=256m','--mount','type=volume,source='+VOL+',target=/snapshot,readonly','--interactive',IMAGE,'python3','-I','-c',(ROOT/'scripts/bridge/container-e2e/inspect_snapshot.py').read_text()],input=payload,timeout=180)
        result.update(json.loads(inspection));result['passed']=True
    finally:
        if started:subprocess.run(['docker','stop','--time','10',NAME],timeout=30,capture_output=True)
        logs=subprocess.run(['docker','logs','--tail','80',NAME],capture_output=True,text=True,timeout=15)
        import re
        diagnostic=re.sub(r'(?im)^.*(?:token|password|secret|api.key|authorization).*$', '[REDACTED]',(logs.stdout+logs.stderr)[-20000:])
        (OUT/'dashboard-diagnostic.txt').write_text(diagnostic)
        (OUT/'result.json').write_text(json.dumps(result,indent=2))
        # Do not upload raw candidate logs or tokens as trusted evidence.
        if (OUT/'install-untrusted.log').exists():
            text=(OUT/'install-untrusted.log').read_text(errors='replace')[-16000:]
            import re
            text=re.sub(r'(?im)^.*(?:token|password|secret|api.key|authorization).*$','[REDACTED]',text)
            (OUT/'install-diagnostic.txt').write_text(text)
        print(json.dumps({'passed':result['passed'],'candidate':META['candidate'],'publication_enabled':False}))
if __name__=='__main__':main()
