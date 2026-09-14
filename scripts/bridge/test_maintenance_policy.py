"""Maintenance must not relax the automated publisher's required check."""
import unittest

class MaintenancePolicyTests(unittest.TestCase):
    def test_ruleset_preserves_release_check_and_limits_bypass(self):
        import maintenance_policy as m
        p=m.ruleset()
        self.assertEqual(p['conditions']['ref_name'], {'include':['refs/heads/main'],'exclude':[]})
        self.assertEqual(p['bypass_actors'], [{'actor_id':5,'actor_type':'RepositoryRole','bypass_mode':'pull_request'}])
        by_type={x['type']:x for x in p['rules']}
        checks=by_type['required_status_checks']['parameters']
        self.assertTrue(checks['strict_required_status_checks_policy'])
        self.assertEqual(checks['required_status_checks'], [{'context':'Bridge release / exact-candidate','integration_id':4931424}])
        self.assertTrue(by_type['pull_request']['parameters']['require_code_owner_review'])
        self.assertTrue(by_type['pull_request']['parameters']['dismiss_stale_reviews_on_push'])
        self.assertEqual(p['enforcement'],'active')

    def test_gate_rejects_wrong_head_owner_or_check(self):
        import maintenance_policy as m
        h='a'*40
        pr={'state':'OPEN','isDraft':False,'baseRefName':'main','headRefOid':h,'author':{'login':'Skimbee'},'isCrossRepository':False}
        checks=[{'name':'contracts','head_sha':h,'status':'completed','conclusion':'success','app':{'id':15368}}]
        self.assertIsNone(m.validate(pr,checks,h,h))
        for field,value in [('state','CLOSED'),('isDraft',True),('headRefOid','b'*40),('author',{'login':'other'}),('isCrossRepository',True)]:
            with self.subTest(field=field),self.assertRaises(ValueError):m.validate(dict(pr,**{field:value}),checks,h,h)
        with self.assertRaises(ValueError):m.validate(pr,checks,h,'b'*40)
        for change in [{'conclusion':'failure'},{'head_sha':'b'*40},{'app':{'id':4931424}},{'status':'in_progress'}]:
            with self.assertRaises(ValueError):m.validate(pr,[dict(checks[0],**change)],h,h)
        with self.assertRaises(ValueError):m.validate(pr,checks*2,h,h)
