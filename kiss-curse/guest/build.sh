#!/usr/bin/env bash
# Builds the module and copies it to ../ext/kiss_curse.wasm.
# Needs `rustup target add wasm32-unknown-unknown`.
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release --target wasm32-unknown-unknown
cp target/wasm32-unknown-unknown/release/kiss_curse.wasm ../ext/kiss_curse.wasm
ls -l ../ext/kiss_curse.wasm
