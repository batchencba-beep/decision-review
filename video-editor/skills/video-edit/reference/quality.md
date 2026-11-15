# Quality chain

The rule: decode the source once, keep everything in 10-bit ProRes, encode lossy exactly once.

```
iPhone HEVC / AI clip ──ingest──▶ ProRes 422 HQ mezzanine ──cut──▶ segment clips ──concat (copy)──▶ base.mov
                                                                                                      │
                     Remotion caption layer (ProRes 4444 + alpha) ──────────────────────────────────▶ composite ──▶ master.mov (ProRes HQ, archive)
                                                                                                                         │
                                                                                                           export (one lossy encode) ──▶ instagram.mp4 / tiktok_shorts.mp4
```

| Stage | Setting | Why |
|---|---|---|
| Ingest | constant 30 fps (`fps` filter) | iPhone records variable frame rate. Cutting VFR drifts captions and lands cuts on the wrong frame. |
| Ingest | HLG/PQ → Rec.709 tone-map (zscale + hable) | iPhone "HDR Video" footage turns grey and washed out when it's edited and published as SDR. Flag it, tone-map it, and recommend turning HDR off. |
| Ingest | ProRes 422 HQ, 10-bit 4:2:2, PCM 48 kHz | Edit-grade, intra-frame: every frame is a keyframe, so cuts are exact. |
| Canvas | 2160×3840 only when every a_roll is ≥ 2160 wide, otherwise 1080×1920 | Never upscale the main picture. |
| Cut | frame-exact trim, sample-exact audio, 12 ms fades | No black frames, no audio clicks at cuts. |
| Cutaways | lanczos cover-fit, ≤ 2× upscale | AI clips are usually 1080p; 2× is the limit before they look soft next to 4K speech. |
| Captions | rendered alone, transparent, at canvas size | The browser never touches source pixels: no colour shift, no softening. |
| Export | H.264 High, CRF 16 (≤ 20 Mb/s) at 1080; CRF 17 (≤ 45 Mb/s) at 4K; yuv420p; bt709 tags; faststart | The platforms re-encode everything. A clean, high-bitrate upload survives that best. Explicit colour tags stop phones guessing. |
| Loudness | -14 LUFS integrated, ≤ -1 dBTP, two-pass loudnorm | The platforms' normalisation target: no level jumps between reels, no clipping after their AAC re-encode. |

## Shooting advice to pass on (iPhone)

Settings → Camera → Record Video: **4K at 30 fps**, **HDR Video off**. Lock exposure and focus (long
press). An external lavalier mic matters more than resolution. Shoot vertical. Leave a beat of silence
before and after each line; it makes clean cuts possible.

## Render times (reference: 4 CPU cores, 15 s reel, 4K)

ingest ≈ 7× real time when tone-mapping HDR · transcription ≈ 0.4× real time · cut ≈ 1.5 min ·
captions + composite ≈ 4 min · export ≈ 2 min. Apple-silicon Macs are roughly 2–3× faster. Revisions
re-render only the changed segments.
