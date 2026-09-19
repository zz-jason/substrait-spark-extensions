#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Contract loading, canonical digest and validation."""

from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "protocol" / "contract.json"
SCHEMA_PATH = ROOT / "protocol" / "contract.schema.json"
YAML_PATH = ROOT / "extensions" / "functions_spark.yaml"
GENERATED_PATH = ROOT / "generated"
CAPABILITIES_PATH = ROOT / "capabilities" / "capabilities.json"

SEMVER_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[a-z][a-z0-9_.]*$")
URN_RE = re.compile(r"^extension:[A-Za-z0-9._-]+:[A-Za-z0-9._-]+$")
SIGNATURE_RE = re.compile(r"^[a-z][a-z0-9_]*:[a-z0-9_]*$")
ENUM_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
KIND_ORDER = {"SCALAR": 0, "AGGREGATE": 1, "WINDOW": 2}
OUTPUT_OPS = {
    "CONCRETE": {"op", "type"},
    "TYPE_ARGUMENT": {"op", "index"},
    "SAME_AS_ARGUMENT": {"op", "index", "nullable"},
    "DECIMAL": {"op", "nullable", "precision", "scale"},
}
INTEGER_OPS = {
    "CONSTANT": {"op", "value"},
    "ARGUMENT_PRECISION": {"op", "index"},
    "ARGUMENT_SCALE": {"op", "index"},
    "ADD": {"op", "left", "right"},
    "MIN": {"op", "left", "right"},
}

class ContractError(ValueError):
    pass


def reject_duplicate_keys(pairs: Iterable[Tuple[str, Any]]) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ContractError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream, object_pairs_hook=reject_duplicate_keys)


