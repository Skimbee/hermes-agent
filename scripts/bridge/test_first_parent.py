"""Real Git DAG regression for ordered first-parent ancestry."""
import pathlib,subprocess,tempfile,unittest
import release_evidence as e

class FirstParentTests(unittest.TestCase):
    def fixture(self,reversed_parents):
        with tempfile.TemporaryDirectory() as tmp:
            repo=pathlib.Path(tmp)/'objects.git'
            subprocess.run(['git','init','--bare',str(repo)],check=True,capture_output=True)
            def git(*args,input=None):return subprocess.check_output(['git','-c','user.name=Synthetic test','-c','user.email=synthetic@example.invalid','--git-dir='+str(repo),*args],input=input,stderr=subprocess.PIPE)
            tree=git('mktree',input=b'').decode().strip()
            root=git('commit-tree',tree,'-m','root').decode().strip()
            base=git('commit-tree',tree,'-p',root,'-m','base').decode().strip()
            upstream=git('commit-tree',tree,'-p',root,'-m','upstream').decode().strip()
            parents=[upstream,base] if reversed_parents else [base,upstream]
            middle=git('commit-tree',tree,'-p',parents[0],'-p',parents[1],'-m','intermediate merge').decode().strip()
            candidate=git('commit-tree',tree,'-p',middle,'-m','candidate').decode().strip()
            # Both graphs pass general ancestry: that check is insufficient.
            git('merge-base','--is-ancestor',base,middle)
            if reversed_parents:
                with self.assertRaises(ValueError):e.verify_first_parent(base,candidate,git)
            else:e.verify_first_parent(base,candidate,git)
    def test_legitimate_intermediate_merge(self):self.fixture(False)
    def test_base_only_on_second_parent_is_rejected(self):self.fixture(True)
if __name__=='__main__':unittest.main()
