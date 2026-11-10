#!/usr/bin/env bash
# Builds ../ext/window.wasm; needs `rustup target add wasm32-unknown-unknown`.
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release --target wasm32-unknown-unknown
cp target/wasm32-unknown-unknown/release/window.wasm ../ext/window.wasm
ls -l ../ext/window.wasm
