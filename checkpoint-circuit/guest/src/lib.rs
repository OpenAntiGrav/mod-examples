//! Checkpoint Circuit: every craft races a clock to its next checkpoint, and a pit lane
//! puts energy back.
//!
//! - **Checkpoints**: the track's triggers with `mod_checkpoint = n` (1 to 4 in lap
//!   order). Each craft has `CHECKPOINT_TICKS` to reach the next one; reaching it (a
//!   `TriggerEnter` on that trigger) resets the clock. Past zero the craft loses
//!   `DRAIN_SHARE` of its energy a tick (`shield_delta`) until it reaches the checkpoint
//!   or is wrecked. A checkpoint out of order does nothing.
//! - **Pit lane**: the trigger with `mod_pit = 1`. Inside it a craft gains
//!   `RECHARGE_SHARE` of its energy a tick, never past its maximum.
//! - **HUD**: a person's craft shows the time left under the mod's `CPC_CHECKPOINT`
//!   string, red in the last three seconds; past zero the energy bar turns red and
//!   shakes; in the pit `CPC_RECHARGING` shows and the energy bar turns cyan.
//! - **AI**: an AI craft below `AI_LOW_SHARE` of its energy asks to take the pit lane
//!   (`prefer_route` on the route carrying the pit lane's `mod_pit`) every tick it stays
//!   low; the host still throws the coin at the fork, so a craft with energy to spare
//!   takes whichever way its coin says. It drives the pit lane with the same physics as
//!   every other craft: the hook only picks the way.
//!
//! A track module on the `oag-ext` guest SDK, bound to `tracks/checkpoint-circuit.track.toml`.
//! Nothing survives a tick in this module's memory; each slot's clock lives in the state
//! blob the host owns, hashes and rolls back.
#![cfg_attr(not(test), no_std)]

use core::fmt::Write;

use oag_ext::{
    Anchor, Craft, Event, Extension, HudElement, HudPlace, Line, MAX_CRAFTS, Observation, Reply,
    Rgba, Track,
};

// The numbers below are chosen, not measured.

/// Ticks a craft has to reach its next checkpoint: 20 s at the engine's 60 Hz.
pub const CHECKPOINT_TICKS: u16 = 1200;
/// What a craft past its time loses a tick, as a share of its maximum: a full pool
/// lasts 4 s.
pub const DRAIN_SHARE: f32 = 1.0 / 240.0;
/// What a craft in the pit lane gains a tick, as a share of its maximum: empty to full
/// in 5 s.
pub const RECHARGE_SHARE: f32 = 1.0 / 300.0;
/// Below this share of its maximum an AI craft asks for the pit lane.
pub const AI_LOW_SHARE: f32 = 0.4;
/// The last stretch of the clock drawn in red: 3 s.
const WARN_TICKS: u16 = 180;
/// The energy bar's shake while it drains, HUD pixels.
const SHAKE: f32 = 2.0;
const WHITE: Rgba = Rgba::new(0xFF, 0xFF, 0xFF, 0xFF);
const RED: Rgba = Rgba::new(0xFF, 0x30, 0x30, 0xFF);
const CYAN: Rgba = Rgba::new(0x40, 0xE0, 0xFF, 0xFF);

oag_ext::blob! {
    /// Every slot's clock (64 bytes).
    #[derive(Debug, Clone, Copy, PartialEq, Default)]
    pub struct Clocks {
        /// Ticks left to the next checkpoint.
        pub left: [u16; MAX_CRAFTS],
        /// The next checkpoint's number, 0 before the craft's race starts.
        pub next: [u8; MAX_CRAFTS],
        /// 1 while the craft is inside the pit trigger.
        pub pit: [u8; MAX_CRAFTS],
    }
}

/// What the track says, read off the region each tick.
struct Course {
    /// The highest checkpoint number: the lap's last.
    checkpoints: u8,
    /// The route through the pit lane, if the track has one.
    pit_route: Option<u16>,
}

