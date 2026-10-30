//! Energy Turbo: a pickup of its own, handed out in place of every second Turbo.
//!
//! - **Pick it up**: `pickup_roll` swaps every second Turbo a weapon pad draws for this
//!   pickup; `hud_tint` draws it as the Turbo's icon on a red backdrop; while boosting, `hud_bar_extra` and `hud_shake` show the added speed and the drain. The engine
//!   never fires or absorbs it.
//! - **Hold fire**: the craft boosts (`scale_thrust`) and pays from its shield
//!   (`shield_delta`) while fire is held and the pool lasts. An AI craft holds no
//!   button: it boosts for a 1 s burst when its driver fires, then rests 2 s.
//! - **Absorb it**: half of the energy spent on it comes back.
//! - **Speed pads**: while it is carried, a pad fills the pool instead of boosting:
//!   `scale_slot_pads` at 0 takes the pad's push, and the `SpeedPad` event that a
//!   craft scaled so on the tick it entered hears pays the energy.
//!
//! The drain stops short of wrecking the craft, but a hit on a drained pool wrecks it
//! as any hit does.
//!
//! A simulation module on the `oag-ext` guest SDK. Nothing survives a tick in this
//! module's memory; each slot's numbers live in the state blob the host owns.
#![cfg_attr(not(test), no_std)]

use oag_ext::{
    Craft, Cue, Effect, Event, Extension, HudElement, Observation, Pickup, Reply, Rgba, Slot, Weapon,
};

// The numbers below are chosen, not measured.

/// Thrust factor while boosting.
const BOOST_FACTOR: f32 = 1.9;
/// A boosting tick's cost, as a share of the craft's pool (about 48 % a second).
const DRAIN_SHARE: f32 = 0.008;
/// No boost below this share of the pool, so the drain alone never wrecks a craft.
const FLOOR_SHARE: f32 = 0.05;
/// The share of the energy spent that an absorb gives back: the maintainer's cap.
const PAYBACK: f32 = 0.5;
/// What a speed pad gives while the turbo is carried, as a share of the pool.
const PAD_SHARE: f32 = 0.15;
/// An AI craft's boost per decision to fire, in ticks (1 s).
const AI_BURST: u16 = 60;
/// Ticks an AI craft rests after a burst; its driver asks every tick the Turbo gate
/// passes, so without a rest it would boost down every straight.
const AI_REST: u16 = 120;
/// One Turbo in this many becomes this pickup.
const ROLL_EVERY: u8 = 2;
/// Ticks between two spark bursts at the nozzle.
const SPARK_EVERY: u8 = 20;
/// The energy bar's shake while the turbo drains, in HUD pixels. Chosen.
const SHAKE: f32 = 2.0;
const RED: Rgba = Rgba::new(0xE0, 0x20, 0x20, 0xFF);
const SLOTS: usize = 8;

oag_ext::blob! {
    /// One slot's account of the turbo it carries (12 bytes).
    #[derive(Clone, Copy, Default)]
    pub struct Memory {
        /// Energy spent on it so far.
        pub spent: f32,
        /// An AI craft's boost ticks left.
        pub burst: u16,
        /// It boosted last tick.
        pub boosting: bool,
        /// Ticks to the next spark burst.
        pub spark: u8,
        /// An AI craft's burst-and-rest ticks left.
        pub rest: u16,
        /// It sent its slot's speed pads to 0 last tick, so a pad entered then gave no
        /// boost and pays energy.
        pub pad_held: bool,
        /// Pads the record to 12 bytes. The fields keep the order the module was first
        /// built with, so the blob layout does not move.
        pub _spare: u8,
    }
}

oag_ext::blob! {
    /// Every slot's record.
    pub struct Slots {
        pub slots: [Memory; SLOTS],
    }
}

pub struct EnergyTurbo;

/// This tick's events, one bit per slot each.
#[derive(Default)]
struct Events {
    fired: u32,
    absorbed: u32,
    pads: u32,
}

impl Events {
    fn read(obs: &Observation<'_>) -> Self {
        let mut events = Self::default();
        for event in obs.events() {
            match event {
                Event::PickupFire { slot } => events.fired |= slot.bit(),
                Event::PickupAbsorbed { slot } => events.absorbed |= slot.bit(),
                Event::SpeedPad { slot, .. } => events.pads |= slot.bit(),
                _ => {}
            }
        }
        events
    }
}

