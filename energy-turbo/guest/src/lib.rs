//! Energy Turbo: every Turbo pickup becomes an energy turbo.
//!
//! - **Carry it**: the module claims the craft's Turbo (`claim-pickup`), so the engine
//!   no longer fires it as a Turbo; its backdrop on the HUD turns red (`pickup-tint`).
//! - **Hold fire**: the craft boosts (`scale-thrust` above 1) and pays for it from its
//!   shield (`shield-delta`), for as long as fire is held and the pool lasts. An AI
//!   craft, which holds no button, boosts for a fixed burst each time its driver fires.
//!   A Turbo cue on each boost start, the title's wall sparks at the nozzle while it
//!   runs.
//! - **Absorb it**: the pickup is gone and half of the energy spent on it comes back.
//! - **Speed pads**: while it is carried, a pad gives no boost (`pad-mode`) and fills
//!   the pool instead, a separate income that is not part of the absorb's half.
//!
//! The risk is the empty pool: the drain stops short of wrecking the craft, but a hit on
//! a drained pool wrecks it as any hit does.
//!
//! OpenAntiGrav extension ABI 1 (`oag_modhost::abi`). Nothing survives a tick in this
//! module's memory; each slot's numbers live in the 64-byte state blob the host owns.
#![no_std]

use core::ptr::{addr_of_mut, read_volatile, write_volatile};

/// Thrust while boosting. Chosen.
const BOOST_FACTOR: f32 = 1.6;
/// Energy a boosting tick costs, as a share of the craft's pool (about 24 % a second).
/// Chosen.
const DRAIN_SHARE: f32 = 0.004;
/// No boost below this share of the pool: the drain alone never wrecks a craft. Chosen.
const FLOOR_SHARE: f32 = 0.05;
/// What an absorb gives back of the energy spent on the turbo it absorbs. The
/// maintainer's cap, taken at the cap rather than "nothing" so absorbing is a choice.
const PAYBACK: f32 = 0.5;
/// What a speed pad gives while the turbo is carried, as a share of the pool. Chosen.
const PAD_SHARE: f32 = 0.15;
/// An AI craft's boost per decision to fire, ticks (1 s). Chosen.
const AI_BURST: u16 = 60;
/// Ticks between two spark bursts at the nozzle. Chosen.
const SPARK_EVERY: u8 = 6;
/// The backdrop's red: 0xE0, 0x20, 0x20, opaque. Chosen.
const RED: u32 = 0xFF20_20E0;

/// `oag_tables::weapons::Weapon::ALL`'s Turbo, plus one.
const TURBO: u8 = 5;

// The ABI 1 layout (`oag_modhost::abi`).
const IO_LEN: usize = 4096;
const EVENT_COUNT_AT: usize = 24;
const EVENTS_AT: usize = 32;
const MAX_EVENTS: usize = 32;
const STATE_AT: usize = EVENTS_AT + 8 * MAX_EVENTS;
const REPLY_AT: usize = STATE_AT + 1024;
const MAX_COMMANDS: usize = 64;
const CRAFTS_AT: usize = REPLY_AT + 4 + 12 * MAX_COMMANDS;
const EVENT_PICKUP_FIRE: u8 = 2;
const EVENT_PICKUP_ABSORBED: u8 = 3;
const EVENT_PAD_ENERGY: u8 = 4;
const SCALE_THRUST: u8 = 1;
const SHIELD_DELTA: u8 = 2;
const CLAIM_PICKUP: u8 = 3;
const PAD_MODE: u8 = 4;
const PLAY_CUE: u8 = 5;
const FIRE_EFFECT: u8 = 6;
const PICKUP_TINT: u8 = 7;
const CUE_TURBO: u16 = 1;
const CUE_ABSORB: u16 = 3;
const EFFECT_SPARKS: u16 = 0;
const CRAFT_PERSON: u8 = 1;
const CRAFT_FIRE_HELD: u8 = 2;
const CRAFT_RACING: u8 = 4;
const CRAFT_CLAIMED: u8 = 8;

/// Grid slots: one 8-byte record each in the blob.
const SLOTS: usize = 8;

static mut IO: [u8; IO_LEN] = [0; IO_LEN];

fn io() -> *mut u8 {
    addr_of_mut!(IO).cast()
}

