"""Pure maintenance policy; no credentials, writes or release attestations.

Owner maintenance is explicitly NOT automated bridge release evidence.
The ruleset owner exception is PR-only. Classic force/delete protection stays.
"""
import re

def ruleset():
    return {
        'name':'Bridge release checks and owner maintenance',
        'target':'branch','enforcement':'active',
        'conditions':{'ref_name':{'include':['refs/heads/main'],'exclude':[]}},
        'bypass_actors':[{'actor_id':5,'actor_type':'RepositoryRole','bypass_mode':'pull_request'}],
        'rules':[
            {'type':'required_status_checks','parameters':{
                'strict_required_status_checks_policy':True,
                'required_status_checks':[{'context':'Bridge release / exact-candidate','integration_id':4931424}]}},
            {'type':'pull_request','parameters':{
                'required_approving_review_count':0,
                'dismiss_stale_reviews_on_push':True,
                'require_code_owner_review':True,
                'require_last_push_approval':False,
                'required_review_thread_resolution':True,
                'allowed_merge_methods':['merge']}}
        ]}

def validate(pr,checks,expected_head,reviewed_head):
    """Inputs: gh pr view --json and REST check-runs?filter=latest.

Parent supplies independently assessed review head, not candidate claims.

Does not prove an Opus review happened. Parent must read/assess its artifact.
A successful CI is also not permission to merge or an App release attestation.
"""
    def require(ok,message):
        if not ok:raise ValueError(message)
    require(bool(re.fullmatch('[0-9a-f]{40}',expected_head)),'Exact SHA required')
    require(reviewed_head==expected_head,'Review is stale')
    require(pr['state']=='OPEN' and not pr['isDraft'],'PR not ready')
    require(pr['baseRefName']=='main' and not pr['isCrossRepository'],'Wrong repository/base')
    require(pr['author']['login']=='Skimbee','Owner maintenance only')
    require(pr['headRefOid']==expected_head,'PR head drift')
    selected=[c for c in checks if c['name']=='contracts']
    require(len(selected)==1,'Missing or ambiguous contracts check')
    c=selected[0]
    require(c['head_sha']==expected_head and c['app']['id']==15368,'Wrong check identity')
    require(c['status']=='completed' and c['conclusion']=='success','CI not successful')
