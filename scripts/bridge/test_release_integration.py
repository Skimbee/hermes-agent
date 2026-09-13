"""Contract integration tests with a stateful synthetic GitHub boundary.
No live writes; real release orchestration and policy run unchanged.
"""
import contextlib,copy,json,os,pathlib,tempfile,unittest
from unittest.mock import patch
import release_v2 as m

class ReleaseIntegrationTests(unittest.TestCase):
    def exercise(self,mode='publish',protected=False,approved=False,wrong_check=False,moved=False,proof_changed=False,enabled=True):
        run={'id':44,'run_attempt':1,'head_sha':'a'*40}
        proof={'schema':3,'base':'a'*40,'candidate':'b'*40,'parents':['a'*40],'first_parent_contains_base':True,'dashboard_run':{'id':22},'protected_paths':['scripts/x.py'] if protected else []}
        document={'proof':proof,'proof_sha256':m.canonical_hash(proof)};artifact={'id':55,'digest':'sha256:'+'c'*64}
        fresh=copy.deepcopy(proof)
        if proof_changed:fresh['candidate']='f'*40
        state={'head':'d'*40 if moved else 'a'*40,'writes':[]}
        branch='bridge/candidate/'+'b'*40
        pr={'number':7,'state':'open','draft':False,'base':{'ref':'main','repo':{'full_name':m.REPO}},'head':{'ref':branch,'sha':'b'*40,'repo':{'full_name':m.REPO}},'user':{'type':'Bot','login':m.BOT},'html_url':'https://github.com/'+m.REPO+'/pull/7'}
        external,url=m.check_identity(run,document,artifact)
        check={'id':66,'name':m.CHECK,'head_sha':'b'*40,'app':{'id':15368 if wrong_check else m.APP_ID},'status':'completed','conclusion':'success','external_id':external,'details_url':url}
        def api(path,method='GET',data=None,app=False,raw=False):
            if method!='GET':
                self.assertTrue(app,'Writes must use dedicated App channel')
                state['writes'].append((path,method,data))
                if path=='git/refs/heads/main':
                    self.assertEqual(data,{'sha':'b'*40,'force':False});state['head']=data['sha'];return {'object':{'sha':state['head']}}
                if path=='check-runs':return check
                self.fail('Unexpected synthetic API write '+path)
            if path=='git/ref/heads/main':return {'object':{'sha':state['head']}}
            if path=='branches/main':return {'protected':True}
            if path.startswith('pulls?'):return [pr]
            if path=='pulls/7':return pr
            if path.startswith('pulls/7/reviews'):
                return [{'id':1,'state':'APPROVED','commit_id':'b'*40,'user':{'type':'User','login':'Skimbee'}}] if approved else []
            if path.startswith('commits/') and '/check-runs?' in path:return {'total_count':1,'check_runs':[check]}
            if path.startswith('check-runs/'):return check
            if path.startswith('git/matching-refs/'):return [{'ref':'refs/heads/'+branch,'object':{'sha':'b'*40}}]
            if path=='git/ref/heads/'+branch:return {'object':{'sha':'b'*40}}
            self.fail('Unexpected synthetic API read '+path)
        with tempfile.TemporaryDirectory() as temp,contextlib.ExitStack() as stack:
            old=os.getcwd();os.chdir(temp);stack.callback(os.chdir,old)
            stack.enter_context(patch.dict(os.environ,{'RUNNER_TEMP':temp,'BRIDGE_RELEASE_ENABLED':'true' if enabled else 'false'}))
            stack.enter_context(patch('sys.argv',['release_v2.py',mode]))
            stack.enter_context(patch.object(m,'run_context',return_value=run))
            stack.enter_context(patch.object(m,'source_proof',return_value=(document,artifact)))
            stack.enter_context(patch.object(m,'verify',return_value=(fresh,pathlib.Path(temp)/'objects.git')))
            stack.enter_context(patch.object(m,'completed_job'))
            stack.enter_context(patch.object(m,'api',side_effect=api))
            try:m.main()
            except ValueError:
                self.assertEqual(state['writes'],[],'Fail-closed case performed write')
                raise
            output=json.loads(pathlib.Path('publication.json').read_text()) if pathlib.Path('publication.json').exists() else None
        return state,output
    def test_routine_publishes_exact_commit(self):
        state,result=self.exercise();self.assertEqual(state['head'],'b'*40);self.assertTrue(result['exact_sha_published'])
    def test_control_waits_for_owner_without_write(self):
        state,result=self.exercise(protected=True);self.assertEqual(state['writes'],[]);self.assertFalse(result['exact_sha_published'])
    def test_control_publishes_after_exact_owner_approval(self):
        state,result=self.exercise(protected=True,approved=True);self.assertEqual(state['head'],'b'*40)
    def test_wrong_check_issuer_never_publishes(self):
        with self.assertRaises(ValueError):self.exercise(wrong_check=True)
    def test_changed_base_never_publishes(self):
        with self.assertRaises(ValueError):self.exercise(moved=True)
    def test_changed_evidence_never_publishes(self):
        with self.assertRaises(ValueError):self.exercise(proof_changed=True)
    def test_disabled_activation_never_publishes(self):
        with self.assertRaises(ValueError):self.exercise(enabled=False)
    def test_attestor_uses_only_checks_write(self):
        state,_=self.exercise(mode='attest');self.assertEqual([x[0] for x in state['writes']],['check-runs'])
    def test_existing_stage_is_idempotent_no_write(self):
        state,_=self.exercise(mode='stage');self.assertEqual(state['writes'],[])
    def test_nonmain_controller_rejected_before_api(self):
        with patch.dict(os.environ,{'GITHUB_REPOSITORY':m.REPO,'GITHUB_REF':'refs/heads/unreviewed'}),patch.object(m,'api') as api,self.assertRaises(ValueError):m.run_context()
        api.assert_not_called()
if __name__=='__main__':unittest.main()
