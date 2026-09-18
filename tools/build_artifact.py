#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the reproducible ZIP-compatible protocol JAR."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import zipfile
from pathlib import Path
from typing import Dict, List

ROOT = Path(__file__).resolve().parents[1]
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
COORDINATE = "io.github.zzjason:substrait-spark-extensions"


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def payload_paths() -> List[Path]:
    explicit = [
        ROOT / "LICENSE",
        ROOT / "README.md",
        ROOT / "VERSION",
        ROOT / "protocol" / "contract.json",
        ROOT / "protocol" / "contract.schema.json",
        ROOT / "extensions" / "functions_spark.yaml",
        ROOT / "capabilities" / "capabilities.json",
    ]
    generated = sorted(path for path in (ROOT / "generated").rglob("*") if path.is_file())
    paths = explicit + generated
    missing = [str(path.relative_to(ROOT)) for path in paths if not path.is_file()]
    if missing:
        raise ValueError(f"missing artifact inputs: {missing}")
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix().encode("ascii"))


def archive_name(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    if relative.startswith("extensions/"):
        return "substrait/" + relative
    if relative.startswith("generated/scala/"):
        return "scala/" + relative.removeprefix("generated/scala/")
    if relative.startswith("generated/cpp/"):
        return "cpp/" + relative.removeprefix("generated/cpp/")
    return relative


def zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, FIXED_TIMESTAMP)
    info.compress_type = zipfile.ZIP_STORED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    info.extra = b""
    info.comment = b""
    return info


def build(output: Path) -> Dict[str, str]:
    version = (ROOT / "VERSION").read_text(encoding="utf-8").strip()
    contract = json.loads((ROOT / "protocol" / "contract.json").read_text(encoding="utf-8"))
    if version != contract["protocol"]["version"]:
        raise ValueError("VERSION and contract protocol version differ")
    members = {archive_name(path): path.read_bytes() for path in payload_paths()}
    member_hashes = {name: sha256(content) for name, content in sorted(members.items())}
    protocol_manifest = {
        "schemaVersion": 1,
        "coordinate": COORDINATE,
        "artifactVersion": version,
        "protocolVersion": version,
        "substraitVersion": contract["protocol"]["substraitVersion"],
        "canonicalSha256": contract["protocol"]["canonicalSha256"],
        "generatorFormatVersion": 1,
        "members": member_hashes,
    }
    members["META-INF/substrait-spark/protocol-manifest.json"] = (
        json.dumps(protocol_manifest, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode("utf-8")
    jar_manifest = (
        "Manifest-Version: 1.0\r\n"
        "Implementation-Title: Substrait Spark Extensions\r\n"
        f"Implementation-Version: {version}\r\n"
        "Automatic-Module-Name: io.github.zzjason.substrait.spark.protocol\r\n"
        "\r\n"
    ).encode("ascii")
    output.mkdir(parents=True, exist_ok=True)
    base = f"substrait-spark-extensions-{version}"
    jar_path = output / f"{base}.jar"
    zip_path = output / f"{base}.zip"
    with zipfile.ZipFile(jar_path, "w", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        archive.comment = b""
        archive.writestr(zip_info("META-INF/MANIFEST.MF"), jar_manifest)
        for name in sorted(members, key=lambda value: value.encode("ascii")):
            archive.writestr(zip_info(name), members[name])
    shutil.copyfile(jar_path, zip_path)
    digest = sha256(jar_path.read_bytes())
    checksum_path = output / f"{base}.jar.sha256"
    checksum_path.write_text(f"{digest}  {jar_path.name}\n", encoding="ascii", newline="\n")
    return {
        "jar": str(jar_path),
        "zip": str(zip_path),
        "sha256File": str(checksum_path),
        "artifactSha256": digest,
        "canonicalSha256": contract["protocol"]["canonicalSha256"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), indent=2))


if __name__ == "__main__":
    main()
