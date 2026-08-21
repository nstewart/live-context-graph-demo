"""Read the resolved white-label config that `make label` produced.

The agent's persona and system prompt are label-driven so the assistant speaks
the customer's vocabulary. Its tool set, graph structure, and the ontology it
reads are not -- those are data-model shape and identical for every label.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

DEFAULT_LABEL_FILE = "/labels/active.json"
# Fallback for running outside the container (tests, local CLI).
REPO_FALLBACK = Path(__file__).resolve().parents[2] / "labels" / ".resolved" / "active.json"


@lru_cache(maxsize=1)
def load_label() -> dict[str, Any]:
    path = Path(os.environ.get("DEMO_LABEL_FILE") or DEFAULT_LABEL_FILE)
    if not path.exists():
        path = REPO_FALLBACK
    try:
        with path.open() as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"resolved label not found at {path}. Run `make label` to generate it."
        ) from exc


def system_prompt() -> str:
    prompt = load_label()["agent"].get("system_prompt")
    if not prompt:
        raise RuntimeError(
            "the active label defines no agent.system_prompt; "
            "add one to labels/<name>.yaml"
        )
    return prompt


def persona() -> str:
    return load_label()["agent"]["persona"]

def empty_state() -> str:
    """One line telling the operator what this deployment can be asked about."""
    return load_label()["agent"].get("empty_state", "")


def default_store() -> str:
    return load_label()["agent"].get("default_store", "")


def stored_enum_value(predicate: str, value: str) -> str:
    """Map a display word back to the fixed enum value the SQL joins on.

    The label renames what a status READS as -- DELIVERED shows as "Settled" for
    an insurance carrier -- but the stored value is data-model shape. A user who
    says "mark it settled" must not end up writing SETTLED, which no view keys
    on, so the case would silently drop out of every status filter.

    Unrecognised values pass through untouched: a predicate with no enum, or a
    genuinely new value, is the caller's business. Matching is case-insensitive
    and ignores spacing, so "on case", "On Case" and "ON_CASE" all resolve.
    """
    enums = load_label().get("enums", {})
    # The field and its enum usually share a name; these are the ones that don't.
    by_field = {
        "store_zone": "zone",
        "task_status": "task_status",
        "delivery_task_status": "task_status",
        "health_status": "capacity_health",
    }
    name = by_field.get(predicate, predicate)
    mapping = enums.get(name)
    if not mapping:
        return value

    def norm(s: str) -> str:
        return "".join(ch for ch in s.lower() if ch.isalnum())

    target = norm(value)
    # Already a stored value.
    for stored in mapping:
        if norm(stored) == target:
            return stored
    # A display word for one.
    for stored, shown in mapping.items():
        if norm(shown) == target:
            return stored
    return value


def order_prefix() -> str:
    """Order-number prefix, e.g. 'FM-'. Used when the agent mints an order."""
    return load_label()["vocabulary"]["order"]["id_prefix"]


# ---------------------------------------------------------------------------
# Display aliasing for tool RETURN payloads.
#
# The tools hand the model JSON keyed by the fixed wire field names, and the
# model renders those keys as prose: `has_perishable_items` comes back to the
# operator as "Has Perishable Items: Yes" on a mortgage loan file. The system
# prompt cannot prevent it -- the key is the only name the model is given.
#
# `web/src` has solved this since white-labeling landed: HighlightedJson runs
# keys through aliasColumn() and values through displayValue() at render time.
# These are the same two maps, applied at the tool boundary instead.
#
# Display only. What the tools WRITE is untouched -- write_triples still sends
# raw predicates, and stored_enum_value() above still maps display words back to
# the fixed value on the way in.
# ---------------------------------------------------------------------------

# Keys whose value is a subject id or a fixed enum the agent must be able to
# quote back verbatim in a later tool call. Their names are aliased; their
# values are left exactly as stored.
_ID_KEYS = frozenset(
    {
        "customer_id", "store_id", "product_id", "order_id", "inventory_id",
        "courier_id", "task_id", "line_id", "subject_id", "assigned_courier_id",
        "predicate", "object_type", "batch_id", "thread_id",
    }
)

_CLASS_VOCABULARY = {
    "Customer": "customer",
    "Store": "store",
    "Product": "product",
    "InventoryItem": "inventory",
    "Order": "order",
    "OrderLine": "orderline",
    "Courier": "courier",
    "DeliveryTask": "task",
}


def entity_word(key: str, form: str = "one") -> str:
    """A display word for an entity type, e.g. entity_word("courier", "many").

    `perishable` is not an entity and carries `adjective` rather than one/many.
    """
    vocab = load_label().get("vocabulary", {}).get(key)
    if not vocab:
        return key
    return vocab.get(form) or vocab.get("one") or vocab.get("adjective") or key


# Entity nouns that appear as a token inside a synthetic key. Only unambiguous
# ones: "item" is left alone because `critical_items` means inventory items in
# one place and line items in another, and guessing wrong is worse than leaving
# a word that no label reserves anyway.
_NOUN_TOKENS = {
    "store": "store", "stores": "store",
    # not an entity, but the default vertical's most conspicuous word: keys like
    # `is_perishable` and `perishable_item` appear in OpenSearch payloads and no
    # label authors an alias for them.
    "perishable": "perishable",
    "order": "order", "orders": "order",
    "product": "product", "products": "product",
    "inventory": "inventory",
    "customer": "customer", "customers": "customer",
    "courier": "courier", "couriers": "courier",
}


def alias_column(name: str) -> str:
    """Wire field name -> the name this deployment shows for it.

    An explicit `aliases.columns` entry always wins. Failing that, substitute any
    entity noun appearing as a token in the key: the health tool returns
    aggregates like `total_stores` and `critical_stores` that no label authors,
    because they are not columns of anything -- but the model still reads them
    out as "Total Stores" on a mortgage demo.
    """
    explicit = load_label().get("aliases", {}).get("columns", {}).get(name)
    if explicit:
        return explicit
    parts = name.split("_")
    if not any(part in _NOUN_TOKENS for part in parts):
        return name
    out = []
    for part in parts:
        key = _NOUN_TOKENS.get(part)
        if not key:
            out.append(part)
            continue
        form = "many" if part.endswith("s") and part != "inventory" else "one"
        word = entity_word(key, form).lower()
        # the composed name is identifier-shaped, so spaces and hyphens in a
        # display word ("rate-locked", "fulfillment center") both become _
        out.append(re.sub(r"[^a-z0-9]+", "_", word).strip("_"))
    return "_".join(out)


def alias_class(class_name: str) -> str:
    """Ontology class name -> display word, e.g. "Courier" -> "Underwriter"."""
    key = _CLASS_VOCABULARY.get(class_name)
    return entity_word(key, "title") if key else class_name


def alias_subject(subject_id: str) -> str:
    """`order:LN-1001` -> `loan_file:LN-1001`; the local part is never touched."""
    if not isinstance(subject_id, str) or ":" not in subject_id:
        return subject_id
    prefix, _, rest = subject_id.partition(":")
    if prefix not in load_label().get("vocabulary", {}):
        return subject_id
    return f"{entity_word(prefix).lower().replace(' ', '_')}:{rest}"


def display_enum(field: str, value: Any) -> Any:
    """A stored enum value as this deployment shows it; anything else passes."""
    if not isinstance(value, str):
        return value
    lab = load_label()
    enums = lab.get("enums", {})
    which = lab.get("enum_fields", {}).get(field, field)
    for name in (which, field):
        mapping = enums.get(name)
        if mapping and value in mapping:
            return mapping[value]
    # store_zone/zone and friends: fall back to any enum that owns the value.
    for mapping in enums.values():
        if value in mapping and value.isupper():
            return mapping[value]
    return value


def alias_payload(obj: Any) -> Any:
    """Recursively alias field NAMES, and enum values, for display.

    Applied to what a tool returns, so the model narrates in this deployment's
    vocabulary instead of reading the wire schema aloud.
    """
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            shown = alias_column(key)
            if key in _ID_KEYS:
                out[shown] = alias_payload(value) if isinstance(value, (dict, list)) else value
            elif isinstance(value, (dict, list)):
                out[shown] = alias_payload(value)
            elif isinstance(value, str):
                nested = _alias_embedded_json(value)
                out[shown] = nested if nested is not None else display_enum(key, value)
            else:
                out[shown] = value
        return out
    if isinstance(obj, list):
        return [alias_payload(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Tool DESCRIPTIONS.
#
# LangChain ships each tool's docstring to the model as its description, so the
# prose in them is copy the customer hears back. They are written in the default
# vertical's nouns ("List all stores with IDs and zone info"), and the model
# echoes those nouns even when the payload it gets back is correctly aliased --
# that is where "store id" and "couriers" survived after alias_payload landed.
#
# Rewriting 163 sites by hand would mean editing the model's own instructions,
# which is the last thing to do by hand before a demo. Substituting instead
# keeps one mechanism and tracks any label automatically.
#
# What is protected, because the model has to reproduce it exactly:
#   snake_case identifiers   search_orders, store_id, live_price, order_status
#   subject ids              order:FM-1001, store:BK-01
#   quoted literals          "summary", "inventory_risk"
#   fixed enum values        DELIVERED, OUT_FOR_DELIVERY
# ---------------------------------------------------------------------------

_DOC_NOUNS = (
    ("orderline", "orderline"), ("orderlines", "orderline"),
    ("order", "order"), ("orders", "order"),
    ("store", "store"), ("stores", "store"),
    ("product", "product"), ("products", "product"),
    ("inventory", "inventory"),
    ("customer", "customer"), ("customers", "customer"),
    ("courier", "courier"), ("couriers", "courier"),
)

_PROTECT = re.compile(
    r"`[^`]*`"                                  # backticked
    r"|\"[^\"]*\"|'[^']*'"                      # quoted
    r"|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b"       # snake_case
    r"|\b(?:order|orderline|store|product|inventory|customer|courier|task):[A-Za-z0-9_\-]+"
    r"|\b[A-Z][A-Z_]{2,}\b"                     # SHOUTING enum values
)


def _plural(word: str) -> bool:
    return word.endswith("s") and word != "inventory"


def localize_doc(doc: str | None) -> str | None:
    """Rewrite a tool docstring's prose into the active label's nouns."""
    if not doc:
        return doc
    vocab = load_label().get("vocabulary", {})
    if not vocab:
        return doc

    def sub_words(chunk: str) -> str:
        def one(m: re.Match[str]) -> str:
            raw = m.group(0)
            key = raw.lower()
            vkey = dict(_DOC_NOUNS).get(key)
            if not vkey or vkey not in vocab:
                return raw
            form = "many" if _plural(key) else "one"
            word = entity_word(vkey, form)
            if raw[0].isupper():
                word = word[:1].upper() + word[1:]
            return word

        pattern = r"\b(" + "|".join(sorted({w for w, _ in _DOC_NOUNS}, key=len, reverse=True)) + r")\b"
        return re.sub(pattern, one, chunk, flags=re.I)

    out, last = [], 0
    for m in _PROTECT.finditer(doc):
        out.append(sub_words(doc[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(sub_words(doc[last:]))
    return "".join(out)


def _alias_embedded_json(value: str) -> str | None:
    """Alias inside a JSON document carried as a string, or None if it is not one.

    `line_items` comes out of OpenSearch as serialized JSON, so its nested
    `product_name` / `inventory_id` / `is_perishable` keys are invisible to a walk
    over the outer dict -- which is how "perishable item: yes" survived on a
    mortgage demo after every other key was aliased. Re-serialized the same way
    it arrived, so nothing downstream sees a shape change.
    """
    probe = value.lstrip()
    if not probe.startswith(("[", "{")):
        return None
    try:
        parsed = json.loads(value)
    except (ValueError, TypeError):
        return None
    if not isinstance(parsed, (list, dict)):
        return None
    return json.dumps(alias_payload(parsed))
