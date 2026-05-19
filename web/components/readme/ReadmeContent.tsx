'use client';

const H2 = 'mt-8 mb-3 text-xs uppercase tracking-widest text-white/60 border-b border-white/10 pb-1';
const P = 'text-[12px] text-white/80 leading-relaxed normal-case tracking-normal';
const CODE = 'text-white';
const PRE = 'text-[11px] text-white/70 my-3 overflow-x-auto whitespace-pre normal-case tracking-normal';
const LIST = 'list-disc pl-5 my-2 space-y-1 text-[12px] text-white/80 normal-case tracking-normal';
const TABLE = 'w-full my-3 border border-white/20 border-collapse text-[11px] normal-case tracking-normal';
const TH = 'border border-white/20 px-2 py-1 text-left text-white/60 uppercase tracking-wider text-[10px]';
const TD = 'border border-white/20 px-2 py-1 text-white/80';
const TD_MONO = 'border border-white/20 px-2 py-1 text-white';

function MeshGossipSvg() {
  return (
    <svg viewBox="0 0 480 200" className="my-4 w-full max-w-[480px]" stroke="white" fill="none" strokeWidth="1">
      <rect x="20" y="60" width="120" height="60" />
      <text x="80" y="84" fill="white" fontSize="11" fontFamily="monospace" textAnchor="middle">DRONE A</text>
      <text x="80" y="102" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        originate · maybe_tx
      </text>

      <rect x="340" y="60" width="120" height="60" />
      <text x="400" y="84" fill="white" fontSize="11" fontFamily="monospace" textAnchor="middle">DRONE B</text>
      <text x="400" y="102" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        inbox · drain · merge
      </text>

      <line x1="140" y1="80" x2="340" y2="80" />
      <polygon points="340,80 332,76 332,84" fill="white" />
      <text x="240" y="72" fill="white" fontSize="10" fontFamily="monospace" textAnchor="middle">
        BEACON / TOPOLOGY_MERGE / TOKEN
      </text>

      <line x1="340" y1="110" x2="140" y2="110" strokeDasharray="2 3" />
      <polygon points="140,110 148,106 148,114" fill="white" />
      <text x="240" y="128" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        accepted iff RSSI ≥ sensitivity (and SNR ≥ min_snr_db)
      </text>

      <text x="240" y="160" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        wire frame:  physics_header_json  |||  packet_json
      </text>
      <text x="240" y="176" fill="rgba(255,255,255,0.4)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        no TTL · no multi-hop relay · pairwise merge on receive
      </text>
    </svg>
  );
}

function MultiProcessSvg() {
  return (
    <svg viewBox="0 0 480 260" className="my-4 w-full max-w-[480px]" stroke="white" fill="none" strokeWidth="1">
      <rect x="160" y="14" width="160" height="42" />
      <text x="240" y="32" fill="white" fontSize="11" fontFamily="monospace" textAnchor="middle">
        sim_kernel_udp
      </text>
      <text x="240" y="48" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        orchestrator · spawn · join
      </text>

      <line x1="200" y1="56" x2="60" y2="92" />
      <line x1="240" y1="56" x2="240" y2="92" />
      <line x1="280" y1="56" x2="420" y2="92" />

      <rect x="10" y="92" width="100" height="50" />
      <text x="60" y="112" fill="white" fontSize="10" fontFamily="monospace" textAnchor="middle">worker 0</text>
      <text x="60" y="128" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        :8700
      </text>

      <rect x="190" y="92" width="100" height="50" />
      <text x="240" y="112" fill="white" fontSize="10" fontFamily="monospace" textAnchor="middle">worker 1</text>
      <text x="240" y="128" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        :8701
      </text>

      <rect x="370" y="92" width="100" height="50" />
      <text x="420" y="112" fill="white" fontSize="10" fontFamily="monospace" textAnchor="middle">worker N</text>
      <text x="420" y="128" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        :8700+N
      </text>

      <line x1="110" y1="160" x2="370" y2="160" />
      <text x="240" y="156" fill="white" fontSize="10" fontFamily="monospace" textAnchor="middle">
        UDP loopback · 127.0.0.1 · TransmissionLayer
      </text>
      <line x1="60" y1="142" x2="60" y2="160" />
      <line x1="240" y1="142" x2="240" y2="160" />
      <line x1="420" y1="142" x2="420" y2="160" />

      <line x1="240" y1="178" x2="240" y2="200" strokeDasharray="2 3" />
      <rect x="120" y="200" width="240" height="42" />
      <text x="240" y="220" fill="white" fontSize="11" fontFamily="monospace" textAnchor="middle">
        swap → 802.11 WiFi adapters
      </text>
      <text x="240" y="236" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        same ABC · same payload codec · zero agent changes
      </text>
    </svg>
  );
}

