"""Runtime repair must request the same SDK as the native installer."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from plugins.memory import hindsight
from tools import lazy_deps

@pytest.mark.parametrize('installed', ['0.0.1', hindsight._MIN_CLIENT_VERSION])
def test_upgrade_uses_native_dependency_contract(installed):
    with patch('importlib.metadata.version', return_value=installed), patch.object(
        lazy_deps, 'install_specs', return_value=SimpleNamespace(ok=True)
    ) as installer:
        hindsight._maybe_upgrade_client()
    if installed == hindsight._MIN_CLIENT_VERSION:
        installer.assert_not_called()
    else:
        installer.assert_called_once_with(list(lazy_deps.LAZY_DEPS['memory.hindsight']), timeout=120)
