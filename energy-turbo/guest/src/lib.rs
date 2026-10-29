//! Energy Turbo: a pickup of its own, handed out in place of every second Turbo.
//!
//! - **Pick it up**: the module asks the engine (`pickup_roll`) to hand out its own
//!   pickup in place of every second Turbo a weapon pad draws, so half the Turbos stay
//!   the title's own. The HUD draws it with the Turbo's icon on a red backdrop
//!   (`pickup_tint`); the engine never fires or absorbs it.
//! - **Hold fire**: the craft boosts (`scale_thrust` above 1) and pays for it from its
//!   shield (`shield_delta`), for as long as fire is held and the pool lasts. An AI
//!   craft, which holds no button, boosts for a fixed 1 s burst when its driver fires
//!   (where it would fire a Turbo), then rests 2 s before another.
//!   A Turbo cue on each boost start, the title's wall sparks at the nozzle while it
//!   runs.
//! - **Absorb it**: the pickup is gone and half of the energy spent on it comes back.
//! - **Speed pads**: while it is carried, a pad gives no boost (`pad_mode`) and fills
//!   the pool instead, a separate income that is not part of the absorb's half.
//!
//! The risk is the empty pool: the drain stops short of wrecking the craft, but a hit on
//! a drained pool wrecks it as any hit does.
//!
//! A simulation module on OpenAntiGrav's guest SDK (`oag-ext`). Nothing survives a tick
//! in this module's memory; each slot's numbers live in the 96-byte state blob the host
//! owns.
#![cfg_attr(not(test), no_std)]

use oag_ext::{Cue, Effect, Event, Extension, Observation, Pickup, Reply, Rgba, Slot, Weapon};

/// Thrust while boosting. Chosen.
const BOOST_FACTOR: f32 = 1.9;
/// Energy a boosting tick costs, as a share of the craft's pool (about 48 % a second).
/// Chosen.
const DRAIN_SHARE: f32 = 0.008;
/// No boost below this share of the pool: the drain alone never wrecks a craft. Chosen.
const FLOOR_SHARE: f32 = 0.05;
/// What an absorb gives back of the energy spent on the turbo it absorbs. The
/// maintainer's cap, taken at the cap rather than "nothing" so absorbing is a choice.
const PAYBACK: f32 = 0.5;
/// What a speed pad gives while the turbo is carried, as a share of the pool. Chosen.
const PAD_SHARE: f32 = 0.15;
/// An AI craft's boost per decision to fire, ticks (1 s). Chosen.
const AI_BURST: u16 = 60;
/// Ticks an AI craft waits after a burst before its next: its driver asks every tick
/// the Turbo gate passes, so without a rest it would boost down every straight. Chosen.
const AI_REST: u16 = 120;
/// The share of the title's Turbos handed out as this pickup instead: every second.
/// Chosen.
const ROLL_EVERY: u8 = 2;
/// Ticks between two spark bursts at the nozzle. Chosen.
const SPARK_EVERY: u8 = 20;
/// The backdrop's red. Chosen.
const RED: Rgba = Rgba::new(0xE0, 0x20, 0x20, 0xFF);
/// Grid slots this mod tracks: one record each.
const SLOTS: usize = 8;

oag_ext::blob! {
    /// One slot's account of the turbo it carries.
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
        /// Keeps the record at 12 bytes, the layout the module was first built with.
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
        // Race-wide; the same rule each tick keeps its count. Every refusal below is
        // ruled out by construction (at most 49 commands, values bounded).
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

            // Absorbed: half of what this turbo cost comes back.
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
                // The host refuses more than the pool's maximum either way.
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
