//! Energy Turbo: a pickup of its own, handed out in place of every second Turbo.
//!
//! - **Pick it up**: `pickup_roll` swaps every second Turbo a weapon pad draws for this
//!   pickup; `pickup_tint` draws it as the Turbo's icon on a red backdrop. The engine
//!   never fires or absorbs it.
//! - **Hold fire**: the craft boosts (`scale_thrust`) and pays from its shield
//!   (`shield_delta`) while fire is held and the pool lasts. An AI craft holds no
//!   button: it boosts for a 1 s burst when its driver fires, then rests 2 s.
//! - **Absorb it**: half of the energy spent on it comes back.
//! - **Speed pads**: while it is carried, a pad fills the pool instead of boosting.
//!
//! The drain stops short of wrecking the craft, but a hit on a drained pool wrecks it
//! as any hit does.
//!
//! A simulation module on the `oag-ext` guest SDK. Nothing survives a tick in this
//! module's memory; each slot's numbers live in the state blob the host owns.
#![cfg_attr(not(test), no_std)]

use oag_ext::{Cue, Effect, Event, Extension, Observation, Pickup, Reply, Rgba, Slot, Weapon};

// The numbers below are chosen, not measured.

/// Thrust factor while boosting.
const BOOST_FACTOR: f32 = 1.9;
/// A boosting tick's cost, as a share of the craft's pool (about 48 % a second).
const DRAIN_SHARE: f32 = 0.008;
/// No boost below this share of the pool, so the drain alone never wrecks a craft.
const FLOOR_SHARE: f32 = 0.05;
/// What an absorb gives back of the energy spent: the maintainer's cap, so absorbing is
/// a choice rather than nothing.
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
const RED: Rgba = Rgba::new(0xE0, 0x20, 0x20, 0xFF);
/// Grid slots this mod tracks.
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
        pub _spare: u16,
    }
}

oag_ext::blob! {
    /// Every slot's record.
    pub struct Slots {
        pub slots: [Memory; SLOTS],
    }
}

pub struct EnergyTurbo;

impl Extension for EnergyTurbo {
    type State = Slots;

    fn tick(obs: &Observation<'_>, state: &mut Slots, reply: &mut Reply<'_>) {
        // This tick's events, one bit per slot each.
        let (mut fired, mut absorbed, mut pads) = (0_u32, 0_u32, 0_u32);
        for event in obs.events() {
            match event {
                Event::PickupFire { slot } => fired |= slot.bit(),
                Event::PickupAbsorbed { slot } => absorbed |= slot.bit(),
                Event::PadEnergy { slot } => pads |= slot.bit(),
                Event::WallContact { .. } => {}
            }
        }
        // Replies are refused only past the command cap or outside their bounds, which
        // this module never reaches, so their results are dropped.
        let _ = reply.pickup_roll(Weapon::Turbo, ROLL_EVERY);
        for (index, memory) in state.slots.iter_mut().enumerate() {
            let Some(craft) = Slot::new(index).and_then(|slot| obs.craft(slot)) else {
                *memory = Memory::default();
                continue;
            };
            let bit = |mask: u32| mask & craft.slot().bit() != 0;
            let (shield, max) = (craft.shield(), craft.shield_max());
            let mut delta = 0.0_f32;
            let mut cue = None;

            if bit(absorbed) && memory.spent > 0.0 {
                delta += memory.spent * PAYBACK;
                cue = Some(Cue::Absorb);
            }
            if craft.pickup() != Pickup::Ours || !craft.is_racing() {
                // Absorbed, wrecked or replaced: this turbo's account is closed.
                *memory = Memory::default();
            } else {
                let _ = reply.pad_mode(&craft);
                let _ = reply.pickup_tint(&craft, RED);
                if bit(pads) {
                    delta += max * PAD_SHARE;
                }
                if !craft.is_person() {
                    if memory.burst == 0 && memory.rest == 0 && bit(fired) {
                        memory.burst = AI_BURST;
                        memory.rest = AI_BURST + AI_REST;
                    }
                    memory.rest = memory.rest.saturating_sub(1);
                }
                let wants = if craft.is_person() {
                    craft.fire_held()
                } else {
                    memory.burst > 0
                };
                memory.burst = memory.burst.saturating_sub(1);
                let cost = max * DRAIN_SHARE;
                let boosting = wants && shield + delta - cost > max * FLOOR_SHARE;
                if boosting {
                    let _ = reply.scale_thrust(&craft, BOOST_FACTOR);
                    delta -= cost;
                    memory.spent += cost;
                    if !memory.boosting {
                        cue = Some(Cue::Turbo);
                    }
                    if memory.spark == 0 {
                        let _ = reply.fire_effect(&craft, Effect::CollisionSpark);
                        memory.spark = SPARK_EVERY;
                    }
                    memory.spark -= 1;
                } else {
                    memory.spark = 0;
                }
                memory.boosting = boosting;
            }
            if delta != 0.0 {
                // The host refuses a change beyond the pool's maximum either way.
                let bounded = if delta > max {
                    max
                } else if delta < -max {
                    -max
                } else {
                    delta
                };
                let _ = reply.shield_delta(&craft, bounded);
            }
            if let Some(cue) = cue {
                let _ = reply.play_cue(&craft, cue);
            }
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
                Command::PadMode { slot: me },
                Command::PickupTint {
                    slot: me,
                    rgba: RED
                },
                Command::ScaleThrust {
                    slot: me,
                    factor: BOOST_FACTOR
                },
            ]
        );
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
        assert_eq!(
            race.tick()[1..],
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
