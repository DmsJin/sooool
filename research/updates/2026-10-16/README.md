# 2026-10-16 checkpoint map

Read [the update report](../../../docs/update-2026-10-16.md) for results, limitations, profile semantics and validation. These are evolving research snapshots; the root recipes are the portable frozen reference.

The Rhythm snapshot includes the retired coordinate-to-time campaign and earlier literal-time experiments. Start with [the current Rhythm case study](../../../docs/rhythm-autoresearch.md) and [workflow](../../../docs/rhythm.md); the selected 17s run is indexed under `artifacts/rhythm/selected/`. A snapshot’s “selected” or “current” wording refers to its original experiment, not the active release.

| Material | Main path |
|---|---|
| Historical Rhythm runner/transport/tests | `rhythm/source/` |
| Historical Rhythm v20/v21 memories | `rhythm/policies/` |
| Historical Rhythm native and simulation summaries | `rhythm/data/` |
| Touhou latest Ubuntu research source | `ubuntu/touhou/latest-source/` |
| Touhou newer local known-plan feedback source | `touhou/local-source/` |
| Touhou optimization/visual-policy summaries and profiles | `ubuntu/touhou/study/` |
| Asterix candidate prompts | `asterix/prompts/` |
| Asterix food-sequence diagnostics and helper scripts | `asterix/food_sequence_iteration/`, `asterix/source/` |
| Asterix paired complete 20-second summaries | `ubuntu/asterix/full20/` |
| Historical PingPong direct-action source/tests | `ubuntu/pingpong/` |
| Racing selected policy and records | [Racing workflow](../../../docs/racing.md); former snapshot directories redirect there |

All paths are relative to this directory. Local and Ubuntu snapshots are kept separately because other threads were editing concurrently; neither is assumed byte-identical to the other's frozen run source. Run-specific frozen source is retained in evidence when collected.

`manifest.json` maps retained checkpoint files to source and packaged hashes; Racing snapshot entries have moved to `research/racing/selection.json`. The optional 570,039,933-byte archive contains 63,281 indexed evidence records plus complete provenance indexes, in 15 checked parts. Retained records are a filtered development subset. Discussion archives are separately indexed under `research/discussions/`.