fn has(mask: u32, craft: &Craft<'_>) -> bool {
    mask & craft.slot().bit() != 0
}

/// Starts, runs down and rests an AI craft's burst. It holds no button, so its driver
/// firing the Turbo is the only signal.
fn ai_wants_boost(memory: &mut Memory, fired: bool) -> bool {
    if memory.burst == 0 && memory.rest == 0 && fired {
        memory.burst = AI_BURST;
        memory.rest = AI_BURST + AI_REST;
    }
    memory.rest = memory.rest.saturating_sub(1);
    let wants = memory.burst > 0;
    memory.burst = memory.burst.saturating_sub(1);
    wants
}

/// One boosting tick: thrust, the drain (added to `delta`), sparks at the nozzle. The
/// cue is returned on the tick the boost starts.
fn boost(
    reply: &mut Reply<'_>,
    craft: &Craft<'_>,
    memory: &mut Memory,
    delta: &mut f32,
) -> Option<Cue> {
    let cost = craft.shield_max() * DRAIN_SHARE;
    *delta -= cost;
    memory.spent += cost;
    let _ = reply.scale_thrust(craft, BOOST_FACTOR);
    // The speed bar shows the vanilla share and, blending into red, the share this
    // turbo adds; the energy bar shakes while it drains.
    let _ = reply.hud_bar_extra(craft, HudElement::Speed, BOOST_FACTOR - 1.0, RED);
    let _ = reply.hud_shake(craft, HudElement::Energy, SHAKE);
    if memory.spark == 0 {
        let _ = reply.fire_effect(craft, Effect::CollisionSpark);
        memory.spark = SPARK_EVERY;
    }
    memory.spark -= 1;
    (!memory.boosting).then_some(Cue::Turbo)
}

/// The host refuses a change beyond the pool's maximum either way. An `if` chain rather
/// than `clamp` or `min`/`max`: it builds about 30 bytes smaller.
fn bounded(delta: f32, max: f32) -> f32 {
    if delta > max {
        max
    } else if delta < -max {
        -max
    } else {
        delta
    }
}

fn settle(reply: &mut Reply<'_>, craft: &Craft<'_>, delta: f32, cue: Option<Cue>) {
    if delta != 0.0 {
        let _ = reply.shield_delta(craft, bounded(delta, craft.shield_max()));
    }
    if let Some(cue) = cue {
        let _ = reply.play_cue(craft, cue);
    }
}

impl Extension for EnergyTurbo {
    type State = Slots;

    fn tick(obs: &Observation<'_>, state: &mut Slots, reply: &mut Reply<'_>) {
        let events = Events::read(obs);
        // Replies are refused only past the command cap or outside their bounds, which
        // this module never reaches, so their results are dropped.
        let _ = reply.pickup_roll(Weapon::Turbo, ROLL_EVERY);
        for (index, memory) in state.slots.iter_mut().enumerate() {
            let Some(craft) = Slot::new(index).and_then(|slot| obs.craft(slot)) else {
                *memory = Memory::default();
                continue;
            };

            let mut delta = 0.0_f32;
            let mut cue = None;
            if has(events.absorbed, &craft) && memory.spent > 0.0 {
                delta += memory.spent * PAYBACK;
                cue = Some(Cue::Absorb);
            }
            if craft.pickup() != Pickup::Ours || !craft.is_racing() {
                // Absorbed, wrecked or replaced: this turbo's account is closed.
                *memory = Memory::default();
                settle(reply, &craft, delta, cue);
                continue;
            }

            let _ = reply.scale_slot_pads(&craft, 0.0);
            let _ = reply.hud_tint(&craft, HudElement::Pickup, RED);
            if has(events.pads, &craft) && memory.pad_held {
                delta += craft.shield_max() * PAD_SHARE;
            }
            memory.pad_held = true;
            let wants = if craft.is_person() {
                craft.fire_held()
            } else {
                ai_wants_boost(memory, has(events.fired, &craft))
            };
            let affordable = craft.shield() + delta - craft.shield_max() * DRAIN_SHARE
                > craft.shield_max() * FLOOR_SHARE;
            let boosting = wants && affordable;
            if boosting {
                cue = boost(reply, &craft, memory, &mut delta).or(cue);
            } else {
                memory.spark = 0;
            }
            memory.boosting = boosting;
            settle(reply, &craft, delta, cue);
        }
    }
}

oag_ext::export!(EnergyTurbo);

