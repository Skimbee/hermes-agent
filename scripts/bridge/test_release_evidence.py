import copy,hashlib,unittest
import release_evidence as e

class EvidenceTests(unittest.TestCase):
    def fixture(self):
        c={'repository':{'full_name':e.REPO},'id':11,'run_attempt':1,'workflow_id':1,'path':e.CANDIDATE_PATH,'head_sha':'a'*40,'event':'schedule','status':'completed','conclusion':'success','head_branch':'main'}
        d={**c,'id':22,'workflow_id':2,'path':e.DASHBOARD_PATH,'event':'workflow_run'}
        a={'id':33,'digest':'sha256:'+'d'*64,'expired':False}
        r={'schema':1,'run_id':'11','run_attempt':'1','workflow_sha':'a'*40,'base':'a'*40,'candidate':'b'*40,'upstream':'c'*40,'bundle_sha256':hashlib.sha256(b'synthetic').hexdigest()}
        binding={'schema':2,'candidate_run':{**e.identity(c),'status':'completed','conclusion':'success'},'candidate_artifact':{'id':33,'run_id':11,'digest':a['digest'],'expired':False},'candidate':r['candidate'],'bundle_sha256':r['bundle_sha256'],'dashboard_identity':e.identity(d)}
        result={**binding,'dashboard_run':e.identity(d),'passed':True,'reconnected':True,'tracked_tree_matches':True,'candidate_stopped':True,'pre_head':e.CLIENT_BASE,'post_head':r['candidate'],'tracked_files_verified':1,'observed_receipt':{'pre_sha':e.CLIENT_BASE,'post_sha':r['candidate'],'outcome':'success'},'browser_sandbox_requested':True,'browser_sandbox_status':'PID namespaces Yes Seccomp-BPF sandbox Yes'}
        return [c,d,a,r,b'synthetic',binding,result,'a'*40]
    def test_no_change_receipt_is_not_a_release(self):
        c,d,a,_,_,_,_,base=self.fixture()
        receipt={'schema':1,'kind':'no-change','run_id':'11','run_attempt':'1','workflow_sha':base,'base':base,'candidate':base,'upstream':'c'*40}
        observed={'schema':3,'state':'no_change','candidate_run':{**e.identity(c),'status':'completed','conclusion':'success'},'candidate_artifact':{'id':a['id'],'run_id':c['id'],'digest':a['digest'],'expired':False},'dashboard_identity':e.identity(d)}
        e.verify_no_change(c,d,a,receipt,observed,base)
        receipt['candidate']='b'*40
        with self.assertRaises(ValueError):e.verify_no_change(c,d,a,receipt,observed,base)
    def test_complete_original_bindings(self):e.verify_bindings(*self.fixture())
    def test_mismatches_rejected(self):
        for idx,key,value in [(0,'conclusion','failure'),(0,'head_branch','other'),(1,'head_sha','f'*40),(1,'run_attempt',2),(1,'path','wrong'),(2,'id',34),(2,'digest','sha256:'+'e'*64),(3,'bundle_sha256','0'*64),(3,'run_id','12'),(5,'schema',1),(6,'post_head','f'*40),(6,'passed',False),(6,'candidate_stopped',False),(6,'browser_sandbox_requested',False),(6,'tracked_files_verified',True)]:
            data=copy.deepcopy(self.fixture());data[idx][key]=value
            with self.subTest(idx=idx,key=key),self.assertRaises(ValueError):e.verify_bindings(*data)
        data=self.fixture();data[-1]='f'*40
        with self.assertRaises(ValueError):e.verify_bindings(*data)
if __name__=='__main__':unittest.main()
