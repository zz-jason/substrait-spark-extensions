import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import protocol_contract  # noqa: E402
import protocol_render  # noqa: E402

class GenerationTest(unittest.TestCase):
    def test_generated_files_are_current_and_deterministic(self):
        contract = protocol_contract.load_json(ROOT / "protocol" / "contract.json")
        first = protocol_render.rendered_files(contract)
        second = protocol_render.rendered_files(contract)
        self.assertEqual(first, second)
        protocol_render.check_rendered(first)

    def test_generated_identity_constants_contain_canonical_digest(self):
        digest = protocol_contract.load_json(ROOT / "protocol" / "contract.json")["protocol"]["canonicalSha256"]
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


