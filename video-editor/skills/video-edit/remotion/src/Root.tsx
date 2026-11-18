import React from "react";
import { Composition } from "remotion";
import { Captions } from "./Captions";
import type { CaptionProps } from "./types";

// Preview props for `npm run studio`; real renders pass --props from render.py.
const preview: CaptionProps = {
  width: 1080,
  height: 1920,
  fps: 30,
  durationInFrames: 90,
  direction: "rtl",
  style: {
    font: "Heebo", weight: 800, size: 0.074, color: "#FFFFFF", highlight: "#FFD60A",
    stroke: "#000000", positionY: 0.64, animation: "pop",
  },
  chunks: [
    { from: 0, to: 30, emphasis: false, words: [{ text: "ככה", from: 0, to: 10 }, { text: "עורכים", from: 10, to: 20 }, { text: "רילס", from: 20, to: 30 }] },
    { from: 30, to: 55, emphasis: true, words: [{ text: "בחינם", from: 30, to: 55 }] },
    { from: 55, to: 90, emphasis: false, words: [{ text: "עם", from: 55, to: 65 }, { text: "AI", from: 65, to: 75 }, { text: "ב-2026", from: 75, to: 90 }] },
  ],
};

export const Root: React.FC = () => (
  <Composition
    id="Captions"
    component={Captions as unknown as React.FC<Record<string, unknown>>}
    defaultProps={preview as unknown as Record<string, unknown>}
    width={preview.width}
    height={preview.height}
    fps={preview.fps}
    durationInFrames={preview.durationInFrames}
    calculateMetadata={({ props }) => {
      const p = props as unknown as CaptionProps;
      return { width: p.width, height: p.height, fps: p.fps, durationInFrames: Math.max(1, p.durationInFrames) };
    }}
  />
);
