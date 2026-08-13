#!/usr/bin/env python3
"""Resolve a demo label into the artifacts every service reads.

This is the ONLY place label YAML is parsed and merged. Everything downstream
consumes the resolved JSON, so merge semantics can only ever be wrong once.

    labels/freshmart.yaml        complete reference label (every key)
    labels/<label>.yaml          diffs only; deep-merged over freshmart
            |
            v   resolve_label.py
            |
            +--> web/src/generated/label.json      committed; Vite + vitest import it
            +--> labels/.resolved/active.json      gitignored; api / agents / seeder
            +--> os-bootstrap/rendered/templates/  gitignored; index mappings

The web artifact is a PROJECTION, not the whole label: the 760-row seed catalog,
the synonym list, and the system prompt are server-side only and would otherwise
ship to the browser for no reason. See WEB_SECTIONS / WEB_AGENT_KEYS.

Merge semantics: dicts merge recursively, every other value (including lists)
is REPLACED wholesale. A label that wants to change one entry of a list must
restate the list. This is deliberate -- element-wise list merging makes it
impossible to remove or reorder an inherited entry.

Usage:
    python3 tools/resolve_label.py                       # freshmart
    python3 tools/resolve_label.py --label acme-claims
    python3 tools/resolve_label.py --list
    python3 tools/resolve_label.py --check               # CI drift check
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LABELS_DIR = REPO_ROOT / "labels"
BASE_LABEL = "freshmart"

WEB_ARTIFACT = REPO_ROOT / "web" / "src" / "generated" / "label.json"
ACTIVE_ARTIFACT = LABELS_DIR / ".resolved" / "active.json"
TEMPLATE_SRC_DIR = REPO_ROOT / "os-bootstrap" / "templates"
TEMPLATE_OUT_DIR = REPO_ROOT / "os-bootstrap" / "rendered" / "templates"

# Sections a fully-resolved label must define. A label file itself may omit any
# of these (it inherits them); the *resolved* result may not.
REQUIRED_SECTIONS = (
    "label",
    "brand",
    "vocabulary",
    "enums",
    "aliases",
    "nav",
    "pages",
    "copy",
    "placeholders",
    "examples",
    "seed",
    "search",
    "agent",
)

# What the browser actually needs. `seed` (760 catalog rows) and `search`
# (synonyms) are server-side only, so they are omitted from the web artifact.
WEB_SECTIONS = (
    "label",
    "brand",
    "vocabulary",
    "enums",
    "aliases",
    "nav",
    "pages",
    "copy",
    "placeholders",
    "examples",
)
# Of the agent section, only what the chat widget renders.
WEB_AGENT_KEYS = ("persona", "placeholder", "empty_state")


class LabelError(Exception):
    """A label could not be loaded, merged, or validated."""


# --------------------------------------------------------------------------
# loading + merging
# --------------------------------------------------------------------------


def _require_yaml():
    try:
        import yaml  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise LabelError(
            "PyYAML is required to resolve labels.\n"
            "  pip install pyyaml     (or)     uv run --with pyyaml "
            "python3 tools/resolve_label.py"
        ) from exc
    return yaml


def available_labels() -> list[str]:
    """Every authorable label, base first."""
    names = sorted(p.stem for p in LABELS_DIR.glob("*.yaml"))
    return [BASE_LABEL] + [n for n in names if n != BASE_LABEL]


def load_label_file(name: str) -> dict[str, Any]:
    yaml = _require_yaml()
    path = LABELS_DIR / f"{name}.yaml"
    if not path.exists():
        raise LabelError(
            f"unknown label '{name}'.\nAvailable: {', '.join(available_labels())}"
        )
    try:
        loaded = yaml.safe_load(path.read_text()) or {}
    except Exception as exc:  # yaml.YAMLError and friends
        raise LabelError(f"{path.name} is not valid YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise LabelError(f"{path.name} must contain a YAML mapping at the top level")
    return loaded


def deep_merge(base: Any, override: Any, _path: str = "") -> Any:
    """Recursively merge `override` onto `base`.

    Dicts merge key-by-key. Everything else -- scalars, and notably lists --
    is replaced outright. See the module docstring for why lists replace.
    """
    if isinstance(base, dict) and isinstance(override, dict):
        merged = dict(base)
        for key, value in override.items():
            merged[key] = (
                deep_merge(base[key], value, f"{_path}.{key}") if key in base else value
            )
        return merged
    return override


def resolve(name: str) -> dict[str, Any]:
    """Load `name` and deep-merge it over the base label."""
    base = load_label_file(BASE_LABEL)
    if name == BASE_LABEL:
        resolved = base
    else:
        resolved = deep_merge(base, load_label_file(name))
    # The label's own identity is never inherited.
    resolved["label"] = name
    validate(resolved, name)
    return resolved


# --------------------------------------------------------------------------
# validation
# --------------------------------------------------------------------------


def validate(resolved: dict[str, Any], name: str) -> None:
    """Validate the resolved label.

    Uses jsonschema against labels/schema.json when the package is available
    (CI, dev machines); otherwise falls back to the structural checks below so
    `make label` still works on a host with nothing but PyYAML.
    """
    errors = _structural_errors(resolved)

    schema_path = LABELS_DIR / "schema.json"
    if schema_path.exists():
        try:
            import jsonschema  # noqa: PLC0415
        except ImportError:
            # Silently skipping validation is how a broken label ships. Say so.
            print(
                "warning: jsonschema not installed -- labels/schema.json was NOT "
                "checked (structural checks still ran). Install jsonschema, or "
                "run via `uv run --with pyyaml --with jsonschema`.",
                file=sys.stderr,
            )
        else:
            schema = json.loads(schema_path.read_text())
            validator = jsonschema.Draft202012Validator(schema)
            for err in sorted(validator.iter_errors(resolved), key=str):
                location = "/".join(str(p) for p in err.absolute_path) or "(root)"
                errors.append(f"{location}: {err.message}")

    if errors:
        joined = "\n".join(f"  - {e}" for e in errors)
        raise LabelError(f"label '{name}' is invalid:\n{joined}")


def _structural_errors(resolved: dict[str, Any]) -> list[str]:
    """Dependency-free invariants. Cheap, and the ones that actually bite."""
    errors: list[str] = []

    for section in REQUIRED_SECTIONS:
        if section not in resolved:
            errors.append(f"missing required section '{section}'")

    brand = resolved.get("brand")
    if isinstance(brand, dict):
        for key in ("name", "tagline", "tab_title", "theme", "favicon"):
            if not brand.get(key):
                errors.append(f"brand.{key} must be set")
    elif brand is not None:
        errors.append("brand must be a mapping")

    vocab = resolved.get("vocabulary")
    if isinstance(vocab, dict):
        order = vocab.get("order")
        if isinstance(order, dict) and not order.get("id_prefix"):
            errors.append("vocabulary.order.id_prefix must be set (e.g. 'FM-')")

    enums = resolved.get("enums")
    if isinstance(enums, dict):
        for enum_name, mapping in enums.items():
            if not isinstance(mapping, dict):
                errors.append(f"enums.{enum_name} must be a mapping of value -> label")
                continue
            for value, display in mapping.items():
                if not isinstance(display, str) or not display:
                    errors.append(
                        f"enums.{enum_name}.{value} must be a non-empty string"
                    )

    errors.extend(_catalog_errors(resolved.get("seed")))
    return errors


def _catalog_errors(seed: Any) -> list[str]:
    """The catalog feeds the seeder directly, so bad rows fail loudly here."""
    errors: list[str] = []
    if not isinstance(seed, dict):
        return ["seed must be a mapping"] if seed is not None else []

    locations = seed.get("locations")
    if not isinstance(locations, list) or not locations:
        errors.append("seed.locations must be a non-empty list")
    else:
        for i, loc in enumerate(locations):
            if not isinstance(loc, dict) or not loc.get("code") or not loc.get("name"):
                errors.append(f"seed.locations[{i}] needs both 'code' and 'name'")

    catalog = seed.get("catalog")
    if not isinstance(catalog, dict):
        errors.append("seed.catalog must be a mapping")
        return errors

    categories = catalog.get("categories")
    known_categories: set[str] = set()
    if not isinstance(categories, list) or not categories:
        errors.append("seed.catalog.categories must be a non-empty list")
    else:
        for i, cat in enumerate(categories):
            if not isinstance(cat, dict) or not cat.get("name"):
                errors.append(f"seed.catalog.categories[{i}] needs a 'name'")
            else:
                known_categories.add(cat["name"])

    items = catalog.get("items")
    if not isinstance(items, list) or not items:
        errors.append("seed.catalog.items must be a non-empty list")
        return errors

    # Rows are [name, category, price, weight_grams, perishable]. The pricing and
    # bundling SQL key on weight and the perishable flag, so they are mandatory
    # even in verticals where the words mean something else.
    for i, row in enumerate(items):
        where = f"seed.catalog.items[{i}]"
        if not isinstance(row, (list, tuple)) or len(row) != 5:
            errors.append(
                f"{where} must be [name, category, price, weight_grams, perishable]"
            )
            continue
        name, category, price, weight, perishable = row
        if not isinstance(name, str) or not name:
            errors.append(f"{where}[0] name must be a non-empty string")
        if known_categories and category not in known_categories:
            errors.append(
                f"{where}[1] category '{category}' is not in seed.catalog.categories"
            )
        if not isinstance(price, (int, float)) or isinstance(price, bool) or price < 0:
            errors.append(f"{where}[2] price must be a non-negative number")
        if not isinstance(weight, int) or isinstance(weight, bool) or weight <= 0:
            errors.append(f"{where}[3] weight_grams must be a positive integer")
        if not isinstance(perishable, bool):
            errors.append(f"{where}[4] perishable must be true or false")

    expand_to = catalog.get("expand_to")
    if not isinstance(expand_to, int) or isinstance(expand_to, bool) or expand_to <= 0:
        errors.append("seed.catalog.expand_to must be a positive integer")
    elif expand_to < len(items):
        errors.append(
            f"seed.catalog.expand_to ({expand_to}) is smaller than the "
            f"{len(items)} authored items -- the catalog would be truncated"
        )

    return errors


# --------------------------------------------------------------------------
# artifacts
# --------------------------------------------------------------------------


def _serialize(resolved: dict[str, Any]) -> str:
    """Stable JSON so committed artifacts diff cleanly and --check is exact."""
    return json.dumps(resolved, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def _write(path: Path, content: str) -> bool:
    """Write only when changed; returns True if the file was modified."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text() == content:
        return False
    path.write_text(content)
    return True


