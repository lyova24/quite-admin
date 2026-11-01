"""Check the committed public API baseline. Optional adapters use separate profiles.

This is a conservative structural check, not a replacement for behavior contracts.
Do not regenerate a baseline to make an incompatible change pass.
"""

from __future__ import annotations

import argparse
import importlib
import inspect
import json
from dataclasses import fields, is_dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def resolve(reference):
    module, name = reference.split(":", 1)
    target = importlib.import_module(module)
    for part in name.split("."):
        target = getattr(target, part)
    return target


def signature(target):
    try:
        actual = inspect.signature(target)
    except (TypeError, ValueError):
        # Exception inherits a built-in constructor; inspect its initializer instead.
        if inspect.isclass(target) and issubclass(target, BaseException):
            actual = inspect.signature(target.__init__)
        else:
            raise
    parameters = []
    for parameter in actual.parameters.values():
        item = {"name": parameter.name, "kind": parameter.kind.name}
        if parameter.default is not inspect.Parameter.empty:
            item["default"] = repr(parameter.default)
        if parameter.annotation is not inspect.Parameter.empty:
            item["annotation"] = str(parameter.annotation)
        parameters.append(item)
    result = {"parameters": parameters, "async": inspect.iscoroutinefunction(target)}
    if actual.return_annotation is not inspect.Signature.empty:
        result["returns"] = str(actual.return_annotation)
    return result


def describe(target):
    if not inspect.isclass(target):
        return {"kind": "function", "signature": signature(target)}
    protocol = bool(getattr(target, "_is_protocol", False))
    result = {"kind": "class", "protocol": protocol, "methods": {}, "properties": {}}
    if protocol:
        result["attributes"] = {}
    if not protocol:
        result["signature"] = signature(target)
    for name, member in inspect.getmembers(target):
        if name.startswith("_") and name != "__call__":
            continue
        if isinstance(member, property):
            result["properties"][name] = signature(member.fget)
        elif inspect.isfunction(member) or inspect.ismethod(member):
            result["methods"][name] = signature(member)
        elif protocol:
            result["attributes"][name] = None
    if protocol:
        for base in reversed(target.__mro__):
            for name, annotation in getattr(base, "__annotations__", {}).items():
                if not name.startswith("_"):
                    result["attributes"][name] = str(annotation)
    if is_dataclass(target):
        result["fields"] = [item.name for item in fields(target)]
        result["frozen"] = target.__dataclass_params__.frozen
    return result


def compare_signature(name, previous, current):
    if previous is None:
        return []
    if current is None:
        return [f"{name}: signature is no longer inspectable"]
    errors = []
    for key in ("async", "returns"):
        if previous.get(key) != current.get(key):
            errors.append(f"{name}: changed {key}")
    old = {item["name"]: item for item in previous["parameters"]}
    new = {item["name"]: item for item in current["parameters"]}
    positional = {"POSITIONAL_ONLY", "POSITIONAL_OR_KEYWORD"}
    old_positions = [item["name"] for item in previous["parameters"] if item["kind"] in positional]
    new_positions = [item["name"] for item in current["parameters"] if item["kind"] in positional]
    if new_positions[: len(old_positions)] != old_positions:
        errors.append(f"{name}: changed positional argument order")
    if any(item["kind"] == "VAR_POSITIONAL" for item in old.values()):
        if new_positions != old_positions:
            errors.append(f"{name}: new positional arguments would consume existing *args")
    for parameter, before in old.items():
        after = new.get(parameter)
        if after is None:
            errors.append(f"{name}: removed parameter {parameter}")
            continue
        for key in ("kind", "annotation"):
            if before.get(key) != after.get(key):
                errors.append(f"{name}.{parameter}: changed {key}")
        if "default" in before and before["default"] != after.get("default"):
            errors.append(f"{name}.{parameter}: changed default")
    for parameter, after in new.items():
        if parameter not in old and after["kind"] in positional | {"KEYWORD_ONLY"}:
            if "default" not in after:
                errors.append(f"{name}: added required parameter {parameter}")
    return errors


def compare_symbol(name, previous, current):
    errors = []
    for key in ("kind", "protocol", "frozen"):
        if previous.get(key) != current.get(key):
            errors.append(f"{name}: changed {key}")
    if not set(previous.get("fields", ())) <= set(current.get("fields", ())):
        errors.append(f"{name}: removed data fields")
    if previous.get("protocol") and previous.get("attributes") != current.get("attributes"):
        errors.append(f"{name}: changed required protocol attributes")
    errors.extend(compare_signature(name, previous.get("signature"), current.get("signature")))
    for section in ("methods", "properties"):
        before = previous.get(section, {})
        after = current.get(section, {})
        if previous.get("protocol") and set(before) != set(after):
            errors.append(f"{name}: changed required protocol {section}")
        for member, expected in before.items():
            if member not in after:
                errors.append(f"{name}: removed {section} member {member}")
            else:
                errors.extend(compare_signature(f"{name}.{member}", expected, after[member]))
    return errors


def check(root=ROOT, profile="core"):
    baseline = json.loads((root / "api" / f"{profile}-0.4.json").read_text())
    errors = []
    for module, exports in baseline.get("exports", {}).items():
        current = set(importlib.import_module(module).__all__)
        if not set(exports) <= current:
            errors.append(f"{module}: removed public exports {sorted(set(exports) - current)}")
    for reference, expected in baseline.get("constants", {}).items():
        try:
            current = resolve(reference)
        except (AttributeError, ImportError):
            errors.append(f"{reference}: removed public constant")
            continue
        if current != expected:
            errors.append(f"{reference}: changed public constant")
    for reference, expected in baseline.get("capabilities", {}).items():
        current = resolve(reference)
        compatible = (
            set(expected) <= set(current) if isinstance(expected, list) else current == expected
        )
        if not compatible:
            errors.append(f"{reference}: removed adapter capability")
    for reference, expected in baseline["symbols"].items():
        try:
            current = describe(resolve(reference))
        except (AttributeError, ImportError) as exc:
            errors.append(f"{reference}: cannot import public symbol ({type(exc).__name__})")
            continue
        errors.extend(compare_symbol(reference, expected, current))
    if "templates" in baseline:
        from jinja2 import Environment, nodes

        for template, blocks in baseline["templates"].items():
            path = root / "src/quite_admin/templates" / template
            if not path.is_file():
                errors.append(f"{template}: removed template")
                continue
            parsed = Environment().parse(path.read_text())
            actual = {block.name for block in parsed.find_all(nodes.Block)}
            if not set(blocks) <= actual:
                errors.append(f"{template}: removed extension blocks")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("modern", "gino"), action="append", default=[])
    args = parser.parse_args()
    errors = []
    for profile in ["core", *args.profile]:
        errors.extend(check(profile=profile))
    if errors:
        parser.exit(1, "Public API compatibility failed:\n" + "\n".join(errors) + "\n")
    print("Public API baseline is compatible (0.4.x).")


if __name__ == "__main__":
    main()
