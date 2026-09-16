#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Validate the canonical contract and generate dependency-free catalogs."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
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


def validate_contract(contract: Dict[str, Any]) -> None:
    require_keys(
        contract,
        {"$schema", "schemaVersion", "protocol", "functions"},
        {"$schema", "schemaVersion", "protocol", "functions"},
        "contract",
    )
    if contract["$schema"] != "contract.schema.json" or contract["schemaVersion"] != 1:
        raise ContractError("unsupported contract schema")
    protocol = contract["protocol"]
    protocol_keys = {
        "id", "version", "substraitVersion", "protoPackage", "planSemanticsTypeUrl",
        "sparkReadSemanticsTypeUrl", "functionExtensionUrn", "functionExtensionSha256",
        "canonicalSha256", "canonicalization",
    }
    require_keys(protocol, protocol_keys, protocol_keys, "protocol")
    if protocol["version"] != "1.1.0" or not SEMVER_RE.fullmatch(protocol["version"]):
        raise ContractError("protocol version must be 1.1.0")
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
        expected_call_sites = ["SCALAR"] if function["kind"] == "SCALAR" else (
            ["AGGREGATE", "WINDOW"] if function["kind"] == "AGGREGATE" else ["WINDOW"]
        )
        if function["callSites"] != expected_call_sites:
            raise ContractError(f"{context}: invalid call sites")
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
    if len(functions) != 132:
        raise ContractError(f"expected the current 132-function profile, found {len(functions)}")
    custom = [function for function in functions if function["urn"] == protocol["functionExtensionUrn"]]
    if len(custom) != 13 or not all("customDefinition" in function for function in custom):
        raise ContractError("expected all thirteen custom Spark SQL extension definitions")
    actual_yaml_sha = hashlib.sha256(YAML_PATH.read_bytes()).hexdigest()
    if actual_yaml_sha != protocol["functionExtensionSha256"]:
        raise ContractError("functions_spark.yaml differs from its canonical protocol digest")
    # Loading the schema with duplicate-key rejection keeps it reviewable even without jsonschema.
    schema = load_json(SCHEMA_PATH)
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ContractError("contract schema must use JSON Schema draft 2020-12")


def scala_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def cpp_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def option_projection(function: Dict[str, Any]) -> Dict[str, List[str]]:
    return {name: values for name, values in function["options"].items() if values}


def render_protocol_identity_scala(contract: Dict[str, Any]) -> str:
    protocol = contract["protocol"]
    major, minor, patch = protocol["version"].split(".")
    lines = [
        "// SPDX-License-Identifier: Apache-2.0",
        "// Generated by tools/generate.py. Do not edit.",
        "package io.github.zzjason.substrait.spark.v1",
        "",
        "object ProtocolIdentity {",
        f"  final val Version = {scala_string(protocol['version'])}",
        f"  final val Major = {major}",
        f"  final val Minor = {minor}",
        f"  final val Patch = {patch}",
        f"  final val SubstraitVersion = {scala_string(protocol['substraitVersion'])}",
        f"  final val CanonicalSha256 = {scala_string(protocol['canonicalSha256'])}",
        f"  final val FunctionExtensionUrn = {scala_string(protocol['functionExtensionUrn'])}",
        f"  final val PlanSemanticsTypeUrl = {scala_string(protocol['planSemanticsTypeUrl'])}",
        f"  final val SparkReadSemanticsTypeUrl = {scala_string(protocol['sparkReadSemanticsTypeUrl'])}",
        "}",
        "",
    ]
    return "\n".join(lines)


def scala_seq(values: List[str]) -> str:
    return "Vector(" + ", ".join(scala_string(value) for value in values) + ")"


def scala_map(options: Dict[str, List[str]]) -> str:
    if not options:
        return "Map.empty"
    entries = [f"{scala_string(name)} -> {scala_seq(values)}" for name, values in sorted(options.items())]
    return "Map(" + ", ".join(entries) + ")"


def render_function_catalog_scala(contract: Dict[str, Any]) -> str:
    lines = [
        "// SPDX-License-Identifier: Apache-2.0",
        "// Generated by tools/generate.py. Do not edit.",
        "package io.github.zzjason.substrait.spark.v1",
        "",
        "sealed trait FunctionKind",
        "object FunctionKind {",
        "  case object Scalar extends FunctionKind",
        "  case object Aggregate extends FunctionKind",
        "  case object Window extends FunctionKind",
        "}",
        "",
        "final case class FunctionDescriptor(",
        "    id: String, urn: String, signature: String, kind: FunctionKind,",
        "    callSites: Vector[String], options: Map[String, Vector[String]])",
        "",
        "object FunctionCatalog {",
        "  import FunctionKind._",
        "  val Functions: Vector[FunctionDescriptor] = Vector(",
    ]
    kind = {"SCALAR": "Scalar", "AGGREGATE": "Aggregate", "WINDOW": "Window"}
    for index, function in enumerate(contract["functions"]):
        suffix = "," if index + 1 < len(contract["functions"]) else ""
        options = option_projection(function)
        lines.append(
            "    FunctionDescriptor(" + ", ".join([
                scala_string(function["id"]), scala_string(function["urn"]),
                scala_string(function["signature"]), kind[function["kind"]],
                scala_seq(function["callSites"]), scala_map(options),
            ]) + ")" + suffix
        )
    lines += [
        "  )",
        "  val ByIdentity: Map[(FunctionKind, String, String), FunctionDescriptor] =",
        "    Functions.map(value => (value.kind, value.urn, value.signature) -> value).toMap",
        "}",
        "",
    ]
    return "\n".join(lines)


