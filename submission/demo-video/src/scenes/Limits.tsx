import {color, Frame, Panel, Tag} from '../design';

export function Limits() {
  return <Frame chapter="06 / 06 · 4:50–5:00" title="Traceable today. Clear about the limits." seconds={10} cue="Next: verify every final question through the model path and strengthen routing at the schema boundary.">
    <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 26}}><Panel style={{background: color.green}}><Tag>VERIFIED ARTIFACT</Tag><h2 style={{fontSize: 47, fontWeight: 500}}>18 sample scenarios</h2><p style={{fontSize: 29, lineHeight: 1.45}}>Passed in deterministic replay.<br />This does not mean every scenario passed live model routing.</p></Panel><Panel><Tag amber>DISCLOSED IN THE SCRIPT</Tag><div style={{fontSize: 31, lineHeight: 1.65, marginTop: 24}}>nao is not on the default path.<br />Graph + Mem0 are projections.<br />PostgreSQL remains authoritative.</div></Panel></div>
  </Frame>;
}
