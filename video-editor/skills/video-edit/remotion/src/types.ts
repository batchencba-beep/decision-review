export type Word = { text: string; from: number; to: number };

export type Chunk = { from: number; to: number; words: Word[]; emphasis: boolean };

export type CaptionStyle = {
  font: string;          // CSS family. "Heebo" is bundled; anything else needs fontFile
  fontFile?: string;     // file name inside the public dir (brand font), optional
  weight: number;        // 800 recommended for legibility
  size: number;          // font size as a fraction of frame width (0.074 ≈ 80px at 1080)
  color: string;         // resting word colour
  highlight: string;     // active word / emphasis colour
  stroke: string;        // outline colour
  positionY: number;     // vertical centre of the caption block, fraction of height (safe: 0.25–0.70)
  animation: "pop" | "none";
};

export type CaptionProps = {
  width: number;
  height: number;
  fps: number;
  durationInFrames: number;
  direction: "rtl" | "ltr";
  style: CaptionStyle;
  chunks: Chunk[];
};
