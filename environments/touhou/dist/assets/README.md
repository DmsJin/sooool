# Original TH08 asset provenance

The current presentation consumes the supplied `th08/` asset handoff. See `th08/manifest.json` for the source archive SHA256, extraction tool and atlas inventory; each atlas preserves `frames.json` and `sprites.txt`. See `th08/HANDOFF.txt` for integration notes.

Artwork, sprites, HUD, background textures, fonts and WAV/OGG audio are original ZUN / Team Shanghai Alice game materials. They are not project-authored or CC0 assets. The extraction tool license does not grant rights to these materials. This Site remains private.

`th08/audio/kaguya-original.ogg` is extracted from thbgm.dat, not the earlier third-party MP3. Exact loop points are read from `th08/audio/kaguya-loop.json` and applied to Web Audio BufferSource.

Background motion, composition and selected effect transforms are a lightweight presentation reconstruction, not a full original ANM/STD virtual machine. Bullet trajectories, hitboxes and Gym state are owned solely by the unchanged engine.