fn get_u8(at: usize) -> u8 {
    // SAFETY: every caller indexes below `IO_LEN`.
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

fn get_f32(at: usize) -> f32 {
    f32::from_bits(get_u32(at))
}

/// One slot's record in the blob.
struct Memory {
    spent: f32,
    burst: u16,
    boosting: bool,
    spark: u8,
}

fn load(slot: usize) -> Memory {
    let at = STATE_AT + slot * 8;
    Memory {
        spent: get_f32(at),
        burst: u16::from_le_bytes([get_u8(at + 4), get_u8(at + 5)]),
        boosting: get_u8(at + 6) != 0,
        spark: get_u8(at + 7),
    }
}

fn store(slot: usize, memory: &Memory) {
    let at = STATE_AT + slot * 8;
    put_u32(at, memory.spent.to_bits());
    let [lo, hi] = memory.burst.to_le_bytes();
    put_u8(at + 4, lo);
    put_u8(at + 5, hi);
    put_u8(at + 6, u8::from(memory.boosting));
    put_u8(at + 7, memory.spark);
}

struct Reply {
    count: usize,
}

impl Reply {
    fn push(&mut self, kind: u8, slot: usize, arg: u16, value: f32, word: u32) {
        let at = REPLY_AT + 4 + self.count * 12;
        put_u8(at, kind);
        put_u8(at + 1, slot as u8);
        let [lo, hi] = arg.to_le_bytes();
        put_u8(at + 2, lo);
        put_u8(at + 3, hi);
        put_u32(at + 4, value.to_bits());
        put_u32(at + 8, word);
        self.count += 1;
    }
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
    // This tick's events, one bit per slot each.
    let (mut fired, mut absorbed, mut pads) = (0_u32, 0_u32, 0_u32);
    let events = (get_u32(EVENT_COUNT_AT) as usize).min(MAX_EVENTS);
    for i in 0..events {
        let at = EVENTS_AT + i * 8;
        let slot = get_u8(at + 1);
        if usize::from(slot) >= SLOTS {
            continue;
        }
        match get_u8(at) {
            EVENT_PICKUP_FIRE => fired |= 1 << slot,
            EVENT_PICKUP_ABSORBED => absorbed |= 1 << slot,
            EVENT_PAD_ENERGY => pads |= 1 << slot,
            _ => {}
        }
    }
    let mut reply = Reply { count: 0 };
    for slot in 0..SLOTS {
        let craft = CRAFTS_AT + slot * 16;
        let (pickup, flags) = (get_u8(craft), get_u8(craft + 1));
        let (shield, max) = (get_f32(craft + 4), get_f32(craft + 8));
        let bit = |mask: u32| mask & (1 << slot) != 0;
        let mut memory = load(slot);
        let mut delta = 0.0_f32;
        let mut cue = None;

        // Absorbed: half of what this turbo cost comes back.
        if bit(absorbed) && memory.spent > 0.0 {
            delta += memory.spent * PAYBACK;
            cue = Some(CUE_ABSORB);
        }
        let carries = pickup == TURBO && flags & CRAFT_RACING != 0;
        if !carries {
            // Absorbed, wrecked or replaced: this turbo's account is closed.
            memory = Memory { spent: 0.0, burst: 0, boosting: false, spark: 0 };
        } else {
            if flags & CRAFT_CLAIMED == 0 {
                reply.push(CLAIM_PICKUP, slot, 0, 0.0, 0);
            }
            reply.push(PAD_MODE, slot, 0, 0.0, 0);
            reply.push(PICKUP_TINT, slot, 0, 0.0, RED);
            if bit(pads) {
                delta += max * PAD_SHARE;
            }
            if flags & CRAFT_PERSON == 0 && bit(fired) {
                memory.burst = AI_BURST;
            }
            let wants = if flags & CRAFT_PERSON != 0 {
                flags & CRAFT_FIRE_HELD != 0
            } else {
                memory.burst > 0
            };
            memory.burst = memory.burst.saturating_sub(1);
            let cost = max * DRAIN_SHARE;
            let boosting = wants && shield + delta - cost > max * FLOOR_SHARE;
            if boosting {
                reply.push(SCALE_THRUST, slot, 0, BOOST_FACTOR, 0);
                delta -= cost;
                memory.spent += cost;
                if !memory.boosting {
                    cue = Some(CUE_TURBO);
                }
                if memory.spark == 0 {
                    reply.push(FIRE_EFFECT, slot, EFFECT_SPARKS, 0.0, 0);
                    memory.spark = SPARK_EVERY;
                }
                memory.spark -= 1;
            } else {
                memory.spark = 0;
            }
            memory.boosting = boosting;
        }
        if delta != 0.0 {
            // The host refuses more than the pool's maximum either way.
            let bounded = if delta > max { max } else if delta < -max { -max } else { delta };
            reply.push(SHIELD_DELTA, slot, 0, bounded, 0);
        }
        if let Some(code) = cue {
            reply.push(PLAY_CUE, slot, code, 0.0, 0);
        }
        store(slot, &memory);
    }
    put_u32(REPLY_AT, reply.count as u32);
    0
}

#[panic_handler]
fn panic(_: &core::panic::PanicInfo<'_>) -> ! {
    core::arch::wasm32::unreachable()
}
