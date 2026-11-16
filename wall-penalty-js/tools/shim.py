"""Turns Javy's static module into one the OpenAntiGrav host accepts.

Javy's output imports nine WASI functions, exports kebab-case WIT functions with no
result, and has no `oag_*` exports. The host refuses any import and wants `oag_abi`,
`oag_io` and `tick() -> u32`. This rewrites the module's text form (wasm-dis) so that:

- the nine WASI imports become functions inside the module. Standard input is the
  observation, compacted: the active mask (u32), the event count (u32, at most MAX_EVENTS),
  the state blob, then each event's kind and slot (2 bytes); the script reads the whole
  stream in one call, into a buffer of `observation_bytes`. Reading the ABI's 16-byte
  events and unused tail whole costs fuel by the byte, and the shim holds what the script
  asks for. Standard output is one byte stream in three segments: its first STATE_BYTES
  bytes the state blob, the next POOL_BYTES the reply's string pool, the rest the reply (the
  count and the commands, up to REPLY_BYTES). The host's layout leaves gaps between the
  regions, which a script need not write, and a script writes only the reply it uses. The
  stream is appended by byte, so a write the runtime splits (standard output is line
  buffered: a 0x0A byte ends a write) still lands whole. The rest do nothing;
- `oag_abi`, `oag_io` (a buffer taken once from the module's own allocator, so it lies
  where the runtime will not write) and `tick` (the script's `js-tick`, then 0) are
  exported, and `oag_state_len` too.

Everything stays in the guest: no host capability is involved.

usage: shim.py in.wat out.wat ABI_WORD STATE_BYTES POOL_BYTES REPLY_BYTES
"""
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import abi  # noqa: E402

LAYOUT = abi.constants()
STATE_AT = LAYOUT["STATE_AT"]
REPLY_AT = LAYOUT["REPLY_AT"]
POOL_AT = LAYOUT["POOL_AT"]
IO_LEN = LAYOUT["IO_LEN"]
POOL_LEN = LAYOUT["POOL_LEN"]
source, target, abi_word = sys.argv[1], sys.argv[2], sys.argv[3]
state_bytes, pool_bytes, reply_bytes = (int(value) for value in sys.argv[4:7])
MAX_EVENTS = LAYOUT["MAX_EVENTS"]
OBSERVATION_BYTES = 8 + state_bytes + 2 * MAX_EVENTS
if pool_bytes > POOL_LEN or STATE_AT + state_bytes > REPLY_AT or REPLY_AT + reply_bytes > POOL_AT:
    sys.exit("a segment is longer than the ABI region it lands in")

text = open(source, encoding="utf-8").read()


def export_of(name):
    found = re.search(r'^ \(export "%s" \(func (\$\S+)\)\)$' % re.escape(name), text, re.M)
    if not found:
        sys.exit("javy output does not export " + name)
    return found


realloc = export_of("cabi_realloc").group(1)
js_tick = export_of("js-tick").group(1)
for name in ("tick", "oag-abi"):
    found = re.search(r'^ \(export "%s" \(func \$\S+\)\)\n' % re.escape(name), text, re.M)
    if found:
        text = text.replace(found.group(0), "", 1)


def define(name, body):
    global text
    found = re.search(
        r'^ \(import "wasi_snapshot_preview1" "%s" \(func (\$\S+) (.*)\)\)$' % name, text, re.M
    )
    if not found:
        sys.exit("javy output has no import of " + name)
    text = text.replace(
        found.group(0), " (func %s %s\n%s\n )" % (found.group(1), found.group(2), body), 1
    )


