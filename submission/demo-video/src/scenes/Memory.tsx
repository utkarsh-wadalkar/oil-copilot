import {useCurrentFrame, useVideoConfig} from 'remotion';
import {Beat, color, Frame, Panel, Source, Table, Tag} from '../design';

export function Memory() {
  const f = useCurrentFrame();
  const {fps} = useVideoConfig();
  const second = f / fps;
  return <Frame chapter="05 / 06 · 4:10–4:50" title="Shared facts. Private conversations." seconds={40} subtitle="“For the three wells we discussed yesterday, what have repairs cost this year?”" cue="An unresolved private reference must not widen into another engineer’s history—or a fleet-wide query.">
    {second < 20 ? <Beat><Panel style={{padding: 44}}><Tag amber>JESSICA REED · NO MATCHING PRIVATE HISTORY</Tag><h2 style={{fontSize: 44, fontWeight: 400, lineHeight: 1.35}}>“I have no such earlier conversation of yours.”</h2><p style={{fontSize: 28, color: color.muted}}>The copilot does not borrow Michael Turner’s saved well set.</p><Source>Private lookup: current user → owned conversation → saved result</Source></Panel></Beat> : <Beat from={20}><Panel style={{padding: 12}}><div style={{padding: 17}}><Tag>MICHAEL TURNER · HIS SAVED THREE-WELL SET</Tag></div><Table columns={['Well', '2026 repair cost', 'Source']} rows={[
      ['WELL-0121', '$25,794', 'Maintenance records'],
      ['WELL-0138', '$46,942', 'Maintenance records'],
      ['WELL-0107', '$5,176', 'Maintenance records'],
    ]} /><p style={{fontSize: 24, padding: '0 22px', color: color.muted}}>The original well set is recovered; current corrected facts are queried.</p></Panel></Beat>}
  </Frame>;
}
