import hashlib,json,pathlib,subprocess,sys,tempfile,unittest
SCRIPT=(pathlib.Path(__file__).parent / 'container-e2e/inspect_snapshot.py').read_text()
class SnapshotTests(unittest.TestCase):
    def run_case(self,mutation=None,expect=True):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)/'client';root.mkdir();(root/'.git').mkdir()
            (root/'.git/HEAD').write_text('a'*40+'\n')
            (root/'src').mkdir();(root/'src/file').write_bytes(b'content')
            digest=hashlib.sha1(b'blob 7\0content').hexdigest()
            payload={'candidate':'a'*40,'manifest':[{'path':'src/file','mode':'100644','oid':digest}]}
            if mutation:mutation(root,payload)
            code=SCRIPT.replace("'/snapshot/client'",repr(str(root)))
            run=subprocess.run([sys.executable,'-I','-c',code],input=json.dumps(payload),capture_output=True,text=True,timeout=10)
            self.assertEqual(run.returncode==0,expect,run.stderr)
    def test_exact_tree(self):self.run_case()
    def test_modified_blob(self):self.run_case(lambda r,p:(r/'src/file').write_text('tampered'),False)
    def test_wrong_head(self):self.run_case(lambda r,p:(r/'.git/HEAD').write_text('b'*40),False)
    def test_wrong_mode(self):self.run_case(lambda r,p:(r/'src/file').chmod(0o755),False)
    def test_file_symlink_escape(self):
        def change(r,p):
            (r/'src/file').unlink();(r/'src/file').symlink_to('/etc/passwd')
        self.run_case(change,False)
    def test_directory_symlink_escape(self):
        def change(r,p):
            (r/'src/file').unlink();(r/'src').rmdir();(r/'src').symlink_to('/etc')
        self.run_case(change,False)
    def test_explicit_crlf_checkout(self):
        def change(r,p):
            (r/'src/file').write_bytes(b'content\r\n')
            p['manifest'][0].update(eol='crlf',oid=hashlib.sha1(b'blob 8\0content\n').hexdigest())
        self.run_case(change)
    def test_crlf_not_silently_normalized(self):
        def change(r,p):
            (r/'src/file').write_bytes(b'content\r\n')
            p['manifest'][0].update(oid=hashlib.sha1(b'blob 8\0content\n').hexdigest())
        self.run_case(change,False)
    def test_parent_traversal(self):self.run_case(lambda r,p:p['manifest'][0].update(path='../outside'),False)
if __name__=='__main__':unittest.main()
