"""The numbers of the engine's `oag-ext-abi` crate that the build needs, read from its
source (the submodule sits in the engine repository, so the crate is at a fixed relative
path): `constants()` maps a `pub const NAME: ty = expr;` of `lib.rs` to its value."""
import pathlib
import re

SOURCE = pathlib.Path(__file__).resolve().parents[5] / "crates/ext-abi/src/lib.rs"


def constants():
    text = SOURCE.read_text(encoding="utf-8")
    pending = re.findall(r"^pub const ([A-Z][A-Z0-9_]*): (?:u32|usize) = (.+);$", text, re.M)
    values = {}
    while pending:
        later = []
        for name, expr in pending:
            try:
                values[name] = eval(expr, {"__builtins__": {}}, dict(values))
            except NameError:
                later.append((name, expr))
        if len(later) == len(pending):
            raise SystemExit(f"{SOURCE}: cannot evaluate {[name for name, _ in later]}")
        pending = later
    return values
