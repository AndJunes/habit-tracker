"""Fixtures for the tests of ``tools/``: a folder of scripts, not a package.

Each script is loaded from its file, the way Python runs it, and registered under a private
module name so that it cannot be mistaken for anything importable.
"""

import importlib.util
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
TOOLS = REPO_ROOT / "tools"

ToolLoader = Callable[[str], ModuleType]


@pytest.fixture
def load_tool() -> Iterator[ToolLoader]:
    """Loads ``tools/<name>.py`` and returns its module; every load is undone afterwards."""
    loaded: list[str] = []

    def load(name: str) -> ModuleType:
        module_name = f"tools_{name}"
        spec = importlib.util.spec_from_file_location(module_name, TOOLS / f"{name}.py")
        assert spec is not None
        assert spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        # Registered first: dataclasses look their own module up in sys.modules.
        sys.modules[module_name] = module
        loaded.append(module_name)
        spec.loader.exec_module(module)
        return module

    yield load
    for module_name in loaded:
        sys.modules.pop(module_name, None)


@pytest.fixture
def capture_screens(load_tool: ToolLoader) -> ModuleType:
    return load_tool("capture_screens")


@pytest.fixture
def build_macos_app(load_tool: ToolLoader) -> ModuleType:
    return load_tool("build_macos_app")
