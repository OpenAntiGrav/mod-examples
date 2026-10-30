---
name: oag-mod-author
description: Write, change or debug an OpenAntiGrav mod - an oag-mod.toml, a WebAssembly simulation extension (rules module or track module) on the oag-ext guest SDK, a particle effect, HUD text or icon, a string file, a custom track (Blender oag_track add-on) or a custom campaign. Use for anything in this mod-examples repository or any mod built against the OpenAntiGrav engine.
---

# Authoring an OpenAntiGrav mod

This is a guide, not the spec. The engine repository owns the truth (paths at the
end); when this file and the engine disagree, the engine wins and this file is stale.
State checked against engine branch `wasm-extensions`, ABI 1 revision 3, 2026-10-30.

## Layout of this repository

One folder per mod, each with `oag-mod.toml` at its root. Examples to copy:

| Mod | Kind | Copy it for |
| --- | --- | --- |
| `wall-penalty/` | rules module | smallest complete guest: one event, one command, one effect |
| `energy-turbo/` | rules module | a pickup of its own, HUD outputs, strings, effects, state in a blob |
| `hillside/` | track + track module | a track in Blender (`hillside.py`) and a module bound to that track |
| `example-campaign/` | campaign | a campaign, a pilot, a bundled track, another mod's track |

## The manifest, `oag-mod.toml`

Starts with `toml-schema = { location = "https://oag.topaxi.com/mods/schemas/v1/mod.tosd", version = "1.0.0" }`.
`[mod]`: `id` (lowercase letters, digits, `.`, `-`, `_`), `name`, `version` (semver),
`authors`, `license` (SPDX) or `license-file`, `description`, optional `repository`,
`homepage`, `keywords`, `titles` (slugs: `wipeout-pulse`, `wipeout-pure`, `wipeout-hd`,
`wipeout-omega-collection`, `wipeout-2048`; empty means any), `oag` (semver requirement).
No licence still loads but is flagged. Check one with `just mods-check <path>`
(engine checkout); `just mods-list` shows what the search finds.

