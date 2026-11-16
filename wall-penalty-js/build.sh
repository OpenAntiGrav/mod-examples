#!/usr/bin/env bash
# Builds ext/wall_penalty_js.wasm: the script (src/main.js) through Javy, then the shim.
#
# Needs a Javy 9.1.0 CLI whose plugin was built WITHOUT `+simd128` (stock Javy's plugin
# uses SIMD, which the host's deterministic subset refuses): JAVY=/path/to/javy, and
# binaryen's `wasm-dis`/`wasm-as` on PATH. See ../README.md in this folder.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
javy="${JAVY:?set JAVY to a Javy 9.1.0 CLI built with its plugin without simd128}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

"$javy" build "$here/src/main.js" -C wit="$here/wit.wit" -C wit-world=ext \
  -C source=omitted -C deterministic=y -J javy-stream-io=y -o "$work/javy.wasm"
wasm-dis "$work/javy.wasm" -o "$work/javy.wat"
abi_word="$(python3 -I "$here/tools/abi_word.py")"
python3 -I "$here/tools/shim.py" "$work/javy.wat" "$work/shimmed.wat" "$abi_word" 16
mkdir -p "$here/ext"
wasm-as --all-features "$work/shimmed.wat" -o "$here/ext/wall_penalty_js.wasm"
ls -l "$here/ext/wall_penalty_js.wasm"
