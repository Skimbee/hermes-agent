"""Fresh consumers must work with the utils cached by a pre-signature updater.

The d131988d53c3b8389801f6cee03b990bd51ac49a updater evicts hermes_cli,
agent and gateway modules, but retains utils and the update_receipt singleton.
Do not call the new purge here: that code cannot fix an already-running updater.
"""

import os
from pathlib import Path
import subprocess
import sys

import pytest


_ROOT = Path(__file__).resolve().parents[2]
_LEGACY_UTILS = """
import utils
# Model the cached pre-update API, not an empty mock module: all other helpers
# remain real. Never reload/evict utils to make the fresh consumer import work.
if hasattr(utils, 'file_signature'):
    del utils.file_signature
legacy_utils = utils
"""


def _run(script, tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", _LEGACY_UTILS + script],
        cwd=_ROOT,
        env={**os.environ, "HERMES_HOME": str(tmp_path)},
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("consumer", [
    "hermes_cli.config",
    "hermes_cli.gateway",
    "hermes_cli.auth",
    "hermes_cli.auth_oauth_grants",
    "hermes_cli.cli_info_mixin",
    "hermes_cli.model_switch",
    "agent.prompt_builder",
    "gateway.run_profile_reconcile",
    "model_tools",
    "tui_gateway.server",
])
def test_fresh_consumers_accept_legacy_cached_utils(consumer, tmp_path):
    _run(f"""
import importlib
import sys
importlib.import_module({consumer!r})
assert sys.modules['utils'] is legacy_utils
assert not hasattr(legacy_utils, 'file_signature')
""", tmp_path)


def test_pending_receipt_survives_fresh_config_with_legacy_utils(tmp_path):
    _run("""
import json
import sys
from hermes_cli import update_receipt
update_receipt.begin_update_receipt()
receipt = update_receipt._current
assert receipt is not None
update_receipt.record_step('before-code-swap', True)
# Receipt finalization lazily imports fresh config to resolve its output dir.
# On the broken candidate this silently returns None and consumes _current.
path = update_receipt.finalize_pending_update_receipt(1, 'restart failed')
assert path is not None, 'the pending failure receipt was silently lost'
body = json.loads(path.read_text())
assert body['outcome'] == 'failed'
assert body['exit_code'] == 1
assert body['steps'][0]['name'] == 'before-code-swap'
assert json.loads((path.parent / 'latest.json').read_text()) == body
assert update_receipt.finalize_pending_update_receipt(1) is None
assert sys.modules['utils'] is legacy_utils
""", tmp_path)
