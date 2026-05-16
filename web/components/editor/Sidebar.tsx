'use client';

import type { Dispatch } from 'react';
import type { AppAction, AppState, EditorTool, WallMaterialId } from '@/types';
import { WALL_MATERIALS } from '@/constants';

const TOOLS: { id: EditorTool; label: string }[] = [
  { id: 'wall', label: 'Wall' },
  { id: 'door', label: 'Door' },
  { id: 'entrance', label: 'Entrance' },
  { id: 'target', label: 'Target' },
];

export function Sidebar({ state, dispatch }: { state: AppState; dispatch: Dispatch<AppAction> }) {
  const { editor, floorplan, mode, compilationError } = state;
  const canRun = mode === 'editing' && floorplan.entrance !== null && floorplan.target !== null;

  return (
    <div className="flex flex-col gap-6 text-xs uppercase tracking-wider">
      <div>
        <div className="mb-2 text-white/60">MODE</div>
        <div className="flex flex-col gap-1">
          {TOOLS.map((t) => (
            <button
              key={t.id}
              onClick={() => dispatch({ type: 'SET_TOOL', tool: t.id })}
              className={`border px-2 py-1.5 text-left transition ${
                editor.tool === t.id
                  ? 'bg-white text-black border-white'
                  : 'border-white/40 text-white hover:border-white'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {editor.tool === 'wall' && (
        <div>
          <div className="mb-2 text-white/60">MATERIAL</div>
          <div className="flex flex-col gap-1">
            {WALL_MATERIALS.map((m) => (
              <button
                key={m.id}
                onClick={() => dispatch({ type: 'SET_MATERIAL', material: m.id as WallMaterialId })}
                className={`border px-2 py-1.5 text-left transition ${
                  editor.selectedMaterial === m.id
                    ? 'bg-white text-black border-white'
                    : 'border-white/40 text-white hover:border-white'
                }`}
              >
                <div className="flex justify-between">
                  <span>{m.label}</span>
                  <span className="opacity-60">{m.attenuationDb}dB</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="mb-2 text-white/60">PLACEMENT</div>
        <div className="text-[10px] text-white/50 leading-relaxed">
          {!floorplan.entrance && <div>! Set entrance</div>}
          {!floorplan.target && <div>! Set target</div>}
          {floorplan.entrance && floorplan.target && <div className="text-white">READY</div>}
        </div>
      </div>

      <div>
        <div className="mb-2 text-white/60">DRONES</div>
        <input
          type="number"
          min={1}
          max={32}
          value={state.simParams.nDrones}
          onChange={(e) => {
            const n = parseInt(e.target.value, 10);
            if (Number.isFinite(n)) {
              dispatch({ type: 'SET_N_DRONES', value: Math.max(1, Math.min(32, n)) });
            }
          }}
          className="w-full border border-white/40 bg-black px-2 py-1.5 text-white tracking-wider focus:outline-none focus:border-white"
        />
      </div>

      <button
        onClick={() => dispatch({ type: 'CLEAR_FLOORPLAN' })}
        className="border border-white/40 px-2 py-1.5 text-left text-white/60 hover:border-white hover:text-white"
      >
        Clear All
      </button>

      <button
        disabled={!canRun}
        onClick={() => dispatch({ type: 'RUN_SIMULATION' })}
        className={`w-full px-4 py-3 text-center font-bold tracking-[0.2em] border-2 ${
          canRun
            ? 'bg-white text-black border-white hover:bg-white/90'
            : 'border-white/20 text-white/30 cursor-not-allowed'
        }`}
      >
        ▶ RUN
      </button>

      {compilationError && (
        <div className="text-[10px] text-red-400 normal-case tracking-normal">
          {compilationError}
        </div>
      )}

      <div className="text-[10px] text-white/40 normal-case tracking-normal leading-relaxed">
        Wall: click two points.<br />
        Door: click on a wall.<br />
        Esc to cancel pending wall.
      </div>
    </div>
  );
}
