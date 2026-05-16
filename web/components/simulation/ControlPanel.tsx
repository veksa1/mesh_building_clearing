'use client';

import type { Dispatch } from 'react';
import type { AppAction, AppState } from '@/types';

export function ControlPanel({
  state,
  dispatch,
}: {
  state: AppState;
  dispatch: Dispatch<AppAction>;
}) {
  const total = state.compiled?.timeline.length ?? 0;
  const frame = state.currentFrame;
  const droneCount = state.compiled?.timeline[0]?.dronesRC.length ?? 0;

  return (
    <div className="text-xs uppercase tracking-wider flex flex-col gap-3">
      <div className="text-white/60">CONTROLS</div>
      <div className="flex gap-2">
        <button
          onClick={() => dispatch({ type: 'TOGGLE_PLAY' })}
          className="border border-white/40 px-3 py-1.5 hover:border-white flex-1"
        >
          {state.isPlaying ? '‖ PAUSE' : '▶ PLAY'}
        </button>
        <button
          onClick={() => dispatch({ type: 'RESET' })}
          className="border border-white/40 px-3 py-1.5 hover:border-white"
        >
          RESET
        </button>
      </div>
      <input
        type="range"
        min={0}
        max={Math.max(0, total - 1)}
        value={frame}
        onChange={(e) => dispatch({ type: 'SEEK_FRAME', frame: Number(e.target.value) })}
        className="w-full accent-white"
      />
      <div className="font-mono text-[10px] text-white/70 normal-case tracking-normal">
        FRAME {String(frame).padStart(3, '0')} / {String(total).padStart(3, '0')}
      </div>
      <div className="font-mono text-[10px] text-white/70 normal-case tracking-normal">
        DRONES: {droneCount} (1 scout + {Math.max(0, droneCount - 1)} relays)
      </div>
    </div>
  );
}
