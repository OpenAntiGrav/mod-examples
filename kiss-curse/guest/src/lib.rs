//! Kiss Curse: a craft that touches a wall has its engine cursed, a quarter of its
//! thrust for a second and a half, renewed by every tick it stays on the wall.
//!
//! A simulation module for OpenAntiGrav's extension ABI 1 (`oag_modhost::abi` in the
//! engine repository). The host writes an observation into the I/O buffer, calls
//! `tick`, and reads back the state blob and the commands. The guest keeps nothing in
//! its own memory between ticks: its instance is fresh every tick, and the curse's
//! countdown lives in the 16-byte state blob the host owns, hashes and rolls back.
//!
//! There is no engine timer: each tick a curse runs, the guest sends
//! `scale-thrust{slot, 0.25}` again, and the host multiplies it into that tick's
//! engine output for that craft.
#![no_std]

use core::ptr::{addr_of_mut, read_volatile, write_volatile};

/// How long a curse lasts: 1.5 s at the engine's 60 Hz tick.
const CURSE_TICKS: u16 = 90;
/// The engine output a cursed craft keeps.
const CURSE_FACTOR: f32 = 0.25;

/// The ABI 1 layout (`oag_modhost::abi`).
const IO_LEN: usize = 4096;
const ACTIVE_AT: usize = 20;
const EVENT_COUNT_AT: usize = 24;
const EVENTS_AT: usize = 32;
const EVENT_LEN: usize = 8;
const MAX_EVENTS: usize = 32;
const STATE_AT: usize = EVENTS_AT + EVENT_LEN * MAX_EVENTS;
const REPLY_AT: usize = STATE_AT + 1024;
const COMMAND_LEN: usize = 12;
const EVENT_WALL_CONTACT: u8 = 1;
const COMMAND_SCALE_THRUST: u8 = 1;
/// Grid slots this mod tracks: one `u16` each in the blob.
const SLOTS: usize = 8;

static mut IO: [u8; IO_LEN] = [0; IO_LEN];

fn io() -> *mut u8 {
    addr_of_mut!(IO).cast()
}

fn get_u8(at: usize) -> u8 {
    // SAFETY: `at` is inside `IO`, every caller indexes below `IO_LEN`.
    unsafe { read_volatile(io().add(at)) }
}

fn put_u8(at: usize, value: u8) {
    // SAFETY: as `get_u8`.
    unsafe { write_volatile(io().add(at), value) }
}

fn get_u32(at: usize) -> u32 {
    u32::from_le_bytes([get_u8(at), get_u8(at + 1), get_u8(at + 2), get_u8(at + 3)])
}

fn put_u32(at: usize, value: u32) {
    for (i, byte) in value.to_le_bytes().into_iter().enumerate() {
        put_u8(at + i, byte);
    }
}

fn countdown(slot: usize) -> u16 {
    u16::from_le_bytes([get_u8(STATE_AT + slot * 2), get_u8(STATE_AT + slot * 2 + 1)])
}

fn set_countdown(slot: usize, ticks: u16) {
    let [lo, hi] = ticks.to_le_bytes();
    put_u8(STATE_AT + slot * 2, lo);
    put_u8(STATE_AT + slot * 2 + 1, hi);
}

#[unsafe(no_mangle)]
pub extern "C" fn oag_abi() -> u32 {
    1
}

#[unsafe(no_mangle)]
pub extern "C" fn oag_io() -> u32 {
    io() as u32
}

#[unsafe(no_mangle)]
pub extern "C" fn tick() -> u32 {
    let events = (get_u32(EVENT_COUNT_AT) as usize).min(MAX_EVENTS);
    for i in 0..events {
        let at = EVENTS_AT + i * EVENT_LEN;
        let slot = get_u8(at + 1) as usize;
        if get_u8(at) == EVENT_WALL_CONTACT && slot < SLOTS {
            set_countdown(slot, CURSE_TICKS);
        }
    }
    let active = get_u32(ACTIVE_AT);
    let mut commands = 0;
    for slot in 0..SLOTS {
        let left = countdown(slot);
        if left == 0 {
            continue;
        }
        set_countdown(slot, left - 1);
        // A slot that emptied (a craft gone from the grid) is not named: the host
        // refuses a command for a slot with no craft.
        if active & (1 << slot) == 0 {
            continue;
        }
        let at = REPLY_AT + 4 + commands * COMMAND_LEN;
        put_u8(at, COMMAND_SCALE_THRUST);
        put_u8(at + 1, slot as u8);
        put_u32(at + 4, CURSE_FACTOR.to_bits());
        commands += 1;
    }
    put_u32(REPLY_AT, commands as u32);
    0
}

#[panic_handler]
fn panic(_: &core::panic::PanicInfo<'_>) -> ! {
    core::arch::wasm32::unreachable()
}