def canonical_contract_bytes(contract: Dict[str, Any]) -> bytes:
    semantic = copy.deepcopy(contract)
    semantic["protocol"].pop("canonicalSha256", None)
    return json.dumps(
        semantic,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(contract: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_contract_bytes(contract)).hexdigest()


def require_keys(value: Dict[str, Any], required: Iterable[str], allowed: Iterable[str], context: str) -> None:
    required_set = set(required)
    allowed_set = set(allowed)
    missing = required_set - set(value)
    extra = set(value) - allowed_set
    if missing or extra:
        raise ContractError(f"{context}: missing={sorted(missing)}, extra={sorted(extra)}")


def require_sorted_unique(values: List[str], context: str) -> None:
    if values != sorted(set(values)):
        raise ContractError(f"{context} must be sorted and duplicate-free")


def validate_integer_formula(formula: Dict[str, Any], argument_count: int, context: str) -> None:
    if not isinstance(formula, dict) or formula.get("op") not in INTEGER_OPS:
        raise ContractError(f"{context}: unsupported integer formula")
    op = formula["op"]
    require_keys(formula, INTEGER_OPS[op], INTEGER_OPS[op], context)
    if op == "CONSTANT":
        if type(formula["value"]) is not int or not 0 <= formula["value"] <= 38:
            raise ContractError(f"{context}: invalid constant")
    elif op in {"ARGUMENT_PRECISION", "ARGUMENT_SCALE"}:
        if type(formula["index"]) is not int or not 0 <= formula["index"] < argument_count:
            raise ContractError(f"{context}: invalid argument index")
    else:
        validate_integer_formula(formula["left"], argument_count, context + ".left")
        validate_integer_formula(formula["right"], argument_count, context + ".right")


def validate_custom_definition(definition: Dict[str, Any], context: str) -> None:
    require_keys(definition, {"arguments", "output"}, {"arguments", "output"}, context)
    arguments = definition["arguments"]
    if not isinstance(arguments, list):
        raise ContractError(f"{context}.arguments must be an array")
    for index, argument in enumerate(arguments):
        where = f"{context}.arguments[{index}]"
        if not isinstance(argument, dict) or argument.get("kind") not in {"VALUE", "TYPE", "ENUM"}:
            raise ContractError(f"{where}: invalid argument kind")
        if argument["kind"] == "ENUM":
            require_keys(argument, {"kind", "values"}, {"kind", "values"}, where)
            require_sorted_unique(argument["values"], where + ".values")
            if not all(ENUM_RE.fullmatch(value) for value in argument["values"]):
                raise ContractError(f"{where}: invalid enum value")
        else:
            require_keys(argument, {"kind", "type"}, {"kind", "type"}, where)
            if not isinstance(argument["type"], str) or not argument["type"]:
                raise ContractError(f"{where}: invalid type")
    output = definition["output"]
    if not isinstance(output, dict) or output.get("op") not in OUTPUT_OPS:
        raise ContractError(f"{context}.output: unsupported output operation")
    op = output["op"]
    require_keys(output, OUTPUT_OPS[op], OUTPUT_OPS[op], context + ".output")
    if op in {"TYPE_ARGUMENT", "SAME_AS_ARGUMENT"}:
        if type(output["index"]) is not int or not 0 <= output["index"] < len(arguments):
            raise ContractError(f"{context}.output: invalid argument index")
    if op == "DECIMAL":
        validate_integer_formula(output["precision"], len(arguments), context + ".output.precision")
        validate_integer_formula(output["scale"], len(arguments), context + ".output.scale")


PAYLOAD_KINDS = {"STRING", "NUMBER", "STRUCT", "LIST", "ENUM"}


def validate_payload_fields(fields: Any, context: str) -> None:
    if not isinstance(fields, list) or not fields:
        raise ContractError(f"{context} must be a non-empty array")
    names = []
    for index, field in enumerate(fields):
        where = f"{context}[{index}]"
        if not isinstance(field, dict):
            raise ContractError(f"{where} must be an object")
        kind = field.get("kind")
        if kind not in PAYLOAD_KINDS:
            raise ContractError(f"{where}: unsupported payload field kind")
        if kind == "STRUCT":
            require_keys(field, {"name", "kind", "fields"}, {"name", "kind", "fields"}, where)
            validate_payload_fields(field["fields"], where + ".fields")
        elif kind == "LIST":
            require_keys(field, {"name", "kind", "element"}, {"name", "kind", "element"}, where)
            element = field["element"]
            if not isinstance(element, dict) or element.get("kind") != "STRUCT":
                raise ContractError(f"{where}.element must be a struct")
            require_keys(element, {"kind", "fields"}, {"kind", "fields"}, where + ".element")
            validate_payload_fields(element["fields"], where + ".element.fields")
        elif kind == "ENUM":
            require_keys(field, {"name", "kind", "values"}, {"name", "kind", "values"}, where)
            require_sorted_unique(field["values"], where + ".values")
        else:
            require_keys(field, {"name", "kind"}, {"name", "kind"}, where)
        if not isinstance(field["name"], str) or not field["name"]:
            raise ContractError(f"{where}: invalid payload field name")
        names.append(field["name"])
    if names != sorted(set(names)):
        raise ContractError(f"{context} names must be sorted and unique")


def validate_payloads(contract: Dict[str, Any]) -> None:
    protocol = contract["protocol"]
    payloads = contract.get("payloads")
    if not isinstance(payloads, dict):
        raise ContractError("contract.payloads must be an object")
    require_keys(
        payloads,
        {"planSemantics", "sparkReadSemantics"},
        {"planSemantics", "sparkReadSemantics"},
        "payloads",
    )
    expected_type_urls = {
        "planSemanticsTypeUrl": f"type.googleapis.com/{protocol['protoPackage']}.PlanSemantics",
        "sparkReadSemanticsTypeUrl": f"type.googleapis.com/{protocol['protoPackage']}.SparkReadSemantics",
    }
    for name, payload in payloads.items():
        context = f"payloads.{name}"
        require_keys(
            payload,
            {"encoding", "typeUrlField", "fields"},
            {"encoding", "typeUrlField", "fields", "version", "rebaseModes", "sparkTypeNames", "sparkTypePattern"},
            context,
        )
        if payload["encoding"] != "google.protobuf.Struct":
            raise ContractError(f"{context}: unsupported payload encoding")
        field = payload["typeUrlField"]
        if field not in expected_type_urls:
            raise ContractError(f"{context}: unknown type URL field")
        if protocol[field] != expected_type_urls[field]:
            raise ContractError(f"{context}: type URL does not match the protobuf package")
        validate_payload_fields(payload["fields"], context + ".fields")
    read = payloads["sparkReadSemantics"]
    for key in ("version", "rebaseModes", "sparkTypeNames", "sparkTypePattern"):
        if key not in read:
            raise ContractError(f"payloads.sparkReadSemantics.{key} is required")
    if type(read["version"]) is not int or read["version"] != 1:
        raise ContractError("payloads.sparkReadSemantics.version must be 1")
    require_sorted_unique(read["rebaseModes"], "payloads.sparkReadSemantics.rebaseModes")
    require_sorted_unique(read["sparkTypeNames"], "payloads.sparkReadSemantics.sparkTypeNames")
    if not all(ENUM_RE.fullmatch(value) for value in read["sparkTypeNames"]):
        raise ContractError("payloads.sparkReadSemantics.sparkTypeNames must be canonical enum names")
    re.compile(read["sparkTypePattern"])


def validate_contract(contract: Dict[str, Any]) -> None:
    require_keys(
        contract,
        {"$schema", "schemaVersion", "protocol", "functions", "payloads"},
        {"$schema", "schemaVersion", "protocol", "functions", "payloads"},
        "contract",
    )
    if contract["$schema"] != "contract.schema.json" or contract["schemaVersion"] != 2:
        raise ContractError("unsupported contract schema")
    protocol = contract["protocol"]
    protocol_keys = {
        "id", "version", "substraitVersion", "protoPackage", "planSemanticsTypeUrl",
        "sparkReadSemanticsTypeUrl", "functionExtensionUrn", "functionExtensionSha256",
        "canonicalSha256", "canonicalization",
    }
    require_keys(protocol, protocol_keys, protocol_keys, "protocol")
    if protocol["version"] != "0.1.0" or not SEMVER_RE.fullmatch(protocol["version"]):
        raise ContractError("protocol version must be 0.1.0")
    if protocol["substraitVersion"] != "0.98.0":
        raise ContractError("Substrait version must be 0.98.0")
    if protocol["protoPackage"] != "io.github.zzjason.substrait.spark.v1":
        raise ContractError("unexpected protobuf package")
    expected_urls = {
        "planSemanticsTypeUrl": "type.googleapis.com/io.github.zzjason.substrait.spark.v1.PlanSemantics",
        "sparkReadSemanticsTypeUrl": "type.googleapis.com/io.github.zzjason.substrait.spark.v1.SparkReadSemantics",
    }
    for field, expected in expected_urls.items():
        if protocol[field] != expected:
            raise ContractError(f"unexpected {field}")
    actual_digest = canonical_sha256(contract)
    if protocol["canonicalSha256"] != actual_digest or not SHA_RE.fullmatch(actual_digest):
        raise ContractError(f"canonical SHA-256 mismatch: expected {actual_digest}")
    if not SHA_RE.fullmatch(protocol["functionExtensionSha256"]):
        raise ContractError("invalid function extension SHA-256")
    functions = contract["functions"]
    ids = []
    identities = []
    for index, function in enumerate(functions):
        context = f"functions[{index}]"
        required = {"id", "urn", "signature", "kind", "callSites", "options"}
        allowed = required | {"customDefinition"}
        require_keys(function, required, allowed, context)
        if not ID_RE.fullmatch(function["id"]):
            raise ContractError(f"{context}: invalid id")
        if not URN_RE.fullmatch(function["urn"]):
            raise ContractError(f"{context}: invalid URN")
        if not SIGNATURE_RE.fullmatch(function["signature"]):
            raise ContractError(f"{context}: invalid compound signature")
        if function["kind"] not in KIND_ORDER:
            raise ContractError(f"{context}: invalid kind")
        allowed_call_sites = {
            "SCALAR": [["SCALAR"]],
            "AGGREGATE": [["AGGREGATE"], ["AGGREGATE", "WINDOW"]],
            "WINDOW": [["WINDOW"]],
        }[function["kind"]]
        if function["callSites"] not in allowed_call_sites:
            raise ContractError(
                f"{context}: kind {function['kind']} does not admit call sites {function['callSites']}"
            )
        option_names = list(function["options"])
        if option_names != sorted(option_names):
            raise ContractError(f"{context}: options must be sorted")
        for name, values in function["options"].items():
            require_sorted_unique(values, context + ".options." + name)
            if not values or not all(ENUM_RE.fullmatch(value) for value in values):
                raise ContractError(f"{context}: invalid option value")
        if "customDefinition" in function:
            if function["urn"] != protocol["functionExtensionUrn"]:
                raise ContractError(f"{context}: custom definition uses the wrong URN")
            validate_custom_definition(function["customDefinition"], context + ".customDefinition")
        ids.append(function["id"])
        identities.append((KIND_ORDER[function["kind"]], function["urn"], function["signature"]))
    if ids != sorted(set(ids)):
        raise ContractError("function ids must be sorted and unique")
    if len(set(identities)) != len(identities):
        raise ContractError("function identities must be unique")
    if len(functions) != 133:
        raise ContractError(f"expected the current 133-function profile, found {len(functions)}")
    custom = [function for function in functions if function["urn"] == protocol["functionExtensionUrn"]]
    if len(custom) != 14 or not all("customDefinition" in function for function in custom):
        raise ContractError("expected all fourteen custom Spark SQL extension definitions")
    actual_yaml_sha = hashlib.sha256(YAML_PATH.read_bytes()).hexdigest()
    if actual_yaml_sha != protocol["functionExtensionSha256"]:
        raise ContractError("functions_spark.yaml differs from its canonical protocol digest")
    validate_payloads(contract)
    # Loading the schema with duplicate-key rejection keeps it reviewable even without jsonschema.
    schema = load_json(SCHEMA_PATH)
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ContractError("contract schema must use JSON Schema draft 2020-12")
    if schema.get("properties", {}).get("schemaVersion", {}).get("const") != contract["schemaVersion"]:
        raise ContractError("contract schema and contract disagree on schemaVersion")


