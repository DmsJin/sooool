# 2026-10-16 checkpoint map

Read [the update report](../../../docs/update-2026-10-16.md) for results, limitations, profile semantics and validation. These are evolving research snapshots; the root recipes are the portable frozen reference.

| Material | Main path |
|---|---|
| Rhythm runner/transport/tests | `rhythm/source/` |
| Rhythm v20/v21 memories | `rhythm/policies/` |
| Rhythm native and simulation summaries | `rhythm/data/` |
| Touhou latest Ubuntu research source | `ubuntu/touhou/latest-source/` |
| Touhou newer local known-plan feedback source | `touhou/local-source/` |
| Touhou optimization/visual-policy summaries and profiles | `ubuntu/touhou/study/` |
| Asterix candidate prompts | `asterix/prompts/` |
| Asterix food-sequence diagnostics and helper scripts | `asterix/food_sequence_iteration/`, `asterix/source/` |
| Asterix paired complete 20-second summaries | `ubuntu/asterix/full20/` |
| PingPong current direct-action source/tests | `ubuntu/pingpong/` |
| Racing research and native-action implementation | `ubuntu/racing/`, `racing/local/` |

All paths are relative to this directory. Local and Ubuntu snapshots are kept separately because other threads were editing concurrently; neither is assumed byte-identical to the other's frozen run source. Run-specific frozen source is retained in evidence when collected.

`manifest.json` maps 4,780 main checkpoint files to source and packaged hashes. The optional 570,039,933-byte archive contains 63,281 indexed evidence records plus complete provenance indexes, in 15 checked parts. Retained records are a filtered development subset. Discussion archives are separately indexed under `research/discussions/`.
