//! Hillside's rain: the first craft of any kind, a person's or the AI's, to enter its
//! final lap turns on the host title's own rain, fades the sun and its lens flare out
//! and greys the sky, over three seconds. Every earlier lap sends nothing at all, so
//! it is the vanilla frame.
//!
//! A track module on OpenAntiGrav's guest SDK (`oag-ext`), bound to
//! `tracks/hillside.track.toml` by `[extension.track]`. The three commands are
//! race-wide outputs: the host holds the last tick's and the view half draws them, so
//! the guest re-sends them every tick it wants them and never touches the simulation.
//! The guest keeps nothing in its own memory between ticks: `started` and the ramp's
//! tick count live in the 3-byte state blob the host owns, hashes and rolls back.
#![cfg_attr(not(test), no_std)]

use oag_ext::{Extension, Observation, Reply, WeatherKind};

/// The ramp, in ticks: 3 s at the engine's 60 Hz tick.
const RAMP_TICKS: u16 = 180;

oag_ext::blob! {
    /// Whether a craft has entered its final lap, and how far the ramp has run.
    #[derive(Debug, Clone, Copy, PartialEq, Default)]
    pub struct Rain {
        pub started: u8,
        pub ticks: u16,
    }
}

pub struct HillsideRain;

impl Extension for HillsideRain {
    type State = Rain;

    fn tick(obs: &Observation<'_>, state: &mut Rain, reply: &mut Reply<'_>) {
        if state.started == 0 {
            let final_lap = obs.crafts().any(|craft| {
                craft.is_racing() && craft.laps_target() > 0 && craft.lap() == craft.laps_target()
            });
            if !final_lap {
                return;
            }
            state.started = 1;
        }
        state.ticks = (state.ticks + 1).min(RAMP_TICKS);
        let strength = f32::from(state.ticks) / f32::from(RAMP_TICKS);
        // Refused only past 64 commands or outside [0, 1]; three in range are sent.
        let _ = reply.set_weather(WeatherKind::Rain, strength);
        let _ = reply.set_sun(1.0 - strength);
        let _ = reply.grade_sky(strength);
    }
}

oag_ext::export!(HillsideRain);

#[cfg(test)]
mod tests {
    use oag_ext::test::{CraftRecord, Race};
    use oag_ext::{Command, Slot};

    use super::*;

    fn racer(lap: u8, laps_target: u8) -> CraftRecord {
        CraftRecord {
            racing: true,
            lap,
            laps_target,
            ..CraftRecord::default()
        }
    }

    #[test]
    fn nothing_is_sent_until_a_craft_enters_its_final_lap_then_the_ramp_runs_three_seconds() {
        let (person, ai) = (Slot::new(0).unwrap(), Slot::new(3).unwrap());
        let mut race = Race::<HillsideRain>::new()
            .with_craft(
                person,
                CraftRecord {
                    person: true,
                    ..racer(1, 3)
                },
            )
            .with_craft(ai, racer(2, 3));
        for _ in 0..600 {
            assert_eq!(race.tick(), []);
        }
        assert_eq!(
            race.state(),
            Rain {
                started: 0,
                ticks: 0
            }
        );

        // An AI craft entering the last lap starts it for the whole race.
        *race.craft_mut(ai) = Some(racer(3, 3));
        let first = race.tick();
        assert_eq!(
            first,
            [
                Command::SetWeather {
                    kind: WeatherKind::Rain,
                    strength: 1.0 / 180.0
                },
                Command::SetSun {
                    intensity: 1.0 - 1.0 / 180.0
                },
                Command::GradeSky { grey: 1.0 / 180.0 },
            ]
        );
        for _ in 1..179 {
            race.tick();
        }
        let last = race.tick();
        assert_eq!(
            last,
            [
                Command::SetWeather {
                    kind: WeatherKind::Rain,
                    strength: 1.0
                },
                Command::SetSun { intensity: 0.0 },
                Command::GradeSky { grey: 1.0 },
            ]
        );
        // Held at the end, and it keeps running after the craft that started it has
        // finished (its lap is past the target) or left the grid.
        *race.craft_mut(ai) = None;
        assert_eq!(race.tick(), last);
        assert_eq!(
            race.state(),
            Rain {
                started: 1,
                ticks: RAMP_TICKS
            }
        );
    }

    #[test]
    fn a_person_on_the_final_lap_starts_it_and_a_race_with_no_target_never_does() {
        let person = Slot::new(1).unwrap();
        let mut race = Race::<HillsideRain>::new().with_craft(
            person,
            CraftRecord {
                person: true,
                ..racer(5, 0)
            },
        );
        assert_eq!(race.tick(), []);
        *race.craft_mut(person) = Some(CraftRecord {
            person: true,
            ..racer(5, 5)
        });
        assert_eq!(race.tick().len(), 3);
        // A craft on the grid or wrecked is not racing: its lap does not start it.
        let mut grid = Race::<HillsideRain>::new().with_craft(
            person,
            CraftRecord {
                racing: false,
                ..racer(3, 3)
            },
        );
        assert_eq!(grid.tick(), []);
    }
}
