'use client';

import { useEffect, useRef } from 'react';
import { FRAME_INTERVAL_MS } from '@/constants';

export function useAnimationLoop(isPlaying: boolean, onTick: () => void) {
  const handleRef = useRef<number | null>(null);
  const lastTsRef = useRef<number>(0);
  const onTickRef = useRef(onTick);
  onTickRef.current = onTick;

  useEffect(() => {
    if (!isPlaying) {
      if (handleRef.current !== null) {
        cancelAnimationFrame(handleRef.current);
        handleRef.current = null;
      }
      return;
    }

    lastTsRef.current = 0;
    const loop = (ts: number) => {
      if (lastTsRef.current === 0) lastTsRef.current = ts;
      if (ts - lastTsRef.current >= FRAME_INTERVAL_MS) {
        onTickRef.current();
        lastTsRef.current = ts;
      }
      handleRef.current = requestAnimationFrame(loop);
    };
    handleRef.current = requestAnimationFrame(loop);

    return () => {
      if (handleRef.current !== null) {
        cancelAnimationFrame(handleRef.current);
        handleRef.current = null;
      }
    };
  }, [isPlaying]);
}
