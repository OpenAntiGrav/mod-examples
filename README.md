# OpenAntiGrav mod examples

Example mods for [OpenAntiGrav](https://github.com/topaxi/OpenAntiGrav). The
engine repository mounts this one as a submodule at `assets/mods/examples`, so the
game run from a checkout (`just play`) offers them, and its tests read them.

| Mod | What it shows |
| --- | --- |
| [`hillside/`](hillside/) (`oag.hillside`) | A track-only mod: one track of OpenAntiGrav's own format, with art. Raced from RACE REMIX's CUSTOM title, or from another mod's campaign. |
| [`example-campaign/`](example-campaign/) (`oag.example-campaign`) | NIGHT RUN, a custom campaign: disc circuits, a pilot of its own, a track it bundles (`tracks/practice-octagon.track.toml`) and Hillside out of `oag.hillside`. |
| [`kiss-curse/`](kiss-curse/) (`oag.kiss-curse`) | Kiss Curse, a simulation mod in WebAssembly: a craft that touches a wall keeps a quarter of its thrust for 1.5 s. Rust source in `kiss-curse/guest/` (`guest/build.sh`), the built module committed as `kiss-curse/ext/kiss_curse.wasm`. Needs a game built with the `extensions` feature. |

![Hillside on Wipeout Pulse: the start gantry, the grid and the mountain range](hillside/screenshot.png)

*Hillside raced on Wipeout Pulse (PSP). The road, walls and sky are Pulse's own textures,
read from the player's disc at race time; the terrain, mountains, lake, gantry, grid and light
are this repository's. `hillside/hillside.py` rebuilds the track in Blender.*

Both are for Wipeout Pulse only: their art borrows Pulse's textures by name. To
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
