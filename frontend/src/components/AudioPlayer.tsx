import { Pause, Play } from "lucide-react";
import { forwardRef, useEffect, useImperativeHandle, useRef, useState, type MouseEvent } from "react";

import type { Marker } from "../api/conversations";
import { Button } from "../design-system/Button";
import { Select } from "../design-system/FormControls";
import styles from "./AudioPlayer.module.css";

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

const WAVEFORM_BARS = 160;
const PLAYBACK_RATES = [0.75, 1, 1.25, 1.5, 2];

/** Decodes the audio file client-side (Web Audio API) into a small number
 * of peak-amplitude buckets for a lightweight waveform visualization — no
 * new dependency, no server-side change. Best-effort: if decoding fails
 * (e.g. an unsupported container), the player still works via the plain
 * seek bar, it just renders no waveform. */
function useWaveformPeaks(src: string): number[] | null {
  const [peaks, setPeaks] = useState<number[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPeaks(null);

    async function loadPeaks() {
      try {
        const response = await fetch(src, { credentials: "include" });
        const arrayBuffer = await response.arrayBuffer();
        const AudioContextCtor = window.AudioContext;
        const audioContext = new AudioContextCtor();
        const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
        const channel = audioBuffer.getChannelData(0);
        const blockSize = Math.max(1, Math.floor(channel.length / WAVEFORM_BARS));
        const values: number[] = [];
        for (let i = 0; i < WAVEFORM_BARS; i++) {
          let sum = 0;
          const start = i * blockSize;
          for (let j = 0; j < blockSize; j++) {
            sum += Math.abs(channel[start + j] ?? 0);
          }
          values.push(sum / blockSize);
        }
        const max = Math.max(...values, 0.0001);
        void audioContext.close();
        if (!cancelled) setPeaks(values.map((v) => v / max));
      } catch {
        if (!cancelled) setPeaks([]);
      }
    }

    void loadPeaks();
    return () => {
      cancelled = true;
    };
  }, [src]);

  return peaks;
}

/** Imperative seek handle — used by the Transcript tab so clicking a
 * transcript segment seeks the same underlying <audio> element (spec:
 * "Audio/transcript synchronization"). */
export interface AudioPlayerHandle {
  seekToMs: (ms: number) => void;
  play: () => void;
}

export const AudioPlayer = forwardRef<
  AudioPlayerHandle,
  {
    src: string;
    sourceLabel: string;
    markers?: Marker[];
    /** Fired on every timeupdate, in milliseconds — used to highlight the
     * currently-playing transcript segment. */
    onTimeUpdateMs?: (ms: number) => void;
  }
>(function AudioPlayer({ src, sourceLabel, markers = [], onTimeUpdateMs }, ref) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [playbackRate, setPlaybackRate] = useState(1);
  const peaks = useWaveformPeaks(src);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onTimeUpdate = () => {
      setCurrentTime(audio.currentTime);
      onTimeUpdateMs?.(audio.currentTime * 1000);
    };
    const onLoadedMetadata = () => setDuration(audio.duration || 0);
    const onEnded = () => setPlaying(false);
    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("loadedmetadata", onLoadedMetadata);
    audio.addEventListener("ended", onEnded);
    return () => {
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("loadedmetadata", onLoadedMetadata);
      audio.removeEventListener("ended", onEnded);
    };
  }, [src, onTimeUpdateMs]);

  useEffect(() => {
    if (audioRef.current) audioRef.current.playbackRate = playbackRate;
  }, [playbackRate]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const width = canvas.clientWidth || 1;
    const height = canvas.clientHeight || 1;
    canvas.width = width;
    canvas.height = height;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    ctx.clearRect(0, 0, width, height);

    const bars = peaks && peaks.length > 0 ? peaks : new Array(WAVEFORM_BARS).fill(0.08);
    const barWidth = width / bars.length;

    function drawBars(color: string, clipWidth?: number) {
      if (!ctx) return;
      ctx.save();
      if (clipWidth !== undefined) {
        ctx.beginPath();
        ctx.rect(0, 0, clipWidth, height);
        ctx.clip();
      }
      ctx.fillStyle = color;
      bars.forEach((value, i) => {
        const barHeight = Math.max(2, value * height);
        ctx.fillRect(i * barWidth, (height - barHeight) / 2, Math.max(1, barWidth - 1), barHeight);
      });
      ctx.restore();
    }

    const progressFraction = duration > 0 ? currentTime / duration : 0;
    drawBars(getComputedStyle(canvas).getPropertyValue("--waveform-track").trim() || "#cbd5e1");
    drawBars(
      getComputedStyle(canvas).getPropertyValue("--waveform-progress").trim() || "#2563eb",
      width * progressFraction
    );
  }, [peaks, currentTime, duration]);

  function togglePlay() {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
    } else {
      void audio.play();
    }
    setPlaying(!playing);
  }

  function seekTo(seconds: number) {
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = seconds;
    setCurrentTime(seconds);
  }

  function seekFromCanvasClick(event: MouseEvent<HTMLCanvasElement>) {
    const canvas = canvasRef.current;
    if (!canvas || duration <= 0) return;
    const rect = canvas.getBoundingClientRect();
    const fraction = (event.clientX - rect.left) / rect.width;
    seekTo(Math.max(0, Math.min(1, fraction)) * duration);
  }

  useImperativeHandle(
    ref,
    () => ({
      seekToMs: (ms: number) => seekTo(ms / 1000),
      play: () => {
        const audio = audioRef.current;
        if (audio) {
          void audio.play();
          setPlaying(true);
        }
      },
    }),
    []
  );

  return (
    <div className={styles.player}>
      {/* Audio-only conversation recording — no captions track applies. */}
      <audio ref={audioRef} src={src} preload="metadata" />

      <canvas
        ref={canvasRef}
        className={styles.waveform}
        onClick={seekFromCanvasClick}
        role="img"
        aria-label="Audio-Waveform, klicken zum Springen"
      />

      <div className={styles.controlsRow}>
        <Button
          variant="secondary"
          aria-label={playing ? "Pause" : "Abspielen"}
          onClick={togglePlay}
          type="button"
        >
          {playing ? <Pause size={16} /> : <Play size={16} />}
        </Button>
        <span className={styles.timeText}>
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
        <div className={styles.seekWrap}>
          <input
            type="range"
            className={styles.seek}
            min={0}
            max={duration || 0}
            step={0.1}
            value={currentTime}
            aria-label="Wiedergabeposition"
            onChange={(event) => seekTo(Number(event.target.value))}
          />
          {duration > 0 &&
            markers.map((marker) => (
              <span
                key={marker.id}
                className={styles.markerTick}
                style={{ left: `${(marker.timestamp_ms / 1000 / duration) * 100}%` }}
                title={marker.label ?? `Marker bei ${formatTime(marker.timestamp_ms / 1000)}`}
              />
            ))}
        </div>
        <Select
          aria-label="Wiedergabegeschwindigkeit"
          value={String(playbackRate)}
          onChange={(event) => setPlaybackRate(Number(event.target.value))}
          style={{ minWidth: "auto" }}
        >
          {PLAYBACK_RATES.map((rate) => (
            <option key={rate} value={rate}>
              {rate}×
            </option>
          ))}
        </Select>
      </div>
      <span className={styles.sourceLine}>{sourceLabel}</span>
    </div>
  );
});
