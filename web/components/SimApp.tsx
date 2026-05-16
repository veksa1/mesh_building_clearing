'use client';

import { useEffect, useReducer } from 'react';
import type { AppAction, AppState } from '@/types';
import { DEFAULT_SIM_PARAMS } from '@/constants';
import { defaultFloorplan } from '@/lib/defaultFloorplan';
import { compile } from '@/lib/compiler';
import { Sidebar } from './editor/Sidebar';
import { EditorCanvas } from './editor/EditorCanvas';
import { SimCanvas } from './simulation/SimCanvas';
import { ControlPanel } from './simulation/ControlPanel';
import { NeutralisedOverlay } from './simulation/NeutralisedOverlay';
import { ThinkingPanel } from './simulation/ThinkingPanel';
import { useAnimationLoop } from '@/hooks/useAnimationLoop';

const initialState: AppState = {
  mode: 'editing',
  floorplan: defaultFloorplan(),
  editor: {
    tool: 'wall',
    selectedMaterial: 'drywall',
    pendingWallStart: null,
    hoveredCell: null,
  },
  simParams: DEFAULT_SIM_PARAMS,
  compiled: null,
  currentFrame: 0,
  isPlaying: false,
  compilationError: null,
  viewMode: 'drone',
};

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_TOOL':
      return { ...state, editor: { ...state.editor, tool: action.tool, pendingWallStart: null } };
    case 'SET_MATERIAL':
      return { ...state, editor: { ...state.editor, selectedMaterial: action.material } };
    case 'ADD_WALL':
      return {
        ...state,
        floorplan: { ...state.floorplan, walls: [...state.floorplan.walls, action.segment] },
      };
    case 'ADD_DOOR':
      return {
        ...state,
        floorplan: { ...state.floorplan, doors: [...state.floorplan.doors, action.door] },
      };
    case 'DELETE_WALL':
      return {
        ...state,
        floorplan: {
          ...state.floorplan,
          walls: state.floorplan.walls.filter((w) => w.id !== action.id),
          doors: state.floorplan.doors.filter((d) => d.wallSegmentId !== action.id),
        },
      };
    case 'SET_ENTRANCE':
      return { ...state, floorplan: { ...state.floorplan, entrance: action.cell } };
    case 'SET_TARGET':
      return { ...state, floorplan: { ...state.floorplan, target: action.cell } };
    case 'SET_HOVERED':
      return { ...state, editor: { ...state.editor, hoveredCell: action.cell } };
    case 'SET_PENDING_WALL_START':
      return { ...state, editor: { ...state.editor, pendingWallStart: action.cell } };
    case 'CLEAR_FLOORPLAN':
      return {
        ...state,
        floorplan: { gridRows: 60, gridCols: 80, walls: [], doors: [], entrance: null, target: null },
        editor: { ...state.editor, pendingWallStart: null },
      };
    case 'RUN_SIMULATION':
      return { ...state, mode: 'compiling', compilationError: null };
    case 'COMPILATION_DONE':
      return {
        ...state,
        mode: 'simulating',
        compiled: action.result,
        currentFrame: 0,
        isPlaying: true,
        compilationError: null,
      };
    case 'COMPILATION_FAILED':
      return { ...state, mode: 'editing', compilationError: action.error };
    case 'TICK_FRAME': {
      if (!state.compiled) return state;
      const total = state.compiled.timeline.length;
      if (state.currentFrame >= total - 1) {
        return { ...state, isPlaying: false, mode: 'finished' };
      }
      return { ...state, currentFrame: state.currentFrame + 1 };
    }
    case 'SEEK_FRAME':
      return { ...state, currentFrame: action.frame, isPlaying: false };
    case 'TOGGLE_PLAY': {
      if (!state.compiled) return state;
      const atEnd = state.currentFrame >= state.compiled.timeline.length - 1;
      if (atEnd && !state.isPlaying) {
        return { ...state, isPlaying: true, currentFrame: 0, mode: 'simulating' };
      }
      return { ...state, isPlaying: !state.isPlaying };
    }
    case 'RESET':
      return {
        ...initialState,
        floorplan: state.floorplan,
        editor: { ...initialState.editor, selectedMaterial: state.editor.selectedMaterial },
        viewMode: state.viewMode,
      };
    case 'SET_VIEW_MODE':
      return { ...state, viewMode: action.viewMode };
    default:
      return state;
  }
}

export function SimApp() {
  const [state, dispatch] = useReducer(appReducer, initialState);

  // Trigger compile when entering 'compiling' mode.
  useEffect(() => {
    if (state.mode !== 'compiling') return;
    let cancelled = false;
    (async () => {
      try {
        const result = await compile(state.floorplan);
        if (cancelled) return;
        if (result.ok) {
          dispatch({ type: 'COMPILATION_DONE', result: result.compiled });
        } else {
          dispatch({ type: 'COMPILATION_FAILED', error: result.error });
        }
      } catch (err) {
        if (!cancelled) {
          dispatch({
            type: 'COMPILATION_FAILED',
            error: err instanceof Error ? err.message : String(err),
          });
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [state.mode, state.floorplan]);

  useAnimationLoop(state.isPlaying, () => dispatch({ type: 'TICK_FRAME' }));

  const currentFrameState = state.compiled?.timeline[state.currentFrame] ?? null;
  const isNeutralised = currentFrameState?.phase === 'neutralised';

  return (
    <div className="flex h-screen w-screen bg-black text-white font-mono overflow-hidden">
      {state.mode === 'editing' && (
        <aside className="w-56 flex-shrink-0 border-r border-white/10 p-4 overflow-y-auto">
          <Sidebar state={state} dispatch={dispatch} />
        </aside>
      )}

      <main className="flex-1 flex flex-col items-center justify-center p-4 relative">
        {state.mode === 'editing' && <EditorCanvas state={state} dispatch={dispatch} />}
        {state.mode === 'compiling' && (
          <div className="text-white/70 text-sm uppercase tracking-widest">
            Compiling Mesh Strategy...
          </div>
        )}
        {(state.mode === 'simulating' || state.mode === 'finished') && state.compiled && (
          <SimCanvas
            compiled={state.compiled}
            params={state.simParams}
            currentFrame={state.currentFrame}
            viewMode={state.viewMode}
          />
        )}
        {isNeutralised && <NeutralisedOverlay visible={true} />}
      </main>

      {(state.mode === 'simulating' || state.mode === 'finished') && state.compiled && currentFrameState && (
        <aside className="w-80 flex-shrink-0 border-l border-white/10 p-4 overflow-y-auto flex flex-col gap-6">
          <ControlPanel state={state} dispatch={dispatch} />
          <div className="border-t border-white/10 pt-4">
            <ThinkingPanel
              frame={currentFrameState}
              roomGraph={state.compiled.roomGraph}
              currentFrame={state.currentFrame}
              viewMode={state.viewMode}
              setViewMode={(viewMode) => dispatch({ type: 'SET_VIEW_MODE', viewMode })}
            />
          </div>
        </aside>
      )}
    </div>
  );
}