def render_index_templates(resolved: dict[str, Any]) -> list[Path]:
    """Render os-bootstrap/templates/*.json.tmpl with the label's synonyms.

    Source templates keep the `"__SYNONYMS__"` string placeholder so they stay
    valid JSON for editing; the rendered copy substitutes a real array. The
    `__LABEL__` marker stamps each index with the label that created it, which is
    how create-indices.sh detects an index left over from a different vertical.
    """
    synonyms = resolved.get("search", {}).get("synonyms", [])
    replacement = json.dumps(synonyms, ensure_ascii=False)
    label_name = resolved["label"]

    written: list[Path] = []
    for src in sorted(TEMPLATE_SRC_DIR.glob("*.json.tmpl")):
        rendered = (
            src.read_text()
            .replace('"__SYNONYMS__"', replacement)
            .replace("__LABEL__", label_name)
        )
        try:
            json.loads(rendered)
        except json.JSONDecodeError as exc:
            raise LabelError(
                f"{src.name} did not render to valid JSON: {exc}"
            ) from exc
        out = TEMPLATE_OUT_DIR / src.name[: -len(".tmpl")]
        _write(out, rendered)
        written.append(out)
    return written


def web_projection(resolved: dict[str, Any]) -> dict[str, Any]:
    """The subset of a resolved label that the browser needs."""
    projected = {k: resolved[k] for k in WEB_SECTIONS if k in resolved}
    agent = resolved.get("agent", {})
    projected["agent"] = {k: agent[k] for k in WEB_AGENT_KEYS if k in agent}
    return projected


