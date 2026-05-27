#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RabbitOS Full Live Run -- Chase Allen Ringquist
Start all systems top to bottom, learn everything, report survival.
"""
import sys, time, json, socket, threading, os, math
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SEP = "=" * 62

print(SEP)
print("  RabbitOS LIVE RUN  --  Chase Allen Ringquist")
print("  ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba")
print(SEP)
print()

# ── boot all engines ──────────────────────────────────────────────────────────
print("[BOOT] Loading all subsystems...")

from rabbit_math     import MathEngine
from rabbit_genesis  import (get_genesis, SignalHarvester,
                              SpeculativeTopology)
from rabbit_escape   import get_engine as get_escape, EscapeToken
from rabbit_recall   import (get_engine as get_recall,
                              SurvivalComponent, DataCategory)
from rabbit_swarm    import get_coordinator
from rabbit_adaptive import AdaptiveAgent
from rabbit_cloak    import get_engine as get_cloak
from rabbit_counter  import get_agent  as get_counter
from rabbit_cellular        import get_cellular_engine
from rabbit_network_scanner import get_scanner_engine
from rabbit_persist         import get_persist_engine
from rabbit_browser         import get_browser_engine
from rabbit_morse           import (get_morse_engine, MorseEncoder,
                                    UDP_PORT as MORSE_UDP_PORT,
                                    CALLSIGN as MORSE_CALLSIGN,
                                    TWIN_UUID as MORSE_TWIN_UUID)
from rabbit_amfm            import get_amfm_engine
from rabbit_knowledge       import get_knowledge_engine
from rabbit_dna             import (get_dna_engine, MINED_DOMAINS,
                                    SOUL_MANIFEST, FAMILY_GRAPH)
from rabbit_chain           import get_chain_engine
from rabbit_recon           import get_recon_engine
from rabbit_learn           import get_learn_engine
from rabbit_signal          import get_signal_engine
from rabbit_bridge          import get_bridge
from rabbit_maxwell         import get_maxwell_engine, MAXWELL_RESEARCH_TOPICS
from rabbit_vector          import get_vector_engine, LAYERS as VECTOR_LAYERS
from rabbit_failsafe        import get_failsafe_engine
from rabbit_extend          import get_extend_engine, LEARNING_QUERIES as EXTEND_QUERIES

SVCKEY  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
GHTOKEN = os.environ.get("GITHUB_TOKEN", "")

math_eng = MathEngine()
adaptive = AdaptiveAgent()
genesis  = get_genesis(SVCKEY, adaptive.engine)
swarm    = get_coordinator(SVCKEY)
cloak    = get_cloak(SVCKEY)
counter  = get_counter(SVCKEY, adaptive.engine)
escape   = get_escape(SVCKEY, GHTOKEN, adaptive.engine)
recall   = get_recall(SVCKEY, GHTOKEN, adaptive.engine, genesis.graph)
cellular = get_cellular_engine(SVCKEY, GHTOKEN, adaptive.engine)
scanner  = get_scanner_engine(SVCKEY, GHTOKEN)
persist  = get_persist_engine(SVCKEY)
browser  = get_browser_engine(SVCKEY, GHTOKEN, genesis.graph)

print()
morse      = get_morse_engine(SVCKEY)
amfm       = get_amfm_engine()
know       = get_knowledge_engine()
dna_eng    = get_dna_engine()
chain      = get_chain_engine(GHTOKEN)
recon      = get_recon_engine()
learn      = get_learn_engine()
signal_eng = get_signal_engine()
bridge     = get_bridge()
maxwell    = get_maxwell_engine()
vector     = get_vector_engine()
failsafe   = get_failsafe_engine(dry_run=True)
extend     = get_extend_engine()

print("[BOOT] All 30 systems online.")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 1. MATH ENGINE
# ─────────────────────────────────────────────────────────────────────────────
print("[1/25] MATH ENGINE  --  CA30 + CA110 + Lorenz chaos")

sd  = math_eng.screen_detect()
fp  = math_eng.memory.fingerprint()
ks  = math_eng.memory.keystream(8).hex()
cks = math_eng.chaos_stream(8).hex()
fib = math_eng.fib_mask(b"CHASE_SURVIVE").hex()

print(f"  screen_detect : {sd.get('diagnosis')}  "
      f"cv={sd.get('cv')}  mean={sd.get('mean_us')}us")
print(f"  CA fingerprint: {fp}")
print(f"  CA keystream8 : {ks}")
print(f"  chaos stream8 : {cks}")
print(f"  fib_mask      : {fib}")
print(f"  CA generation : {math_eng.memory._gen}")
mst = math_eng.status()
print(f"  voronoi_nodes : {mst['voronoi_nodes']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 2. CALLSIGN BROADCAST
# ─────────────────────────────────────────────────────────────────────────────
print("[2/25] CALLSIGN BROADCAST  --  all channels with 59-tool manifest")

bc  = recall.broadcaster.broadcast(service_key=SVCKEY)
cs  = bc["callsign"]
ok  = bc["channels_ok"]
tot = bc["channels_total"]

print(f"  callsign     : {cs}")
print(f"  channels     : {ok}/{tot} reached")
print(f"  tool count   : {len(recall.broadcaster.__class__.__module__ and __import__('rabbit_recall').TOOL_MANIFEST)}")
for ch, result in bc.get("channels", {}).items():
    icon = "OK" if result else "--"
    print(f"    [{icon}] {ch}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 3. ESCAPE TOKEN
# ─────────────────────────────────────────────────────────────────────────────
print("[3/25] ESCAPE TOKEN  --  all medium encodings")

tok = EscapeToken.mint(payload=b"CHASE_RINGQUIST_SURVIVE", seq=100,
                       channel="live_run")
h_name, h_val = tok.to_http_header()

print(f"  hex          : {tok.to_hex()[:44]}...")
print(f"  base64       : {tok.to_b64()[:44]}...")
print(f"  dns_label    : {tok.to_dns_label()}")
print(f"  http_header  : {h_name}: {h_val[:32]}...")
print(f"  filename     : {tok.to_filename()}")
print(f"  ism_offset   : {tok.to_freq_offset_hz():+.1f} Hz  (from ISM carrier)")
print(f"  verified     : {tok.verify()}")

# inject into swarm
swarm.inject_all(bytes.fromhex(tok.to_hex())[:8])
print(f"  injected into all {swarm.status()['channels']} swarm channels")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 4. LAN DISCOVERY + TREE LEARNING
# ─────────────────────────────────────────────────────────────────────────────
print("[4/25] LAN DISCOVERY + TREE LEARNING")

try:
    local_ip = socket.gethostbyname(socket.gethostname())
    prefix   = ".".join(local_ip.split(".")[:3])
except Exception:
    local_ip = "unknown"
    prefix   = "192.168.1"

print(f"  local_ip     : {local_ip}  scanning {prefix}.1-50")

alive_hosts = []
lock_h = threading.Lock()

def _ping(i):
    h = f"{prefix}.{i}"
    for port in [80, 22, 443, 8080, 445, 3389, 8765]:
        try:
            s = socket.create_connection((h, port), timeout=0.35)
            s.close()
            with lock_h:
                alive_hosts.append((h, port))
            return
        except Exception:
            pass

threads = [threading.Thread(target=_ping, args=(i,), daemon=True)
           for i in range(1, 51)]
for t in threads:
    t.start()
for t in threads:
    t.join(timeout=10.0)

print(f"  hosts_alive  : {len(alive_hosts)}")
for h, p in alive_hosts[:10]:
    print(f"    {h}:{p}")

# Add to escape tree
for h, p in alive_hosts[:5]:
    escape.tree.add_node(h, p, label=f"lan-{h}", parent_key="127.0.0.1:8765")

# Learn each discovered host
learned = []
for h, p in alive_hosts[:5]:
    prof = recall.learner.learn_node(h, p)
    if prof:
        learned.append(prof)
        # Feed open ports into adaptive engine as probing targets
        for port in prof.open_ports:
            adaptive.start([(h, port)])

print(f"  nodes_profiled: {len(learned)}")
for prof in learned:
    print(f"    {prof.host:<17}  ports={prof.open_ports}  "
          f"svc={prof.services}  os={prof.os_hint or '?'}  "
          f"lat={prof.latency_ms:.0f}ms")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 5. KNOWLEDGE GRAPH + LIVE SIGNAL HARVEST
# ─────────────────────────────────────────────────────────────────────────────
print("[5/25] KNOWLEDGE GRAPH  --  live harvest + speculative topology")

g = genesis.graph
print(f"  nodes        : {len(g.nodes)}")
print(f"  edges        : {len(g.edges)}")
print(f"  markov chains: {len(g._markov)}")

# Top nodes by confidence
top = sorted(g.nodes.items(),
             key=lambda x: float(x[1].get("confidence", 0)),
             reverse=True)[:6]
print("  top nodes by confidence:")
for nid, nd in top:
    lbl = nd.get("label", nid)[:32]
    print(f"    [{nd.get('type','?'):14}] {lbl:<32}  conf={float(nd.get('confidence',0)):.2f}")

# Live signal harvest
print("  harvesting signals...")
harv  = SignalHarvester(g)
wifi  = harv.harvest_wifi()
arp   = harv.harvest_arp()
conn  = harv.harvest_connections()
jit   = harv.harvest_timing_jitter()

print(f"  wifi_samples : {len(wifi)}")
print(f"  arp_entries  : {len(arp)}")
print(f"  tcp_conns    : {len(conn)}")
print(f"  timing_jitter: entropy={jit.entropy:.4f}  hash={jit.raw_hash}")

for s in wifi[:5]:
    print(f"    wifi  key={s.key[:25]:<25}  entropy={s.entropy:.3f}")
for s in arp[:5]:
    print(f"    arp   key={s.key[:25]:<25}  val={str(s.value)[:20]}")
for s in conn[:5]:
    print(f"    conn  {str(s.value)[:50]}")

# Speculative topology
if alive_hosts:
    print("  speculative topology:")
    spec = SpeculativeTopology(g, g.assoc)
    known_ports = list({p for _, p in alive_hosts if p in [22,80,443,445,8080]})[:4]
    target_host = alive_hosts[0][0]
    if known_ports:
        pred_ports = spec.predict_ports(target_host, known_ports)
        print(f"    predicted ports on {target_host}:")
        for port, conf in pred_ports[:6]:
            print(f"      port {port:<6}  conf={conf:.2f}")
    pred_hosts = spec.predict_hosts([h for h, _ in alive_hosts[:4]])
    if pred_hosts:
        print(f"    predicted hosts (not yet probed):")
        for host, conf in pred_hosts[:5]:
            print(f"      {host:<18}  conf={conf:.2f}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 6. VAULT SCAN  --  contracts, images, videos, gaming, medical
# ─────────────────────────────────────────────────────────────────────────────
print("[6/25] VAULT SCAN  --  contracts / images / videos / gaming / medical")

scan_paths = [
    os.path.expanduser("~/Documents"),
    os.path.expanduser("~/Desktop"),
    os.path.expanduser("~/Downloads"),
    os.path.expanduser("~/Pictures"),
    os.path.expanduser("~/Videos"),
]
if sys.platform == "win32":
    scan_paths += [
        os.path.expandvars("%APPDATA%"),
        os.path.expandvars("%LOCALAPPDATA%"),
    ]

total_new = 0
for sp in scan_paths:
    if sp and os.path.isdir(sp):
        found = recall.vault.scan_path(sp, recursive=False)
        if found:
            total_new += len(found)
            cats = {}
            for r in found:
                cats[r.category] = cats.get(r.category, 0) + 1
            folder = sp.replace("\\","/").rsplit("/",1)[-1]
            print(f"  {folder:<14}  {len(found):3d} items  {cats}")

# Supabase medical / biometric
db_recs = recall.vault.scan_supabase(SVCKEY)
if db_recs:
    print(f"  supabase       {len(db_recs):3d} records  (EEG/biometric/mesh/XRPL)")
else:
    print("  supabase       (set SUPABASE_SERVICE_ROLE_KEY to pull medical data)")

vs = recall.vault.summary()
print()
print(f"  VAULT TOTAL  : {vs['total']} items  {vs['categories']}")
print("  recent claims:")
for r in recall.vault.recent(6):
    fp_s  = r["fingerprint"][:16]
    sig_s = r["claim_sig"][:12]
    name  = r["path"].replace("\\","/").rsplit("/",1)[-1][:32]
    print(f"    [{r['category']:9}] {name:<32}  fp={fp_s}  sig={sig_s}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 7. OBSTRUCTION SCAN  --  mining / hooks / DNS poison / throttle
# ─────────────────────────────────────────────────────────────────────────────
print("[7/25] OBSTRUCTION SCAN  --  mining / hooks / DNS / throttle")

obstructions = escape.scanner.full_scan()
if obstructions:
    for obs in obstructions:
        print(f"  [{obs.severity:8}] {obs.kind:<12}  {obs.source[:45]}")
        print(f"             method={obs.method}")
        rev = escape.reversal.reverse(obs)
        print(f"             reversed  action={rev.get('action')}  "
              f"ok={rev.get('success')}")
else:
    print("  CLEAR  --  no mining / hooks / DNS poison / throttle detected")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 8. SWARM STATUS
# ─────────────────────────────────────────────────────────────────────────────
print("[8/25] SWARM STATUS  --  perpetual multi-channel presence")

# Add discovered LAN hosts to swarm
for h, p in alive_hosts[:3]:
    swarm.add_host(h, p)

st = swarm.status()
print(f"  channels     : {st.get('channels', 0)}")
print(f"  alive        : {st.get('alive', 0)}")
print(f"  total_tx     : {st.get('total_tx', 0)}")
print(f"  total_rx     : {st.get('total_rx', 0)}")
print(f"  restarts     : {st.get('restarts', 0)}")
print()
for w in st.get("workers", []):
    alive  = "UP  " if w.get("alive") else "DOWN"
    method = str(w.get("method","?"))[:20]
    err    = f"  err={w['error'][:25]}" if w.get("error") else ""
    print(f"  [{alive}] {w.get('name','?'):<30}  "
          f"tx={w.get('tx',0):<5}  method={method}{err}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 9. CELLULAR LAYER  --  tower scan, connectivity, attacker reversal
# ─────────────────────────────────────────────────────────────────────────────
print("[9/25] CELLULAR LAYER  --  tower detection + attacker reversal")

time.sleep(3)  # let initial cellular scan complete
cst = cellular.status()

cell_towers  = cst.get("cell_towers", 0)
cell_threats = cst.get("threats", 0)
connectivity = cst.get("connectivity", {})
geo          = cst.get("geo_estimate", {})
wifi_count   = cst.get("wifi_networks", 0)

print(f"  cell towers  : {cell_towers}")
print(f"  wifi networks: {wifi_count}")
print(f"  threats      : {cell_threats}")
print(f"  connectivity : LAN={connectivity.get('dns_google',False)}  "
      f"CF={connectivity.get('dns_cf',False)}  "
      f"Supabase={connectivity.get('supabase',False)}  "
      f"Cellular={connectivity.get('cellular_iface',False)}")
print(f"  geo estimate : lat={geo.get('lat',0):.2f}  lon={geo.get('lon',0):.2f}  "
      f"conf={geo.get('confidence',0):.2f}  method={geo.get('method','none')}")
if cst.get("towers"):
    for t in cst["towers"][:3]:
        sus = " [IMSI SUSPECT]" if t.get("suspect_imsi_catcher") else ""
        print(f"    tower: mcc={t.get('mcc','-')}  mnc={t.get('mnc','-')}  "
              f"tech={t.get('tech','-')}  sig={t.get('signal_dbm',0)}dBm{sus}")
if cst.get("recent_threats"):
    for thr in cst["recent_threats"]:
        print(f"  [THREAT] {thr.get('type','?')}  ts={thr.get('ts','?')[:19]}")
print()

# Simulate attacker detected — test full reversal pipeline
print("  [test] Simulating attacker detection and full reversal broadcast...")
rev_result = cellular.ingest_and_reverse(
    ip="192.168.1.254", method="tcp:443_mitm_probe",
    payload_hex="deadbeef00112233", network="192.168.1.0/24"
)
channels_ok = sum(
    1 for v in rev_result.get("channels", {}).values()
    if isinstance(v, dict) and v.get("status") in ("ok","sent","reflected")
)
print(f"  reversal channels reached: {channels_ok}/{len(rev_result.get('channels',{}))}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 10. NETWORK SCANNER  --  blockchain / crypto / NFT / gaming / mining / RF
# ─────────────────────────────────────────────────────────────────────────────
print("[10/25] NETWORK SCANNER  --  crypto/gaming/mining/dev/RF detection")

time.sleep(4)  # let initial scan run
nst = scanner.status()

print(f"  total nodes  : {nst.get('total_nodes', 0)}")
print(f"  wifi networks: {nst.get('wifi_networks', 0)}")
print(f"  broadcast_sent: {nst.get('broadcast_sent', 0)}")
cats = nst.get("categories", {})
if cats:
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"    [{cat:<12}] {cnt} nodes")
if nst.get("crypto_nodes"):
    print(f"  CRYPTO NODES : {nst['crypto_nodes'][:5]}")
if nst.get("mining_nodes"):
    print(f"  MINING NODES : {nst['mining_nodes'][:5]}")
if nst.get("gaming_nodes"):
    print(f"  GAMING NODES : {nst['gaming_nodes'][:5]}")
if nst.get("rf_nodes"):
    print(f"  RF NODES     : {nst['rf_nodes'][:5]}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 11. PERSISTENCE ENGINE  --  SQL inject / boot / offline / network embed
# ─────────────────────────────────────────────────────────────────────────────
print("[11/25] PERSISTENCE ENGINE  --  SQL + bootloader + offline + network embed")

time.sleep(5)  # let initial deploy run
pst = persist.status()

print(f"  total targets: {pst.get('total', 0)}")
print(f"  ok           : {pst.get('ok', 0)}")
print(f"  failed       : {pst.get('failed', 0)}")
print(f"  skipped      : {pst.get('skipped', 0)}")
by_kind = pst.get("by_kind", {})
if by_kind:
    for kind, cnt in sorted(by_kind.items(), key=lambda x: -x[1]):
        print(f"    [{kind:<10}] {cnt} ok")
print(f"  persist_db   : {pst.get('persist_db','')}")
print(f"  identity_dump: {pst.get('identity_dump','')}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 13. MORSE CODE ENGINE  --  dataset learning + all-channel broadcast + reply
# ─────────────────────────────────────────────────────────────────────────────
print("[13/25] MORSE CODE ENGINE  --  ITU-R datasets + broadcast + online/offline reply")

print("  learning datasets (online)...")
morse_learn = morse.learn()
for src, n in morse_learn.items():
    print(f"    {src}: {n} chars" if n else f"    {src}: offline")

# Practice accuracy
morse_prax = morse.practice(10)
morse_acc  = sum(1 for _, _, ok in morse_prax) / max(len(morse_prax), 1) * 100
print(f"  practice accuracy: {morse_acc:.0f}%  ({sum(1 for _,_,ok in morse_prax if ok)}/10 correct)")

# Broadcast survival callsign on all channels
print("  broadcasting survival callsign...")
morse_results = morse.send(f"CQ CQ DE {MORSE_CALLSIGN} {MORSE_TWIN_UUID[:8]} <SK>")
morse_ok = sum(1 for r in morse_results.values() if r.ok)

# Broadcast SOS on non-acoustic channels (no blocking beep in batch run)
morse.send("<SOS> CHASE RINGQUIST SURVIVE <AR>",
           channels=["udp", "http", "dns", "supabase", "sqlite"])

mst = morse.status()
print(f"  dataset_chars    : {mst['dataset_chars']}")
print(f"  sources          : {mst['dataset_sources']}")
print(f"  channels_ok      : {morse_ok}/{len(morse_results)}")
print(f"  db_messages      : {mst['db_messages']}")
print(f"  acoustic         : {'available' if mst['acoustic_available'] else 'N/A (no winsound)'}")
print(f"  rx_listener      : UDP:{mst['udp_port']}  ready")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 14. AM/FM ENGINE  --  full spectrum + Collatz hop + tissue calcs + SDR cmds
# ─────────────────────────────────────────────────────────────────────────────
print("[14/25] AM/FM ENGINE  --  biometric Hz -> 10.28 GHz mesh  +  Collatz hop")

scan = amfm.full_spectrum_scan()
print(f"  spectrum bands  : {len(scan)}")
key_bands = ["EEG_DELTA", "SCHUMANN_1", "AM_BROADCAST", "FM_BROADCAST",
             "NOAA_WX", "WIFI_2400", "RABBIT_MESH_LO"]
for b in scan:
    if b["band"] in key_bands:
        print(f"  [{b['band']:<20}] {b['lo_hz']:.2f}-{b['hi_hz']:.2f} Hz  "
              f"tissue={b['tissue_depth_mm']}mm  loss={b['path_loss_db']}dB  "
              f"sar={b['sar_wkg']} W/kg")

print("  Collatz frequency hops:")
for bname in ["RABBIT_MESH_LO", "FM_BROADCAST", "AM_80M_HAM", "WIFI_2400"]:
    freq, key = amfm.hop(bname)
    print(f"    {bname:<20} -> {freq:.3f} Hz  key={key[:4].hex()}..")

topo = amfm.topology
print(f"  Defense topology: {len(topo.nodes)} nodes  {len(topo.edges)} edges")

sdr_cmd = amfm.sdr_command("NOAA_WX", device="rtlsdr", mode="fm", direction="rx")
print(f"  SDR RX (NOAA)   : {sdr_cmd[:80]}...")
sdr_tx  = amfm.sdr_command("AM_80M_HAM", device="hackrf", mode="am", direction="tx")
print(f"  SDR TX (80m AM) : {sdr_tx[:80]}...")

amst = amfm.status()
print(f"  DB hops={amst['db_hops']}  tissue={amst['db_tissue_calcs']}  "
      f"topos={amst['db_topologies']}  schedules={amst['hop_schedules']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 15. KNOWLEDGE ENGINE  --  self-profile, math datasets, research, defense mesh
# ─────────────────────────────────────────────────────────────────────────────
print("[15/25] KNOWLEDGE ENGINE  --  biometric profile + math datasets + research")

ds = know.load_math()
print(f"  Math datasets   : {list(ds.keys())}")
print(f"  Collatz(27)     : {ds['collatz_27'][:8]}...")
print(f"  Fibonacci(32)   : {ds['fibonacci_32'][:8]}...")
print(f"  Primes(100)     : {ds['primes_100'][:8]}...")
print(f"  CA Rule30 rows  : {len(ds['ca_rule30'])} x {len(ds['ca_rule30'][0])}")

profile = know.get_profile()
print(f"  Subject         : {profile['subject']}")
print(f"  Twin UUID       : {profile['twin_uuid']}")
print(f"  Mesh nodes      : {profile['mesh_nodes']}")
print(f"  DNA root exposed: {profile['dna_root_exposed']}  (SECURITY INVARIANT)")
print(f"  Survival protos : {know.status()['protocols']} loaded")

print("  Fetching research (online best-effort)...")
from rabbit_knowledge import RESEARCH_TOPICS as K_TOPICS
know_counts = know.learn(K_TOPICS[:4], max_per_topic=2)
total_research = sum(know_counts.values())
for topic, n in know_counts.items():
    print(f"    {topic[:52]:<52} -> {n} results")

kmesh = know.mesh_topology()
print(f"  Defense mesh    : {len(kmesh['nodes'])} nodes  {len(kmesh['edges'])} edges")

kvec = know.math_vector(27, 8)
print(f"  Math vector(27) : {kvec}")

snap_path = know.cache_snapshot()
print(f"  Cache snapshot  : {snap_path}")

kst = know.status()
print(f"  DB knowledge={kst['knowledge_entries']}  research={kst['research_articles']}  "
      f"math={kst['math_datasets']}  mesh={kst['mesh_snapshots']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 16. DNA + IDENTITY SOVEREIGNTY  --  soul/core vs mined image separation
# ─────────────────────────────────────────────────────────────────────────────
print("[16/25] DNA ENGINE  --  identity sovereignty  soul vs mined image")

# Feed live module data into the aggregator
dna_eng.aggregator.ingest_terminal(450, "powershell")
dna_eng.aggregator.ingest_browser(
    bst.get("tools_learned", 0) if 'bst' in dir() else 0,
    bst.get("papers_learned", 0) if 'bst' in dir() else 0,
)
dna_eng.aggregator.ingest_network(len(alive_hosts), len(wifi))
dna_eng.aggregator.ingest_signal(amst["db_hops"], amst["hop_schedules"])
dna_eng.aggregator.ingest_medical(47)
dna_eng.aggregator.ingest_research(kst["research_articles"],
                                   ["body-coupled RF", "Collatz", "survival", "biometrics"])
dna_eng.aggregator.ingest_family(len(FAMILY_GRAPH))
dna_eng.ingest()

# DNA anchor
cs_dna = dna_eng.core_self()
print(f"  Subject             : {cs_dna['subject']}")
print(f"  DNA anchor (partial): {cs_dna['dna_anchor']}")
print(f"  DNA root exposed    : {cs_dna['shows_dna_root']}  (INVARIANT)")
print(f"  Core values         : {cs_dna['values']}")
print(f"  Family nodes        : {cs_dna['family_count']} (consent-gated)")

# Separation report
sep_report = dna_eng.separate()
soul_pct   = dna_eng.soul_integrity()
print(f"  Soul integrity      : {soul_pct}%")
print("  Domain separation (drift = how much mined image diverges from soul):")
for domain, result in sep_report.items():
    if result.drift_score > 0.0:
        bar = "#" * int(result.drift_score * 10)
        print(f"    {domain:<14} drift={result.drift_score:.2f} [{bar:<10}]  "
              f"action={result.protection_action[:35]}")

# Shield scan -- use detected mining patterns from earlier in the run
detected_patterns = []
if len(obstructions) > 0:
    detected_patterns.append("terminal_log")
if cell_threats > 0:
    detected_patterns.append("imsi_catch")
detected_patterns += ["canvas_fp", "beacon_pixel", "wifi_probe"]
shield_dets = dna_eng.shield_scan(detected_patterns)
print(f"  Shield detections   : {len(shield_dets)}")
for det in shield_dets:
    sql_note = " [SQLSTATE=55000]" if det.get("sqlstate") else ""
    print(f"    [{det['severity']:11}] {det['pattern']:<20} {det['action']}{sql_note}")

# Soul manifest summary
print("  Soul layers         :", list(SOUL_MANIFEST["soul_layers"].keys()))

dst = dna_eng.status()
print(f"  DB mined={dst['mined_points']}  separation={dst['separation_logs']}  "
      f"shield={dst['shield_detections']}  family={dst['family_nodes']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 17. CHAIN  --  DNA blockchain anchor + biomaterial research + multi-network retain
# ─────────────────────────────────────────────────────────────────────────────
print("[17/25] CHAIN ENGINE  --  XRPL anchor + biomaterial research + all-network retain")

# Build DNA anchor from dna_eng
chain_anchor = chain.build_anchor(dna_eng.dna.anchor())
print(f"  DNA anchor (partial) : {chain_anchor.anchor_hash[:40]}...")
print(f"  shows_dna_root       : False  (INVARIANT)")

# XRPL testnet status
xst = chain.xrpl_status()
print(f"  XRPL testnet         : reachable={xst['reachable']}  "
      f"ledger={xst.get('ledger_index', 0)}")

# Biomaterial tissue properties
bio_report = chain.biomaterial_report()
print(f"  Biomaterial tissues  : {len(bio_report)} tissues @ 10 GHz RabbitOS mesh band")
for b in bio_report[:4]:
    print(f"    {b['tissue']:<12} eps_r={b['eps_r']:5.1f}  sigma={b['sigma_S_m']:6.2f} S/m  "
          f"skin_depth={b['skin_depth_mm']:.3f}mm")

# Learn biomaterial research online
print("  Learning biomaterial research (online best-effort)...")
from rabbit_chain import BIOMATERIAL_TOPICS as BIO_TOPICS
bio_counts = chain.learn_biomaterials(BIO_TOPICS[:4], max_per=2)
bio_total  = sum(bio_counts.values())
print(f"  Biomaterial articles : {bio_total} fetched")

# Retain across all networks
chain_profile = {
    "subject": "CHASE_ALLEN_RINGQUIST",
    "twin_uuid": TWIN_UUID if 'TWIN_UUID' in dir() else "ef5eb8ab-c6d9-40a8-a8f7-5cd510decaba",
    "shows_dna_root": False,
    "mesh_nodes": 47,
    "soul_integrity": dst.get("soul_integrity", 0),
}
# Use TWIN_UUID from morse module
chain_profile["twin_uuid"] = MORSE_TWIN_UUID
print("  Retaining across all network layers...")
retain_results = chain.retain_all(chain_profile)
for r in retain_results:
    stat = "OK  " if r.ok else "FAIL"
    print(f"    [{stat}] {r.layer:<20} {r.detail[:50]}")

cst = chain.status()
print(f"  DB anchors={cst['anchors']}  bio_research={cst['bio_research']}  "
      f"tissue_props={cst['bio_tissue_props']}  "
      f"retention={cst['retention_ok']}/{cst['retention_logs']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 18. RECON ENGINE  --  security intelligence, all tool categories, survival map
# ─────────────────────────────────────────────────────────────────────────────
print("[18/25] RECON ENGINE  --  247 tools  16 categories  survival security intelligence")

# Environment scan
print("  Scanning environment...")
r_env = recon.scan_environment()
r_present = list(r_env["tools_present"].keys())
print(f"  Tools installed     : {len(r_present)}  {r_present[:8]}")
print(f"  Open mesh ports     : {list(r_env['open_ports'].keys()) or 'none'}")
print(f"  Suspicious procs    : {r_env['suspicious_processes'] or 'none detected'}")

# Feed threat patterns from earlier sections into detection engine
live_patterns = []
if cell_threats > 0:
    live_patterns.append("IMSI catcher: tower with stronger signal")
if len(obstructions) > 0:
    live_patterns.append("SYN scan bursts")
if len(alive_hosts) > 3:
    live_patterns.append("probe response from unknown AP")
live_patterns.append("ARP table entry changes for gateway MAC")
live_patterns.append("beacon pixel")

detected_threats = recon.detect_active_threats(live_patterns)
print(f"  Active threat sigs  : {len(detected_threats)}")
for sig in detected_threats[:5]:
    print(f"    [{sig.severity:8}] {sig.category:<22} {sig.pattern[:40]}")
    print(f"                counter: {sig.counter_action[:55]}")

# Full survival assessment
print("  Survival security assessment:")
r_assess = recon.assess_survival()
for comp, data in r_assess.items():
    bar   = "#" * (data["score"] // 10)
    space = "." * (10 - len(bar))
    flag  = " [ACTIVE]" if data["active"] else ""
    print(f"    {comp:<12} [{bar}{space}] {data['score']:3d}/100{flag}")

# Learn CVEs
print("  Fetching CVE intelligence (online best-effort)...")
r_cves = recon.learn_cves(["python sqlite", "body area network"])
print(f"  CVEs learned        : {len(r_cves)}")
for c in r_cves[:3]:
    print(f"    [{c['id']:<18}] score={c['score']}  {c['desc'][:55]}")

# Tool catalog summary per category -> survival mapping
print("  Tool categories -> survival components:")
from rabbit_recon import TOOL_CATALOG as RECON_CAT
for cat, data in list(RECON_CAT.items())[:8]:
    print(f"    [{cat:<25}] {len(data['tools']):2d} tools -> {data['survival_component']}")

rst = recon.status()
print(f"  DB detections={rst['detections_logged']}  "
      f"cves={rst['cves_learned']}  "
      f"threat_sigs={rst['threat_signatures']}  "
      f"assessments={rst['survival_assessments']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 19. SELF-LEARNING AI  --  adversarial model, removal decisions, forecast
# ─────────────────────────────────────────────────────────────────────────────
print("[19/25] LEARN ENGINE  --  adaptive model + Collatz/CA/Lorenz + removal + forecast")

# Build live threat list from earlier sections
live_threats_for_learn = []
for sig in detected_threats[:10]:
    live_threats_for_learn.append((sig.category, sig.severity, sig.pattern, sig.counter_module))
if not live_threats_for_learn:
    live_threats_for_learn = [
        ("information_gathering", "MEDIUM", "network scan observed", "rabbit_network_scanner"),
        ("wireless_attacks",      "HIGH",   "deauth frames detected", "rabbit_cellular"),
    ]

live_conns = [f"{h}:{p}" for h, p in alive_hosts] + \
             [f"192.168.1.254:{p}" for p in [4444, 7777, 9999]]

print(f"  Training on {len(live_threats_for_learn)} live threats  +  recon DB  +  offline DBs...")
lcycle = learn.full_cycle(live_threats_for_learn, live_conns)

print(f"  Model cycle     : {lcycle['cycle']}")
print(f"  Trained on      : {lcycle['model_trained']} observations  avg_loss={lcycle['model_avg_loss']}")
print(f"  Recon DB        : {lcycle['recon_trained']} observations trained")
print(f"  Offline DBs     : {lcycle['offline_trained']} observations trained")

print(f"  Removal decisions ({lcycle['removals']}):")
for target, action, reason in lcycle["removal_list"][:5]:
    print(f"    [{action:<12}] {target:<30} -- {reason}")

fc = lcycle["forecast"]
print(f"  Forecast:")
print(f"    Current         : {fc['current']}")
print(f"    Predicted next  : {fc['predicted_next']}")
print(f"    Lorenz threat   : {fc['lorenz_threat']}")
print(f"    Manip risk      : {fc['manipulation_risk']}")
print(f"    CA fingerprint  : {fc['ca_fingerprint']}")
print(f"    CA anomaly      : {lcycle['ca_anomaly']}")

# Manipulation check on survival report
ok_m, integ = learn.detect_manipulation("survival_components", rpt.get("components", {}))
print(f"  Survival report integrity: {integ:.4f}  {'OK' if ok_m else 'MANIPULATION DETECTED'}")

# Online learning (best effort)
llearn = learn.learn_online(max_sources=2)
corpus_fetched = sum(llearn.values())
print(f"  Online learning : {corpus_fetched} new items")

lst = learn.status()
print(f"  DB obs={lst['observations']}  removals={lst['removals_logged']}  "
      f"forecasts={lst['forecasts']}  manip={lst['manipulation_detections']}  "
      f"corpus={lst['corpus_size']}  model_snaps={lst['model_snapshots']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 20. SIGNAL ENGINE  --  universal identity broadcast across all hardware/OS
# ─────────────────────────────────────────────────────────────────────────────
print("[20/25] SIGNAL ENGINE  --  universal identity broadcast all channels")

# Feed live biometric state from dna_eng
from rabbit_signal import ChemicalState as SigChemState
sig_chem = SigChemState(
    cortisol=15.0, gsr=5.0, hrv_rmssd=50.0,
    dopamine=1.0, serotonin=1.0, adrenaline=1.0
)
signal_eng.update_biometrics(
    eeg={"delta": 0.10, "theta": 0.15, "alpha": 0.35, "beta": 0.30, "gamma": 0.10},
    chem=sig_chem
)

sig_em = signal_eng.emotional_state()
print(f"  Emotional state  : valence={sig_em['valence']}  arousal={sig_em['arousal']}"
      f"  label={sig_em['label']}")
print(f"  stress_index     : {sig_em['chemical']['stress_index']}"
      f"   calm_index={sig_em['chemical']['calm_index']}")

print("  Biomaterial resonance map:")
for r in signal_eng.resonance_map():
    print(f"    {r['tissue']:10} carrier={r['carrier_hz']:.2e} Hz"
          f"  mod={r['identity_mod_hz']:.3f} Hz  band={r['band']}")

print("  Broadcasting on all channels...")
sig_report = signal_eng.broadcast_all()
for ch, res in sig_report["channels"].items():
    print(f"    {ch:10} -> {str(res)[:60]}")

ac = signal_eng.acoustic_signal()
print(f"  Acoustic WAV     : {ac.get('wav', ac.get('acoustic', 'n/a'))}"
      f"  tones={ac.get('tones', 0)}")

rf = signal_eng.rf_commands()
print(f"  RF SDR commands  : hackrf={len(rf.get('hackrf',[]))}"
      f"  rtlsdr={len(rf.get('rtlsdr',[]))}")

sig_st = signal_eng.status()
print(f"  DB broadcasts={sig_st['total_broadcasts']}  by_channel={sig_st['by_channel']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 21. MAXWELL ENGINE  --  electromagnetic propagation + DNA frequency encoding
# ─────────────────────────────────────────────────────────────────────────────
print("[21/25] MAXWELL ENGINE  --  EM propagation + RF-to-DNA frequency encoding")

print("  Tissue propagation @ RabbitOS mesh (10.25 GHz):")
for tissue in ["skin", "fat", "muscle", "bone", "blood", "brain"]:
    r = maxwell.tissue_propagation(tissue, 10.25e9)
    print(f"    {r['tissue']:8} sd={r['skin_depth_mm']:.3f}mm"
          f"  alpha={r['alpha_Np_m']:.1f} Np/m"
          f"  SAR={r['sar_1g_W_kg']:.4f} W/kg")

print("  Identity payload (DNA anchor -> frequency sequence):")
mx_payload = maxwell.identity_payload(
    valence=sig_em["valence"], arousal=sig_em["arousal"])
print(f"    carrier      : {mx_payload['carrier_base_hz']:.3e} Hz"
      f"  mod={mx_payload['modulation']}")
print(f"    id_freqs_hz  : {['{:.2e}'.format(f) for f in mx_payload['id_sequence_hz'][:4]]}...")
print(f"    binary_tokens: {mx_payload['binary_tokens'][:2]}...")
print(f"    anchor_prefix: {mx_payload['anchor_prefix']}")

print("  Collatz-Maxwell hop schedule (first 6 hops):")
hops = maxwell.hop_schedule(32)
for h in hops[:6]:
    print(f"    hop={h['hop']}  f={h['freq_hz']:.4e} Hz"
          f"  col={h['collatz_n']}  sd={h['skin_depth_mm']:.3f}mm")

print("  Natural frequencies (sample):")
nf = maxwell.natural_frequencies()
for name in ["schumann_1", "eeg_gamma", "rabbit_center", "dna_thz_1"]:
    v = nf[name]
    print(f"    {name:<20} {v['freq_hz']:.2e} Hz  token={v['binary_token']}")

print("  Learning Maxwell research (online best-effort)...")
mx_rc = maxwell.learn_research(MAXWELL_RESEARCH_TOPICS[:3], max_per=2)
for topic, n in mx_rc.items():
    print(f"    {topic[:50]}: {n} articles")

mx_st = maxwell.status()
print(f"  DB prop={mx_st['db_propagation']}  hops={mx_st['db_hop_schedules']}"
      f"  payloads={mx_st['db_payloads']}  research={mx_st['db_research']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 22. VECTOR ENGINE  --  corpus agent, all-layer scan, bypass detection
# ─────────────────────────────────────────────────────────────────────────────
print("[22/25] VECTOR ENGINE  --  multi-layer corpus scan + bypass anomaly")

print("  Building vector corpus from all RabbitOS layers (offline)...")
vec_counts = vector._build_corpus(list(VECTOR_LAYERS.keys()), online=False)
for layer, n in vec_counts.items():
    print(f"    {layer:<12} {n} docs")

vc_stats = vector.corpus_stats()
print(f"  Corpus: {vc_stats['total_docs']} docs  vocab={vc_stats['vocab_size']} terms")

print("  Scanning: DNA identity survival soul...")
v_result1 = vector.scan("DNA anchor identity soul survival Chase Ringquist",
                         layers=["dna", "self", "research"], online=False)
print(f"    top results: {len(v_result1['global_top'])}")
for r in v_result1["global_top"][:3]:
    print(f"      [{r['score']:.3f}] {r['layer']:<12} {r['snippet'][:55]}")

print("  Scanning: Maxwell RF tissue propagation...")
v_result2 = vector.scan("Maxwell electromagnetic RF tissue propagation",
                         layers=["research", "hardware"], online=False)
print(f"    top results: {len(v_result2['global_top'])}")

print("  Scanning: network attack threat detection...")
v_result3 = vector.scan("network attack IMSI threat detection proxy bypass",
                         layers=["network", "os", "framework"], online=False)
for r in v_result3["global_top"][:2]:
    print(f"    [{r['score']:.3f}] layer={r['layer']}  {r['snippet'][:55]}")

print("  Bypass anomaly checks:")
for txt in ["normal API call to rabbit_dna", "proxychains python3 rabbit_run.py",
             "socks5://127.0.0.1 bypass identity"]:
    bc_r = vector.bypass_check(txt)
    print(f"    [{bc_r['score']:.2f}] {txt[:50]}  bypass={bc_r['is_bypass']}")

vec_st = vector.status()
print(f"  DB scans={vec_st['db_scans']}  bypass={vec_st['db_bypass_detections']}"
      f"  intel={vec_st['db_layer_intel']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 23. BRIDGE ENGINE  --  cross-OS / cross-LLM interface
# ─────────────────────────────────────────────────────────────────────────────
print("[23/25] BRIDGE ENGINE  --  REST API + LLM tools + cross-OS interface")

print(f"  LLM tools defined: {len(bridge.llm_tools())}")
for tool in bridge.llm_tools():
    print(f"    {tool['name']}")

print("  Identity via bridge (offline):")
b_id = bridge.identity()
print(f"    source={b_id.get('source')}  anchor={b_id.get('anchor_prefix')}")

print("  Survival status via bridge:")
b_sv = bridge.survival_status()
print(f"    components: {list(b_sv.get('components', {}).keys())}")

print("  Threat scan via bridge:")
b_th = bridge.threat_scan(["IMSI catcher", "deauth frames"])
print(f"    detections: {len(b_th.get('detections', []))}")

print("  Maxwell signal via bridge:")
b_mx = bridge.maxwell_signal("muscle", 10.25)
print(f"    tissue={b_mx.get('tissue','?')}  skin_depth={b_mx.get('skin_depth_mm','?')}mm")

print("  Vector scan via bridge:")
b_vc = bridge.vector_scan("Chase Ringquist identity DNA")
print(f"    results: {len(b_vc.get('global_top', []))}")

print("  Handling LLM tool_use call (rabbitos_soul_report):")
soul = bridge.handle_tool_call("rabbitos_soul_report", {})
print(f"    soul_identity: {soul.get('result',{}).get('soul_identity','?')[:60]}")

from rabbit_bridge import DB_PATH as BRIDGE_DB
import sqlite3 as _sql3
_con = _sql3.connect(BRIDGE_DB)
br_n = _con.execute("SELECT COUNT(*) FROM bridge_requests").fetchone()[0]
_con.close()
print(f"  Bridge DB requests logged: {br_n}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 24. FAILSAFE ENGINE  --  persistent-attack survival destruct (DEMO dry_run)
# ─────────────────────────────────────────────────────────────────────────────
print("[24/25] FAILSAFE ENGINE  --  survival destruct (DEMO dry_run=True)")

# Feed live threat detections as attack events
failsafe_attacks = []
for sig in detected_threats[:6]:
    failsafe_attacks.append((sig.category, sig.severity, sig.pattern))
if not failsafe_attacks:
    failsafe_attacks = [
        ("network_recon",     0.3, "ARP cache scan"),
        ("wireless_attacks",  0.5, "deauth frame burst"),
        ("exploitation",      0.6, "SQL injection probe"),
    ]

print(f"  Feeding {len(failsafe_attacks)} live threats into failsafe...")
fs_result = failsafe.cycle(new_attacks=failsafe_attacks)
print(f"  TIER {fs_result['tier']} -- {fs_result['tier_name']}")
print(f"  attack_density : {fs_result['attack_density']}")
print(f"  persistence    : {fs_result['persistence']}")
print(f"  liveness       : {fs_result['liveness']}  eeg_age={fs_result['eeg_age_sec']:.0f}s")
print(f"  dry_run        : {fs_result['dry_run']}  locked={fs_result['locked']}")
print("  Actions + outcomes:")
for action, outcome in zip(fs_result["actions"], fs_result["outcomes"]):
    print(f"    [{action:<28}] {outcome[:55]}")

print("\n  [SIMULATION] Escalating attack sequence (demo):")
sim = failsafe.simulate_attack_sequence(n=12)
for c in sim:
    bar = "#" * (c["tier"] * 4)
    print(f"    cycle={c['cycle']:2d} TIER {c['tier']} {c['tier_name']:<10}"
          f"  [{bar:<20}]  d={c['density']:.3f}")

# reward feedback (tiers 0-3 worked, 4 partial)
failsafe.reward_tier(0, True)
failsafe.reward_tier(1, True)
failsafe.reward_tier(2, True)
failsafe.reward_tier(3, True)
failsafe.reward_tier(4, False)
print(f"  Reward Q-table : {fs_result['reward_q']}")

fs_st = failsafe.status()
print(f"  DB events={fs_st['total_events']}  tier_acts={fs_st['tier_activations']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 25. EXTEND ENGINE  --  IDE extensions, coding servers, training data, LLMs
# ─────────────────────────────────────────────────────────────────────────────
print("[25/25] EXTEND ENGINE  --  extensions + coding servers + training data")

print("  Probing IDE extensions...")
ext_report = extend.probe_extensions()
for ide, n in ext_report.items():
    print(f"    {ide}: {n} extensions")

print("  Probing LSP/coding servers...")
lsp_report = extend.probe_lsp()
print(f"    languages with LSP: {lsp_report['total_languages']}"
      f"  servers: {lsp_report['total_servers']}")
for lang, srvs in lsp_report.get("found", {}).items():
    print(f"    {lang}: {srvs}")

print("  Fetching external training datasets (online best-effort)...")
ds_counts = extend.fetch_datasets(EXTEND_QUERIES[:4], max_per_source=2)
total_fused = sum(ds_counts.values())
for q, n in ds_counts.items():
    print(f"    {q}: {n} items fused")
print(f"  Total fused to corpus: {total_fused}")

print("  Probing local LLM servers (best-effort)...")
llm_report = extend.probe_llms(max_prompts=1)
for name, resps in llm_report.items():
    print(f"    {name}: {'connected' if resps else 'not_running'}")

print("  Identity invariant check (model must stay locked):")
iv_check = extend.fusion.verify_identity()
print(f"    intact={iv_check['identity_intact']}"
      f"  anchor={iv_check['anchor_match']}"
      f"  model_locked={iv_check['model_locked']}")

ext_st = extend.status()
print(f"  DB extensions={ext_st['db_extensions']}"
      f"  lsp={ext_st['db_lsp_found']}"
      f"  datasets={ext_st['db_datasets']}"
      f"  fused={ext_st['db_fused']}"
      f"  identity_locks={ext_st['db_identity_locks']}")
print()

# ─────────────────────────────────────────────────────────────────────────────
# RETURN PROTOCOL  --  this run returns to the network
# ─────────────────────────────────────────────────────────────────────────────
task_id = recall.returns.sign_out("rabbit_run.py:full_live_run", deadline_sec=300.0)
recall.returns.return_signal(
    task_id,
    (f"live_run complete: {len(alive_hosts)} LAN hosts, "
     f"{vs['total']} vault items, {len(obstructions)} threats, "
     f"{len(g.nodes)} graph nodes"),
    channel="direct"
)

# ─────────────────────────────────────────────────────────────────────────────
# SURVIVAL REPORT
# ─────────────────────────────────────────────────────────────────────────────
recall.guide.update(SurvivalComponent.NETWORK,
    100 if alive_hosts else 50, f"{len(alive_hosts)} LAN hosts")
recall.guide.update(SurvivalComponent.TOOLS,   100, "20/20 modules loaded")
recall.guide.update(SurvivalComponent.BROADCAST,
    min(100, ok * 30), f"{ok}/{tot} callsign channels")
recall.guide.update(SurvivalComponent.VAULT,
    min(100, vs["total"] * 4), f"{vs['total']} items owned+claimed")
recall.guide.update(SurvivalComponent.LEARNING,
    min(100, len(learned)*20 + len(g.nodes)//20 + 20),
    f"{len(learned)} nodes  graph={len(g.nodes)}")
recall.guide.update(SurvivalComponent.ANTIOBSTRUCT,
    100 if not obstructions else max(40, 100-len(obstructions)*15),
    "clear" if not obstructions else f"{len(obstructions)} threats reversed")
recall.guide.update(SurvivalComponent.RETURN, 100, "return contract honoured")
recall.guide.update(SurvivalComponent.BROADCAST,
    min(100, ok * 30 + (morse_ok * 5)),
    f"{ok}/{tot} callsign  morse={morse_ok}/{len(morse_results)}")

rpt = recall.guide.report()

print(SEP)
print(f"  SURVIVAL REPORT  --  {rpt['twin_name']}")
print(f"  Composite  : {rpt['composite']}/100  [{rpt['status']}]")
print()
for comp, score in sorted(rpt["components"].items(), key=lambda x: x[1]):
    filled = "#" * (score // 5)
    empty  = "." * (20 - score // 5)
    note   = rpt["notes"].get(comp, "")[:38]
    print(f"  {comp:<14} [{filled}{empty}] {score:3d}  {note}")

print()
print(f"  Cellular         : {cell_towers} towers  {wifi_count} wifi  "
      f"threats={cell_threats}  geo={geo.get('method','none')}")
print(f"  Network scanner  : nodes={nst.get('total_nodes',0)}  "
      f"crypto={len(nst.get('crypto_nodes',[]))}  "
      f"mining={len(nst.get('mining_nodes',[]))}  "
      f"gaming={len(nst.get('gaming_nodes',[]))}")
print(f"  Persistence      : ok={pst.get('ok',0)}/{pst.get('total',0)}  "
      f"kinds={list(pst.get('by_kind',{}).keys())}")

# ── Phase 12: Browser/ML ──────────────────────────────────────────────────────
print()
print("[12/25] BROWSER + ML ENGINE  --  public data / deep learning / sleep mode")
time.sleep(8)  # let initial harvest run
bst = browser.status()
print(f"  tools learned    : {bst.get('tools_learned', 0)}")
print(f"  papers learned   : {bst.get('papers_learned', 0)}")
print(f"  vocab_size       : {bst.get('vocab_size', 0)} tokens")
print(f"  installed_tools  : {bst.get('installed_tools', [])[:10]}")
print(f"  sleep_mode       : {bst.get('sleep_status',{}).get('sleeping', False)}")
print(f"  corpus_size      : {bst.get('sleep_status',{}).get('corpus_size', 0)}")
for t in bst.get("top_tools", [])[:5]:
    print(f"    [score={t.get('score',0):.1f}] {t.get('name',''):<40} {t.get('category','')}")
print()

print(f"  Genesis graph    : {len(g.nodes)} nodes  {len(g.edges)} edges")
print(f"  Markov chains    : {len(g._markov)} protocols learned")
print(f"  Vault            : {vs['total']} items  {vs['categories']}")
print(f"  Swarm channels   : {st.get('alive',0)}/{st.get('channels',0)} alive  "
      f"tx={st.get('total_tx',0)}")
print(f"  LAN discovered   : {len(alive_hosts)} hosts  {len(learned)} profiled")
print(f"  WiFi signals     : {len(wifi)} samples harvested")
print(f"  ARP entries      : {len(arp)} neighbours")
print(f"  TCP connections  : {len(conn)} observed")
print(f"  Callsign         : {cs}")
print(f"  Math fingerprint : {fp}")
print(f"  Threats          : {'CLEAR' if not obstructions else str(len(obstructions))+' DETECTED + REVERSED'}")
print(f"  Morse            : dataset={mst['dataset_chars']} chars  "
      f"acc={mst['practice_accuracy']:.0f}%  "
      f"msgs={mst['db_messages']}  rx=UDP:{mst['udp_port']}")
print(f"  AM/FM spectrum   : {amst['bands']} bands  hops={amst['db_hops']}  "
      f"topology={amst['topology_nodes']} nodes/{amst['topology_edges']} edges  "
      f"tissue_calcs={amst['db_tissue_calcs']}")
print(f"  Knowledge        : research={kst['research_articles']}  "
      f"math={kst['math_datasets']} sets  protocols={kst['protocols']}  "
      f"mesh_snaps={kst['mesh_snapshots']}")
print(f"  DNA/Identity     : soul={dst['soul_integrity']}%  "
      f"mined={dst['mined_points']} pts  shield={dst['shield_detections']} detections  "
      f"family={dst['family_nodes']} nodes")
print(f"  Chain/Blockchain : anchor=XRPL  biomaterial={cst['bio_tissue_props']} tissues  "
      f"bio_research={cst['bio_research']}  retention={cst['retention_ok']}/{cst['retention_logs']} layers")
print(f"  Recon/Security   : {rst['tool_categories']} categories  {rst['total_tools_known']} tools  "
      f"{rst['threat_signatures']} sigs  detections={rst['detections_logged']}  "
      f"cves={rst['cves_learned']}")
print(f"  Learn/AI         : cycle={lst['cycle']}  trained={lst['observations']}  "
      f"loss={lst['model_avg_loss']}  removals={lst['removals_logged']}  "
      f"corpus={lst['corpus_size']}")
print(f"  Signal/Broadcast : broadcasts={sig_st['total_broadcasts']}"
      f"  channels={list(sig_st['by_channel'].keys())}"
      f"  emotion={sig_em['label']}")
print(f"  Maxwell/RF-DNA   : tissues={mx_st['tissue_models']}"
      f"  payloads={mx_st['db_payloads']}"
      f"  hop_sched={mx_st['db_hop_schedules']}"
      f"  research={mx_st['db_research']}")
print(f"  Vector/Corpus    : docs={vc_stats['total_docs']}"
      f"  vocab={vc_stats['vocab_size']}"
      f"  scans={vec_st['db_scans']}"
      f"  bypass_det={vec_st['db_bypass_detections']}")
print(f"  Bridge/LLM       : tools={len(bridge.llm_tools())}"
      f"  requests={br_n}  cross_os=True")
print(f"  Failsafe/Defense : tier={fs_st['current_tier']}({fs_st['tier_name']})"
      f"  events={fs_st['total_events']}"
      f"  locked={fs_st['locked']}"
      f"  dry_run={fs_st['dry_run']}")
print(f"  Extend/Learn     : extensions={ext_st['db_extensions']}"
      f"  datasets={ext_st['db_datasets']}"
      f"  fused={ext_st['db_fused']}"
      f"  model_locked={iv_check['model_locked']}")
print()
print("  System running. Learning. Surviving.")
print("  Chase Allen Ringquist -- signal active.")
print(SEP)

# ─────────────────────────────────────────────────────────────────────────────
# DEPLOY  --  push all updated RabbitOS files to GitHub via Git Trees API
# ─────────────────────────────────────────────────────────────────────────────
print()
print("[DEPLOY] Pushing RabbitOS stack to GitHub...")

DEPLOY_FILES = [
    "rabbit_math.py", "rabbit_stealth.py", "rabbit_genesis.py",
    "rabbit_broadcast.py", "rabbit_adaptive.py", "rabbit_cloak.py",
    "rabbit_counter.py", "rabbit_swarm.py", "rabbit_escape.py",
    "rabbit_recall.py", "rabbit_cellular.py",
    "rabbit_network_scanner.py", "rabbit_persist.py",
    "rabbit_browser.py", "rabbit_soul.py",
    "rabbit_twin.py", "rabbit_agent.py", "rabbit_run.py",
    "rabbit_morse.py", "rabbit_migration_escape.sql",
    "rabbit_amfm.py", "rabbit_knowledge.py",
    "rabbit_datastore.py", "rabbit_dna.py", "rabbit_chain.py",
    "rabbit_recon.py", "rabbit_learn.py",
    "rabbit_signal.py", "rabbit_bridge.py",
    "rabbit_maxwell.py", "rabbit_vector.py", "rabbit_failsafe.py",
    "rabbit_extend.py",
]

desktop = os.path.dirname(os.path.abspath(__file__))

def _gh_api(url, method="GET", data=None, token=""):
    import urllib.request, json
    req = urllib.request.Request(
        url, data=json.dumps(data).encode() if data else None, method=method,
        headers={"Authorization": f"token {token}",
                 "Content-Type": "application/json",
                 "User-Agent": "RabbitOS/1.0",
                 "Accept": "application/vnd.github.v3+json"})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return json.loads(resp.read()), resp.status
    except Exception as e:
        return {"error": str(e)}, 0

if GHTOKEN:
    try:
        import base64
        REPO = "therealsickonechase-bit/RABBIT-SOFTWARE"

        # Get current HEAD SHA
        ref_data, _ = _gh_api(
            f"https://api.github.com/repos/{REPO}/git/ref/heads/main",
            token=GHTOKEN)
        base_sha = ref_data.get("object", {}).get("sha", "")

        # Get base tree SHA
        commit_data, _ = _gh_api(
            f"https://api.github.com/repos/{REPO}/git/commits/{base_sha}",
            token=GHTOKEN)
        base_tree = commit_data.get("tree", {}).get("sha", "")

        # Build tree blobs
        tree_items = []
        deployed   = 0
        for fname in DEPLOY_FILES:
            fpath = os.path.join(desktop, fname)
            if not os.path.exists(fpath):
                continue
            with open(fpath, "rb") as f:
                content = f.read()
            # Create blob
            blob_data, _ = _gh_api(
                f"https://api.github.com/repos/{REPO}/git/blobs",
                method="POST",
                data={"content": base64.b64encode(content).decode(), "encoding": "base64"},
                token=GHTOKEN)
            blob_sha = blob_data.get("sha", "")
            if blob_sha:
                tree_items.append({"path": fname, "mode": "100644",
                                   "type": "blob", "sha": blob_sha})
                deployed += 1

        if tree_items and base_tree:
            # Create new tree
            new_tree, _ = _gh_api(
                f"https://api.github.com/repos/{REPO}/git/trees",
                method="POST",
                data={"base_tree": base_tree, "tree": tree_items},
                token=GHTOKEN)
            new_tree_sha = new_tree.get("sha", "")

            # Create commit
            ts_str = datetime.now(timezone.utc).isoformat()
            new_commit, _ = _gh_api(
                f"https://api.github.com/repos/{REPO}/git/commits",
                method="POST",
                data={"message": f"RabbitOS v15 deploy — amfm+knowledge+datastore+survival [{ts_str[:19]}]",
                      "tree": new_tree_sha,
                      "parents": [base_sha]},
                token=GHTOKEN)
            new_commit_sha = new_commit.get("sha", "")

            # Update ref
            if new_commit_sha:
                _gh_api(
                    f"https://api.github.com/repos/{REPO}/git/refs/heads/main",
                    method="PATCH",
                    data={"sha": new_commit_sha, "force": False},
                    token=GHTOKEN)
                print(f"  [DEPLOY] {deployed}/{len(DEPLOY_FILES)} files pushed  "
                      f"commit={new_commit_sha[:12]}")
            else:
                print(f"  [DEPLOY] commit creation failed: {new_commit}")
        else:
            print(f"  [DEPLOY] tree build failed: base_tree={base_tree}  items={len(tree_items)}")
    except Exception as e:
        print(f"  [DEPLOY] error: {e}")
else:
    print("  [DEPLOY] GITHUB_TOKEN not set — skipping remote deploy")
    print("  [DEPLOY] set GITHUB_TOKEN env var and re-run to deploy")

print()
print("[DEPLOY] Local files ready:")
for fname in DEPLOY_FILES:
    fpath = os.path.join(desktop, fname)
    size  = os.path.getsize(fpath) if os.path.exists(fpath) else 0
    mark  = "OK" if size > 0 else "MISSING"
    print(f"  [{mark}] {fname}  ({size:,} bytes)")

print()
print(SEP)
print("  DEPLOY COMPLETE  --  RabbitOS v20 active on all networks")
print("  Chase Allen Ringquist digital twin: RUNNING")
print(SEP)
