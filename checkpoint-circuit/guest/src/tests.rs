use oag_ext::test::{CraftRecord, Race, TrackRecord};
use oag_ext::{Command, Event, Slot, prop_key};

use super::*;

const MAX: f32 = 120.0;

/// The track as the host writes it for checkpoint-circuit.track.toml: four checkpoint
/// gates, the pit trigger last, and one route carrying the pit lane's `pit`.
fn circuit() -> TrackRecord {
    let checkpoint = |n: f32| vec![(prop_key("checkpoint"), n)];
    TrackRecord {
        triggers: vec![
            checkpoint(1.0),
            checkpoint(2.0),
            checkpoint(3.0),
            checkpoint(4.0),
            vec![(prop_key("pit"), 1.0)],
        ],
        paths: vec![vec![], vec![(prop_key("pit"), 1.0)], vec![]],
        routes: vec![vec![(prop_key("pit"), 1.0)]],
        ..TrackRecord::default()
    }
}

const PIT: u16 = 4;

fn craft(person: bool, shield: f32) -> CraftRecord {
    CraftRecord {
        person,
        racing: true,
        lap: 1,
        laps_target: 3,
        shield,
        shield_max: MAX,
        ..CraftRecord::default()
    }
}

fn slot(i: usize) -> Slot {
    Slot::new(i).unwrap()
}

fn shield_deltas(commands: &[Command]) -> Vec<f32> {
    commands
        .iter()
        .filter_map(|c| match c {
            Command::ShieldDelta { amount, .. } => Some(*amount),
            _ => None,
        })
        .collect()
}

#[test]
fn past_its_time_a_craft_loses_energy_every_tick_until_its_next_checkpoint() {
    let ai = slot(3);
    let mut race = Race::<CheckpointCircuit>::new()
        .with_craft(ai, craft(false, MAX))
        .with_track(&circuit());
    for _ in 0..CHECKPOINT_TICKS - 1 {
        assert!(shield_deltas(&race.tick()).is_empty());
    }
    for _ in 0..30 {
        assert_eq!(shield_deltas(&race.tick()), [-MAX * DRAIN_SHARE]);
    }
    // Checkpoint 2 is out of order: still draining.
    race.event(Event::TriggerEnter {
        slot: ai,
        trigger: 1,
    });
    assert_eq!(shield_deltas(&race.tick()), [-MAX * DRAIN_SHARE]);
    race.event(Event::TriggerEnter {
        slot: ai,
        trigger: 0,
    });
    assert!(shield_deltas(&race.tick()).is_empty());
    let clocks = race.state();
    assert_eq!(
        (clocks.left[3], clocks.next[3]),
        (CHECKPOINT_TICKS - 1, 2)
    );
}

#[test]
fn the_fourth_checkpoint_wraps_to_the_first() {
    let ai = slot(0);
    let mut race = Race::<CheckpointCircuit>::new()
        .with_craft(ai, craft(false, MAX))
        .with_track(&circuit());
    race.tick();
    for trigger in 0..4 {
        race.event(Event::TriggerEnter { slot: ai, trigger });
        race.tick();
    }
    assert_eq!(race.state().next[0], 1);
}

#[test]
fn the_pit_lane_recharges_up_to_the_maximum_and_stops_on_leaving() {
    let ai = slot(1);
    let mut race = Race::<CheckpointCircuit>::new()
        .with_craft(ai, craft(false, MAX - 0.1))
        .with_track(&circuit());
    race.event(Event::TriggerEnter {
        slot: ai,
        trigger: PIT,
    });
    let deltas = shield_deltas(&race.tick());
    assert_eq!(deltas.len(), 1);
    assert!((deltas[0] - 0.1).abs() < 1e-4, "{deltas:?}: capped at the maximum");
    *race.craft_mut(ai) = Some(craft(false, 10.0));
    assert_eq!(shield_deltas(&race.tick()), [MAX * RECHARGE_SHARE]);
    *race.craft_mut(ai) = Some(craft(false, MAX));
    assert!(shield_deltas(&race.tick()).is_empty(), "full: nothing to add");
    *race.craft_mut(ai) = Some(craft(false, 10.0));
    race.event(Event::TriggerExit {
        slot: ai,
        trigger: PIT,
    });
    assert!(shield_deltas(&race.tick()).is_empty());
}

#[test]
fn a_low_ai_craft_asks_for_the_pit_route_and_a_person_or_a_full_one_does_not() {
    let (low, full, person) = (slot(2), slot(5), slot(0));
    let mut race = Race::<CheckpointCircuit>::new()
        .with_craft(low, craft(false, MAX * AI_LOW_SHARE - 1.0))
        .with_craft(full, craft(false, MAX))
        .with_craft(person, craft(true, 1.0))
        .with_track(&circuit());
    let routes: Vec<_> = race
        .tick()
        .into_iter()
        .filter(|c| matches!(c, Command::PreferRoute { .. }))
        .collect();
    assert_eq!(routes, [Command::PreferRoute { slot: low, route: 0 }]);
}

#[test]
fn a_person_sees_the_clock_and_the_recharge_label() {
    let person = slot(0);
    let mut race = Race::<CheckpointCircuit>::new()
        .with_craft(person, craft(true, 50.0))
        .with_track(&circuit());
    race.event(Event::TriggerEnter {
        slot: person,
        trigger: PIT,
    });
    let commands = race.tick();
    let texts: Vec<(&str, bool)> = commands
        .iter()
        .filter_map(|c| match c {
            Command::HudText { text, own, .. } => Some((text.as_str(), *own)),
            _ => None,
        })
        .collect();
    assert_eq!(
        texts,
        [
            ("CPC_CHECKPOINT", true),
            ("19.9", false),
            ("CPC_RECHARGING", true)
        ]
    );
}

#[test]
fn a_track_without_checkpoints_sends_nothing() {
    let mut race = Race::<CheckpointCircuit>::new()
        .with_craft(slot(0), craft(false, 1.0))
        .with_track(&TrackRecord::default());
    for _ in 0..CHECKPOINT_TICKS + 10 {
        assert!(race.tick().is_empty());
    }
}
