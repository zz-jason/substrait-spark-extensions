# Third-party notices

This repository and everything it generates are licensed under the Apache License 2.0
(see `LICENSE`). The definitions below are third party work and keep their own
licence terms.

| Component | Where it comes from | Licence |
|---|---|---|
| Substrait specification and protobuf definitions | `substrait-io/substrait` | Apache-2.0 |
| Substrait extension definitions (the `functions_spark.yaml` vocabulary it follows) | `substrait-io/substrait` | Apache-2.0 |

The generated catalogue, contract rendering and artifact keep this attribution: the
generator copies `LICENSE`, `NOTICE` and this file into the artifact payload, and
`tools/check_licenses.py` fails when a declared component or a licence file is
missing.

Only permissive dependencies are accepted. A component under a copyleft licence
needs a design decision before it can be referenced or shipped.