EBADF = 8
define("environ_get", "(i32.const 0)")
define(
    "environ_sizes_get",
    "(i32.store (local.get 0) (i32.const 0))\n(i32.store (local.get 1) (i32.const 0))\n(i32.const 0)",
)
define(
    "clock_time_get",
    "(i64.store (local.get 2) (i64.const 0))\n(i32.const 0)",
)
define("fd_close", "(i32.const 0)")
define("fd_fdstat_get", "(i32.const %d)" % EBADF)
define("fd_seek", "(i32.const %d)" % EBADF)
define("proc_exit", "(unreachable)")
define(
    "fd_read",
    """(local $dst i32)
(local $io i32)
(local $count i32)
(local $i i32)
(if (i32.ne (local.get 0) (i32.const 0)) (then (return (i32.const %(ebadf)d))))
(if (global.get $oag_read) (then (i32.store (local.get 3) (i32.const 0)) (return (i32.const 0))))
(global.set $oag_read (i32.const 1))
(if (i32.lt_u (i32.load offset=4 (local.get 1)) (i32.const %(wanted)d)) (then (return (i32.const 28))))
(local.set $dst (i32.load (local.get 1)))
(local.set $io (call $oag_io))
(local.set $count (i32.load (i32.add (local.get $io) (i32.const %(event_count_at)d))))
(if (i32.gt_u (local.get $count) (i32.const %(max_events)d)) (then (local.set $count (i32.const %(max_events)d))))
(i32.store (local.get $dst) (i32.load (i32.add (local.get $io) (i32.const %(active_at)d))))
(i32.store offset=4 (local.get $dst) (local.get $count))
(memory.copy (i32.add (local.get $dst) (i32.const 8)) (i32.add (local.get $io) (i32.const %(state_at)d)) (i32.const %(state)d))
(loop $event
 (if (i32.lt_u (local.get $i) (local.get $count))
  (then
   (i32.store16
    (i32.add (local.get $dst) (i32.add (i32.const %(events_out)d) (i32.shl (local.get $i) (i32.const 1))))
    (i32.load16_u (i32.add (local.get $io) (i32.add (i32.const %(events_at)d) (i32.shl (local.get $i) (i32.const 4))))))
   (local.set $i (i32.add (local.get $i) (i32.const 1)))
   (br $event))))
(i32.store (local.get 3) (i32.add (i32.const %(events_out)d) (i32.shl (local.get $count) (i32.const 1))))
(i32.const 0)"""
    % {
        "ebadf": EBADF,
        "wanted": OBSERVATION_BYTES,
        "event_count_at": LAYOUT["EVENT_COUNT_AT"],
        "max_events": MAX_EVENTS,
        "active_at": LAYOUT["ACTIVE_AT"],
        "state_at": STATE_AT,
        "state": state_bytes,
        "events_out": 8 + state_bytes,
        "events_at": LAYOUT["EVENTS_AT"],
    },
)
define(
    "fd_write",
    """(local $i i32)
(local $len i32)
(local $total i32)
(local $room i32)
(local $dst i32)
(local $from i32)
(local $cursor i32)
(loop $next
 (if (i32.lt_u (local.get $i) (local.get 2))
  (then
   (local.set $len (i32.load offset=4 (i32.add (local.get 1) (i32.shl (local.get $i) (i32.const 3)))))
   (local.set $from (i32.load (i32.add (local.get 1) (i32.shl (local.get $i) (i32.const 3)))))
   (if (i32.eq (local.get 0) (i32.const 1))
    (then
     (if (i32.gt_u (i32.add (global.get $oag_cursor) (local.get $len)) (i32.const %(span)d))
      (then (return (i32.const 28))))
     (local.set $total (i32.add (local.get $total) (local.get $len)))
     (loop $part
      (if (local.get $len)
       (then
        (local.set $cursor (global.get $oag_cursor))
        (if (i32.lt_u (local.get $cursor) (i32.const %(state)d))
         (then
          (local.set $dst (i32.add (i32.const %(state_at)d) (local.get $cursor)))
          (local.set $room (i32.sub (i32.const %(state)d) (local.get $cursor))))
         (else
          (if (i32.lt_u (local.get $cursor) (i32.const %(pool_end)d))
           (then
            (local.set $dst (i32.add (i32.const %(pool_at)d) (i32.sub (local.get $cursor) (i32.const %(state)d))))
            (local.set $room (i32.sub (i32.const %(pool_end)d) (local.get $cursor))))
           (else
            (local.set $dst (i32.add (i32.const %(reply_at)d) (i32.sub (local.get $cursor) (i32.const %(pool_end)d))))
            (local.set $room (i32.sub (i32.const %(span)d) (local.get $cursor)))))))
        (if (i32.gt_u (local.get $room) (local.get $len)) (then (local.set $room (local.get $len))))
        (memory.copy (i32.add (call $oag_io) (local.get $dst)) (local.get $from) (local.get $room))
        (global.set $oag_cursor (i32.add (global.get $oag_cursor) (local.get $room)))
        (local.set $from (i32.add (local.get $from) (local.get $room)))
        (local.set $len (i32.sub (local.get $len) (local.get $room)))
        (br $part)))))
    (else (local.set $total (i32.add (local.get $total) (local.get $len)))))
   (local.set $i (i32.add (local.get $i) (i32.const 1)))
   (br $next))))
(i32.store (local.get 3) (local.get $total))
(i32.const 0)"""
    % {
        "state": state_bytes,
        "state_at": STATE_AT,
        "reply_at": REPLY_AT,
        "pool_at": POOL_AT,
        "pool_end": state_bytes + pool_bytes,
        "span": state_bytes + pool_bytes + reply_bytes,
    },
)

globals_text = """ (global $oag_buffer (mut i32) (i32.const 0))
 (global $oag_cursor (mut i32) (i32.const 0))
 (global $oag_read (mut i32) (i32.const 0))
"""
anchor = re.search(r"^ \(global \$global\$0 .*\)$", text, re.M)
text = text.replace(anchor.group(0), anchor.group(0) + "\n" + globals_text.rstrip("\n"), 1)

glue = """
 (func $oag_abi (result i32) (i32.const %(abi)s))
 (func $oag_state_len (result i32) (i32.const %(state)s))
 (func $oag_io (result i32)
  (if (i32.eqz (global.get $oag_buffer))
   (then (global.set $oag_buffer
    (call %(realloc)s (i32.const 0) (i32.const 0) (i32.const 8) (i32.const %(io_len)d)))))
  (global.get $oag_buffer))
 (func $oag_tick (result i32)
  (call %(js_tick)s)
  (i32.const 0))
 (export "oag_abi" (func $oag_abi))
 (export "oag_io" (func $oag_io))
 (export "oag_state_len" (func $oag_state_len))
 (export "tick" (func $oag_tick))
)
""" % {
    "abi": abi_word,
    "state": state_bytes,
    "realloc": realloc,
    "js_tick": js_tick,
    "io_len": IO_LEN,
}
end = text.rstrip().rfind(")")
text = text[:end] + glue
open(target, "w", encoding="utf-8").write(text)