def render_protocol_identity_hpp(contract: Dict[str, Any]) -> str:
    protocol = contract["protocol"]
    major, minor, patch = protocol["version"].split(".")
    digest_bytes = ", ".join("0x" + protocol["canonicalSha256"][index:index + 2] for index in range(0, 64, 2))
    return "\n".join([
        "// SPDX-License-Identifier: Apache-2.0",
        "// Generated by tools/generate.py. Do not edit.",
        "#pragma once",
        "#include <array>",
        "#include <cstdint>",
        "#include <string_view>",
        "",
        "namespace io::github::zzjason::substrait::spark::v1 {",
        f"inline constexpr std::string_view kProtocolVersion = {cpp_string(protocol['version'])};",
        f"inline constexpr std::uint32_t kProtocolMajor = {major};",
        f"inline constexpr std::uint32_t kProtocolMinor = {minor};",
        f"inline constexpr std::uint32_t kProtocolPatch = {patch};",
        f"inline constexpr std::string_view kSubstraitVersion = {cpp_string(protocol['substraitVersion'])};",
        f"inline constexpr std::string_view kCanonicalSha256Hex = {cpp_string(protocol['canonicalSha256'])};",
        f"inline constexpr std::array<std::uint8_t, 32> kCanonicalSha256 = {{{digest_bytes}}};",
        f"inline constexpr std::string_view kFunctionExtensionUrn = {cpp_string(protocol['functionExtensionUrn'])};",
        f"inline constexpr std::string_view kPlanSemanticsTypeUrl = {cpp_string(protocol['planSemanticsTypeUrl'])};",
        f"inline constexpr std::string_view kSparkReadSemanticsTypeUrl = {cpp_string(protocol['sparkReadSemanticsTypeUrl'])};",
        "}  // namespace io::github::zzjason::substrait::spark::v1",
        "",
    ])


def render_function_catalog_hpp(contract: Dict[str, Any]) -> str:
    count = len(contract["functions"])
    return "\n".join([
        "// SPDX-License-Identifier: Apache-2.0",
        "// Generated by tools/generate.py. Do not edit.",
        "#pragma once",
        "#include <array>",
        "#include <string_view>",
        "",
        "namespace io::github::zzjason::substrait::spark::v1 {",
        "enum class FunctionKind { kScalar, kAggregate, kWindow };",
        "struct FunctionDescriptor {",
        "  std::string_view id;",
        "  std::string_view urn;",
        "  std::string_view signature;",
        "  FunctionKind kind;",
        "  std::string_view call_sites_csv;",
        "  std::string_view options_json;",
        "};",
        f"extern const std::array<FunctionDescriptor, {count}> kFunctionCatalog;",
        "const FunctionDescriptor *FindFunction(FunctionKind kind, std::string_view urn, std::string_view signature);",
        "}  // namespace io::github::zzjason::substrait::spark::v1",
        "",
    ])


def compact_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def render_function_catalog_cpp(contract: Dict[str, Any]) -> str:
    kind = {"SCALAR": "kScalar", "AGGREGATE": "kAggregate", "WINDOW": "kWindow"}
    lines = [
        "// SPDX-License-Identifier: Apache-2.0",
        "// Generated by tools/generate.py. Do not edit.",
        '#include "substrait_spark/function_catalog.hpp"',
        "",
        "namespace io::github::zzjason::substrait::spark::v1 {",
        f"const std::array<FunctionDescriptor, {len(contract['functions'])}> kFunctionCatalog = {{{{",
    ]
    for function in contract["functions"]:
        options = option_projection(function)
        values = [
            function["id"], function["urn"], function["signature"],
            ",".join(function["callSites"]), compact_json(options),
        ]
        lines.append(
            "    {" + ", ".join([
                cpp_string(values[0]), cpp_string(values[1]), cpp_string(values[2]),
                "FunctionKind::" + kind[function["kind"]],
                cpp_string(values[3]), cpp_string(values[4]),
            ]) + "},"
        )
    lines += [
        "}};",
        "",
        "const FunctionDescriptor *FindFunction(FunctionKind kind, std::string_view urn, std::string_view signature) {",
        "  for (const auto &function : kFunctionCatalog) {",
        "    if (function.kind == kind && function.urn == urn && function.signature == signature) return &function;",
        "  }",
        "  return nullptr;",
        "}",
        "}  // namespace io::github::zzjason::substrait::spark::v1",
        "",
    ]
    return "\n".join(lines)


