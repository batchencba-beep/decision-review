import "@fontsource/heebo/800.css";
import "@fontsource/heebo/900.css";
import React, { useEffect, useState } from "react";
import {
  AbsoluteFill, continueRender, delayRender, interpolate, spring, staticFile,
  useCurrentFrame, useVideoConfig,
} from "remotion";
import type { CaptionProps, Chunk } from "./types";

// Platform UI (like / comment / share column) sits on the RIGHT in every language,
// so the caption block is centred inside [6%, 84%] of the width, not the full frame.
const SAFE_LEFT = 0.06;
const SAFE_RIGHT = 0.16;

const useFonts = (family: string, weight: number, fontFile?: string) => {
  const [handle] = useState(() => delayRender(`fonts ${family}`));
  useEffect(() => {
    const jobs: Promise<unknown>[] = [];
    if (fontFile) {
      const face = new FontFace(family, `url(${staticFile(fontFile)})`, { weight: String(weight) });
      (document.fonts as unknown as { add: (f: FontFace) => void }).add(face);
      jobs.push(face.load());
    }
    // load every subset we may draw: Hebrew, Latin, digits
    jobs.push(document.fonts.load(`${weight} 100px "${family}"`, "אבגדהוזחטיכלמנסעפצקרשת"));
    jobs.push(document.fonts.load(`${weight} 100px "${family}"`, "AaBb0123456789?!"));
    Promise.all(jobs).then(() => continueRender(handle)).catch((e) => {
      console.error(e);
      continueRender(handle);
    });
  }, [family, weight, fontFile, handle]);
};

const ChunkView: React.FC<{ chunk: Chunk; p: CaptionProps }> = ({ chunk, p }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = p.style;
  const local = frame - chunk.from;
  const enter = s.animation === "pop"
    ? spring({ frame: local, fps, config: { damping: 15, stiffness: 260, mass: 0.6 }, durationInFrames: 7 })
    : 1;
  const scale = interpolate(enter, [0, 1], [0.82, 1]) * (chunk.emphasis ? 1.22 : 1);
  const opacity = s.animation === "pop" ? interpolate(local, [0, 2], [0, 1], { extrapolateRight: "clamp" }) : 1;

  // active word = the last word that has started (stays lit through micro-gaps, no flicker)
  let active = -1;
  chunk.words.forEach((w, i) => { if (frame >= w.from) active = i; });

  const fontPx = s.size * p.width;
  const strokePx = Math.max(2, fontPx * 0.09);
  return (
    <div
      dir={p.direction}
      style={{
        position: "absolute",
        left: SAFE_LEFT * p.width,
        right: SAFE_RIGHT * p.width,
        top: s.positionY * p.height,
        transform: `translateY(-50%) scale(${scale})`,
        opacity,
        display: "flex",
        flexDirection: "row",
        flexWrap: "wrap",
        justifyContent: "center",
        alignItems: "center",
        columnGap: fontPx * 0.26,
        rowGap: fontPx * 0.05,
        direction: p.direction,
        fontFamily: `"${s.font}", "Heebo", sans-serif`,
        fontWeight: chunk.emphasis ? Math.min(900, s.weight + 100) : s.weight,
        fontSize: fontPx,
        lineHeight: 1.1,
        letterSpacing: p.direction === "rtl" ? 0 : "-0.01em",
        textAlign: "center",
      }}
    >
      {chunk.words.map((w, i) => {
        const lit = chunk.emphasis || i === active;
        return (
          <span
            key={i}
            style={{
              unicodeBidi: "isolate",   // keeps English words and numbers in order inside RTL lines
              color: lit ? s.highlight : s.color,
              WebkitTextStroke: `${strokePx}px ${s.stroke}`,
              paintOrder: "stroke fill",
              textShadow: `0 ${fontPx * 0.05}px ${fontPx * 0.12}px rgba(0,0,0,0.55)`,
              display: "inline-block",
              transform: lit && !chunk.emphasis ? "scale(1.06)" : "none",
            }}
          >
            {w.text}
          </span>
        );
      })}
    </div>
  );
};

export const Captions: React.FC<CaptionProps> = (p) => {
  useFonts(p.style.font, p.style.weight, p.style.fontFile);
  const frame = useCurrentFrame();
  const chunk = p.chunks.find((c) => frame >= c.from && frame < c.to);
  return (
    <AbsoluteFill style={{ backgroundColor: "transparent" }}>
      {chunk ? <ChunkView key={chunk.from} chunk={chunk} p={p} /> : null}
    </AbsoluteFill>
  );
};
