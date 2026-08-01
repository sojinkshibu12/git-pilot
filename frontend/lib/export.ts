"use client";

import type { ContributionDay } from "@/lib/types";

/**
 * Dependency-free export helpers for the contribution heatmap.
 * Generates an SVG grid, then rasterizes to PNG via canvas and embeds the PNG
 * as a JPEG into a minimal single-page PDF (DCTDecode) — no external libraries.
 */

const CELL = 10;
const GAP = 3;
const GUTTER = 26;
const TOP_PAD = 18;

const LIGHT_COLORS = ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"];
const DARK_COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"];

const MONTHS = [
  "Jan", "Feb", "Mar", "Apr", "May", "Jun",
  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
];

export interface GridSpec {
  startISO: string;
  endISO: string;
  weeks: (ContributionDay | null)[][];
}

function isDarkMode(): boolean {
  return typeof document !== "undefined" && document.documentElement.classList.contains("dark");
}

function palette(): string[] {
  return isDarkMode() ? DARK_COLORS : LIGHT_COLORS;
}

function gridWidth(weeks: (ContributionDay | null)[][]): number {
  return GUTTER + weeks.length * (CELL + GAP) - GAP + 4;
}

function gridHeight(): number {
  return TOP_PAD + 7 * CELL + 6 * GAP + 4;
}

export function buildGridSvg({ startISO, weeks }: GridSpec): string {
  const colors = palette();
  const w = gridWidth(weeks);
  const h = gridHeight();
  const parts: string[] = [];
  parts.push(
    `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}">`,
  );

  // Month labels.
  const start = new Date(`${startISO}T00:00:00Z`);
  const gridStart = new Date(start);
  gridStart.setUTCDate(gridStart.getUTCDate() - gridStart.getUTCDay());
  const monthStarts: { index: number; label: string }[] = [];
  weeks.forEach((_, wi) => {
    for (let d = 0; d < 7; d++) {
      const day = new Date(gridStart);
      day.setUTCDate(day.getUTCDate() + wi * 7 + d);
      if (day.getUTCDate() !== 1) continue;
      monthStarts.push({ index: wi, label: MONTHS[day.getUTCMonth()] });
      break;
    }
  });
  for (const m of monthStarts) {
    parts.push(
      `<text x="${GUTTER + m.index * (CELL + GAP) + 1}" y="${TOP_PAD - 5}" font-size="9" fill="#57606a">${m.label}</text>`,
    );
  }

  // Weekday gutter (all 7 days).
  for (const row of [0, 1, 2, 3, 4, 5, 6]) {
    const label = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"][row];
    parts.push(
      `<text x="0" y="${TOP_PAD + row * (CELL + GAP) + CELL - 2}" font-size="8" fill="#57606a">${label}</text>`,
    );
  }

  // Cells.
  weeks.forEach((week, wi) => {
    week.forEach((day, row) => {
      if (!day) return;
      const x = GUTTER + wi * (CELL + GAP);
      const y = TOP_PAD + row * (CELL + GAP);
      const fill = colors[Math.min(4, Math.max(0, day.level))] ?? colors[0];
      parts.push(
        `<rect x="${x}" y="${y}" width="${CELL}" height="${CELL}" rx="2" fill="${fill}"><title>${day.count} contributions on ${day.date}</title></rect>`,
      );
    });
  });

  parts.push("</svg>");
  return parts.join("");
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

export function exportContributionSvg(spec: GridSpec): void {
  const svg = buildGridSvg(spec);
  downloadBlob(new Blob([svg], { type: "image/svg+xml;charset=utf-8" }), `contributions-${spec.endISO}.svg`);
}

async function svgToPng(svg: string): Promise<{ dataUrl: string; width: number; height: number }> {
  const img = new Image();
  img.src = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
  await img.decode();
  const width = img.naturalWidth || 800;
  const height = img.naturalHeight || 240;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D is not supported.");
  ctx.drawImage(img, 0, 0, width, height);
  return { dataUrl: canvas.toDataURL("image/png"), width, height };
}

export async function exportContributionPng(spec: GridSpec): Promise<void> {
  const { dataUrl } = await svgToPng(buildGridSvg(spec));
  downloadBlob(await (await fetch(dataUrl)).blob(), `contributions-${spec.endISO}.png`);
}

/**
 * Build a minimal single-page PDF embedding a JPEG image (DCTDecode).
 */
export function buildPdf(
  jpeg: Uint8Array,
  width: number,
  height: number,
): Uint8Array<ArrayBuffer> {
  const enc = new TextEncoder();
  const chunks: Uint8Array[] = [];
  const offsets = new Array<number>(6).fill(0);
  let pos = 0;
  const push = (s: string) => {
    const b = enc.encode(s);
    chunks.push(b);
    pos += b.length;
  };
  const pushBytes = (b: Uint8Array) => {
    chunks.push(b);
    pos += b.length;
  };
  const object = (num: number, body: string) => {
    offsets[num] = pos;
    push(`${num} 0 obj`);
    push(body);
    push("endobj\n");
  };

  push("%PDF-1.4\n");
  object(1, "<</Type/Catalog/Pages 2 0 R>>\n");
  object(2, "<</Type/Pages/Kids[3 0 R]/Count 1>>\n");
  object(
    3,
    `<</Type/Page/Parent 2 0 R/MediaBox[0 0 ${width} ${height}]/Resources<</XObject<</Im0 5 0 R>>>>/Contents 4 0 R>>\n`,
  );
  const content = `q ${width} 0 0 ${height} 0 0 cm /Im0 Do Q\n`;
  object(4, `<</Length ${content.length}>>stream\n${content}endstream\n`);
  object(
    5,
    `<</Type/XObject/Subtype/Image/Width ${width}/Height ${height}/ColorSpace/DeviceRGB/BitsPerComponent 8/Filter/DCTDecode/Length ${jpeg.length}>>stream\n`,
  );
  pushBytes(jpeg);
  push("\nendstream\n");

  const xrefStart = pos;
  push("xref\n0 6\n0000000000 65535 f \n");
  for (let i = 1; i <= 5; i++) {
    push(`${String(offsets[i]).padStart(10, "0")} 00000 n \n`);
  }
  push(`trailer\n<</Size 6/Root 1 0 R>>\nstartxref\n${xrefStart}\n%%EOF\n`);

  const out = new Uint8Array(pos);
  let o = 0;
  for (const c of chunks) {
    out.set(c, o);
    o += c.length;
  }
  return out;
}

export async function exportContributionPdf(spec: GridSpec): Promise<void> {
  const { dataUrl } = await svgToPng(buildGridSvg(spec));
  const img = new Image();
  img.src = dataUrl;
  await img.decode();
  const width = img.naturalWidth || 800;
  const height = img.naturalHeight || 240;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas 2D is not supported.");
  ctx.drawImage(img, 0, 0, width, height);
  const jpegDataUrl = canvas.toDataURL("image/jpeg", 0.92);
  const base64 = jpegDataUrl.split(",")[1] ?? "";
  const bin = atob(base64);
  const jpeg = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) jpeg[i] = bin.charCodeAt(i);
  const pdf = buildPdf(jpeg, width, height);
  downloadBlob(new Blob([pdf], { type: "application/pdf" }), `contributions-${spec.endISO}.pdf`);
}
