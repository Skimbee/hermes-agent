"""Exercise the bounded lock-metadata CLI on real temporary TOML files."""
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import tomllib
import unittest

SCRIPT = pathlib.Path(__file__).with_name('lock_metadata.py')
PROJECT = '''[project]
name = "synthetic"
version = "1.0"
[tool.uv.exclude-newer-package]
existing = false
new_package = false
'''
LOCK = '''version = 1
revision = 3
[options]
exclude-newer-span = "P14D"
[options.exclude-newer-package]
existing = false
[[package]]
name = "new-package"
version = "1.2.3"
source = { registry = "https://example.invalid/simple" }
wheels = [{ url = "https://example.invalid/package.whl", hash = "sha256:synthetic" }]
'''


class LockMetadataTests(unittest.TestCase):
    def invoke(self, root):
        self.assertTrue(SCRIPT.is_file(), 'Missing bounded metadata helper')
        env = {'PATH': os.environ['PATH'], 'HOME': str(root), 'LANG': 'C.UTF-8'}
        return subprocess.run([sys.executable, str(SCRIPT), str(root)],
                              env=env, capture_output=True, text=True, timeout=15)

    def test_only_missing_false_option_changes_and_rerun_is_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            project = root / 'pyproject.toml'
            lock = root / 'uv.lock'
            project.write_text(PROJECT)
            lock.write_text(LOCK)
            before = tomllib.loads(LOCK)
            result = self.invoke(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            receipt = json.loads(result.stdout)
            self.assertEqual(receipt['added_exclusions'], ['new-package'])
            after = tomllib.loads(lock.read_text())
            self.assertEqual(after['package'], before['package'])
            self.assertIs(after['options']['exclude-newer-package'].pop('new-package'), False)
            self.assertEqual(after, before)
            self.assertEqual(project.read_text(), PROJECT)
            repaired = lock.read_bytes()
            result = self.invoke(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['added_exclusions'], [])
            self.assertEqual(lock.read_bytes(), repaired)

    def test_unsupported_or_ambiguous_inputs_fail_without_any_write(self):
        cases = {
            'new_non_false_option': (PROJECT.replace('new_package = false', 'new_package = true'), LOCK),
            'existing_value_drift': (PROJECT, LOCK.replace('existing = false', 'existing = true')),
            'removed_exclusion': (PROJECT.replace('existing = false\n', ''), LOCK),
            'package_not_locked': (PROJECT, LOCK.replace('name = "new-package"', 'name = "other-package"')),
            'ambiguous_name_aliases': (PROJECT + 'new-package = false\n', LOCK),
            'future_lock_schema': (PROJECT, LOCK.replace('revision = 3', 'revision = 4')),
            'project_symlink': (PROJECT, LOCK),
            'lock_symlink': (PROJECT, LOCK),
            'lock_hardlink': (PROJECT, LOCK),
        }
        for case, (project_text, lock_text) in cases.items():
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                root = pathlib.Path(tmp)
                project = root / 'pyproject.toml'
                lock = root / 'uv.lock'
                project.write_text(project_text)
                lock.write_text(lock_text)
                if case == 'project_symlink':
                    project.rename(root / 'external-project')
                    project.symlink_to(root / 'external-project')
                elif case == 'lock_symlink':
                    lock.rename(root / 'external-lock')
                    lock.symlink_to(root / 'external-lock')
                elif case == 'lock_hardlink':
                    os.link(lock, root / 'external-lock')
                before = {p.name: p.read_bytes() for p in root.iterdir()}
                result = self.invoke(root)
                self.assertNotEqual(result.returncode, 0, f'{case} was accepted: {result.stdout}')
                self.assertEqual({p.name: p.read_bytes() for p in root.iterdir()}, before)


if __name__ == '__main__':
    unittest.main()
