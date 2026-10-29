//! Kiss Curse: a craft that touches a wall has its engine cursed, a quarter of its
//! thrust for a second and a half, renewed by every tick it stays on the wall.
//!
//! A simulation module on OpenAntiGrav's guest SDK (`oag-ext`). The guest keeps
//! nothing in its own memory between ticks: its instance is fresh every tick, and the
//! curse's countdown lives in the 16-byte state blob the host owns, hashes and rolls
//! back.
//!
//! There is no engine timer: each tick a curse runs, the guest asks again for a
//! quarter of the craft's thrust, and the host multiplies it into that tick's engine
//! output for that craft.
#![cfg_attr(not(test), no_std)]

use oag_ext::{Event, Extension, Observation, Reply, Slot};

/// How long a curse lasts: 1.5 s at the engine's 60 Hz tick.
const CURSE_TICKS: u16 = 90;
/// The engine output a cursed craft keeps.
const CURSE_FACTOR: f32 = 0.25;
/// Grid slots this mod tracks: one countdown each.
const SLOTS: usize = 8;

oag_ext::blob! {
    /// One countdown per grid slot, in ticks.
    pub struct Curses {
        pub countdown: [u16; SLOTS],
    }
}

pub struct KissCurse;

impl Extension for KissCurse {
    type State = Curses;

    fn tick(obs: &Observation<'_>, state: &mut Curses, reply: &mut Reply<'_>) {
        for event in obs.events() {
            if let Event::WallContact { slot } = event
                && let Some(left) = state.countdown.get_mut(slot.index())
            {
                *left = CURSE_TICKS;
            }
        }
        for (index, left) in state.countdown.iter_mut().enumerate() {
            if *left == 0 {
                continue;
            }
            *left -= 1;
            // A slot that emptied (a craft gone from the grid) holds no craft to name;
            // its curse still runs out.
            if let Some(craft) = Slot::new(index).and_then(|slot| obs.craft(slot)) {
                // Refused only past 64 commands; eight slots send at most eight.
                let _ = reply.scale_thrust(&craft, CURSE_FACTOR);
            }
        }
    }
}

oag_ext::export!(KissCurse);

#[cfg(test)]
mod tests {
    use oag_ext::test::{CraftRecord, Race};
    use oag_ext::{Command, Event, Slot};

    use super::*;

    #[test]
    fn a_wall_contact_curses_the_next_ninety_ticks_and_an_empty_slot_is_not_named() {
        let (one, two) = (Slot::new(1).unwrap(), Slot::new(2).unwrap());
        let racer = CraftRecord {
            racing: true,
            ..CraftRecord::default()
        };
        let mut race = Race::<KissCurse>::new().with_craft(one, racer);
        race.event(Event::WallContact { slot: one })
            .event(Event::WallContact { slot: two });
        let cursed = [Command::ScaleThrust {
            slot: one,
            factor: CURSE_FACTOR,
        }];
        for _ in 0..CURSE_TICKS {
            assert_eq!(race.tick(), cursed);
        }
        assert!(race.tick().is_empty());
        assert_eq!(race.state().countdown, [0; SLOTS]);
    }
}
