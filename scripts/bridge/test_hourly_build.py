"""Run real hourly build/reconciliation shells on disposable Git repositories."""
import json
import os
import pathlib
import shlex
import shutil
import subprocess
import tempfile
import textwrap
import tomllib
import unittest

from test_lock_metadata import PROJECT, LOCK

ROOT = pathlib.Path(__file__).resolve().parents[2]


class HourlyBuildTests(unittest.TestCase):
    def shell(self, name):
        workflow = (ROOT / '.github/workflows/bridge-hourly-pilot.yml').read_text()
        marker = '      - name: ' + name + '\n'
        if marker not in workflow:
            return ''
        segment = workflow.split(marker, 1)[1].split('      - name:', 1)[0]
        return textwrap.dedent(segment.split('        run: |\n', 1)[1])

    def build(self, changed, missing_metadata=False):
        shell = self.shell('Build isolated candidate without credentials')
        with tempfile.TemporaryDirectory() as directory:
            t = pathlib.Path(directory)
            source, work = t / 'source', t / 'work'
            source.mkdir()
            work.mkdir()

            def git(*args, repo=source):
                return subprocess.check_output(['git', '-C', str(repo), *args],
                                               stderr=subprocess.PIPE, text=True).strip()

            git('init', '-b', 'main')
            git('config', 'user.name', 'Synthetic test')
            git('config', 'user.email', 'synthetic@example.invalid')
            (source / 'fixture.txt').write_text('synthetic base\n')
            helper = source / 'scripts/bridge/lock_metadata.py'
            helper.parent.mkdir(parents=True)
            shutil.copyfile(ROOT / 'scripts/bridge/lock_metadata.py', helper)
            (source / 'pyproject.toml').write_text(PROJECT.replace('new_package = false\n', ''))
            (source / 'uv.lock').write_text(LOCK)
            git('add', '.')
            git('commit', '-m', 'synthetic base')
            base = git('rev-parse', 'HEAD')
            if changed:
                (source / 'fixture.txt').write_text('synthetic update\n')
                if missing_metadata:
                    (source / 'pyproject.toml').write_text(PROJECT)
                    helper.write_text('raise SystemExit("Incoming helper must never execute")\n')
                git('commit', '-am', 'synthetic update')
            shell = shell.replace('https://github.com/Skimbee/hermes-agent.git', shlex.quote(str(source)))
            shell = shell.replace('https://github.com/NousResearch/hermes-agent.git', shlex.quote(str(source)))
            shell = shell.replace('2f542d949e5729586c6163d027d54c8931fd7cf6', base)
            env = {**os.environ, 'GITHUB_SHA': base, 'GITHUB_RUN_ID': '101',
                   'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_OUTPUT': str(t / 'outputs'),
                   'GITHUB_STEP_SUMMARY': str(t / 'summary')}

            def run(body):
                result = subprocess.run(['bash', '-e', '-u', '-o', 'pipefail'], input=body,
                                        text=True, cwd=work, env=env, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)

            run(shell)
            self.assertEqual((t / 'outputs').read_text(), 'has_candidate=' + ('true' if changed else 'false') + '\n')
            receipt = work / 'evidence/no-change.json'
            self.assertEqual(receipt.exists(), not changed)
            if not changed:
                value = json.loads(receipt.read_text())
                self.assertEqual(value['kind'], 'no-change')
                self.assertEqual(value['candidate'], base)
                self.assertEqual(value['run_id'], '101')
            else:
                candidate = work / 'candidate'
                before = git('rev-parse', 'HEAD', repo=candidate)
                run(self.shell('Reconcile missing lock exclusion metadata'))
                after = git('rev-parse', 'HEAD', repo=candidate)
                if missing_metadata:
                    locked = tomllib.loads((candidate / 'uv.lock').read_text())
                    self.assertIs(locked['options']['exclude-newer-package'].get('new-package'), False)
                    self.assertEqual(locked['package'], tomllib.loads(LOCK)['package'])
                    self.assertNotEqual(after, before)
                    self.assertEqual(git('show', '-s', '--format=%P', 'HEAD', repo=candidate), before)
                    self.assertEqual(git('diff', '--name-only', before, after, repo=candidate), 'uv.lock')
                    self.assertEqual(git('diff', '--exit-code', 'HEAD', repo=candidate), '')
                    run(self.shell('Preserve exact tested candidate'))
                    preserved = json.loads((work / 'evidence/receipt.json').read_text())
                    self.assertEqual(preserved['candidate'], after)
                    self.assertEqual(preserved['lock_metadata_reconciliation']['added_exclusions'], ['new-package'])
                    self.verify_dashboard_preparation(work, candidate, preserved, env)
                else:
                    self.assertEqual(after, before)

    def verify_dashboard_preparation(self, work, candidate, receipt, env):
        """Real downstream parser and Git-object verification; only GitHub is fake."""
        import hashlib
        import importlib.util
        import io
        import zipfile
        from unittest.mock import patch
        import release_evidence
        from test_release_evidence import EvidenceTests
        data = EvidenceTests().fixture()
        data[3]['lock_metadata_reconciliation'] = receipt['lock_metadata_reconciliation']
        release_evidence.verify_bindings(*data)
        raw_receipt = (work / 'evidence/receipt.json').read_bytes()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('receipt.json', raw_receipt)
            archive.writestr('candidate.bundle', (work / 'evidence/candidate.bundle').read_bytes())
        payload = buffer.getvalue()
        source = {'id': 101, 'run_attempt': 1, 'workflow_id': 1,
                  'repository': {'full_name': 'Skimbee/hermes-agent'},
                  'path': '.github/workflows/bridge-hourly-pilot.yml',
                  'head_sha': receipt['base'], 'head_branch': 'main',
                  'status': 'completed', 'conclusion': 'success', 'event': 'workflow_dispatch'}
        dashboard = {**source, 'id': 202, 'workflow_id': 2,
                     'path': '.github/workflows/bridge-dashboard-e2e.yml', 'event': 'workflow_run'}
        artifact = {'id': 303, 'name': 'bridge-candidate-101-1', 'expired': False,
                    'size_in_bytes': len(payload), 'digest': 'sha256:' + hashlib.sha256(payload).hexdigest()}
        responses = {'actions/runs/101': source, 'actions/runs/202': dashboard,
                     'actions/runs/101/artifacts?per_page=100': {'total_count': 1, 'artifacts': [artifact]},
                     'git/ref/heads/main': {'object': {'sha': receipt['base']}}}
        original_run, original_output = subprocess.run, subprocess.check_output

        def run(command, *args, **kwargs):
            self.assertEqual(command[0], 'git', 'No candidate process may execute')
            if command[1:3] == ['clone', '--bare']:
                self.assertEqual(command[3], 'https://github.com/Skimbee/hermes-agent.git')
                command = [*command[:3], str(candidate), *command[4:]]
            return original_run(command, *args, **kwargs)

        def output(command, *args, **kwargs):
            if command[0] == 'gh':
                raw_responses = {
                    ('gh', 'api', 'repos/Skimbee/hermes-agent/actions/artifacts/303/zip'): payload,
                    ('gh', 'api', 'repos/Skimbee/hermes-agent/actions/runs/202'): json.dumps(dashboard).encode(),
                }
                self.assertIn(tuple(command), raw_responses, 'Unexpected GitHub request is forbidden')
                return raw_responses[tuple(command)]
            self.assertEqual(command[0], 'git')
            return original_output(command, *args, **kwargs)

        before_cwd = pathlib.Path.cwd()
        try:
            os.chdir(work)
            spec = importlib.util.spec_from_file_location('trusted_prepare', ROOT / 'scripts/bridge/container-e2e/prepare.py')
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with patch.dict(os.environ, {**env, 'CANDIDATE_RUN': '101', 'GITHUB_RUN_ID': '202',
                                         'GITHUB_REPOSITORY': 'Skimbee/hermes-agent'}), \
                    patch.object(module, 'api', side_effect=lambda path: responses[path]), \
                    patch.object(module.subprocess, 'run', side_effect=run), \
                    patch.object(module.subprocess, 'check_output', side_effect=output):
                module.main()
            self.assertEqual((work / 'e2e-input/original-receipt.json').read_bytes(), raw_receipt)
            binding = json.loads((work / 'e2e-input/binding.json').read_text())
            self.assertEqual(binding['candidate'], receipt['candidate'])
            self.assertEqual(binding['bundle_sha256'], receipt['bundle_sha256'])
            self.assertEqual(binding['candidate_run']['id'], source['id'])
        finally:
            os.chdir(before_cwd)

    def test_no_change_produces_original_receipt(self):
        self.build(False)

    def test_change_keeps_candidate_path(self):
        self.build(True)

    def test_reconciliation_uses_base_helper_and_binds_committed_receipt(self):
        self.build(True, missing_metadata=True)


if __name__ == '__main__':
    unittest.main()
