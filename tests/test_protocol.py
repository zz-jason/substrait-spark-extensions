# SPDX-License-Identifier: Apache-2.0

import copy
import hashlib
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


generate = load_module("protocol_generate", ROOT / "tools" / "generate.py")
builder = load_module("protocol_builder", ROOT / "tools" / "build_artifact.py")


class ContractTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = generate.load_json(ROOT / "protocol" / "contract.json")

    def test_contract_validates_and_has_canonical_identity(self):
        generate.validate_contract(self.contract)
        self.assertEqual("0.1.0", self.contract["protocol"]["version"])
        # The digest is derived from the contract content, so it is checked instead of pinned.
        self.assertEqual(
            self.contract["protocol"]["canonicalSha256"],
            generate.canonical_sha256(self.contract),
        )

    def test_contract_is_implementation_neutral(self):
        self.assertNotIn("capabilityProfiles", self.contract)
        self.assertNotIn("sourceSnapshots", self.contract)
        self.assertEqual(133, len(self.contract["functions"]))
        self.assertEqual(
            Counter({"SCALAR": 85, "AGGREGATE": 43, "WINDOW": 5}),
            Counter(function["kind"] for function in self.contract["functions"]),
        )
        urn_counts = Counter(function["urn"] for function in self.contract["functions"])
        self.assertEqual(71, urn_counts["extension:io.substrait:functions_arithmetic"])
        self.assertEqual(14, urn_counts["extension:io.github.zz-jason:functions_spark"])

    def test_custom_function_identities_are_exact(self):
        custom_urn = self.contract["protocol"]["functionExtensionUrn"]
        actual = {
            (function["kind"], function["signature"])
            for function in self.contract["functions"]
            if function["urn"] == custom_urn
        }
        expected = {
            ("SCALAR", "decimal_divide:dec_dec_dec_req"),
            ("SCALAR", "add:date_i32"),
            ("SCALAR", "raise_error:str"),
            ("SCALAR", "trunc:dec"),
            ("SCALAR", "like_escape:str_str_str"),
            ("SCALAR", "try_add:any_any"),
            ("SCALAR", "try_multiply:any_any"),
            ("SCALAR", "try_subtract:any_any"),
            ("AGGREGATE", "grouping:any"),
            ("AGGREGATE", "stddev_samp:fp64"),
            ("AGGREGATE", "sum:dec"),
            ("AGGREGATE", "avg:dec"),
            ("AGGREGATE", "min:any"),
            ("AGGREGATE", "max:any"),
        }
        self.assertEqual(expected, actual)

    def test_protocol_option_values_are_canonical(self):
        by_identity = {
            (function["urn"], function["signature"]): function
            for function in self.contract["functions"]
        }
        decimal_sum = by_identity[(
            "extension:io.github.zz-jason:functions_spark", "sum:dec"
        )]["options"]["overflow"]
        self.assertEqual(["ERROR", "SATURATE", "SILENT"], decimal_sum)
        like = by_identity[(
            "extension:io.substrait:functions_string", "like:str_str"
        )]["options"]["case_sensitivity"]
        self.assertEqual(["CASE_INSENSITIVE", "CASE_INSENSITIVE_ASCII", "CASE_SENSITIVE"], like)
        floating_divide = by_identity[(
            "extension:io.substrait:functions_arithmetic", "divide:fp64_fp64"
        )]["options"]["rounding"]
        self.assertEqual(["CEILING", "FLOOR", "TIE_AWAY_FROM_ZERO", "TIE_TO_EVEN", "TRUNCATE"], floating_divide)

    def test_modulus_matches_the_upstream_arithmetic_definition(self):
        by_identity = {
            (function["urn"], function["signature"]): function
            for function in self.contract["functions"]
        }
        for token in ("i8", "i16", "i32", "i64"):
            modulus = by_identity[(
                "extension:io.substrait:functions_arithmetic", f"modulus:{token}_{token}"
            )]
            self.assertEqual(
                {
                    "division_type": ["FLOOR", "TRUNCATE"],
                    "on_domain_error": ["ERROR", "NULL"],
                    "overflow": ["ERROR", "SATURATE", "SILENT"],
                },
                modulus["options"],
            )
        divide = by_identity[(
            "extension:io.substrait:functions_arithmetic", "divide:i64_i64"
        )]
        self.assertEqual(["ERROR", "SATURATE", "SILENT"], divide["options"]["overflow"])
        self.assertIn("on_division_by_zero", divide["options"])
        self.assertNotIn("on_division_by_zero", by_identity[(
            "extension:io.substrait:functions_arithmetic", "modulus:i64_i64"
        )]["options"])

    def test_payload_schema_is_the_single_wire_definition(self):
        payloads = self.contract["payloads"]
        self.assertEqual({"planSemantics", "sparkReadSemantics"}, set(payloads))
        for name, payload in payloads.items():
            self.assertEqual("google.protobuf.Struct", payload["encoding"])
            self.assertEqual(
                self.contract["protocol"][payload["typeUrlField"]],
                "type.googleapis.com/"
                + self.contract["protocol"]["protoPackage"]
                + ("." + ("PlanSemantics" if name == "planSemantics" else "SparkReadSemantics")),
            )
        read = payloads["sparkReadSemantics"]
        fields = {field["name"] for field in read["fields"]}
        self.assertEqual(
            {"calendar_rebase", "partition_columns", "protocol_version", "session_timezone", "timestamp_fields"},
            fields,
        )
        self.assertEqual(["CORRECTED"], read["rebaseModes"])

    def test_contract_uses_only_closed_structured_formulas(self):
        allowed_output = set(generate.OUTPUT_OPS)
        allowed_integer = set(generate.INTEGER_OPS)

        def inspect_formula(formula):
            self.assertIn(formula["op"], allowed_integer)
            if formula["op"] in {"ADD", "MIN"}:
                inspect_formula(formula["left"])
                inspect_formula(formula["right"])

        for function in self.contract["functions"]:
            custom = function.get("customDefinition")
            if custom is None:
                continue
            output = custom["output"]
            self.assertIn(output["op"], allowed_output)
            self.assertNotIn("expression", output)
            self.assertNotIn("script", output)
            if output["op"] == "DECIMAL":
                inspect_formula(output["precision"])
                inspect_formula(output["scale"])

    def test_canonical_yaml_matches_the_protocol_digest(self):
        digest = hashlib.sha256((ROOT / "extensions" / "functions_spark.yaml").read_bytes()).hexdigest()
        self.assertEqual(
            self.contract["protocol"]["functionExtensionSha256"],
            digest,
        )

    def test_schema_is_closed_draft_2020_12(self):
        schema = generate.load_json(ROOT / "protocol" / "contract.schema.json")
        self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        self.assertFalse(schema["additionalProperties"])
        self.assertFalse(schema["$defs"]["function"]["additionalProperties"])

    def test_duplicate_json_keys_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "duplicate.json"
            path.write_text('{"a":1,"a":2}\n', encoding="utf-8")
            with self.assertRaises(generate.ContractError):
                generate.load_json(path)

    def test_semantic_mutation_invalidates_the_digest(self):
        changed = copy.deepcopy(self.contract)
        changed["functions"][0]["signature"] = "changed:i8"
        with self.assertRaises(generate.ContractError):
            generate.validate_contract(changed)

    def test_tracked_protocol_files_are_implementation_neutral(self):
        prohibited = "du" + "ck" + "db"
        excluded = {".git", "dist", "__pycache__"}
        violations = []
        for path in ROOT.rglob("*"):
            if not path.is_file() or any(part in excluded for part in path.parts):
                continue
            try:
                content = path.read_text(encoding="utf-8").lower()
            except UnicodeDecodeError:
                continue
            if prohibited in content:
                violations.append(path.relative_to(ROOT).as_posix())
        self.assertEqual([], violations)