impl Course {
    fn read(track: &Track<'_>) -> Self {
        let checkpoints = (0..track.triggers() as u16)
            .filter_map(|t| track.trigger(t)?.prop(oag_ext::prop!("checkpoint")))
            .fold(0_u8, |most, n| most.max(n as u8));
        let pit_route = (0..track.routes() as u16).find(|&r| {
            track
                .route(r)
                .and_then(|route| route.prop(oag_ext::prop!("pit")))
                .is_some_and(|v| v != 0.0)
        });
        Self {
            checkpoints,
            pit_route,
        }
    }
}

pub struct CheckpointCircuit;

impl Extension for CheckpointCircuit {
    type State = Clocks;

    fn tick(obs: &Observation<'_>, state: &mut Clocks, reply: &mut Reply<'_>) {
        let track = obs.track();
        let course = Course::read(&track);
        if course.checkpoints == 0 {
            return;
        }
        for event in obs.events() {
            match event {
                Event::TriggerEnter { slot, trigger } => {
                    let Some(entity) = track.trigger(trigger) else {
                        continue;
                    };
                    let i = slot.index();
                    if let Some(n) = entity.prop(oag_ext::prop!("checkpoint"))
                        && state.next[i] != 0
                        && n as u8 == state.next[i]
                    {
                        state.left[i] = CHECKPOINT_TICKS;
                        state.next[i] = state.next[i] % course.checkpoints + 1;
                    }
                    if entity.prop(oag_ext::prop!("pit")).is_some_and(|v| v != 0.0) {
                        state.pit[i] = 1;
                    }
                }
                Event::TriggerExit { slot, trigger } => {
                    if track
                        .trigger(trigger)
                        .and_then(|entity| entity.prop(oag_ext::prop!("pit")))
                        .is_some_and(|v| v != 0.0)
                    {
                        state.pit[slot.index()] = 0;
                    }
                }
                _ => {}
            }
        }
        for craft in obs.crafts() {
            let i = craft.slot().index();
            let finished = craft.laps_target() > 0 && craft.lap() > craft.laps_target();
            if !craft.is_racing() || finished {
                continue;
            }
            if state.next[i] == 0 {
                state.next[i] = 1;
                state.left[i] = CHECKPOINT_TICKS;
            }
            state.left[i] = state.left[i].saturating_sub(1);
            let max = craft.shield_max();
            let mut delta = 0.0;
            if state.left[i] == 0 {
                delta -= max * DRAIN_SHARE;
            }
            if state.pit[i] != 0 {
                delta += (max * RECHARGE_SHARE).min(max - craft.shield());
            }
            if delta != 0.0 {
                let _ = reply.shield_delta(&craft, delta);
            }
            if craft.is_person() {
                hud(reply, &craft, state.left[i], state.pit[i] != 0);
            } else if let Some(route) = course.pit_route
                && craft.shield() < max * AI_LOW_SHARE
            {
                let _ = reply.prefer_route(&craft, route);
            }
        }
    }
}

/// The clock, and the drain or the recharge, on a person's HUD.
fn hud(reply: &mut Reply<'_>, craft: &Craft<'_>, left: u16, in_pit: bool) {
    let top = |y, quarters| HudPlace {
        anchor: Anchor::Top,
        quarters,
        x: 0,
        y,
    };
    let _ = reply.hud_string(craft, top(6, 3), WHITE, "CPC_CHECKPOINT");
    let tenths = u32::from(left) * 10 / 60;
    let mut line = Line::new();
    let _ = write!(line, "{}.{}", tenths / 10, tenths % 10);
    let colour = if left <= WARN_TICKS { RED } else { WHITE };
    let _ = reply.hud_text(craft, top(20, 5), colour, line.as_str());
    if left == 0 {
        let _ = reply.hud_tint(craft, HudElement::Energy, RED);
        let _ = reply.hud_shake(craft, HudElement::Energy, SHAKE);
    }
    if in_pit {
        let place = HudPlace {
            anchor: Anchor::Center,
            quarters: 5,
            x: 0,
            y: -70,
        };
        let _ = reply.hud_string(craft, place, CYAN, "CPC_RECHARGING");
        if left > 0 {
            let _ = reply.hud_tint(craft, HudElement::Energy, CYAN);
        }
    }
}

oag_ext::export!(CheckpointCircuit);

#[cfg(test)]
mod tests;
