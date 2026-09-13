"""Manual read-only evidence gate; publication is a separate trusted workflow."""
import json,os,pathlib,tempfile
from release_evidence import verify
if __name__=='__main__':
    with tempfile.TemporaryDirectory(dir=os.environ['RUNNER_TEMP']) as temp:
        proof,_=verify(int(os.environ['DASHBOARD_RUN']),pathlib.Path(temp)/'verified')
    pathlib.Path('gate-result.json').write_text(json.dumps({'proof':proof,'publication_enabled':False},indent=2))
    print('EVIDENCE_VERIFIED_NOT_PUBLISHED',proof['candidate'])
