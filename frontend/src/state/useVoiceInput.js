import { useCallback, useEffect, useRef, useState } from 'react';
import { transcribeAudio, ApiError } from '../api/client';

// A spoken query is a sentence or two; Whisper reads 30 seconds at a time.
export const MAX_SECONDS = 30;
const TARGET_RATE = 16000;

// Captures raw samples on the audio thread. MediaRecorder would hand over
// WebM/Opus, which the engine could only read with an audio decoder; plain
// PCM becomes a WAV here and needs nothing on the server.
const WORKLET = `
class Capture extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (ch) this.port.postMessage(ch.slice(0));
    return true;
  }
}
registerProcessor('capture', Capture);
`;

/** Mono float samples at `rate` -> 16 kHz 16-bit PCM WAV. */
function toWav(chunks, rate) {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const input = new Float32Array(total);
  let at = 0;
  for (const c of chunks) { input.set(c, at); at += c.length; }

  // Average each output sample's span of input: a cheap low-pass as well.
  const ratio = rate / TARGET_RATE;
  const length = Math.floor(total / ratio);
  const pcm = new Int16Array(length);
  for (let i = 0; i < length; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(total, Math.floor((i + 1) * ratio)) || start + 1;
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += input[j];
    const s = Math.max(-1, Math.min(1, sum / (end - start)));
    pcm[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }

  const buf = new ArrayBuffer(44 + pcm.length * 2);
  const v = new DataView(buf);
  const str = (o, s) => { for (let i = 0; i < s.length; i += 1) v.setUint8(o + i, s.charCodeAt(i)); };
  str(0, 'RIFF'); v.setUint32(4, 36 + pcm.length * 2, true); str(8, 'WAVE');
  str(12, 'fmt '); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, TARGET_RATE, true); v.setUint32(28, TARGET_RATE * 2, true);
  v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  str(36, 'data'); v.setUint32(40, pcm.length * 2, true);
  new Int16Array(buf, 44).set(pcm);
  return new Blob([buf], { type: 'audio/wav' });
}

/** Whether this browser, on this page, can record at all. */
export function canRecord() {
  return typeof window !== 'undefined'
    && window.isSecureContext                      // the microphone needs https or localhost
    && Boolean(navigator.mediaDevices?.getUserMedia)
    && typeof window.AudioWorkletNode === 'function';
}

/**
 * Record from the microphone and transcribe on the engine.
 *
 * state: 'idle' | 'recording' | 'transcribing'. `onText` receives the
 * transcript; nothing is searched here, so the official can check it first.
 */
export function useVoiceInput({ language, onText }) {
  const [state, setState] = useState('idle');
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState(null);
  const rec = useRef(null);
  const onTextRef = useRef(onText);
  useEffect(() => { onTextRef.current = onText; }, [onText]);

  const release = useCallback(() => {
    const r = rec.current;
    if (!r) return;
    clearInterval(r.timer);
    r.stream.getTracks().forEach((t) => t.stop());
    r.ctx.close().catch(() => {});
    rec.current = null;
  }, []);

  const stop = useCallback(async () => {
    const r = rec.current;
    if (!r || r.stopping) return;
    r.stopping = true;
    const wav = toWav(r.chunks, r.ctx.sampleRate);
    release();
    setState('transcribing');
    try {
      const out = await transcribeAudio(wav, { language });
      onTextRef.current?.(out.text, out);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Could not transcribe the recording.');
    } finally {
      setState('idle');
    }
  }, [language, release]);

  const start = useCallback(async () => {
    setError(null);
    // The capture is set up before the microphone opens: opened first, the
    // words spoken while the worklet loaded were lost ("ceiling fan with
    // regulator" arrived as "with regulator").
    const ctx = new AudioContext();
    const url = URL.createObjectURL(new Blob([WORKLET], { type: 'application/javascript' }));
    try {
      await ctx.audioWorklet.addModule(url);
    } finally {
      URL.revokeObjectURL(url);
    }
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    } catch (err) {
      ctx.close().catch(() => {});
      setError(err?.name === 'NotAllowedError'
        ? 'Microphone access was refused. Allow it in the browser’s site settings to speak a query.'
        : 'No microphone could be opened.');
      return;
    }
    const node = new AudioWorkletNode(ctx, 'capture');
    const r = { stream, ctx, chunks: [], started: Date.now(), stopping: false };
    node.port.onmessage = (e) => r.chunks.push(e.data);
    ctx.createMediaStreamSource(stream).connect(node);
    // Through a muted gain to the output: a node nothing pulls on is not run.
    const mute = ctx.createGain();
    mute.gain.value = 0;
    node.connect(mute).connect(ctx.destination);
    r.timer = setInterval(() => {
      const s = (Date.now() - r.started) / 1000;
      setSeconds(s);
      if (s >= MAX_SECONDS) stop();
    }, 200);
    rec.current = r;
    setSeconds(0);
    setState('recording');
  }, [stop]);

  // Never leave the microphone open after the screen goes away.
  useEffect(() => release, [release]);

  return { state, seconds, error, start, stop, clearError: () => setError(null) };
}
