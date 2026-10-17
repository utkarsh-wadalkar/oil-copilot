import type {CSSProperties, ReactNode} from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

export const color = {paper: '#f6f5f0', ink: '#182c26', muted: '#68756c', line: '#d7ddd3', accent: '#b65032', green: '#e0eadc', amber: '#f4e6cb', white: '#fffefa'};
export const mono = 'Consolas, "Courier New", monospace';
export const serif = 'Georgia, "Times New Roman", serif';

export function Frame({chapter, title, subtitle, children, seconds, cue}: {
  chapter: string; title: string; subtitle?: string; children: ReactNode; seconds: number; cue?: string;
}) {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  return <AbsoluteFill style={{background: color.paper, color: color.ink, fontFamily: '"Segoe UI", Arial, sans-serif', padding: '54px 88px 46px'}}>
    <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: 21, letterSpacing: 3, paddingBottom: 26, borderBottom: `1px solid ${color.line}`}}>
      <span>FIELDNOTE <span style={{color: color.muted}}> / ASSET INTELLIGENCE</span></span>
      <span style={{color: color.muted, letterSpacing: 1}}>{chapter}</span>
    </div>
    <div style={{paddingTop: 34, opacity: interpolate(frame, [0, 17], [0, 1], {extrapolateRight: 'clamp'}), translate: `0 ${interpolate(frame, [0, 22], [16, 0], {extrapolateRight: 'clamp'})}px`}}>
      <h1 style={{fontFamily: serif, fontWeight: 400, fontSize: 76, letterSpacing: -3, lineHeight: 1.08, margin: '0 0 18px', whiteSpace: 'pre-line'}}>{title}</h1>
      {subtitle && <div style={{fontSize: 29, color: color.muted, lineHeight: 1.4}}>{subtitle}</div>}
    </div>
    <div style={{flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', minHeight: 0}}>{children}</div>
    {cue && <div style={{borderTop: `1px solid ${color.line}`, paddingTop: 23, paddingBottom: 22, fontSize: 30, lineHeight: 1.35, color: color.ink}}>{cue}</div>}
    <div style={{display: 'flex', justifyContent: 'space-between', fontSize: 17, color: color.muted, letterSpacing: 1}}>
      <span>RECORDED SAMPLE DATA · ANALYSIS DATE 17 OCT 2026</span>
      <span>EDITORIAL WALKTHROUGH · SYNTHETIC NARRATION</span>
    </div>
    <div style={{position: 'absolute', bottom: 0, left: 0, height: 5, background: color.accent, width: `${interpolate(frame, [0, seconds * fps - 1], [0, 100], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}%`}} />
  </AbsoluteFill>;
}

export function Panel({children, style}: {children: ReactNode; style?: CSSProperties}) {
  return <div style={{background: color.white, border: `1px solid ${color.line}`, borderRadius: 12, padding: 30, ...style}}>{children}</div>;
}

export function Tag({children, amber = false}: {children: ReactNode; amber?: boolean}) {
  return <span style={{display: 'inline-block', fontSize: 19, letterSpacing: 1, padding: '9px 14px', borderRadius: 4, color: amber ? '#8c4e21' : '#38523c', background: amber ? color.amber : color.green}}>{children}</span>;
}

export function Table({columns, rows, emphasis = -1}: {columns: string[]; rows: ReactNode[][]; emphasis?: number}) {
  return <table style={{width: '100%', borderCollapse: 'collapse', fontSize: 27, lineHeight: 1.45}}>
    <thead><tr>{columns.map((c) => <th key={c} style={{textAlign: 'left', padding: '17px 22px', fontWeight: 500, color: color.muted, borderBottom: `1px solid ${color.line}`, fontSize: 21, letterSpacing: 1}}>{c}</th>)}</tr></thead>
    <tbody>{rows.map((row, i) => <tr key={i} style={{background: emphasis === i ? color.green : 'transparent'}}>{row.map((cell, j) => <td key={j} style={{padding: '22px', borderBottom: `1px solid ${color.line}`, fontFamily: j === 0 ? mono : undefined}}>{cell}</td>)}</tr>)}</tbody>
  </table>;
}

export function Source({children}: {children: ReactNode}) {
  return <div style={{fontFamily: mono, fontSize: 19, color: color.muted, marginTop: 20, lineHeight: 1.45}}>{children}</div>;
}

export function Beat({from = 0, children}: {from?: number; children: ReactNode}) {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  return <div style={{opacity: interpolate(f, [from * fps, from * fps + 16], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'})}}>{children}</div>;
}