def write_artifacts(resolved: dict[str, Any]) -> dict[str, bool]:
    return {
        str(WEB_ARTIFACT.relative_to(REPO_ROOT)): _write(
            WEB_ARTIFACT, _serialize(web_projection(resolved))
        ),
        str(ACTIVE_ARTIFACT.relative_to(REPO_ROOT)): _write(
            ACTIVE_ARTIFACT, _serialize(resolved)
        ),
    }


def check_committed_artifact() -> int:
    """CI guard: the committed web artifact must match a fresh freshmart resolve."""
    expected = _serialize(web_projection(resolve(BASE_LABEL)))
    if not WEB_ARTIFACT.exists():
        print(
            f"FAIL {WEB_ARTIFACT.relative_to(REPO_ROOT)} is missing.\n"
            "     Run: make label",
            file=sys.stderr,
        )
        return 1
    if WEB_ARTIFACT.read_text() != expected:
        print(
            f"FAIL {WEB_ARTIFACT.relative_to(REPO_ROOT)} is stale relative to "
            f"labels/{BASE_LABEL}.yaml.\n     Run: make label && git add "
            f"{WEB_ARTIFACT.relative_to(REPO_ROOT)}",
            file=sys.stderr,
        )
        return 1
    print(f"OK   {WEB_ARTIFACT.relative_to(REPO_ROOT)} matches labels/{BASE_LABEL}.yaml")
    return 0


# --------------------------------------------------------------------------
# cli
# --------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a demo label into the artifacts every service reads."
    )
    parser.add_argument(
        "--label",
        default=BASE_LABEL,
        help=f"label to resolve (default: {BASE_LABEL})",
    )
    parser.add_argument(
        "--list", action="store_true", help="list available labels and exit"
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify the committed web artifact matches labels/freshmart.yaml",
    )
    parser.add_argument(
        "--print", action="store_true", help="print the resolved JSON to stdout"
    )
    parser.add_argument("--quiet", action="store_true", help="only report problems")
    args = parser.parse_args(argv)

    try:
        if args.list:
            for name in available_labels():
                suffix = "  (default)" if name == BASE_LABEL else ""
                print(f"{name}{suffix}")
            return 0

        if args.check:
            return check_committed_artifact()

        resolved = resolve(args.label)

        if args.print:
            print(_serialize(resolved), end="")
            return 0

        results = write_artifacts(resolved)
        templates = render_index_templates(resolved)

        if not args.quiet:
            brand = resolved["brand"]["name"]
            print(f"Resolved label '{args.label}' ({brand})")
            for path, changed in results.items():
                print(f"  {'wrote' if changed else 'unchanged'} {path}")
            print(f"  rendered {len(templates)} index template(s)")
        return 0

    except LabelError as exc:
        print(f"\nerror: {exc}\n", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