function RfLinkSvg() {
  return (
    <svg viewBox="0 0 480 240" className="my-4 w-full max-w-[480px]" stroke="white" fill="none" strokeWidth="1">
      <circle cx="40" cy="140" r="12" />
      <text x="40" y="172" fill="white" fontSize="10" fontFamily="monospace" textAnchor="middle">TX</text>
      <text x="40" y="186" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        20 dBm
      </text>

      <circle cx="440" cy="140" r="12" />
      <text x="440" y="172" fill="white" fontSize="10" fontFamily="monospace" textAnchor="middle">RX</text>
      <text x="440" y="186" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        −92 dBm
      </text>

      <line x1="52" y1="140" x2="428" y2="140" strokeDasharray="3 3" />

      <rect x="160" y="100" width="6" height="80" />
      <text x="163" y="94" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        wall
      </text>
      <rect x="260" y="110" width="6" height="60" />
      <text x="263" y="104" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        wall
      </text>
      <rect x="350" y="90" width="6" height="100" />
      <text x="353" y="84" fill="rgba(255,255,255,0.6)" fontSize="9" fontFamily="monospace" textAnchor="middle">
        wall
      </text>

      <text x="240" y="40" fill="white" fontSize="11" fontFamily="monospace" textAnchor="middle">
        L = 20·log₁₀(f) + N·log₁₀(d) − 27.55 + Σ L_f
      </text>
      <text x="240" y="220" fill="white" fontSize="11" fontFamily="monospace" textAnchor="middle">
        received_dbm = tx_dbm − L − Σ wall_db
      </text>
    </svg>
  );
}