#[cfg(test)]
mod tests {
    use oag_ext::test::{CraftRecord, Race};
    use oag_ext::{Command, Event, Pickup, Slot};

    use super::*;

    fn carrier(person: bool, fire_held: bool) -> CraftRecord {
        CraftRecord {
            pickup: Pickup::Ours,
            person,
            fire_held,
            racing: true,
            shield: 100.0,
            shield_max: 100.0,
            speed_kmh: 400.0,
            ..CraftRecord::default()
        }
    }

    #[test]
    fn a_person_holding_fire_boosts_on_the_shield_and_an_absorb_pays_half_back() {
        let me = Slot::new(0).unwrap();
        let mut race = Race::<EnergyTurbo>::new().with_craft(me, carrier(true, true));
        let first = race.tick();
        assert_eq!(
            first[..4],
            [
                Command::PickupRoll {
                    weapon: Weapon::Turbo,
                    every: ROLL_EVERY
                },
                Command::ScaleSlotPads {
                    slot: me,
                    factor: 0.0
                },
                Command::HudTint {
                    slot: me,
                    element: HudElement::Pickup,
                    rgba: RED
                },
                Command::ScaleThrust {
                    slot: me,
                    factor: BOOST_FACTOR
                },
            ]
        );
        assert!(first.contains(&Command::HudBarExtra {
            slot: me,
            element: HudElement::Speed,
            extra: BOOST_FACTOR - 1.0,
            rgba: RED
        }));
        assert!(first.contains(&Command::HudShake {
            slot: me,
            element: HudElement::Energy,
            amplitude: SHAKE
        }));
        assert!(first.contains(&Command::PlayCue {
            slot: me,
            cue: Cue::Turbo
        }));
        let spent = race.state().slots[0].spent;
        assert_eq!(spent, 100.0 * DRAIN_SHARE);
        // Absorbed: the pickup is gone, half of the spend comes back.
        *race.craft_mut(me) = Some(CraftRecord {
            pickup: Pickup::None,
            ..carrier(true, false)
        });
        race.event(Event::PickupAbsorbed { slot: me });
        let paid = race.tick();
        assert!(
            !paid.iter().any(|c| matches!(
                c,
                Command::HudShake { .. } | Command::HudBarExtra { .. }
            )),
            "not boosting: the bars hold still"
        );
        assert_eq!(
            paid[1..],
            [
                Command::ShieldDelta {
                    slot: me,
                    amount: spent * PAYBACK
                },
                Command::PlayCue {
                    slot: me,
                    cue: Cue::Absorb
                },
            ]
        );
        assert_eq!(race.state().slots[0].spent, 0.0);
    }

    #[test]
    fn a_speed_pad_pays_energy_only_when_entered_with_the_pads_held_at_zero() {
        let me = Slot::new(1).unwrap();
        let pad = |race: &mut Race<EnergyTurbo>| {
            race.event(Event::SpeedPad { slot: me, pad: 0 });
            race.tick()
                .iter()
                .find_map(|c| match c {
                    Command::ShieldDelta { amount, .. } => Some(*amount),
                    _ => None,
                })
        };
        let mut race = Race::<EnergyTurbo>::new().with_craft(me, carrier(true, false));
        // The pickup arrived this tick: the pad entered last tick boosted as ever.
        assert_eq!(pad(&mut race), None);
        // Carried since: the pads were held at zero, so the next one pays.
        assert_eq!(pad(&mut race), Some(100.0 * PAD_SHARE));
    }

    #[test]
    fn an_ai_craft_boosts_a_burst_then_rests() {
        let ai = Slot::new(3).unwrap();
        let mut race = Race::<EnergyTurbo>::new().with_craft(ai, carrier(false, false));
        race.event(Event::PickupFire { slot: ai });
        let boosting = |commands: &[Command]| {
            commands
                .iter()
                .any(|c| matches!(c, Command::ScaleThrust { .. }))
        };
        let ticks: Vec<bool> = (0..u32::from(AI_BURST + AI_REST) + 1)
            .map(|tick| {
                if tick > 0 {
                    race.event(Event::PickupFire { slot: ai });
                }
                boosting(&race.tick())
            })
            .collect();
        assert!(ticks[..usize::from(AI_BURST)].iter().all(|b| *b));
        assert!(
            ticks[usize::from(AI_BURST)..usize::from(AI_BURST + AI_REST)]
                .iter()
                .all(|b| !*b)
        );
        assert!(ticks[usize::from(AI_BURST + AI_REST)]);
    }
}
