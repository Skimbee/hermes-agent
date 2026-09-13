"""Fail-closed release policy. Pure functions; no network or candidate execution."""
import re
CHECK='Bridge release / exact-candidate'
APP_ID=4931424
OWNER='Skimbee'

def require(condition,message):
    if not condition:raise ValueError(message)

def sha(value):
    require(type(value) is str and re.fullmatch(r'[0-9a-f]{40}',value) is not None,'Invalid SHA')
    return value

def protected_paths(paths):
    result=[]
    for path in paths:
        require(type(path) is str and path and not path.startswith('/') and not any(x in ('','.','..') for x in path.split('/')),'Unsafe path')
        if path.startswith(('.github/','scripts/')) or path in ('CODEOWNERS','docs/CODEOWNERS'):result.append(path)
    return sorted(set(result))

def owner_approved(reviews,candidate):
    sha(candidate)
    latest=None
    for review in sorted(reviews,key=lambda r:r['id']):
        if review['user']['login']==OWNER and review['user']['type']=='User' and review['state']!='COMMENTED':latest=review
    return latest is not None and latest['state']=='APPROVED' and latest['commit_id']==candidate

def validate_check(check,candidate,external_id,details_url):
    sha(candidate)
    require(check['name']==CHECK and check['app']['id']==APP_ID,'Wrong check issuer/name')
    require(check['head_sha']==candidate and check['status']=='completed' and check['conclusion']=='success','Wrong check commit/status')
    require(check['external_id']==external_id and check['details_url']==details_url,'Wrong check evidence')

def validate_candidate(base,current,candidate,parents,first_parent_contains_base=False):
    for value in (base,current,candidate,*parents):sha(value)
    require(base==current and candidate!=base,'Stale base or no-op')
    require(len(parents) in (1,2) and (parents[0]==base or first_parent_contains_base is True) and len(set(parents))==len(parents),'Unexpected topology')
