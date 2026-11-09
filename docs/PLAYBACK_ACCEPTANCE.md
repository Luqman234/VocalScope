# VocalScope listening and device acceptance

This is a **human checklist**, initially pending. Automated PCM/stream tests do
not fill these results. Record date, operator, software version, PipeWire device,
SoundFont identity, pass/fail and observations. Use a comfortable output level.
Save valuable edits as a new project before testing.

## Known material

From the repository, run:

```bash
GDK_BACKEND=wayland .venv/bin/vocalscope gui
```

Load `results/stage3-human-pyin/vocadito_1.notes.json`. In **Playback**, use:

- Vocal: `data/vocadito/Audio/vocadito_1.wav` (33.212 s).
- Piano: `results/stage4a-release-piano/piano.wav` (34.712 s, normalized in Stage 4A).
- Offset: 0. Keep the original files unchanged.

The piano contains 65 inferred notes; transcription errors are separate from
playback/synthesis defects. Choose a verified local SoundFont in the offline
render panel for edit audition. The reproduction font was TimGM6mb 1.3 (GPL-2),
bank/preset 0/0; no SoundFont is installed or downloaded by this checklist.

## Listening checklist

| Action | Required observation | Human result / notes |
|---|---|---|
| Vocal only, Play | Vocal audible; moving cursor follows song | Pending |
| Pause for 3 s; Resume | Position holds, resumes at same phrase | Pending |
| Piano only | Actual sampled piano audible | Pending |
| Vocal → Piano → Mix repeatedly | Same phrase/time; no unintended restart | Pending |
| Lower/raise each source gain | Correct source responds, no abrupt click from switching | Pending |
| Mix loud sections | No obvious clipping; inspect displayed PCM peak | Pending |
| Seek to 5, 15 and 30 s, then near the end | Both sources continue at the chosen time | Pending |
| Loop a quiet-boundary phrase, then a sustained vowel | Correct repetition; note any gap/click separately | Pending |
| Loop 31.4–32.0 s | Observe the recorded piano release within the chosen region | Pending |
| Edit selected note by +1 key; Render/update | Old audio labeled stale until current revision; changed key audible | Pending |
| Undo/redo; render again | Audible result matches current edited revision | Pending |
| Cancel preview; retry | Last good audio remains; latest result eventually activates | Pending |
| Close during playback, then during a pending preview | Audio stops; no orphan stream/worker | Pending |

Loop policy is an exact hard cut with bounded flushing seeks, without crossfade.
A sustained waveform cut at unrelated phases can click intrinsically. A transport
gap is additional to that discontinuity. Neither clickless nor gapless looping is
promised. Replacement uses a controlled brief pause; it does not alter note times.

For an unambiguous channel check, generate a **diagnostic tone**, not a piano:

```bash
.venv/bin/python scripts/stage4b1_listening_assets.py --output results/stage4b1-channel-check.wav
```

Load that WAV as the vocal source, clear piano, and play Vocal only. Expected:
0–1 s left-only 440 Hz, 1–1.5 s silence, 1.5–2.5 s right-only 660 Hz,
2.5–3 s silence, 3–4 s both channels 440 Hz. Verify the appropriate ears with
headphones. Restore the real vocal/project afterwards.

## Device acceptance, with user participation

The automated test disconnects **only its own PipeWire client socket** and then
verifies an actual recovered stream. This does not verify a physical headphone
power-off, default-device change, or complete daemon restart.

1. Use a session in which changing the selected output will not interrupt other
   people's audio. Record `wpctl status`, `wpctl inspect @DEFAULT_AUDIO_SINK@`
   and `pactl info` before the test. Do not start a second PipeWire daemon.
2. Start the real vocal/piano mix; note media time and gains.
3. Manually disconnect/power off the selected test device. Observe whether
   PipeWire reroutes the stream or output stops. Record the actual destination;
   a default-device policy may legitimately route elsewhere.
4. If output stalls without an explicit plugin error, VocalScope's default
   watchdog checks successful sink-render progress every 100 ms and enters ERROR
   after about 2 s without progress (plus scheduling delay). A running media
   clock alone does not prove sound is delivered. Device-specific behavior can
   differ; record what actually happens.
5. Press Pause while in ERROR, reconnect/select the intended output, then
   **Recover output**. It must remain paused. Play deliberately; verify audible
   continuation and preserved position/mode/gains. Repeat with Stop during ERROR:
   recovery should retain stopped intent at zero.
6. Repeat disconnect/reconnect while previously playing; Recover should resume
   only that retained intent. Confirm exactly one VocalScope stream in `wpctl
   status`. Close while recovering and confirm the stream is removed.
7. If testing default-output migration is appropriate, manually select another
   output through the desktop's normal settings and record behavior before,
   during and after playback. The application does not force a particular
   hardware device; routing follows the existing server policy.

Do not restart shared PipeWire services for routine acceptance. Full daemon
restart testing needs a separately authorized isolated environment. A failed
recovery must be recorded as failed, with diagnostic output, rather than inferred
from an error dialog disappearing.

## Latency

Pipeline queries, appsink arrivals, MIDI sample positions, SoundFont attacks and
physical sound are distinct. Electrical latency needs a documented loopback setup
with a known reference/capture path. Acoustic latency additionally needs suitable
microphone/speaker measurement and propagation accounting. No such hardware
measurement has been performed here; Bluetooth buffering can dominate. Do not
apply a universal 6–8 ms correction from the earlier SoundFont experiment.
