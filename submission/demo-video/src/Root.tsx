import type {ReactNode} from 'react';
import {Audio} from '@remotion/media';
import {AbsoluteFill, Composition, Folder, Series, staticFile, useVideoConfig} from 'remotion';
import {Opening as OpeningScene} from './scenes/Opening';
import {Architecture as ArchitectureScene} from './scenes/Architecture';
import {Compliance as ComplianceScene} from './scenes/Compliance';
import {Correction as CorrectionScene} from './scenes/Correction';
import {Memory as MemoryScene} from './scenes/Memory';
import {Limits as LimitsScene} from './scenes/Limits';

function NarratedChapter({track, children}: {track: string; children: ReactNode}) {
  const {fps} = useVideoConfig();
  return <>{children}<Audio src={staticFile(`narration/${track}.wav`)} volume={1} premountFor={fps} /></>;
}

const Opening = () => <NarratedChapter track="Opening"><OpeningScene /></NarratedChapter>;
const Architecture = () => <NarratedChapter track="Architecture"><ArchitectureScene /></NarratedChapter>;
const Compliance = () => <NarratedChapter track="Compliance"><ComplianceScene /></NarratedChapter>;
const Correction = () => <NarratedChapter track="Correction"><CorrectionScene /></NarratedChapter>;
const Memory = () => <NarratedChapter track="Memory"><MemoryScene /></NarratedChapter>;
const Limits = () => <NarratedChapter track="Limits"><LimitsScene /></NarratedChapter>;

export const Demo = () => {
  const {fps} = useVideoConfig();
  return <AbsoluteFill>
    <Series>
      <Series.Sequence name="The problem and thesis" durationInFrames={35 * fps} premountFor={fps}><Opening /></Series.Sequence>
      <Series.Sequence name="How it is built" durationInFrames={55 * fps} premountFor={fps}><Architecture /></Series.Sequence>
      <Series.Sequence name="Compliance with evidence" durationInFrames={105 * fps} premountFor={fps}><Compliance /></Series.Sequence>
      <Series.Sequence name="A confirmed correction" durationInFrames={55 * fps} premountFor={fps}><Correction /></Series.Sequence>
      <Series.Sequence name="Private memory" durationInFrames={40 * fps} premountFor={fps}><Memory /></Series.Sequence>
      <Series.Sequence name="Limits and next" durationInFrames={10 * fps} premountFor={fps}><Limits /></Series.Sequence>
    </Series>
  </AbsoluteFill>;
};

export const RemotionRoot = () => <>
  <Composition id="Demo" component={Demo} durationInFrames={9000} fps={30} width={1920} height={1080} />
  <Folder name="Chapters">
    <Composition id="Opening" component={Opening} durationInFrames={1050} fps={30} width={1920} height={1080} />
    <Composition id="Architecture" component={Architecture} durationInFrames={1650} fps={30} width={1920} height={1080} />
    <Composition id="Compliance" component={Compliance} durationInFrames={3150} fps={30} width={1920} height={1080} />
    <Composition id="Correction" component={Correction} durationInFrames={1650} fps={30} width={1920} height={1080} />
    <Composition id="Memory" component={Memory} durationInFrames={1200} fps={30} width={1920} height={1080} />
    <Composition id="Limits" component={Limits} durationInFrames={300} fps={30} width={1920} height={1080} />
  </Folder>
</>;
