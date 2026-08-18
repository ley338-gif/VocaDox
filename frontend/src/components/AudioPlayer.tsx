import { Pause, Play } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { Marker } from "../api/conversations";
import { Button } from "../design-system/Button";
import styles from "./AudioPlayer.module.css";

function formatTime(seconds: number): string {
  if (!Number.isFinite(seconds)) return "0:00";
  const mins = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${mins}:${secs.toString().padStart(2, "0")}`;
}

export function AudioPlayer({
  src,
  sourceLabel,
  markers = [],
}: {
  src: string;
  sourceLabel: string;
  markers?: Marker[];
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const onTimeUpdate = () => setCurrentTime(audio.currentTime);
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
  }, [src]);

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

  return (
    <div className={styles.player}>
      {/* Audio-only conversation recording — no captions track applies. */}
      <audio ref={audioRef} src={src} preload="metadata" />
      <div className={styles.controlsRow}>
        <Button
          variant="secondary"
          aria-label={playing ? "Pause" : "Play"}
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
            aria-label="Seek position"
            onChange={(event) => seekTo(Number(event.target.value))}
          />
          {duration > 0 &&
            markers.map((marker) => (
              <span
                key={marker.id}
                className={styles.markerTick}
                style={{ left: `${(marker.timestamp_ms / 1000 / duration) * 100}%` }}
                title={marker.label ?? `Marker at ${formatTime(marker.timestamp_ms / 1000)}`}
              />
            ))}
        </div>
      </div>
      <span className={styles.sourceLine}>{sourceLabel}</span>
    </div>
  );
}