class ProtoTest(unittest.TestCase):
    def test_there_is_no_second_wire_schema_definition(self):
        self.assertFalse((ROOT / "proto").exists())

    def test_type_urls_match_proto_package(self):
        contract = generate.load_json(ROOT / "protocol" / "contract.json")
        package = contract["protocol"]["protoPackage"]
        self.assertEqual(
            f"type.googleapis.com/{package}.PlanSemantics",
            contract["protocol"]["planSemanticsTypeUrl"],
        )
        self.assertEqual(
            f"type.googleapis.com/{package}.SparkReadSemantics",
            contract["protocol"]["sparkReadSemanticsTypeUrl"],
        )


class GenerationTest(unittest.TestCase):
    def test_generated_files_are_current_and_deterministic(self):
        contract = generate.load_json(ROOT / "protocol" / "contract.json")
        first = generate.rendered_files(contract)
        second = generate.rendered_files(contract)
        self.assertEqual(first, second)
        generate.check_rendered(first)

    def test_generated_identity_constants_contain_canonical_digest(self):
        digest = generate.load_json(ROOT / "protocol" / "contract.json")["protocol"]["canonicalSha256"]
        scala = (ROOT / "generated/scala/io/github/zzjason/substrait/spark/v1/ProtocolIdentity.scala").read_text()
        cpp = (ROOT / "generated/cpp/include/substrait_spark/protocol_identity.hpp").read_text()
        self.assertIn(digest, scala)
        self.assertIn(digest, cpp)

    @unittest.skipUnless(shutil.which("g++"), "g++ is not installed")
    def test_generated_cpp_catalog_compiles_as_cpp17(self):
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(
                [
                    "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "generated/cpp/include"),
                    "-c", str(ROOT / "generated/cpp/src/function_catalog.cpp"),
                    "-o", str(Path(directory) / "function_catalog.o"),
                ],
                check=True,
                capture_output=True,
                text=True,
            )


