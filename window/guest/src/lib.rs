//! Window: every so often a window stands on the road ahead of each person's craft, showing the
//! road further on through `portal_view`.
//!
//! - **The surface**: `fire_mod_effect_ahead` plays `fx/window.toml`, a particle
//!   `fx/window.wgsl` draws, at a place on the road the guest then knows as lap progress.
//! - **The view**: `portal_view` re-sent each tick the window stands, at the entrance and an exit
//!   further on. The engine draws the scene through the pair; the shader reads it. One more scene
//!   a frame while the window is in the view, none otherwise. `ViewUpdate::Once` here would be
//!   one snapshot, for the price of one scene.
//!
//! All of it is drawn: nothing here reaches the race.
#![cfg_attr(not(test), no_std)]

use oag_ext::{Distance, Extension, Observation, Reply, ViewUpdate};

// The numbers below are chosen.

/// A craft gets its first window at this speed, and another this many ticks after the last.
const SPEED_KMH: f32 = 440.0;
const EVERY: u32 = 480;
/// How long one stands: `fx/window.toml`'s lifetime.
const STANDS: u32 = 240;
/// How far ahead of the craft it is put up, in track units.
const AHEAD: f32 = 420.0;
/// How far on from the window the view looks out, in track units.
const LOOKS_ON: f32 = 640.0;
/// How far the surface reaches from its centre: half `fx/window.toml`'s size.
const RADIUS: u8 = 22;
/// `[effects]`, by place in name order.
const WINDOW_EFFECT: u16 = 0;

oag_ext::blob! {
    /// One window per slot: where it stands and looks out, on the lap, and when it was put up.
    #[derive(Clone, Copy, Default)]
    pub struct Windows {
        pub entrance: [f32; 8],
        pub exit: [f32; 8],
        pub up_at: [u32; 8],
    }
}

/// `progress` on by `units`, taken round to a place on the lap.
fn on(progress: f32, units: f32, length: f32) -> f32 {
    let at = progress + units;
    let laps = (at / length) as i32 as f32;
    let at = at - laps * length;
    if at < 0.0 { at + length } else { at }
}

struct Window;

impl Extension for Window {
    type State = Windows;

    fn tick(obs: &Observation<'_>, state: &mut Windows, reply: &mut Reply<'_>) {
        let tick = obs.tick() as u32;
        let length = obs.course_length();
        for craft in obs.crafts() {
            let index = craft.slot().index();
            if !craft.is_person() || !craft.is_racing() || index >= state.up_at.len() {
                continue;
            }
            let up_at = state.up_at[index];
            let due = craft.speed_kmh() >= SPEED_KMH && (up_at == 0 || tick >= up_at + EVERY);
            if let (true, Some(progress)) = (due, craft.progress()) {
                let placed = reply.fire_mod_effect_ahead(
                    &craft,
                    WINDOW_EFFECT,
                    Distance::Units(AHEAD),
                );
                if placed.is_ok() {
                    state.entrance[index] = on(progress, AHEAD, length);
                    state.exit[index] = on(state.entrance[index], LOOKS_ON, length);
                    state.up_at[index] = tick;
                }
            }
            let up_at = state.up_at[index];
            if up_at != 0 && tick < up_at + STANDS {
                // A reply that is full loses a look and nothing else.
                let _ = reply.portal_view(
                    &craft,
                    (state.entrance[index], state.exit[index]),
                    RADIUS,
                    ViewUpdate::Continuous,
                    0,
                );
            }
        }
    }
}

oag_ext::export!(Window);