| Table | Purpose |
| --- | --- |
| `[extension]` | `simulation = true` (required with a module), `api = 1`, `memory_pages` (1 to 256, default 16; 2 holds the SDK with a 16 KiB stack), `state_bytes` (at most 1,024; must equal the guest's `oag_state_len`) |
| `[extension.rules]` | `module = "ext/x.wasm"`: runs in every race the mod is on for, every craft, AI too |
| `[extension.track]` | `module = ...` and `track = "tracks/x.track.toml"`: runs only in a race of that track file, never a disc circuit |
| `[effects]` | `name = "fx/name.toml"`: parametric particle effects. A guest fires one by its index in **name order** |
| `[icons]` | `name = "path.png"`: PNGs for `hud_mod_icon` (missing or unreadable draws nothing, load report says so) |
| `[pickup]` | **Required** of a mod that sends `give_pickup` or `pickup_roll`: `icon = { title = "turbo" }` or `{ mod = "<key of [icons]>" }`, and `colour = { rgba = "RRGGBBAA" }` or `{ title = "shield" }`. `title` is a lowercase weapon (`rocket` ... `disruptor`, `leachbeam`, `repulser`). Exactly one key per side; a bad weapon, a `mod` outside `[icons]` or a bad `rgba` refuses the mod at load, by name. Without the table the module is faulted for the race on its first `give_pickup`/`pickup_roll`, naming it |

Other files: `strings/<language>.toml` (`[strings]` rows `ID = { text = "...", human = false }`;
`human = true` only when a person wrote or approved it; ship `english.toml`, it is the
fallback), `menu.toml` (menu rows, closed set of existing pages and actions),
`campaigns/*.toml`, `pilots/*.toml`, `tracks/*.track.toml` + `.glb`. A mod with a
module needs an engine built with the `extensions` feature. No module runs in an
original campaign or a network race; a race running one is MODDED and records no replay.

## The guest SDK, `oag-ext` (`crates/ext` in the engine)

Rust, `no_std`, no `alloc`, no `unsafe`. Implement `Extension`, declare the state with
`blob!`, name the type in `export!`.

- `Observation`: `tick()`, `craft(slot) -> Option<Craft>`, `crafts()`, `events()`, `track()`.
- `Track`: `whole()`, `speed_pad(i)`, `weapon_pad(i)`, `trigger(i)`, `path(i)`, `route(i)` and
  their counts (`speed_pads()`, `weapon_pads()`, `triggers()`, `paths()`, `routes()`); each
  entity has `prop(key)`, `to_world()`, `bounds()`. A route (a way from a fork back to the lap)
  carries the properties of the spline paths it drives, so `route(r).prop(prop!("pit"))` finds
  the route through a path tagged `mod_pit`.
- `Craft` (a view): `slot()`, `is_person()`, `fire_held()`, `is_racing()`, `is_shielded()`,
  `lap()`, `laps_target()`, `shield()`, `shield_max()`, `speed_kmh()`, `pickup()`.
- `Event`: `WallContact`, `PickupFire`, `PickupAbsorbed`, `SpeedPad{pad}`, `WeaponPad{pad}`,
  `TriggerEnter{trigger}`, `TriggerExit{trigger}`, `Hit{amount, weapon}`. At most 32 per call.
- `Reply`: one method per command, `Result<(), Refused>`. `Refused` is `Full` (96 commands),
  `Repeated` (a second per-craft thrust, shield, pad or route command), `Range`, `HudItems`
  (more than 32 text/icon items per craft per tick, or the string pool full), `Pickup`,
  `PickupTint` (`hud_tint` of the pickup).
  Handle or `let _ =` it on purpose; the host would fault on what the SDK refuses.
- `Slot` and `Craft`: a command naming a slot takes a `&Craft`, so an empty slot cannot be named.
- `blob!`: little-endian, field order, no padding; integers, `f32`, `bool`, fixed arrays,
  nested `blob!` structs.
- `prop!("name")`: compile-time key (FNV-1a 32) for a track property; `entity.prop(key) -> Option<f32>`.
- `Line`: fixed-size text buffer with `time(ticks)` and `number(n)`, no allocator.
- `oag_ext::test::Race<E>`: native test harness (`with_craft`, `with_track`, `event`, `tick() -> Vec<Command>`, `state()`), feature `test` as a dev-dependency.

Minimal complete guest (Wall Penalty, trimmed):

```rust
#![cfg_attr(not(test), no_std)]
use oag_ext::{Event, Extension, Observation, Reply, Slot};

oag_ext::blob! {
    pub struct Curses { pub countdown: [u16; 8] }
}

pub struct WallPenalty;

impl Extension for WallPenalty {
    type State = Curses;
    fn tick(obs: &Observation<'_>, state: &mut Curses, reply: &mut Reply<'_>) {
        for event in obs.events() {
            if let Event::WallContact { slot } = event
                && let Some(left) = state.countdown.get_mut(slot.index())
            {
                *left = 90;
            }
        }
        for (index, left) in state.countdown.iter_mut().enumerate() {
            if *left == 0 { continue; }
            *left -= 1;
            if let Some(craft) = Slot::new(index).and_then(|s| obs.craft(s)) {
                let _ = reply.scale_thrust(&craft, 0.25);
            }
        }
    }
}

oag_ext::export!(WallPenalty);
```

`Cargo.toml` (own workspace, `[workspace]` empty table): `crate-type = ["cdylib"]`,
`oag-ext` as a dependency and, with `features = ["test"]`, a dev-dependency; release
profile `opt-level = "s"`, `lto = true`, `panic = "abort"`, `codegen-units = 1`,
`strip = true`. `.cargo/config.toml`: `[target.wasm32-unknown-unknown] rustflags =
["-C", "link-arg=-zstack-size=16384"]`. The examples' `oag-ext` dependency is a relative
`path` into the engine checkout this repo is mounted in (`assets/mods/examples`);
a stand-alone clone needs a git dependency pinned to the ABI revision instead
(none is published yet).

## Hard rules (the host enforces them)

- **Core wasm only.** Imports: only the `oag` namespace, and ABI 1 offers none. No WASI,
  threads, atomics. A module importing anything else is refused at load, naming the import.
- **One call per tick, fresh instance.** Nothing in module memory survives. State lives in
  the host-owned blob (`state_bytes`), which the host hashes, snapshots and rolls back.
- **Events are one tick late**; commands act on the tick being called.
- **No timers.** A held effect (`scale_thrust`, `hold_shield`, `scale_slot_pads`, HUD
  outputs, weather) is re-sent every tick it should hold; race-wide `scale_pad` and
  `pickup_roll` hold until replaced.
- **Determinism.** `f32` only, no `f64` maths that feeds a command, no `mul_add`, no
  platform transcendentals; the host canonicalises NaN and the SDK refuses non-finite
  values. No clock, no randomness the host did not give (none is offered in ABI 1).
- **Fuel:** 200,000 units per tick, instantiation included (Wall Penalty uses about 1,000 to
  2,500; Energy Turbo about 8,000 to 14,000). Checked at function entry and loop headers.
- **Memory:** `memory_pages` 1 to 256; the SDK's I/O buffer is 4,096 bytes, its track
  region 32 KiB, so keep `memory_pages = 2` and the 16 KiB stack.
- **A fault turns the module off for the rest of the race** (the tick it faulted on is
  hashed). Causes: out of fuel, any trap (`unreachable`, out of bounds, stack overflow), a
  refused reply (NaN, a factor out of range, a slot with no craft, more than 96 commands,
  `tick` returning non-zero, a state length that differs from the manifest). The commands
  of that call are discarded and the blob keeps its prior value.
- **Layout revision.** `oag_abi()` returns `(1 << 8) | REVISION` (3 now). A module built for
  another revision is refused by name: rebuild against the engine you run.
- A pickup of the mod's own (`Pickup::Ours`): one module owns the kind per race, and a race
  without weapons refuses it. It draws the look of `[pickup]`; there is no implicit Turbo
  icon. `reply.pickup_look(&craft, Icon, Colour)` (command 22) overrides it for one tick:
  `Icon::{Title(Weapon), Mod(ModIcon::new("name"))}`, `Colour::{Title(Weapon), Rgba(Rgba)}`,
  with maps `icon::title::TURBO`, `colour::title::SHIELD` and so on for every weapon. A
  title colour is that title's own backdrop row (Pulse, HD, Omega); the title's fade-in,
  overshoot, size pulse and fade-out play on any look; the last look is kept for the
  fade-out. **Pure has no backdrop widget: both colour kinds draw nothing there**; 2048
  keeps its backdrop as authored. `hud_tint` of `HudElement::Pickup` is refused
  (`Refused::PickupTint`; a raw record faults the module): use `pickup_look`. `hud_shake`
  on `Pickup` still works.

## What is hashed and what is an output

| Hashed (simulation; both sides must agree) | Output (drawn or heard, never hashed) |
| --- | --- |
| `scale_thrust` (0 to 2), `shield_delta`, `give_pickup`, `clear_pickup`, `pickup_roll`, `scale_pad` (0 to 2, race-wide), `scale_slot_pads` (0 to 2), `give_shield`, `hold_shield`, `clear_shield`, `prefer_route`; the state blob; the fault flag and tick | `play_cue`, `fire_effect`, `fire_mod_effect`, `pickup_look`, `hud_tint`, `hud_shake`, `hud_bar_extra`, `hud_text`, `hud_string`, `hud_icon`, `hud_mod_icon`, `set_weather`, `set_sun`, `grade_sky` |

An output must not feed back into the state: a HUD that reads the simulation is fine, a
rule that depends on what was drawn is not possible. HUD elements: `Speed`, `Thrust`,
`Energy`, `Pickup`, `Position`, `Lap`, `Time`; a title with no widget draws nothing. Text
and icons sit at one of nine `Anchor`s via `HudPlace`, at most 48 bytes a string.
**`prefer_route(&craft, route)`** (command 21): at its next fork the craft's driver takes
`route` (below `track.routes()`) instead of its coin's draw, if the route leaves that fork and
the driver can drive it; the host still throws the coin. Re-send it every tick it should hold.
It moves a driver only (an AI craft, or a person's Autopilot); the AI drives the route with the
player's physics. `checkpoint-circuit/` sends low AI craft down its pit lane with it.

## Build, test, run

1. `rustup target add wasm32-unknown-unknown` once.
2. In the mod's `guest/`: `cargo test` (native, through `oag_ext::test::Race`; no wasm toolchain).
3. `guest/build.sh` builds the release wasm and copies it to `ext/<name>.wasm`. **Commit the
   built wasm**: a player never builds. Rebuild and recommit after any SDK or ABI change.
4. From an engine checkout (this repo is its submodule at `assets/mods/examples`):
   `just play` builds with the `extensions` feature and finds the examples. Mods run by
   default; `OAG_NO_EXTENSIONS=1 just play` builds without. `OAG_MODS=<dir list>` replaces the whole search path.
5. Turn a mod on or off on the MODS page. `just pack-mod <folder>` writes a `.oagmod`.
6. Debugging: the `Dev` overlay shows per module fuel and the fault tick; the boot log and load
   report name a module left out, a missing asset or an effect that drew nothing.

## A mod in JavaScript (experimental; `wall-penalty-js/`)

Rust on `oag-ext` is the way to write a mod. `wall-penalty-js/` shows the only other route that
meets the rules: JavaScript built with Javy (QuickJS in core wasm) behind a guest-side shim.
Choose it only to see what it costs: **a JavaScript tick spends 155,000 to 228,000 of the 200,000
fuel** (Rust Wall Penalty: about 500), so a mod doing more than a few hundred bytecode operations a
tick faults out of fuel; the module is 1.37 MB against 627 bytes; the host spends about 1 s
compiling it at race load.

- Build: `wall-penalty-js/build.sh` with `JAVY=<javy 9.1.0>` whose plugin was built **without**
  `+simd128` (stock Javy's output uses SIMD, which the host refuses), and binaryen's `wasm-dis`
  and `wasm-as` on PATH. The build is byte-reproducible; commit `ext/*.wasm` (LFS).
- `src/main.js` exports `jsTick()`. It cannot see the I/O buffer: `Javy.IO.readSync(0, buf)`
  reads the head of it, and **one** `Javy.IO.writeSync(1, buf)` writes the state blob (its first
  `state_bytes`) then the reply (the command count and records). `tools/shim.py` turns Javy's nine
  WASI imports into functions that do this, and exports `oag_abi`, `oag_io`, `oag_state_len` and
  `tick`. No import remains.
- No clock, no randomness (`Date.now` is 0, `Math.random` is the snapshot's), nothing between ticks.
- TypeScript typings of the ABI: `types/oag-abi.d.ts`, generated from `crates/ext-abi` by the
  engine's `scripts/gen-ext-typings.py` (run it after an ABI change; `just check-extensions`
  fails on a stale file or a script whose own `const NAME = n;` differs from the ABI).
- Prove it the way the Rust one is proved: `crates/modhost/tests/javascript_module.rs` (random
  observations, same state and commands as `wall-penalty/`) and the `wall_penalty_ground_truth`
  JavaScript tests (`--features extensions --run-ignored only`).

## Particle effects

`fx/<name>.toml` with `toml-schema = { location = ".../v1/effect.tosd", version = "1.0.0" }`,
`axis = "rear" | "up"` and up to 64 `[[emitter]]` tables (`duration`, `interval`,
`per-emission`, `lifetime`, `speed`, `spread`, `drag`, `gravity`, `live-cap`, `blend`, `size`,
`alpha`, `colour`, `texture`). Plays at the craft's nozzle (hull back end). A texture is a
PNG of the mod or a disc texture by name (`{ entry = "...", name = "..." }`). A broken file
draws nothing and is named in the load report. Format: engine `docs/formats/mod-effect.md`.

## Tracks, triggers and Blender

The `oag_track` Blender add-on lives in the engine at `scripts/blender/oag_track/` (zip it,
install as an extension, Blender 4.2+). A scene object is exported only when tagged with
`oag_kind` (`spline`, `floor`, `wall`, `start`, `speedup`, `weapon`, `trigger`, ...); an
untagged rendering mesh is art. Export writes `name.track.toml` plus `name.glb`.

- **Properties for a module:** a custom property `mod_<name>` (number or bool, never a
  string or array) on a pad Empty, a trigger Empty, a spline object or the scene; the module
  reads it with `prop!("<name>")`. Caps: 256 entities, 64 triggers, 1,024 properties.
- **A fork (a pit lane, a shortcut):** more than one spline path joined by the scene's
  `oag_junctions` (JSON), as baked point-mesh splines with `oag_entry`/`oag_exit` (a Curve
  spline must be one closed loop). `checkpoint-circuit/checkpoint_circuit.py` builds one.
- **Triggers:** an Empty `oag/triggers/<name>` with Box min/max; **Make trigger from mesh**
  makes one from each selected mesh's bounds. The module hears `TriggerEnter`/`TriggerExit`.
- **Effect preview and export:** **Preview effect** loads an effect TOML onto the active
  object as an editable Text and approximate particles; **Export effect** validates and writes it back.
- **Borrowing disc textures:** set the scene's **Runs on** (`track.host`) and mark a
  material's image with **Make Host Texture** (`oag_host_entry`, `oag_host_name`) or set the
  **Sky** form. Nothing from the disc is exported; the game reads it from the player's disc at race time.
  A host-borrowing track is for that title only (`titles` in the manifest too).
- Headless proof: `scripts/blender/roundtrip.py` (`loop`, `props`, `effect`) in the engine.
  `hillside/hillside.py` rebuilds Hillside in Blender, `checkpoint-circuit/checkpoint_circuit.py`
  Checkpoint Circuit (a forked spline, triggers made from meshes).

## This repository's rules

- **No game content.** Nothing extracted from a disc. A track borrows a texture or sky by name.
  Only exception: a screenshot of a mod in the running game.
- Git LFS for `*.glb`, `*.blend`, `*.png` (`git lfs install` once before cloning).
- One owner per mod folder: change only your own, `git pull --rebase` before pushing.
- Licence: MIT OR Apache-2.0, at your option (`LICENSE-MIT`, `LICENSE-APACHE`); a mod
  states its own in the manifest.
- Add a row to `README.md`'s table for a new mod.

## Where the truth lives (engine repository)

- `docs/architecture/wasm-extensions/README.md` (surface, commands, what is built), `hooks.md`
  (where each event is raised and each command lands), `determinism-and-state.md`
- `docs/tools/mods.md` (manifest, search path, packaging, MODS page)
- `docs/formats/track-file.md`, `docs/formats/mod-effect.md`, `docs/formats/custom-campaign.md`,
  `docs/tools/blender.md`
- Code: `crates/ext-abi` (layout, commands, caps), `crates/ext` (SDK), `crates/modhost`
  (limits, faults), `crates/mod` (manifest); schemas in `schemas/v1/`.

## Keeping this skill current

Any change to the ABI (`oag-ext-abi`), the SDK (`oag-ext`), `oag-mod.toml`, the effect,
track or string formats, or how a mod is built, tested or run must update this file in the
same change. The engine's `CLAUDE.md` says the same.
