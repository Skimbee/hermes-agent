"""Exercise provenance with real Git trees, never candidate code or live GitHub."""
import pathlib
import subprocess
import tempfile
import unittest
import release_evidence as evidence


class SelectiveProtectionTests(unittest.TestCase):
    def test_upstream_changes_are_distinguished_from_fork_controls(self):
        classify = getattr(evidence, 'classify_control_changes', None)
        self.assertTrue(callable(classify), 'Missing tree-based ownership classification')
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            def git(*args):
                return subprocess.check_output(['git', '-C', temp, '-c', 'core.hooksPath=/dev/null', *args], stderr=subprocess.PIPE)
            def commit(files):
                for name, content in files.items():
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    if content is None:
                        path.unlink()
                    else:
                        path.write_text(content)
                git('add', '-A')
                git('commit', '-qm', 'synthetic fixture')
                return git('rev-parse', 'HEAD').decode().strip()
            git('init', '-q');git('config', 'user.name', 'Fixture');git('config', 'user.email', 'fixture@example.invalid')
            osv = '.github/workflows/osv-scanner.yml'
            install = 'scripts/install.sh'
            obsolete = '.github/workflows/obsolete.yml'
            new = '.github/workflows/new.yml'
            own = '.github/workflows/bridge-release.yml'
            ancestor = commit({osv:'old', install:'old', obsolete:'old'})
            git('checkout', '-qb', 'fork')
            base = commit({own:'our controller'})
            git('checkout', '-qb', 'upstream', ancestor)
            upstream = commit({osv:'timeout-minutes: 10', install:'new', obsolete:None, new:'new upstream workflow'})
            git('checkout', 'fork');git('merge', '--no-edit', upstream)
            candidate = git('rev-parse', 'HEAD').decode().strip()
            verify_upstream = getattr(evidence, 'verify_official_upstream', None)
            self.assertTrue(callable(verify_upstream), 'Missing independent official ancestry check')
            def official_git(*args):
                if args[0] == 'fetch':
                    self.assertEqual(args[1:], ('--no-tags', 'https://github.com/NousResearch/hermes-agent.git', 'refs/heads/main'))
                    return git('fetch', temp, 'refs/heads/upstream')
                return git(*args)
            verify_upstream(upstream, official_git)
            with self.assertRaises(subprocess.CalledProcessError):
                verify_upstream(base, official_git)
            result = classify(base, candidate, upstream, git)
            self.assertEqual(result['protected_paths'], [])
            self.assertEqual(result['workflow_changes'], sorted([osv, obsolete, new]))
            self.assertEqual(result['upstream_workflow_changes'], result['workflow_changes'])
            candidate = commit({osv:'fork override', own:'modified controller'})
            result = classify(base, candidate, upstream, git)
            self.assertEqual(result['protected_paths'], sorted([osv, own]))
            self.assertEqual(result['upstream_workflow_changes'], sorted([obsolete, new]))
            # Existing fork customizations cannot silently become upstream-owned.
            git('checkout', '-qb', 'customized', base)
            customized = commit({osv:'local customization'})
            overwritten = commit({osv:'timeout-minutes: 10'})
            self.assertIn(osv, classify(customized, overwritten, upstream, git)['protected_paths'])


if __name__ == '__main__':
    unittest.main()
