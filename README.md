# Substrait Spark Extensions

This repository is the implementation-neutral canonical protocol for Spark SQL plans exchanged through Substrait. It defines the contract that any producer or consumer can implement, including engines such as ClickHouse, DataFusion, Velox, and future runtimes.

Protocol version `0.1.0` removes implementation capability snapshots from the canonical contract. Engine-specific support matrices, function mappings, execution code, and release metadata belong in each implementation repository.

## Contents

- `protocol/contract.json`: canonical function identities, kinds, protocol option values, the `google.protobuf.Struct` payload schemas, metadata identity, protocol version, and canonical SHA-256.
- `protocol/contract.schema.json`: closed JSON Schema draft 2020-12 contract.
- `extensions/functions_spark.yaml`: canonical Spark SQL function extension definitions.
- `capabilities/capabilities.json`: generated, implementation-neutral protocol capability projection.
- `generated/scala`: dependency-free Scala protocol identities, function catalog, and payload schema.
- `generated/cpp`: dependency-free C++17 protocol identities, function catalog, and payload schema.
- `tools/generate.py`: command line entry point for validation and generation.
- `tools/protocol_contract.py`: contract loading, canonical digest, and validation rules.
- `tools/protocol_render.py`: rendering of the generated catalogs and the capability snapshot.
- `tools/build_artifact.py`: reproducible ZIP-compatible JAR builder.
- `tests/test_contract.py`, `tests/test_generate.py`, `tests/test_artifact.py`: contract, generation, and reproducibility tests.

The contract contains 133 exact function identities. Fourteen use `extension:io.github.zz-jason:functions_spark`; the remaining identities use official Substrait 0.98 extension URNs. Function identity is the exact tuple `(kind, URN, compound signature)`. Bare names and inferred URNs are outside the protocol.

Function options list the values that can appear in a conforming Spark SQL protocol plan. Every consumer publishes its own support matrix and must reject an unsupported identity or option before binding or execution.

## Protocol identity

- Protocol version: `0.1.0`
- Substrait version: `0.98.0`
- Custom function URN: `extension:io.github.zz-jason:functions_spark`
- Canonical SHA-256: `ec349b61205080c99ad0a8cb3b0e3389a77f6ebd5f2bd47d3f479829a3d44940`
- Function extension SHA-256: `db4fb05f290ba6652742cea4f3c95c022c3f155858e37076c0cd85bcfdda480e`

The canonical contract digest is SHA-256 over UTF-8 JSON serialized with sorted keys and compact separators after removing `protocol.canonicalSha256`. The contract uses only closed structured output operations and contains no executable expressions.

`Any.value` for both type URLs is a serialized `google.protobuf.Struct`. `protocol/contract.json` under `payloads` is the only definition of each payload's fields, nesting, and enum values, and it is generated into both the Scala and the C++ payload schemas. A payload with an unknown or missing field is invalid.

Every conforming plan carries `PlanSemantics` in `Plan.advanced_extensions.enhancement` with protocol version `0.1.0` and the canonical digest. Its type URL is:

```text
type.googleapis.com/io.github.zzjason.substrait.spark.v1.PlanSemantics
```

Every timestamp-bearing Spark read carries `SparkReadSemantics` in `ReadRel.advanced_extension.enhancement` and lists this type URL in `Plan.expected_type_urls`:

```text
type.googleapis.com/io.github.zzjason.substrait.spark.v1.SparkReadSemantics
```

`ReadRel.base_schema` remains authoritative for the logical schema. Read metadata supplies only Spark timestamp identity, physical timestamp interpretation, Parquet encoding, timezone, and rebase policy that cannot be inferred safely.

## Validation and generation

Only Python 3 and its standard library are required.

```sh
python3 tools/generate.py validate
python3 tools/generate.py generate
python3 tools/generate.py check
python3 -m unittest discover -s tests -v
```

Generated files are committed for direct consumer use. The `check` command byte-compares regenerated output and rejects stale or extra generated files.

## Reproducible artifact

Run:

```sh
./build.sh
```

The build validates the contract, checks generated files, runs tests, and creates byte-reproducible JAR and ZIP artifacts under `dist/`.

## Implementation boundary

This repository must not contain engine-specific names, source paths, version pins, function mappings, benchmarks, or capability claims. Producer and consumer implementations maintain those details in their own repositories. The committed neutrality test scans every tracked protocol file case-insensitively for prohibited implementation identifiers.

## Evolution

Published artifacts are immutable. Additive function support requires a minor protocol increment. Changes to existing identities, options, metadata fields, or semantics require a major protocol increment. Protobuf field numbers and enum values must never be reused. Unknown metadata and unsupported values must be rejected before binding or execution.

## License

Apache License 2.0. See `LICENSE`. The contract implements the Substrait specification and its extension conventions, which the Substrait project publishes under Apache License 2.0.
