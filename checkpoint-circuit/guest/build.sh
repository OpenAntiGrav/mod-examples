#!/usr/bin/env bash
# Builds the module and copies it to ../ext/checkpoint_circuit.wasm.
# Needs `rustup target add wasm32-unknown-unknown`.
set -euo pipefail
cd "$(dirname "$0")"
cargo build --release --target wasm32-unknown-unknown
cp target/wasm32-unknown-unknown/release/checkpoint_circuit.wasm ../ext/checkpoint_circuit.wasm
ls -l ../ext/checkpoint_circuit.wasm
