#!/usr/bin/env bash
# Builds ../ext/energy_turbo.wasm; needs `rustup target add wasm32-unknown-unknown`.
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release --target wasm32-unknown-unknown
cp target/wasm32-unknown-unknown/release/energy_turbo.wasm ../ext/energy_turbo.wasm
ls -l ../ext/energy_turbo.wasm
