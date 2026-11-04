//! Tether: a beam from each person's craft to the nearest craft in its cone, through the mod's
//! own shaders.
//!
//! - **The beam**: `draw_beam` every tick the target stays in the cone (`Aim::in_cone`), through
//!   `fx/beam.wgsl`, a shader of `[shaders]`. Re-sent each tick it should hold.
//! - **A new lock**: `fire_mod_effect_ahead` plays `fx/lock.toml`, a particle `fx/ring.wgsl`
//!   draws, on the road ahead.
//! - **While locked**: `screen_fill_shaded` darkens that craft's view through
//!   `fx/vignette.wgsl`, and `set_shader_param` drives the pulses' speed by the range.
//!
//! All of it is drawn: nothing here reaches the race. A lock is the one thing kept between
//! ticks, in the state blob. The AI's crafts could carry one each, for the price of a picture
//! full of lines.
#![cfg_attr(not(test), no_std)]

use oag_ext::{Craft, Distance, Extension, Observation, Reply, Rgba, Slot};

// The numbers below are chosen.

/// How far ahead a craft reaches, in world units.
const RANGE: f32 = 260.0;
/// The cone: units off the line per unit ahead.
const SPREAD: f32 = 0.35;
/// Half the beam's width, in world units.
const HALF_WIDTH: f32 = 2.0;
/// Where a new lock's ring stands.
const RING_AHEAD: f32 = 200.0;
const BLUE: Rgba = Rgba::new(0x20, 0xC0, 0xFF, 0xFF);
/// `[effects]`, by place in name order.
const LOCK_EFFECT: u16 = 0;
/// `[shaders]`, by place in name order.
const SHADER_BEAM: u16 = 0;
const SHADER_VIGNETTE: u16 = 2;
/// fx/beam.wgsl's `speed`, its first scalar.
const PARAM_SPEED: u8 = 0;

oag_ext::blob! {
    /// One flag per slot: a craft held a lock last tick (8 bytes).
    #[derive(Clone, Copy, Default)]
    pub struct Lock {
        pub held: [u8; 8],
    }
}

/// The nearest craft ahead of `craft` inside the cone, and how far ahead it is.
fn target(obs: &Observation<'_>, craft: &Craft<'_>) -> Option<(Slot, f32)> {
    obs.crafts()
        .filter(|other| other.slot() != craft.slot() && other.is_racing())
        .filter_map(|other| {
            let aim = craft.aim_at(other.slot());
            aim.in_cone(RANGE, SPREAD)
                .then_some((other.slot(), aim.ahead()))
        })
        .fold(None, |best: Option<(Slot, f32)>, next| match best {
            Some(best) if best.1 <= next.1 => Some(best),
            _ => Some(next),
        })
}

struct Tether;

impl Extension for Tether {
    type State = Lock;

    fn tick(obs: &Observation<'_>, state: &mut Lock, reply: &mut Reply<'_>) {
        for craft in obs.crafts() {
            let index = craft.slot().index();
            let aimed = if craft.is_racing() && craft.is_person() {
                target(obs, &craft)
            } else {
                None
            };
            let Some(flag) = state.held.get_mut(index) else {
                continue;
            };
            let was = *flag != 0;
            *flag = u8::from(aimed.is_some());
            let Some((to, ahead)) = aimed else { continue };
            // A reply that is full loses a look and nothing else.
            let _ = reply.draw_beam(&craft, to, BLUE, HALF_WIDTH, Some(SHADER_BEAM));
            let _ = reply.set_shader_param(
                &craft,
                SHADER_BEAM,
                PARAM_SPEED,
                1.0 + 3.0 * (1.0 - ahead / RANGE),
            );
            let _ = reply.screen_fill_shaded(&craft, BLUE, SHADER_VIGNETTE);
            if !was {
                let _ = reply.fire_mod_effect_ahead(&craft, LOCK_EFFECT, Distance::Units(RING_AHEAD));
            }
        }
    }
}

oag_ext::export!(Tether);
