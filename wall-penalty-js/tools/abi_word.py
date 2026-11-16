"""Prints the ABI word a guest returns from `oag_abi`: the major above the revision's 8
bits, read from the engine's `oag-ext-abi` crate."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import abi  # noqa: E402

values = abi.constants()
print((values["ABI"] << 8) | values["REVISION"])
