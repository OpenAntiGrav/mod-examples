#!/usr/bin/env bash
# Builds the module and copies it to ../ext/wall_penalty.wasm.
# Needs `rustup target add wasm32-unknown-unknown`.
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release --target wasm32-unknown-unknown
cp target/wasm32-unknown-unknown/release/wall_penalty.wasm ../ext/wall_penalty.wasm
ls -l ../ext/wall_penalty.wasm
