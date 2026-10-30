"""The layering rules documented in docs/architecture.md, enforced on the imports."""

import ast
from pathlib import Path

import pytest

PACKAGE = "habit_tracker"
SOURCE = Path(__file__).resolve().parents[2] / "src" / PACKAGE

# For each part of the package, the parts of the package it may import. Modules not
# listed here (the composition root: bootstrap, cli, demo, seed) may import anything
# except the rule about tkinter below.
ALLOWED = {
    "domain": ("domain",),
    "clock": (),
    "ports": ("domain",),
    "paths": (),
    "service": ("domain", "ports", "clock"),
    "storage": ("domain", "ports", "clock", "paths", "storage"),
    "notifications": (),
    "ui": ("domain", "ports", "clock", "service", "notifications", "ui"),
}
TKINTER_ALLOWED_IN = ("ui",)


def module_files() -> list[Path]:
    return sorted(path for path in SOURCE.rglob("*.py"))


def layered_files() -> list[Path]:
    return [path for path in module_files() if part_of(module_name(path)) in ALLOWED]


def module_name(path: Path) -> str:
    relative = path.relative_to(SOURCE.parent).with_suffix("")
    parts = list(relative.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def part_of(module: str) -> str:
    """``habit_tracker.domain.models`` is part ``domain``; ``habit_tracker.clock`` is ``clock``."""
    pieces = module.split(".")
    return pieces[1] if len(pieces) > 1 else ""


def imports_of(path: Path) -> tuple[set[str], set[str]]:
    """The modules of this package and the top-level external modules a file imports."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    own_package = module_name(path).split(".")
    if path.name != "__init__.py":
        own_package = own_package[:-1]
    internal: set[str] = set()
    external: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = own_package[: len(own_package) - (node.level - 1)]
                names = [".".join([*base, *([node.module] if node.module else [])])]
            else:
                names = [node.module or ""]
        else:
            continue
        for name in names:
            if name.split(".")[0] == PACKAGE:
                internal.add(name)
            else:
                external.add(name.split(".")[0])
    return internal, external


@pytest.mark.parametrize("path", layered_files(), ids=module_name)
def test_a_module_only_imports_from_the_layers_it_may_depend_on(path: Path) -> None:
    name = module_name(path)
    part = part_of(name)
    internal, _ = imports_of(path)
    forbidden = sorted(
        imported
        for imported in internal
        if (target := part_of(imported)) and target not in ALLOWED[part]
    )
    assert not forbidden, f"{name} must not import {forbidden}"


@pytest.mark.parametrize("path", module_files(), ids=module_name)
def test_only_the_interface_imports_tkinter(path: Path) -> None:
    name = module_name(path)
    _, external = imports_of(path)
    if part_of(name) in TKINTER_ALLOWED_IN:
        return
    assert "tkinter" not in external, f"{name} must not import tkinter"


def test_every_module_belongs_to_a_known_part() -> None:
    parts = {part_of(module_name(path)) for path in module_files()}
    composition_root = {"", "bootstrap", "cli", "demo", "seed", "__main__"}
    assert parts <= set(ALLOWED) | composition_root, parts - set(ALLOWED) - composition_root
