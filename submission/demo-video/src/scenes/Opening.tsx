import {useCurrentFrame, useVideoConfig} from 'remotion';
import {Beat, color, Frame, mono, Panel, Tag} from '../design';

export function Opening() {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const stage = frame / fps < 11 ? 0 : frame / fps < 23 ? 1 : 2;
  return <Frame chapter="01 / 06 · 0:00–0:35" title={"One question.\nScattered evidence."} seconds={35} cue="The model chooses what to ask. Typed calculations and cited sources determine the answer.">
    {stage === 0 && <Beat><Panel style={{padding: 48, maxWidth: 1450}}><Tag>THE ENGINEER'S QUESTION</Tag><p style={{fontSize: 49, lineHeight: 1.3, marginBottom: 15}}>“Which wells were down longest this summer—and why?”</p><p style={{fontSize: 27, color: color.muted}}>Inspections, repair history, manuals, regulator events and human notes.</p></Panel></Beat>}
    {stage === 1 && <Beat from={11}><div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 22}}>{[['01', 'Measurements', 'Temperatures and inspections'], ['02', 'Records', 'Repairs and regulator events'], ['03', 'Context', 'SOPs, corrections and notes']].map(([n, t, d]) => <Panel key={n}><span style={{fontFamily: mono, color: color.accent, fontSize: 22}}>{n}</span><h2 style={{fontSize: 40, fontWeight: 500}}>{t}</h2><p style={{fontSize: 27, color: color.muted}}>{d}</p></Panel>)}</div></Beat>}
    {stage === 2 && <Beat from={23}><Panel style={{background: color.ink, color: color.paper, padding: 50}}><div style={{fontSize: 25, letterSpacing: 2, color: '#c4d1bd'}}>THE DESIGN THESIS</div><div style={{fontSize: 62, lineHeight: 1.2, marginTop: 25}}>Language for the question.<br />Evidence for the conclusion.</div></Panel></Beat>}
  </Frame>;
}