export function ReadmeContent() {
  return (
    <div>
      <section>
        <h2 className={H2}>What It Does</h2>
        <p className={P}>
          A simulation of an autonomous indoor drone swarm clearing a
          building and neutralising a target. N drones enter through an
          entrance, spread out, share what they see over a radio mesh,
          and converge on a target — with no central controller and no
          shared clock beyond their own broadcasts.
        </p>
        <ol className="list-decimal pl-5 my-3 space-y-2 text-[12px] text-white/80 normal-case tracking-normal">
          <li>
            <span className="text-white">Setup.</span> The user draws a
            floorplan (walls of selectable materials, doors), drops an
            entrance and a target, and picks a fleet size N (1–32).
          </li>
          <li>
            <span className="text-white">Roles.</span> The fleet
            auto-splits into <em>1 scout</em> (highest UID) and{' '}
            <em>N−1 relays</em>. The scout is the spearhead that opens
            new rooms; relays stage along the backbone path between the
            lobby and the active room so the radio chain stays alive
            even when the scout pushes deep through walls.
          </li>
          <li>
            <span className="text-white">Perception.</span> Each drone
            runs two simulated sensors per tick. (a) A short-range
            occupancy disc that reveals walls and floor cells within{' '}
            <code className={CODE}>perception_radius</code>. (b) A
            longer-range vision channel that detects doorways and the
            target within <code className={CODE}>vision_radius</code>,
            gated by Bresenham line-of-sight (no wall pixel may sit
            between drone and detection). The vision channel stands in
            for an onboard YOLO model — in a real deployment it would
            be a CV head; here it&apos;s simulated as LOS-checked
            geometric detection that produces the same kind of typed
            <code className={CODE}>{' '}(kind, anchor, bearing, confidence, signature)</code>{' '}
            records a vision model would emit.
          </li>
          <li>
            <span className="text-white">Communication.</span> No
            central controller. Drones gossip three packet kinds
            (BEACON, TOPOLOGY_MERGE, TOKEN) over an RSSI-modeled radio
            mesh; each receiver runs the full link budget (distance +
            wall attenuation + sensitivity gate) locally and accepts a
            frame only if it clears the gate. Merges are pure
            set-unions, so any delivery order converges. Under the
            hood each drone is its own OS process broadcasting real
            bytes on its own UDP port — only the transport changes
            when the system moves to WiFi adapters.
          </li>
          <li>
            <span className="text-white">Decision policy.</span> The
            active planner is BFS over the building&apos;s room
            adjacency graph. From the entrance, every drone computes
            the same spanning tree; the scout always advances toward
            the anchor cell of the next unseen child room, while relays
            distribute themselves by arc-length along the backbone
            polyline to that room. Visited-room state is unioned
            across the fleet via BEACONs, so every drone agrees on
            what&apos;s left to clear.
          </li>
          <li>
            <span className="text-white">Termination.</span> The first
            drone whose vision channel detects the target broadcasts
            the witness.
          </li>
        </ol>
        <p className={P}>
          The rest of this document drills into the three challenge
          layers — mesh, transmission, application — and the runtime
          that hosts them.
        </p>
      </section>

      <section>
        <h2 className={H2}>Mesh Layer</h2>
        <p className={P}>
          Communication between multiple autonomous agents. We use
          epidemic-style gossip on a flat topology — every drone is a
          peer, every transmission is broadcast, every receiver decides
          locally whether the link budget allowed decode. This gives a
          self-healing mesh with no routing tables, no master node, and
          no spanning-tree state to keep consistent under jamming.
        </p>
        <MeshGossipSvg />
      </section>

      <section>
        <h2 className={H2}>Gossip Semantics</h2>
        <p className={P}>
          Each tick the kernel walks every drone through{' '}
          <code className={CODE}>sense → decide → move → maybe_tx → broadcast → recv → drain</code>.
          Accepted packets land in <code className={CODE}>inbox</code>;{' '}
          <code className={CODE}>drain_inbox()</code> applies additive
          merges once per tick. No TTL, no multi-hop relay — multi-hop
          coverage emerges only from repeated originates when geometry
          permits. The merges are pure set/union operations, so any
          delivery order is safe; lost frames cost convergence latency,
          not correctness.
        </p>
      </section>

      <section>
        <h2 className={H2}>Payload Schema</h2>
        <p className={P}>
          Three <code className={CODE}>MsgKind</code> values, all carried
          by the same <code className={CODE}>Packet</code> struct.{' '}
          <code className={CODE}>packet_codec.py</code> serialises to JSON
          bytes — the literal format that crosses the socket.
        </p>
        <pre className={PRE}>
{`┌─ BEACON ───────────────────────────────────────┐
│ kind       : "BEACON"                           │
│ payload    : { r, c, tick, seen_rooms }         │
│ interval   : every 4 ticks                      │
│ role       : pose snapshot + visited-room set   │
│ merge      : union(seen_rooms); last-pose       │
└─────────────────────────────────────────────────┘

┌─ TOPOLOGY_MERGE ───────────────────────────────┐
│ kind       : "TOPOLOGY_MERGE"                   │
│ payload    : { nodes, edges, belief_edges,      │
│                tick }                           │
│ interval   : every 10 ticks                     │
│ role       : floor-graph + portal-belief share  │
│ merge      : set-union nodes / edges / beliefs  │
└─────────────────────────────────────────────────┘

┌─ TOKEN ────────────────────────────────────────┐
│ kind       : "TOKEN"                            │
│ payload    : { signature, ttl_ticks, tick }     │
│ interval   : every 17 ticks                     │
│ ttl        : 48 ticks                           │
│ role       : portal-focus claim (de-dupes work) │
│ merge      : claims[sig] = (uid, expire_tick)   │
└─────────────────────────────────────────────────┘`}
        </pre>
      </section>

      <section>
        <h2 className={H2}>Wire Frame</h2>
        <p className={P}>
          A transmission is a real socket write: a JSON physics header is
          prepended to the application packet and emitted as one
          ethernet-ish frame.
        </p>
        <pre className={PRE}>
{`┌─ wire frame ────────────────────────────────────┐
│  {tx_port, tx_r, tx_c}  |||  {kind, sender_uid, │
│  ── physics header ──        seq, payload}      │
│                              ── packet codec ── │
└──────────────────────────────────────────────────┘`}
        </pre>
        <p className={P}>
          The header carries the sender pose so a receiver can recompute
          the link budget against its own position. Today this serializes
          to UDP on loopback; on real hardware it becomes the equivalent
          radiotap-wrapped 802.11 frame.
        </p>
      </section>

      <section>
        <h2 className={H2}>Transmission Layer</h2>
        <p className={P}>
          Communication between two transceivers. We model RF as a real
          link budget with distance attenuation, wall penetration, and a
          decode pipeline that matches what a real receiver does.
        </p>
        <RfLinkSvg />
        <p className={P}>
          Pairwise received power is{' '}
          <code className={CODE}>tx_dbm − L − Σ wall_db</code>. Path loss
          uses an ITU-R Report P.2346-style compact log-distance form with
          a frequency offset:
        </p>
        <pre className={PRE}>
{`L_db = 20·log₁₀(f_MHz) + N·log₁₀(d_m) − 27.55 + Σ L_f
       (N = distance_exponent ≈ 28.0)
       (d clamped to d_floor = 0.5 m)`}
        </pre>
        <p className={P}>
          Wall crossings are integrated by ray-marching from TX to RX
          (Bresenham-ish sampling, ~48 points per ray); each wall pixel
          contributes <code className={CODE}>lf_per_wall_cell_db</code>{' '}
          (default 9 dB). The decode is staged so reliability can be tuned
          independently of physics:
        </p>
        <pre className={PRE}>
{`stage 1  sensitivity gate  →  rssi ≥ sensitivity_dbm
stage 2  SNR gate (opt.)    →  rssi − noise_floor ≥ min_snr_db
stage 3  MAC drop (opt.)    →  uniform(0,1) ≥ drop_rate
         delivered          ↳  CommEvent(outcome="delivered")
         else               ↳  CommEvent(outcome="below_threshold")`}
        </pre>
      </section>

      <section>
        <h2 className={H2}>Multi-Process Runtime</h2>
        <p className={P}>
          The mesh is not in-process method calls. Each drone runs as a
          separate OS process, spawned via{' '}
          <code className={CODE}>multiprocessing.get_context(&quot;spawn&quot;)</code>{' '}
          (chosen so it&apos;s safe to host on Verda&apos;s VMs without{' '}
          <code className={CODE}>fork()</code> hazards). Each worker binds
          a dedicated UDP port and broadcasts real bytes on a real socket;
          the kernel only sequences ticks and the deterministic move
          resolution.
        </p>
        <MultiProcessSvg />
        <p className={P}>
          Resilience properties this gives us for free: no leader to lose
          to jamming, every neighbor is a relay candidate, frame loss
          degrades convergence latency rather than correctness, and the
          three merge semantics (union, last-write, expiring claim) keep
          state convergent even under heavy reorder or partition.
        </p>
      </section>

      <section>
        <h2 className={H2}>Application Layer</h2>
        <p className={P}>
          What the mesh unlocks: autonomous coordinated building
          clearance. Multiple drones enter an unknown indoor floorplan,
          spread out, share what they see, and converge on a target — with
          no central command and no shared clock beyond the broadcast
          beacons.
        </p>
        <pre className={PRE}>
{`┌─ LayoutBFSDrone ──────────┐   ┌─ DroneAgent ──────────────┐
│ oracle room graph         │   │ local sense only          │
│ BFS spanning tree         │   │ frontier-style explore    │
│ scout + relay choreography│   │ portal hypotheses + cuts  │
│ shared seen_rooms beacon  │   │ topology belief gossip    │
│ layout_bfs_agent.py       │   │ agent.py                  │
└───────────────────────────┘   └───────────────────────────┘`}
        </pre>
        <p className={P}>
          <code className={CODE}>LayoutBFSDrone</code> assumes every drone
          carries the same room graph and runs the same BFS spanning-tree
          choreography. The scout (highest UID) advances along the next
          unseen tree edge; relays stage along the backbone polyline by
          arc-length sampling, holding the link back to the lobby alive.
          Visited-room state is unioned over BEACONs, so the swarm stays
          aligned on coverage even when individual links drop.
        </p>
        <p className={P}>
          <code className={CODE}>DroneAgent</code> drops the oracle. It
          builds an anonymous topology graph from fused floor cells and
          vision-like portal detections, cuts regions at portals, picks a
          frontier portal as focus, and BFSes the known-free graph toward
          it. Belief refines from local perception plus inbound{' '}
          <code className={CODE}>TOPOLOGY_MERGE</code> gossip — the
          richer that gossip, the faster the swarm converges. TOKEN
          claims keep two drones from racing the same doorway.
        </p>
      </section>

      <section>
        <h2 className={H2}>Hardware Bridge</h2>
        <p className={P}>
          The transport is abstracted behind the{' '}
          <code className={CODE}>TransmissionLayer</code> ABC{' '}
          (<code className={CODE}>mock_transmission.py</code>) — two
          methods, <code className={CODE}>broadcast(payload: bytes)</code>{' '}
          and{' '}
          <code className={CODE}>receive(timeout) → (sender_id, payload, rssi_dbm)</code>.
          Today&apos;s implementation is{' '}
          <code className={CODE}>PropagationUDPTransmission</code>: real
          bytes over loopback UDP with a JSON physics header.
        </p>
        <p className={P}>
          That ABC is the hand-off. Swap the loopback socket for a driver
          that pushes raw 802.11 frames out a Kova USB WiFi adapter
          (e.g. via <code className={CODE}>kova-wfb-rs</code>), and
          nothing else moves — same packet codec, same packet kinds, same{' '}
          <code className={CODE}>drain_inbox</code> merge logic, same
          planners. The simulation is already wire-shaped for the field
          demo: today&apos;s loopback mesh becomes tomorrow&apos;s
          three-radio swarm by replacing one class.
        </p>
      </section>

      <section>
        <h2 className={H2}>Key Parameters</h2>
        <table className={TABLE}>
          <thead>
            <tr>
              <th className={TH}>Param</th>
              <th className={TH}>Default</th>
              <th className={TH}>Layer</th>
            </tr>
          </thead>
          <tbody>
            <tr><td className={TD_MONO}>freq_mhz</td><td className={TD}>2400</td><td className={TD}>transmission</td></tr>
            <tr><td className={TD_MONO}>tx_power_dbm</td><td className={TD}>20</td><td className={TD}>transmission</td></tr>
            <tr><td className={TD_MONO}>sensitivity_dbm</td><td className={TD}>−92</td><td className={TD}>transmission</td></tr>
            <tr><td className={TD_MONO}>distance_exponent</td><td className={TD}>28.0</td><td className={TD}>transmission</td></tr>
            <tr><td className={TD_MONO}>lf_per_wall_cell_db</td><td className={TD}>9.0</td><td className={TD}>transmission</td></tr>
            <tr><td className={TD_MONO}>min_snr_db</td><td className={TD}>6.0</td><td className={TD}>transmission</td></tr>
            <tr><td className={TD_MONO}>cell_size_m</td><td className={TD}>0.22 m</td><td className={TD}>transmission</td></tr>
            <tr><td className={TD_MONO}>beacon_interval</td><td className={TD}>4 ticks</td><td className={TD}>mesh</td></tr>
            <tr><td className={TD_MONO}>merge_interval</td><td className={TD}>10 ticks</td><td className={TD}>mesh</td></tr>
            <tr><td className={TD_MONO}>token_interval</td><td className={TD}>17 ticks</td><td className={TD}>mesh</td></tr>
            <tr><td className={TD_MONO}>token_ttl_ticks</td><td className={TD}>48 ticks</td><td className={TD}>mesh</td></tr>
            <tr><td className={TD_MONO}>perception_radius</td><td className={TD}>5 cells</td><td className={TD}>application</td></tr>
          </tbody>
        </table>
      </section>

      <section>
        <h2 className={H2}>Entry Points</h2>
        <ul className={LIST}>
          <li><code className={CODE}>python run_sim.py</code> — interactive matplotlib demo (single-process kernel)</li>
          <li><code className={CODE}>python -m swarm_sim.sim_kernel_udp</code> — multi-process UDP mesh backend</li>
          <li><code className={CODE}>python -m swarm_sim.export_sim &lt;floorplan&gt; -o &lt;bundle&gt;</code> — export bundle for web</li>
          <li><code className={CODE}>npm run dev</code> — local web UI</li>
        </ul>
      </section>
    </div>
  );
}
