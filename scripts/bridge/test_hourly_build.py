"""Run the real hourly build shell against disposable local Git fixtures."""
import json,os,pathlib,re,shlex,subprocess,tempfile,textwrap,unittest
ROOT=pathlib.Path(__file__).resolve().parents[2]

class HourlyBuildTests(unittest.TestCase):
    def build(self,changed):
        yaml=(ROOT/'.github/workflows/bridge-hourly-pilot.yml').read_text()
        segment=yaml.split('      - name: Build isolated candidate without credentials\n',1)[1].split('      - name:',1)[0]
        shell=textwrap.dedent(segment.split('        run: |\n',1)[1])
        with tempfile.TemporaryDirectory() as directory:
            t=pathlib.Path(directory);source=t/'source';source.mkdir();work=t/'work';work.mkdir()
            def git(*args):return subprocess.check_output(['git','-C',str(source),*args],stderr=subprocess.PIPE,text=True).strip()
            git('init','-b','main');git('config','user.name','Synthetic test');git('config','user.email','synthetic@example.invalid')
            (source/'fixture.txt').write_text('synthetic base\n');git('add','.');git('commit','-m','synthetic base');base=git('rev-parse','HEAD')
            if changed:
                (source/'fixture.txt').write_text('synthetic update\n');git('commit','-am','synthetic update')
            shell=shell.replace('https://github.com/Skimbee/hermes-agent.git',shlex.quote(str(source))).replace('https://github.com/NousResearch/hermes-agent.git',shlex.quote(str(source))).replace('2f542d949e5729586c6163d027d54c8931fd7cf6',base)
            env={**os.environ,'GITHUB_SHA':base,'GITHUB_RUN_ID':'101','GITHUB_RUN_ATTEMPT':'1','GITHUB_OUTPUT':str(t/'outputs'),'GITHUB_STEP_SUMMARY':str(t/'summary')}
            run=subprocess.run(['bash','-e','-u','-o','pipefail'],input=shell,text=True,cwd=work,env=env,capture_output=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stderr)
            self.assertEqual((t/'outputs').read_text(),'has_candidate='+('true' if changed else 'false')+'\n')
            receipt=work/'evidence/no-change.json'
            self.assertEqual(receipt.exists(),not changed)
            if not changed:
                r=json.loads(receipt.read_text());self.assertEqual(r['kind'],'no-change');self.assertEqual(r['candidate'],base);self.assertEqual(r['run_id'],'101')
    def test_no_change_produces_original_receipt(self):self.build(False)
    def test_change_keeps_candidate_path(self):self.build(True)
if __name__=='__main__':unittest.main()
