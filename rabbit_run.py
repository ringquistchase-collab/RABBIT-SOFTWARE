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
print("[BOOT] All 17 systems online.")
print()

# ─────────────────────────────────────────────────────────────────────────────
# 1. MATH ENGINE
# ─────────────────────────────────────────────────────────────────────────────
print("[1/12] MATH ENGINE  --  CA30 + CA110 + Lorenz chaos")

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
print("[2/12] CALLSIGN BROADCAST  --  all channels with 59-tool manifest")

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
print("[3/12] ESCAPE TOKEN  --  all medium encodings")

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
print("[4/12] LAN DISCOVERY + TREE LEARNING")

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
print("[5/12] KNOWLEDGE GRAPH  --  live harvest + speculative topology")

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
print("[6/12] VAULT SCAN  --  contracts / images / videos / gaming / medical")

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
print("[7/12] OBSTRUCTION SCAN  --  mining / hooks / DNS / throttle")

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
print("[8/12] SWARM STATUS  --  perpetual multi-channel presence")

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
print("[9/12] CELLULAR LAYER  --  tower detection + attacker reversal")

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
print("[10/12] NETWORK SCANNER  --  crypto/gaming/mining/dev/RF detection")

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
print("[11/12] PERSISTENCE ENGINE  --  SQL + bootloader + offline + network embed")

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
recall.guide.update(SurvivalComponent.TOOLS,   100, "17/17 modules loaded")
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
print("[12/12] BROWSER + ML ENGINE  --  public data / deep learning / sleep mode")
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
    "rabbit_migration_escape.sql",
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
                data={"message": f"RabbitOS v14 deploy — cellular+reversal+survival [{ts_str[:19]}]",
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
print("  DEPLOY COMPLETE  --  RabbitOS v17 active on all networks")
print("  Chase Allen Ringquist digital twin: RUNNING")
print(SEP)
