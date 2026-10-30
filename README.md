# OpenAntiGrav mod examples

Example mods for [OpenAntiGrav](https://github.com/topaxi/OpenAntiGrav). The
engine repository mounts this one as a submodule at `assets/mods/examples`, so the
game run from a checkout (`just play`) offers them, and its tests read them.

| Mod | What it shows |
| --- | --- |
| [`hillside/`](hillside/) (`oag.hillside`) | A track-only mod: one track of OpenAntiGrav's own format, with art. Raced from RACE REMIX's CUSTOM title, or from another mod's campaign. It also carries a WebAssembly **track module**, `hillside/ext/hillside_rain.wasm` (Rust source in `hillside/guest/`, `guest/build.sh`): the first craft of any kind to enter its final lap turns on Pulse's own rain, fades the sun's lens flare and greys the sky over 3 s. Runs only on this track, and only in a game built with the `extensions` feature; without it the track races dry. |
| [`example-campaign/`](example-campaign/) (`oag.example-campaign`) | NIGHT RUN, a custom campaign: disc circuits, a pilot of its own, a track it bundles (`tracks/practice-octagon.track.toml`) and Hillside out of `oag.hillside`. |
| [`wall-penalty/`](wall-penalty/) (`oag.wall-penalty`) | Wall Penalty, a simulation mod in WebAssembly: a craft that touches a wall keeps a quarter of its thrust for 1.5 s. Rust source in `wall-penalty/guest/` (`guest/build.sh`), the built module committed as `wall-penalty/ext/wall_penalty.wasm`. Needs a game built with the `extensions` feature. |
| [`energy-turbo/`](energy-turbo/) (`oag.energy-turbo`) | Energy Turbo, a simulation mod in WebAssembly: a pickup of its own, handed out in place of every second Turbo and drawn as the Turbo on a red backdrop. Hold fire to boost on your shield, absorb it for half of what you spent, carry it over a speed pad to refill instead of boosting. Rust source in `energy-turbo/guest/`, the built module committed as `energy-turbo/ext/energy_turbo.wasm`. Needs the `extensions` feature. |
| [`checkpoint-circuit/`](checkpoint-circuit/) (`oag.checkpoint-circuit`) | Checkpoint Circuit, a track and its WebAssembly **track module**: the example of triggers, track properties, HUD text and the AI route hook. Each craft has 20 s to its next checkpoint gate (triggers with `mod_checkpoint = n`); past zero its energy drains until it reaches the gate or is wrecked. The pit lane beside the main straight is a real fork in the spline; inside it (the trigger `mod_pit = 1`) energy recharges, and an AI craft below 40 % energy takes it (`prefer-route`, found by the pit lane path's `mod_pit`). The clock and RECHARGING are the mod's own strings (`strings/english.toml`). `checkpoint_circuit.py` rebuilds the track in Blender; Rust source in `guest/`, the built module `ext/checkpoint_circuit.wasm`. Needs the `extensions` feature; without it the track races as a plain loop. |

![Hillside on Wipeout Pulse: the start gantry, the grid and the mountain range](hillside/screenshot.png)

*Hillside raced on Wipeout Pulse (PSP). The road, walls and sky are Pulse's own textures,
read from the player's disc at race time; the terrain, mountains, lake, gantry, grid and light
are this repository's. `hillside/hillside.py` rebuilds the track in Blender.*

The tracks are for Wipeout Pulse only: their art borrows Pulse's textures by name. To
play them in an installed game, copy both folders into a mods directory. The
campaign needs `oag.hillside` installed beside it.

The formats are documented in the engine repository: the campaign in
`docs/formats/custom-campaign.md`, the track in `docs/formats/track-file.md`, mods
in `docs/tools/mods.md`.

## Rules

- **No game content.** Nothing extracted from a disc: a track borrows a disc's
  texture or sky by name, and the game reads it from the player's own disc. The one
  exception is a screenshot of a mod in the running game (maintainer, 2026-10-29), which
  shows the disc's art as it draws.
- `*.glb`, `*.blend` and `*.png` are stored with Git LFS (`git lfs install` once
  before cloning).
- Each mod folder has an owner; change only your own and `git pull --rebase`
  before pushing.

## Licence

MIT OR Apache-2.0, at your option ([`LICENSE-MIT`](LICENSE-MIT),
[`LICENSE-APACHE`](LICENSE-APACHE)).
