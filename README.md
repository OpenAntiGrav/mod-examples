# OpenAntiGrav mod examples

Example mods for [OpenAntiGrav](https://github.com/topaxi/OpenAntiGrav). The
engine repository mounts this one as a submodule at `assets/mods/examples`, so the
game run from a checkout (`just play`) offers them, and its tests read them.

| Mod | What it shows |
| --- | --- |
| [`hillside/`](hillside/) (`oag.hillside`) | A track-only mod: one track of OpenAntiGrav's own format, with art. Raced from RACE REMIX's CUSTOM title, or from another mod's campaign. |
| [`example-campaign/`](example-campaign/) (`oag.example-campaign`) | NIGHT RUN, a custom campaign: disc circuits, a pilot of its own, a track it bundles (`tracks/practice-octagon.track.toml`) and Hillside out of `oag.hillside`. |

Both are for Wipeout Pulse only: their art borrows Pulse's textures by name. To
play them in an installed game, copy both folders into a mods directory. The
campaign needs `oag.hillside` installed beside it.

The formats are documented in the engine repository: the campaign in
`docs/formats/custom-campaign.md`, the track in `docs/formats/track-file.md`, mods
in `docs/tools/mods.md`.

## Rules

- **No game content.** Nothing extracted from a disc: a track borrows a disc's
  texture or sky by name, and the game reads it from the player's own disc.
- `*.glb`, `*.blend` and `*.png` are stored with Git LFS (`git lfs install` once
  before cloning).
- Each mod folder has an owner; change only your own and `git pull --rebase`
  before pushing.

## Licence

MIT OR Apache-2.0, at your option ([`LICENSE-MIT`](LICENSE-MIT),
[`LICENSE-APACHE`](LICENSE-APACHE)).
