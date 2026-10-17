import {useCurrentFrame, useVideoConfig} from 'remotion';
import {Beat, color, Frame, mono, Panel, Source, Tag} from '../design';

export function Architecture() {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const second = frame / fps;
  return <Frame chapter="02 / 06 · 0:35–1:30" title="A short path to a traceable answer." seconds={55} subtitle="Current default path: model-guided tools over versioned, effective records." cue="Rules are extracted from manuals and SOPs. Original files and every accepted correction remain auditable.">
    {second < 28 ? <Beat><div style={{display: 'grid', gridTemplateColumns: '1fr 50px 1.2fr 50px 1.1fr', alignItems: 'center'}}>
      <Panel><Tag>EXPERIENCE</Tag><h2 style={{fontSize: 40}}>Next.js + OpenUI</h2><p style={{fontSize: 25, color: color.muted}}>Private threads<br />Inline visuals<br />Evidence drawer</p></Panel><div style={{textAlign: 'center', fontSize: 40}}>→</div>
      <Panel style={{borderColor: '#536e55'}}><Tag>GOVERNED TOOLS</Tag><h2 style={{fontSize: 40}}>FastAPI + Gemma</h2><div style={{fontFamily: mono, fontSize: 23, lineHeight: 1.9}}>asset_query<br />recall_results<br />propose_feedback</div></Panel><div style={{textAlign: 'center', fontSize: 40}}>→</div>
      <Panel><Tag>AUTHORITATIVE</Tag><h2 style={{fontSize: 40}}>PostgreSQL</h2><p style={{fontSize: 25, color: color.muted}}>Effective facts + rules<br />Versioned sources<br />Saved cited results</p></Panel>
    </div><div style={{display: 'flex', gap: 18, marginTop: 22, fontSize: 23, color: color.muted}}><Panel style={{flex: 1, padding: 22}}>Neo4j + Mem0: retriable recall projections</Panel><Panel style={{flex: 1, padding: 22}}>nao: optional sidecar; outside the default path</Panel></div></Beat> : <Beat from={28}><div style={{display: 'grid', gridTemplateColumns: '1.1fr 1fr', gap: 28}}>
      <Panel><Tag>IMMUTABLE SOURCE</Tag><h2 style={{fontFamily: mono, fontWeight: 400, fontSize: 35}}>SourceVersion</h2><div style={{fontFamily: mono, fontSize: 26, lineHeight: 1.8}}>file path + content hash<br />original content + revision<br />record ID + JSONL line<br />active version pointer</div><Source>Reimport creates history; it does not erase it.</Source></Panel>
      <Panel style={{background: color.green}}><Tag>RULES ARE DATA</Tag><div style={{fontSize: 33, lineHeight: 1.8, marginTop: 15}}>Production temperature delta<br />Spill reporting threshold<br />Reporting and containment deadlines</div><Source>Every rule points back to a manual or SOP section.</Source></Panel>
    </div></Beat>}
  </Frame>;
}