def render_capabilities(contract: Dict[str, Any]) -> str:
    projection = {
        "schemaVersion": 1,
        "protocolVersion": contract["protocol"]["version"],
        "canonicalSha256": contract["protocol"]["canonicalSha256"],
        "substraitVersion": contract["protocol"]["substraitVersion"],
        "matching": "EXACT_KIND_URN_COMPOUND_SIGNATURE",
        "unsupportedBehavior": "REJECT_BEFORE_BINDING_OR_EXECUTION",
        "planSemanticsTypeUrl": contract["protocol"]["planSemanticsTypeUrl"],
        "sparkReadSemanticsTypeUrl": contract["protocol"]["sparkReadSemanticsTypeUrl"],
        "readSemantics": {
            "calendarRebaseModes": ["CORRECTED", "EXCEPTION", "LEGACY"],
            "int96TimestampConversions": ["INT96_TIMESTAMP_CONVERSION_DISABLED", "INT96_TIMESTAMP_CONVERSION_ENABLED"],
            "parquetTimestampEncodings": ["INT64_MICROS", "INT64_MILLIS", "INT64_NANOS", "INT96"],
            "physicalTimestampSemantics": ["LOCAL_DATETIME", "UTC_INSTANT"],
            "sparkTimestampIdentities": ["SPARK_TIMESTAMP_LTZ", "SPARK_TIMESTAMP_NTZ"],
        },
        "functions": [
            {
                "id": function["id"],
                "urn": function["urn"],
                "signature": function["signature"],
                "kind": function["kind"],
                "callSites": function["callSites"],
                "options": option_projection(function),
            }
            for function in contract["functions"]
        ],
    }
    return json.dumps(projection, indent=2, ensure_ascii=False, allow_nan=False) + "\n"


def rendered_files(contract: Dict[str, Any]) -> Dict[str, bytes]:
    text_files = {
        "generated/scala/io/github/zzjason/substrait/spark/v1/ProtocolIdentity.scala": render_protocol_identity_scala(contract),
        "generated/scala/io/github/zzjason/substrait/spark/v1/FunctionCatalog.scala": render_function_catalog_scala(contract),
        "generated/cpp/include/substrait_spark/protocol_identity.hpp": render_protocol_identity_hpp(contract),
        "generated/cpp/include/substrait_spark/function_catalog.hpp": render_function_catalog_hpp(contract),
        "generated/cpp/src/function_catalog.cpp": render_function_catalog_cpp(contract),
        "capabilities/capabilities.json": render_capabilities(contract),
    }
    return {path: text.encode("utf-8") for path, text in text_files.items()}


def write_rendered(files: Dict[str, bytes], root: Path) -> None:
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)


def generated_relative_paths() -> List[str]:
    paths = []
    if GENERATED_PATH.exists():
        paths += [path.relative_to(ROOT).as_posix() for path in GENERATED_PATH.rglob("*") if path.is_file()]
    if CAPABILITIES_PATH.exists():
        paths.append(CAPABILITIES_PATH.relative_to(ROOT).as_posix())
    return sorted(paths)


def check_rendered(expected: Dict[str, bytes]) -> None:
    actual_paths = generated_relative_paths()
    expected_paths = sorted(expected)
    errors = []
    for path in sorted(set(actual_paths) | set(expected_paths)):
        target = ROOT / path
        if path not in expected:
            errors.append(f"extra: {path}")
        elif not target.exists():
            errors.append(f"missing: {path}")
        elif target.read_bytes() != expected[path]:
            errors.append(f"changed: {path}")
    if errors:
        raise ContractError("generated output is stale:\n" + "\n".join(errors))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["validate", "generate", "check"])
    args = parser.parse_args()
    contract = load_json(CONTRACT_PATH)
    validate_contract(contract)
    if args.command == "validate":
        print(f"valid contract {contract['protocol']['version']} {contract['protocol']['canonicalSha256']}")
        return 0
    expected = rendered_files(contract)
    if args.command == "check":
        check_rendered(expected)
        print(f"generated output is current ({len(expected)} files)")
        return 0
    with tempfile.TemporaryDirectory(prefix="substrait-spark-generate-") as directory:
        temporary_root = Path(directory)
        write_rendered(expected, temporary_root)
        if GENERATED_PATH.exists():
            shutil.rmtree(GENERATED_PATH)
        shutil.copytree(temporary_root / "generated", GENERATED_PATH)
        CAPABILITIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(temporary_root / "capabilities" / "capabilities.json", CAPABILITIES_PATH)
    print(f"generated {len(expected)} files")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as error:
        print(f"error: {error}", file=sys.stderr)
        raise SystemExit(1)
