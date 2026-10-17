$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$demoRoot = Split-Path -Parent $PSScriptRoot
$demoAudioDirectory = Join-Path $demoRoot 'public/narration'
New-Item -ItemType Directory -Force -Path $demoAudioDirectory | Out-Null
$demoSegments = Get-Content -LiteralPath (Join-Path $demoRoot 'narration.json') -Raw | ConvertFrom-Json
$demoSynth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$demoSynth.SelectVoice('Microsoft Zira Desktop')
$demoFormat = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo -ArgumentList 22050, ([System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen), ([System.Speech.AudioFormat.AudioChannel]::Mono)
try {
    for ($demoIndex = 0; $demoIndex -lt $demoSegments.Count; $demoIndex++) {
        $demoSegment = $demoSegments[$demoIndex]
        $demoOutput = Join-Path $demoAudioDirectory ('segment-{0:D2}.wav' -f $demoIndex)
        $demoFit = $false
        foreach ($demoRate in @(0, 1, 2, 3)) {
            $demoSynth.Rate = $demoRate
            $demoSynth.SetOutputToWaveFile($demoOutput, $demoFormat)
            $demoSynth.Speak($demoSegment.text)
            $demoSynth.SetOutputToNull()
            $demoReader = [System.IO.BinaryReader]::new([System.IO.File]::OpenRead($demoOutput))
            try {
                $demoReader.BaseStream.Position = 12
                while ($demoReader.BaseStream.Position -lt $demoReader.BaseStream.Length) {
                    $demoChunk = [System.Text.Encoding]::ASCII.GetString($demoReader.ReadBytes(4))
                    $demoSize = $demoReader.ReadUInt32()
                    if ($demoChunk -eq 'data') {
                        $demoSeconds = $demoSize / (22050 * 2)
                        break
                    }
                    $demoReader.BaseStream.Position += $demoSize + ($demoSize % 2)
                }
            } finally { $demoReader.Dispose() }
            if ($demoSeconds -le ($demoSegment.end - $demoSegment.start - 0.15)) {
                $demoFit = $true
                break
            }
        }
        if (-not $demoFit) { throw "Narration segment $demoIndex exceeds its visual beat. Shorten its text." }
        Write-Output ('{0}: {1} / {2}s (voice rate {3})' -f $demoIndex, [math]::Round($demoSeconds, 2), ($demoSegment.end - $demoSegment.start), $demoRate)
    }
} finally { $demoSynth.Dispose() }
python (Join-Path $PSScriptRoot 'assemble-narration.py')
if ($LASTEXITCODE -ne 0) { throw 'Narration assembly failed' }
