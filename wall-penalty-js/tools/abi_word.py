"""Prints the ABI word a guest returns from `oag_abi`: the major above the revision's 8
bits, read from the engine's `oag-ext-abi` crate (the submodule sits in the engine
repository, so the crate is at a fixed relative path)."""
import pathlib
import re

source = pathlib.Path(__file__).resolve().parents[5] / "crates/ext-abi/src/lib.rs"
text = source.read_text(encoding="utf-8")
major = int(re.search(r"^pub const ABI: u32 = (\d+);", text, re.M).group(1))
revision = int(re.search(r"^pub const REVISION: u32 = (\d+);", text, re.M).group(1))
print((major << 8) | revision)