class ArtifactTest(unittest.TestCase):
    def test_artifact_is_byte_reproducible_and_zip_compatible(self):
        with tempfile.TemporaryDirectory() as first_directory, tempfile.TemporaryDirectory() as second_directory:
            first = builder.build(Path(first_directory))
            second = builder.build(Path(second_directory))
            first_jar = Path(first["jar"])
            second_jar = Path(second["jar"])
            self.assertEqual(first_jar.read_bytes(), second_jar.read_bytes())
            self.assertEqual(first["artifactSha256"], second["artifactSha256"])
            self.assertEqual(first_jar.read_bytes(), Path(first["zip"]).read_bytes())
            with zipfile.ZipFile(first_jar) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                self.assertEqual("META-INF/MANIFEST.MF", names[0])
                self.assertEqual(sorted(names[1:], key=lambda value: value.encode("ascii")), names[1:])
                self.assertTrue(all(info.date_time == builder.FIXED_TIMESTAMP for info in infos))
                self.assertTrue(all(info.compress_type == zipfile.ZIP_STORED for info in infos))
                self.assertIn("protocol/contract.json", names)
                self.assertIn("substrait/extensions/functions_spark.yaml", names)
                self.assertIn("scala/io/github/zzjason/substrait/spark/v1/FunctionCatalog.scala", names)
                self.assertIn("cpp/include/substrait_spark/function_catalog.hpp", names)
                manifest = json.loads(
                    archive.read("META-INF/substrait-spark/protocol-manifest.json")
                )
                self.assertEqual(first["canonicalSha256"], manifest["canonicalSha256"])
                for name, digest in manifest["members"].items():
                    self.assertEqual(digest, hashlib.sha256(archive.read(name)).hexdigest())


if __name__ == "__main__":
    unittest.main()
