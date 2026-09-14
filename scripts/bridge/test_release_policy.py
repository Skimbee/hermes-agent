"""Offline policy tests; synthetic inputs, no GitHub writes."""
import copy
import unittest
import release_policy as p

class PolicyTests(unittest.TestCase):
    def test_protected_paths_require_owner(self):
        for path in ('.github/workflows/bridge-release.yml','scripts/bridge/new.py','.github/CODEOWNERS','CODEOWNERS','docs/CODEOWNERS','tests/plugins/memory/test_hindsight_pin_contract.py'):
            with self.subTest(path=path):self.assertTrue(p.protected_paths(['tools/x.py',path]))
        self.assertEqual(p.protected_paths(['tools/x.py','tests/test_x.py','.github/workflows/osv-scanner.yml','scripts/install.sh']),[])

    def test_approval_is_latest_owner_state_on_exact_head(self):
        head='b'*40
        good={'user':{'login':'Skimbee','type':'User'},'state':'APPROVED','commit_id':head,'id':1}
        self.assertTrue(p.owner_approved([good],head))
        for mutation in ({'commit_id':'c'*40},{'state':'DISMISSED'},{'user':{'login':'other','type':'User'}}):
            self.assertFalse(p.owner_approved([{**good,**mutation}],head))
        self.assertFalse(p.owner_approved([good,{**good,'id':2,'state':'CHANGES_REQUESTED'}],head))
        self.assertTrue(p.owner_approved([good,{**good,'id':2,'state':'COMMENTED'}],head))
    def test_exact_check_binds_issuer_commit_and_evidence(self):
        check={'name':p.CHECK,'app':{'id':p.APP_ID},'head_sha':'b'*40,'status':'completed','conclusion':'success','external_id':'proof:11:1:digest','details_url':'https://github.com/o/r/actions/runs/11'}
        p.validate_check(check,'b'*40,check['external_id'],check['details_url'])
        for mutation in ({'head_sha':'c'*40},{'app':{'id':15368}},{'external_id':'wrong'},{'status':'in_progress'},{'conclusion':'failure'},{'details_url':'https://evil.invalid'}):
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):p.validate_check({**check,**mutation},'b'*40,check['external_id'],check['details_url'])
    def test_verified_intermediate_merge_parent(self):
        p.validate_candidate('a'*40,'a'*40,'b'*40,['c'*40,'d'*40],first_parent_contains_base=True)
        with self.assertRaises(ValueError):p.validate_candidate('a'*40,'a'*40,'b'*40,['c'*40,'d'*40])
    def test_publication_requires_unchanged_base_and_expected_topology(self):
        p.validate_candidate('a'*40,'a'*40,'b'*40,['a'*40,'c'*40])
        for current,candidate,parents in [('c'*40,'b'*40,['a'*40]),('a'*40,'a'*40,['a'*40]),('a'*40,'b'*40,['c'*40,'a'*40]),('a'*40,'b'*40,['a'*40,'a'*40])]:
            with self.assertRaises(ValueError):p.validate_candidate('a'*40,current,candidate,parents)

if __name__=='__main__':unittest.main()
