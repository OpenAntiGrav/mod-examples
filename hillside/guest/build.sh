#!/usr/bin/env bash
# Builds the module and copies it to ../ext/hillside_rain.wasm.
# Needs `rustup target add wasm32-unknown-unknown`.
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release --target wasm32-unknown-unknown
cp target/wasm32-unknown-unknown/release/hillside_rain.wasm ../ext/hillside_rain.wasm
ls -l ../ext/hillside_rain.wasm
