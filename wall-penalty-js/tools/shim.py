"""Turns Javy's static module into one the OpenAntiGrav host accepts.

Javy's output imports nine WASI functions, exports kebab-case WIT functions with no
result, and has no `oag_*` exports. The host refuses any import and wants `oag_abi`,
`oag_io` and `tick() -> u32`. This rewrites the module's text form (wasm-dis) so that:

- the nine WASI imports become functions inside the module: standard input serves the
  host's I/O buffer once; standard output is one byte stream, its first STATE_BYTES
  bytes the state blob and the rest the reply (the host's layout leaves 1,024 bytes
  between them, which a script need not write). The stream is appended by byte, so a write
  the runtime splits (standard output is line buffered: a 0x0A byte ends a write) still
  lands whole. The rest do nothing;
- `oag_abi`, `oag_io` (a buffer taken once from the module's own allocator, so it lies
  where the runtime will not write) and `tick` (the script's `js-tick`, then 0) are
  exported, and `oag_state_len` too.

Everything stays in the guest: no host capability is involved.

usage: shim.py in.wat out.wat ABI_WORD STATE_BYTES
"""
import re
import sys

STATE_AT = 288
IO_LEN = 4096
REPLY_AT = STATE_AT + 1024
source, target, abi_word, state_bytes = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]

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
    """(local $n i32)
(if (i32.ne (local.get 0) (i32.const 0)) (then (return (i32.const %(ebadf)d))))
(if (global.get $oag_read) (then (i32.store (local.get 3) (i32.const 0)) (return (i32.const 0))))
(global.set $oag_read (i32.const 1))
(local.set $n (i32.load offset=4 (local.get 1)))
(if (i32.gt_u (local.get $n) (i32.const %(io_len)d)) (then (local.set $n (i32.const %(io_len)d))))
(memory.copy (i32.load (local.get 1)) (call $oag_io) (local.get $n))
(i32.store (local.get 3) (local.get $n))
(i32.const 0)"""
    % {"ebadf": EBADF, "io_len": IO_LEN},
)
define(
    "fd_write",
    """(local $i i32)
(local $len i32)
(local $total i32)
(local $head i32)
(local $from i32)
(loop $next
 (if (i32.lt_u (local.get $i) (local.get 2))
  (then
   (local.set $len (i32.load offset=4 (i32.add (local.get 1) (i32.shl (local.get $i) (i32.const 3)))))
   (local.set $from (i32.load (i32.add (local.get 1) (i32.shl (local.get $i) (i32.const 3)))))
   (if (i32.eq (local.get 0) (i32.const 1))
    (then
     (if (i32.gt_u (i32.add (global.get $oag_cursor) (local.get $len))
                   (i32.const %(span)d))
      (then (return (i32.const 28))))
     (local.set $head (i32.const 0))
     (if (i32.lt_u (global.get $oag_cursor) (i32.const %(state)d))
      (then
       (local.set $head (i32.sub (i32.const %(state)d) (global.get $oag_cursor)))
       (if (i32.gt_u (local.get $head) (local.get $len)) (then (local.set $head (local.get $len))))
       (memory.copy
        (i32.add (call $oag_io) (i32.add (i32.const %(state_at)d) (global.get $oag_cursor)))
        (local.get $from) (local.get $head))))
     (if (i32.lt_u (local.get $head) (local.get $len))
      (then
       (memory.copy
        (i32.add (call $oag_io)
         (i32.add (i32.const %(reply_at)d)
          (i32.sub (i32.add (global.get $oag_cursor) (local.get $head)) (i32.const %(state)d))))
        (i32.add (local.get $from) (local.get $head))
        (i32.sub (local.get $len) (local.get $head)))))
     (global.set $oag_cursor (i32.add (global.get $oag_cursor) (local.get $len)))))
   (local.set $total (i32.add (local.get $total) (local.get $len)))
   (local.set $i (i32.add (local.get $i) (i32.const 1)))
   (br $next))))
(i32.store (local.get 3) (local.get $total))
(i32.const 0)"""
    % {
        "state": int(state_bytes),
        "state_at": STATE_AT,
        "reply_at": REPLY_AT,
        "span": int(state_bytes) + (IO_LEN - REPLY_AT),
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
