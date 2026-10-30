# Wall Penalty in JavaScript

`oag.wall-penalty-js` is [`../wall-penalty`](../wall-penalty/) written in JavaScript: a craft
that touches a wall keeps a quarter of its thrust for 1.5 s. It is here to measure what a
JavaScript mod costs under the host's rules, not as the recommended way to write one (that is
Rust on `oag-ext`).

| | Rust (`wall-penalty`) | JavaScript (this) |
| --- | --- | --- |
| Module | 627 bytes | 1,367,899 bytes |
| Fuel a tick (budget 200,000) | 663 peak, 524 mean | 155,800 empty, 168,700 peak in the one-craft race, 178,800 in a 12-craft field, 229,000 worst case (every slot cursed at once: faults) |
| Call, debug host, mean | 19 us | 89 us |
| Compile at race load | negligible | about 1.1 s (Cranelift) |
| Memory | 2 pages | 22 pages at start, no growth in a tick |

## How it works

- `src/main.js` is the mod. Javy has no way to see wasm memory, so it reads the observation
  with `Javy.IO.readSync(0, buffer)` and writes the state blob and the reply with one
  `Javy.IO.writeSync(1, buffer)`.
- `build.sh` runs `javy build` (static module, pre-initialised, `-C deterministic=y`, the WIT
  world in `wit.wit` exporting `js-tick`), disassembles it, and runs `tools/shim.py`: the nine
  WASI imports become functions inside the module (standard input is the host's I/O buffer,
  standard output the state and reply, the rest empty) and `oag_abi`, `oag_io`, `oag_state_len`
  and `tick` are exported. Result: **no import**, which is what the host requires. Nothing is
  asked of the host.
- The Javy used is 9.1.0 with its plugin built without `+simd128` (the host disables SIMD and
  stock Javy's plugin uses it). Build both from the Javy source; the CLI needs
  `RUSTFLAGS="-C link-arg=-fuse-ld=bfd -C link-arg=-Wl,--unresolved-symbols=ignore-all"` on a
  toolchain whose default linker is `rust-lld` (binaryen's DWARF objects miss LLVM symbols the
  CLI never calls).
- The build is byte-reproducible; the built module is committed as `ext/wall_penalty_js.wasm`.

## Proof

- `crates/modhost/tests/javascript_module.rs` (in the engine): 3,000 random observations, the
  same state and commands as the Rust module; one cursed craft fits the budget.
- `wall_penalty_ground_truth` (Pulse PSP EU, `--features extensions --run-ignored only`): the JavaScript
  module flies the Rust module's race tick for tick, the player's and a whole AI field's.
- `types/oag-abi.d.ts` is generated from the engine's `crates/ext-abi` (`scripts/gen-ext-typings.py`);
  `just check-extensions` fails when it or the numbers restated in `src/main.js` drift.
