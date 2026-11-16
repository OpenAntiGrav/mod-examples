// Wall Penalty in JavaScript: a craft that touches a wall has its engine cursed, a quarter of
// its thrust for a second and a half, renewed by every tick it stays on the wall. The same
// rules as ../wall-penalty/guest/src/lib.rs, byte for byte on the wire.
//
// Javy's QuickJS has no way to see the host's I/O buffer, so the build's shim
// (tools/shim.py) serves it as standard input and takes the reply from standard output:
// one read of the observation, one write of the state and the reply.

const ACTIVE_AT = 20;
const EVENT_COUNT_AT = 24;
const EVENTS_AT = 32;
const EVENT_LEN = 8;
const STATE_AT = 288;
const COMMAND_LEN = 12;
const EVENT_WALL_CONTACT = 1;
const COMMAND_SCALE_THRUST = 1;
const COMMAND_FIRE_EFFECT = 6;
const OWN_FLAG = 0x8000;

const CURSE_TICKS = 90;
const CURSE_FACTOR = 0.25;
const PUFF_EVERY = 6;
const SPUTTER = 0;
const SLOTS = 8;

// Only the head of the buffer is read: the header, the 32 events and this mod's 16-byte state.
const io = new Uint8Array(STATE_AT + SLOTS * 2);
const view = new DataView(io.buffer);
// What is written back, in one write: the state (16 bytes, the host's blob), then the reply
// (the command count and the commands, sized for every slot's two commands). The shim cuts
// the stream at the state's length. Written whole each tick, so nothing is allocated.
const STATE_BYTES = SLOTS * 2;
const out = new Uint8Array(STATE_BYTES + 4 + COMMAND_LEN * 2 * SLOTS);
const outView = new DataView(out.buffer);

function jsTick() {
  Javy.IO.readSync(0, io);
  const active = io[ACTIVE_AT] | (io[ACTIVE_AT + 1] << 8);
  const events = io[EVENT_COUNT_AT];
  for (let i = 0; i < events; i++) {
    const at = EVENTS_AT + i * EVENT_LEN;
    if (io[at] === EVENT_WALL_CONTACT && io[at + 1] < SLOTS) {
      io[STATE_AT + io[at + 1] * 2] = CURSE_TICKS;
      io[STATE_AT + io[at + 1] * 2 + 1] = 0;
    }
  }
  let at = STATE_BYTES + 4;
  for (let slot = 0; slot < SLOTS; slot++) {
    const index = STATE_AT + slot * 2;
    let left = io[index] | (io[index + 1] << 8);
    if (left === 0) continue;
    left -= 1;
    out[slot * 2] = left & 255;
    out[slot * 2 + 1] = left >> 8;
    if (active & (1 << slot)) {
      out[at] = COMMAND_SCALE_THRUST;
      out[at + 1] = slot;
      outView.setFloat32(at + 4, CURSE_FACTOR, true);
      at += COMMAND_LEN;
      if (left % PUFF_EVERY === 0) {
        out[at] = COMMAND_FIRE_EFFECT;
        out[at + 1] = slot;
        out[at + 2] = SPUTTER;
        out[at + 3] = OWN_FLAG >> 8;
        at += COMMAND_LEN;
      }
    }
  }
  outView.setUint32(STATE_BYTES, (at - STATE_BYTES - 4) / COMMAND_LEN, true);
  Javy.IO.writeSync(1, out);
}

export { jsTick };
