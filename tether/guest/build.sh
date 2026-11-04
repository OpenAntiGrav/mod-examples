#!/usr/bin/env bash
# Builds ../ext/tether.wasm; needs `rustup target add wasm32-unknown-unknown`.
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release --target wasm32-unknown-unknown
cp target/wasm32-unknown-unknown/release/tether.wasm ../ext/tether.wasm
ls -l ../ext/tether.wasm
