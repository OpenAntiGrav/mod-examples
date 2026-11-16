// Wall Penalty in JavaScript: a craft that touches a wall has its engine cursed, a quarter of
// its thrust for a second and a half, renewed by every tick it stays on the wall. The same
// rules as ../wall-penalty/guest/src/lib.rs, byte for byte on the wire.
//
// Javy's QuickJS has no way to see the host's I/O buffer, so the build's shim
// (tools/shim.py) serves a compact observation as standard input and takes the reply from
// standard output: one read, one write.
//
// The module runs on a fresh instance every tick, top level included, and a top-level
// `const` costs about 1,400 fuel each time, so the numbers below are written in place. The
// ABI's own numbers are named in `// abi NAME = n` lines (comments cost nothing), which
// `just check-extensions` compares with the ABI crate. Every buffer starts zeroed, so only
// the bytes that are not zero are written.
//
// abi COMMAND_LEN = 12
// abi EVENT_WALL_CONTACT = 1
// abi COMMAND_SCALE_THRUST = 1
// abi COMMAND_FIRE_EFFECT = 6
// abi OWN_FLAG = 0x8000
//
// What the shim serves (bytes): 0 the active mask (u32), 4 the event count (u32), 8 the
// state (16: a u16 countdown per slot, 8 slots), 24 each event's kind and slot (2 bytes).
const io = new Uint8Array(88);
// What is written back, in one write the shim cuts into three segments: 0 the state, 16 the
// reply's string pool (the length byte and the name "sputter", the mod's own effect, at pool
// offset 0), 24 the reply (the command count, u32, then 12-byte commands: room for two per slot).
const out = new Uint8Array(220);
out.set([7, 115, 112, 117, 116, 116, 101, 114], 16);

function jsTick() {
  Javy.IO.readSync(0, io);
  const active = io[0] | (io[1] << 8);
  const events = io[4];
  for (let i = 0; i < events; i++) {
    const at = 24 + i * 2;
    if (io[at] === 1 && io[at + 1] < 8) {
      // A curse: 90 ticks.
      io[8 + io[at + 1] * 2] = 90;
      io[9 + io[at + 1] * 2] = 0;
    }
  }
  let at = 28;
  for (let slot = 0; slot < 8; slot++) {
    const index = 8 + slot * 2;
    let left = io[index] | (io[index + 1] << 8);
    if (left === 0) continue;
    left -= 1;
    out[slot * 2] = left & 255;
    out[slot * 2 + 1] = left >> 8;
    if (active & (1 << slot)) {
      // scale-thrust by 0.25: the f32 0x3E800000, little-endian, in the command's value field.
      out[at] = 1;
      out[at + 1] = slot;
      out[at + 6] = 0x80;
      out[at + 7] = 0x3e;
      at += 12;
      if (left % 6 === 0) {
        // fire-effect, the mod's own (0x8000), the name at pool offset 0.
        out[at] = 6;
        out[at + 1] = slot;
        out[at + 3] = 0x80;
        at += 12;
      }
    }
  }
  out[24] = (at - 28) / 12;
  Javy.IO.writeSync(1, out);
}

export { jsTick };
