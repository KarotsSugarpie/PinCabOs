#!/usr/bin/env python3
"""Static validation for the modular PinCabOS WebApp refactor."""
from __future__ import annotations

import ast
import collections
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FILES = [ROOT / "app.py", *sorted(ROOT.glob("pincabos_webapp_*.py"))]


def decorator_path(node: ast.AST) -> str | None:
    for dec in getattr(node, "decorator_list", []):
        if not isinstance(dec, ast.Call) or not dec.args:
            continue
        if not isinstance(dec.args[0], ast.Constant) or not isinstance(dec.args[0].value, str):
            continue
        func = dec.func
        if isinstance(func, ast.Attribute) and func.attr == "route":
            return dec.args[0].value
        if isinstance(func, ast.Name) and func.id == "route":
            return dec.args[0].value
    return None


errors: list[str] = []
routes: list[tuple[str, str, str]] = []
for path in FILES:
    try:
        source = path.read_text(encoding="utf-8")
        compile(source, str(path), "exec")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError as exc:
        errors.append(f"Syntaxe invalide dans {path.name}: {exc}")
        continue

    top_level = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)]
    for name, count in collections.Counter(top_level).items():
        if count > 1:
            errors.append(f"Fonction top-level dupliquée dans {path.name}: {name}")

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            route = decorator_path(node)
            if route:
                routes.append((route, node.name, path.name))

for route, count in collections.Counter(route for route, _, _ in routes).items():
    if count > 1:
        origin = [(name, file) for path, name, file in routes if path == route]
        errors.append(f"Route dupliquée {route}: {origin}")

required = {
    "/audio-ssf/save",
    "/audio-ssf/commander",
    "/audio-ssf/commander/save",
    "/audio-ssf/test-wav-stop",
    "/tools/export-table/download-v7",
    "/dev/submit",
    "/dev/cleanup-nosnap",
    "/first-run/action/<action>",
}
found = {route for route, _, _ in routes}
for route in sorted(required - found):
    errors.append(f"Route critique absente: {route}")

if errors:
    print("NOGO: validation échouée")
    for error in errors:
        print(" -", error)
    sys.exit(1)

print("GO: syntaxe, routes critiques et absence de doublons validées")
print(f"GO: {len(FILES)} fichiers Python contrôlés, {len(routes)} routes déclarées")
