import hashlib
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import importlib.util  # noqa: E402

import protocol_contract  # noqa: E402
import protocol_render  # noqa: E402


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


builder = load_module("protocol_builder", ROOT / "tools" / "build_artifact.py")

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
