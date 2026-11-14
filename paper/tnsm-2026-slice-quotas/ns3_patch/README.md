# Paper 10 standalone programs (Nov 2026)

`ns-3-dev/build` is shared with other papers' campaigns, so the revision neither touched it nor ran `ns3 build` or cmake.
`../bin/p10-pass` and `../bin/p10-tenants` come from `build.sh`, which compiles the sources here with the flags of the shared
build's compile_commands.json and links them against the optimized libraries in `ns-3-dev/build/lib`.

- `orig/`: the two example sources as copied from `contrib/ntn-slice/examples` on 4 Nov 2026.
- `apply_edits.py`: makes the patched copies from `orig/`. `p10_examples.patch` is the same change as a diff.
- Additions: block counters read from the UE PHY trace `RxPacketTraceUe` (passive), the policy `queueprop` in both programs,
  and `--aLimited` in the tenant program. No scheduler code changed; the policy is a controller on the existing scheduler API.
- `m12_release_comments.patch`: comment and name changes for the release of `contrib/ntn-slice` ("delivered" to "built").
  Deliberately not applied, as it would change the shared source.

Check: `../compare_rev.py` reran 19 rows of the first campaign (seeds 101 to 103 in both studies, and one no-error row).
Every old output field is byte-identical (`../out/rev_check.json`). Rows hold `bin` and `libs` hashes. `run_rev.py` stops if a library changes.

To merge at the shared build: apply `p10_examples.patch` under `contrib/ntn-slice/examples` and rebuild.
