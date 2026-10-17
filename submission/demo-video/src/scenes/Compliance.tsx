import {useCurrentFrame, useVideoConfig} from 'remotion';
import {Beat, color, Frame, mono, Panel, Source, Table, Tag} from '../design';

const breaches = [
  ['SR-01', 'Written notice', '41 h / 24 h limit', 'Late; NOV open'],
  ['SR-02', 'Containment', '~7 h / 4 h limit', 'Limit exceeded'],
  ['SR-03', 'Agency verification', 'Due 10 Aug 2026', 'Still open'],
  ['RC-04', 'NOV response', 'Due 30 Jul 2026', 'None recorded'],
];

export function Compliance() {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  return <Frame chapter="03 / 06 · 1:30–3:15" title="WELL-0001: what is still open?" subtitle="A compliance question that combines measurements, regulator events, repair prose and SOPs." seconds={105} cue={t < 36 ? 'Four breaches from the 11 June spill. The recorded notice of violation carries a $5,000 fine and remains open.' : t < 80 ? 'The supporting record and the applicable rule are both visible. Missing evidence is stated as missing.' : 'Pending work is separated from established breaches. The yearly flowline integrity test was recorded as met.'}>
    {t < 14 && <Beat><Panel style={{padding: 42}}><Tag>MICHAEL TURNER · PRODUCTION SUPERVISOR</Tag><p style={{fontSize: 45, lineHeight: 1.35}}>“Which rules has WELL-0001 broken in the last 12 months, and what is still open?”</p><Source>Analysis date 17 Oct 2026 · Recorded sample-data result</Source></Panel></Beat>}
    {t >= 14 && t < 36 && <Beat from={14}><Panel style={{padding: '8px 10px'}}><Table columns={['Protocol', 'Requirement', 'Evidence / deadline', 'Status']} rows={breaches} emphasis={t < 25 ? 0 : 1} /></Panel></Beat>}
    {t >= 36 && t < 58 && <Beat from={36}><div style={{display: 'grid', gridTemplateColumns: '1.2fr 1fr', gap: 28}}><Panel><Tag>RULE · SOP-SR / SR-01</Tag><p style={{fontSize: 36, lineHeight: 1.45}}>Reportable spills need written notice within <strong>24 hours</strong> of discovery.</p><Source>fleet/sops/spill-response-sop.md · Protocols</Source></Panel><Panel style={{background: color.amber}}><Tag amber>RECORD · REG-0001-001</Tag><div style={{fontSize: 96, fontFamily: mono, marginTop: 30}}>41 h</div><p style={{fontSize: 26}}>Recorded time to written notice</p><Source>REG-0001-002 · $5,000 notice of violation · open</Source></Panel></div></Beat>}
    {t >= 58 && t < 80 && <Beat from={58}><Panel style={{padding: 38}}><Tag>EVIDENCE FOUND ONLY IN REPAIR PROSE</Tag><p style={{fontFamily: 'Georgia, serif', fontSize: 45, lineHeight: 1.45}}>“The release was contained about 7 hours after the inspection flight.”</p><div style={{display: 'flex', gap: 28, alignItems: 'center', fontSize: 28}}><span style={{fontFamily: mono, color: color.accent}}>~7 h actual</span><span>vs.</span><span style={{fontFamily: mono}}>4 h SOP limit</span></div><Source>MNT-0001-029 · MNT-0001-june-2026-flowline-spill.md<br />The quote is normalized from the report's Markdown emphasis.</Source></Panel></Beat>}
    {t >= 80 && <Beat from={80}><Panel style={{padding: '10px'}}><Table columns={['Category', 'Action / evidence', 'Treatment']} rows={[
      ['Open action', 'Flowline RCA after 3 corrective repairs', 'Pending; not an extra breach'],
      ['Open action', 'Planned 7 Oct shut-in not in maintenance system', 'Keep the context visible'],
      ['Met duty', 'Annual flowline test recorded 7 Mar 2026', 'RC-02 met'],
    ]} /></Panel></Beat>}
  </Frame>;
}
