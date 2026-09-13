"""Real browser update on disposable GitHub-hosted VM only. No API mocking."""
import json, os, pathlib, subprocess, time, urllib.request
from playwright.sync_api import sync_playwright

root=pathlib.Path.cwd()
assert os.environ.get('GITHUB_ACTIONS')=='true', 'Run only on disposable GitHub runner'
assert os.environ.get('RUNNER_ENVIRONMENT')=='github-hosted', 'No self-hosted execution'
client=root/'client'; home=root/'sandbox-home'; home.mkdir()
state=home/'.hermes'; state.mkdir()
evidence=root/'evidence'; evidence.mkdir(exist_ok=True)
(state/'config.yaml').write_text('memory:\n  provider: none\ncurator:\n  enabled: false\n')
env={k:os.environ[k] for k in ('PATH','LANG','LC_ALL','SSL_CERT_FILE') if k in os.environ}
env.update(HOME=str(home),HERMES_HOME=str(state),XDG_CONFIG_HOME=str(home/'config'),XDG_CACHE_HOME=str(home/'cache'),HERMES_NONINTERACTIVE='1')
env['PATH']=str(client/'.venv/bin')+':'+env['PATH']
base='d131988d53c3b8389801f6cee03b990bd51ac49a'
target=json.loads((root/'input/receipt.json').read_text())['candidate']
def head():
    return subprocess.check_output(['git','-C',str(client),'rev-parse','HEAD'],text=True).strip()
assert head()==base
log=open(evidence/'dashboard.log','w')
# A standalone scope prevents the updater from attributing this manually
# launched Dashboard to the enclosing hosted-compute-agent.service.
import pwd
user=pwd.getpwuid(os.getuid()).pw_name
command=['sudo','systemd-run','--scope','--unit=bridge-dashboard-e2e','--',
         '/usr/sbin/runuser','-u',user,'--','env','-i',
         *[f'{k}={v}' for k,v in env.items()],
         str(client/'.venv/bin/python'),'-m','hermes_cli.main','dashboard',
         '--host','127.0.0.1','--port','19119','--no-open','--isolated','--skip-build']
server=subprocess.Popen(command,cwd=client,env=env,stdout=log,stderr=subprocess.STDOUT)
url='http://127.0.0.1:19119/system'
result={'base':base,'target':target,'passed':False}
try:
    deadline=time.monotonic()+150
    while True:
        try:
            with urllib.request.urlopen(url,timeout=3) as r: assert r.status==200
            break
        except Exception:
            if time.monotonic()>deadline: raise RuntimeError('Dashboard readiness timeout')
            time.sleep(2)
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page()
        page.goto(url,wait_until='domcontentloaded')
        page.get_by_role('button',name='Check for updates',exact=True).click(timeout=90000)
        page.get_by_role('button',name='Update now',exact=True).click(timeout=90000)
        with page.expect_response(lambda r: r.request.method=='POST' and r.url.endswith('/api/hermes/update'),timeout=60000) as response:
            page.get_by_role('button',name='Update now',exact=True).last.click()
        assert response.value.ok, 'Update POST rejected'
        result['post_accepted']=True
        deadline=time.monotonic()+600
        receipt=None
        while time.monotonic()<deadline:
            try:
                page.goto(url,wait_until='domcontentloaded',timeout=10000)
                data=page.evaluate("""async () => { const r=await fetch('/api/hermes/update/receipt',{headers:{'X-Hermes-Session-Token':window.__HERMES_SESSION_TOKEN__}}); return r.ok ? await r.json() : null; }""")
                result['receipt_http_status']=page.evaluate("""async () => (await fetch('/api/hermes/update/receipt',{headers:{'X-Hermes-Session-Token':window.__HERMES_SESSION_TOKEN__}})).status""")
                if data:
                    summary=data.get('summary') or {}
                    result['receipt_summary']=summary
                    if summary.get('finished_at'):
                        receipt=summary; break
            except Exception as exc:
                result['last_poll_error']=type(exc).__name__
            time.sleep(5)
        assert receipt is not None, 'No final receipt'
        assert receipt['post_sha']==target, receipt
        assert receipt['pre_sha']==base, receipt
        assert receipt['outcome']=='success', receipt
        assert head()==target, 'Git HEAD mismatch'
        page.get_by_role('button',name='Check for updates',exact=True).wait_for(timeout=60000)
        page.screenshot(path=str(evidence/'dashboard-after.png'))
        result.update(passed=True,post_head=head(),reconnected=True)
        browser.close()
finally:
    result['final_head']=head()
    result['initial_process_returncode']=server.poll()
    import re
    for f in (state/'logs').glob('*.log'):
        if 'update' in f.name:
            text=f.read_text(errors='replace')[-100000:]
            text=re.sub(r'(?im)^.*(?:token|password|secret|api.key).*$','[REDACTED]',text)
            (evidence/f.name).write_text(text)
    receipts=[]
    for f in (state/'logs/update_receipts').glob('*.json'):
        try:
            r=json.loads(f.read_text())
            receipts.append({k:r.get(k) for k in ('outcome','finished_at','pre_update','post_update','exit_code')})
        except (ValueError,OSError): pass
    result['local_receipts']=receipts
    (evidence/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    if server.poll() is None: server.terminate()
    log.close()
