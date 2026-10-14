# Sound Sketch format (`*.sketch.json`) — for Claude and humans

Files ending in `.sketch.json` in this folder are short music sketches made in Hub's **Sound Sketch** panel.
The panel reloads a file within ~2 seconds when it changes on disk, so editing the JSON is the way to change the music.
Hub renders the audio itself (numpy) — **do not write audio code; edit the JSON**. The user exports a WAV from the panel.

```json
{
  "format": "hub-sketch/1",
  "bpm": 96, "key": "C", "scale": "minor", "bars": 2,
  "drums": {
    "kick":  "x...x...x...x...|x...x...x..xx...",
    "snare": "....x.......x...|....x.......x...",
    "hat":   "x.x.x.x.x.x.x.x.|x.x.x.x.x.x.x.X.",
    "clap":  "................|................"
  },
  "bass":   [ {"at": 0, "note": "C2", "len": 4} ],
  "chords": [ {"at": 0, "name": "Cm", "len": 16}, {"at": 16, "name": "Ab", "len": 16} ],
  "melody": [ {"at": 0, "note": "G4", "len": 2} ],
  "ref":    {"file": "rec-hum (clean).wav", "offset": 0.7, "vol": 0.8, "mute": false},
  "voices": {"melody": {"sample": "glass.wav", "root": "D6"}, "clap": {"sample": "knock.wav"}},
  "mix": {"drums": {"vol": 0.8, "mute": false}, "bass": {"vol": 0.8, "mute": false},
          "chords": {"vol": 0.8, "mute": false}, "melody": {"vol": 0.8, "mute": false}}
}
```

| Field | Rule |
|---|---|
| time grid | 1 step = a 16th note. 16 steps per bar. Total steps = 16 × `bars` |
| `bpm` | 40–240 |
| `key` / `scale` | key: C C# D Eb E F F# G Ab A Bb B / scale: `major` or `minor` |
| `bars` | 1, 2, 4 or 8 |
| `drums.*` | one character per step: `x` hit, `X` accented hit, `.` rest. `|` and spaces are ignored (use `|` between bars) |
| `bass` / `melody` | notes: `at` = start step (0-based), `note` = name with octave (`C4` = middle C, `F#3`, `Bb2`), `len` = steps |
| `chords` | `name`: C, Cm, C7, Cmaj7, Cm7, Cdim, Caug, Csus2, Csus4, C6, Cm6, Cadd9, C9, Cm7b5, Cdim7 (slash bass like `C/E` is accepted but ignored) |
| `ref` | optional reference audio: a `.wav` **in this folder** (name only) that plays along with the sketch. `offset` = seconds into the WAV that line up with step 0. Included in the exported WAV unless `mute`. Use `null` (or leave it out) for none |
| `voices` | optional: play a part (`bass` `chords` `melody`) or a drum (`kick` `snare` `hat` `clap`) with a sound the user recorded instead of the built-in one. `sample` = a `.wav` in the `samples` subfolder (name only). `root` = the note that sample is (pitched parts only); notes are shifted from it. Leave out a part to use the built-in sound |
| `mix` | per part: `vol` 0–1, `mute` true/false |

Notes for editing:
- Typical ranges: bass C1–C3, chords are voiced from octave 3 automatically, melody C4–C6.
- Anything that cannot be read is skipped and shown to the user as a warning (the rest still plays).
- Keep `ref` and `voices` as they are unless asked (they point to the user's recordings). `samples/samples.json` lists each sample's `root`.
- Write the whole file (e.g. `folders_write_text` with `overwrite: true`). Keep `"format": "hub-sketch/1"`.
