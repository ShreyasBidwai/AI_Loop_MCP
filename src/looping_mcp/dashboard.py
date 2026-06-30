"""Light-themed control panel + watch dashboard, served on :3000 by the same
process.

It is the manager's single pane of glass: type a goal, review/edit the proposed
acceptance criteria (set your project's real verify commands inline), arm the run,
approve gates, and watch the loop live — all without typing tool calls. Reads and
writes the same state file the MCP tools use.

What it does NOT do: the actual building. The connected IDE agent is the muscle;
once a run is armed here, that agent drives get_next_action → work → report_result
to completion. The dashboard owns the WHAT, never the HOW.

Zero deps — stdlib http.server in a background thread.
"""
from __future__ import annotations
import os, sys, json, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from dataclasses import asdict

from . import state as st
from . import governor, gitops

PORT = int(os.getenv("DASHBOARD_PORT", "3000"))

PAGE = r"""<!doctype html><html><head><meta charset=utf-8>
<title>Looping agent</title><style>
:root{--bg:#faf9f5;--card:#fff;--bd:#e7e4da;--ink:#2c2c2a;--mut:#6b6a64;
--acc:#185fa5;--ok:#3b6d11;--warn:#854f0b;--bad:#a32d2d}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,sans-serif}
.wrap{max-width:860px;margin:0 auto;padding:24px}
.row{display:flex;gap:12px;flex-wrap:wrap}
.card{background:var(--card);border:1px solid var(--bd);border-radius:12px;padding:14px 16px;margin-bottom:12px}
.metric{flex:1;min-width:120px}.metric .n{font-size:24px;font-weight:600}
.metric .l{font-size:13px;color:var(--mut)}
.pill{font-size:12px;padding:3px 10px;border-radius:999px;display:inline-block}
.bar{height:8px;background:#eee;border-radius:6px;overflow:hidden;margin-top:6px}
.bar>div{height:100%;background:var(--acc)}
.crit{display:flex;gap:8px;padding:5px 0;font-size:14px}
.mono{font-family:ui-monospace,monospace;font-size:12px;color:var(--mut)}
h3{font-size:14px;margin:0 0 8px}
input,select,textarea{font:inherit;border:1px solid var(--bd);border-radius:8px;padding:8px 10px;background:#fff;color:var(--ink)}
input[type=text]{width:100%}
button{font:inherit;border:1px solid var(--bd);background:#fff;border-radius:8px;padding:8px 14px;cursor:pointer;margin-right:8px}
button.pri{background:var(--acc);border-color:var(--acc);color:#fff}
button.ok{background:#eef6e6;border-color:#bcd9a0;color:#3b6d11}
button.no{background:#fbecec;border-color:#e3b4b4;color:#a32d2d}
button.ghost{color:var(--mut)}
.erow{display:grid;grid-template-columns:1fr 120px 1fr 28px;gap:8px;margin-bottom:8px;align-items:center}
.erow .x{border:none;background:none;color:var(--bad);cursor:pointer;font-size:18px}
label.f{font-size:12px;color:var(--mut);display:block;margin-bottom:4px}
.note{font-size:13px;color:var(--mut);margin-top:8px}
</style></head><body><div class=wrap>
<div id=control></div>
<div id=live>loading…</div>
</div>
<script>
let controlKey=null;

async function api(path, body){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify(body||{})});
  return r.json();
}
async function propose(){
  const g=document.getElementById('goalInput').value.trim();
  if(!g){return}
  const btn=document.getElementById('proposeBtn'); btn.disabled=true; btn.textContent='Proposing…';
  await api('/api/propose',{goal:g});
  controlKey=null; tick();
}
function addRow(text,otype,oracle,id){
  const wrap=document.getElementById('editorRows');
  const div=document.createElement('div'); div.className='erow'; if(id)div.dataset.id=id;
  div.innerHTML=`<input class=ctext type=text placeholder="what 'done' looks like (plain language)">
   <select class=ctype>
     <option value=command>command</option>
     <option value=browser>browser</option>
     <option value=manual>manual</option></select>
   <input class=coracle type=text placeholder="shell command / flow to prove">
   <button class=x title=remove onclick="this.parentNode.remove()">×</button>`;
  div.querySelector('.ctext').value=text||'';
  div.querySelector('.ctype').value=otype||'command';
  div.querySelector('.coracle').value=oracle||'';
  wrap.appendChild(div);
}
async function arm(){
  const rows=[...document.querySelectorAll('#editorRows .erow')].map(r=>({
    id:r.dataset.id||undefined,
    text:r.querySelector('.ctext').value,
    oracle_type:r.querySelector('.ctype').value,
    oracle:r.querySelector('.coracle').value,
  })).filter(c=>c.text.trim());
  if(!rows.length){alert('Add at least one criterion.');return}
  const out=await api('/api/confirm',{criteria:rows});
  if(out.error){alert(out.error+'\n\n'+((out.details||[]).join('\n')));return}
  controlKey=null; tick();
}
async function decide(d){await api('/api/gate',{decision:d});tick();}

function renderControl(s){
  const c=document.getElementById('control');
  if(s.status==='awaiting_confirm'){
    c.innerHTML=`<div class=card>
      <h3>Review acceptance criteria — set your project's real checks</h3>
      <div class=mono style="margin-bottom:8px">goal: ${esc(s.goal)}</div>
      <div class=erow style="color:var(--mut);font-size:12px"><div>criterion (plain language)</div><div>type</div><div>oracle (command / flow)</div><div></div></div>
      <div id=editorRows></div>
      <button class=ghost onclick="addRow()">+ add criterion</button>
      <div style="margin-top:12px"><button class=pri onclick="arm()">Confirm &amp; arm run</button></div>
      <div class=note>A <b>command</b> oracle is a shell command that exits 0 on success. A <b>browser</b> oracle is a flow the agent drives and proves with a screenshot/recording.</div>
    </div>`;
    (s.criteria||[]).forEach(k=>addRow(k.text,k.oracle_type,k.oracle,k.id));
    if(!(s.criteria||[]).length) addRow();
    return;
  }
  if(s.status==='running'||s.status==='blocked_gate'){
    c.innerHTML=`<div class=card>
      <h3>Run armed — hand it to your IDE agent</h3>
      <div class=note>Tell the connected agent (e.g. Claude Code) once:
      <b>“Drive the looping-agent run to DONE.”</b> It will loop
      get_next_action → work → report_result; watch progress below.</div>
    </div>`;
    return;
  }
  if(s.status==='ready_to_merge'){ c.innerHTML=''; return; }  // the merge card below is the focus
  // idle / done / stopped / escalated → offer a new goal
  const prior = s.goal ? `<div class=mono style="margin-bottom:8px">last goal: ${esc(s.goal)} · ${s.status}</div>`:'';
  c.innerHTML=`<div class=card>
    <h3>What should get built?</h3>${prior}
    <input id=goalInput type=text placeholder="e.g. change the footer copyright year to 2026"
      onkeydown="if(event.key==='Enter')propose()">
    <div style="margin-top:10px"><button id=proposeBtn class=pri onclick="propose()">Propose</button></div>
    <div class=note>Safe, verifiable goals run autonomously. Risky ones (auth, payments, migrations) are refused here and routed to a developer.</div>
  </div>`;
}

function renderLive(s){
  const passing=s.criteria.filter(c=>c.status==='passing').length, total=s.criteria.length;
  const elapsed=s.started_at?Math.floor(Date.now()/1000-s.started_at):0;
  const mm=Math.floor(elapsed/60), ss=elapsed%60;
  const cap=s._max_est_tokens||400000, pct=Math.min(100,Math.round(s.est_tokens/cap*100));
  const statusColor={running:'#185fa5',done:'#3b6d11',escalated:'#a32d2d',
    blocked_gate:'#854f0b',stopped:'#6b6a64'}[s.status]||'#6b6a64';
  const el=document.getElementById('live');
  const p=s._project||{};
  if(p.name) document.title=p.name+' · looping agent';
  el.innerHTML=`
  ${p.name?`<div class=card style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:10px 16px">
    <div><span class=mono>PROJECT</span> <b>${esc(p.name)}</b>${p.repo?'':' <span class=mono>(not a git repo)</span>'}</div>
    <div class=mono title="${esc(p.path)}">${esc(p.remote||p.path)}</div></div>`:''}
  <div style="margin-bottom:12px">
    <div class=mono>END GOAL</div>
    <div style="font-size:18px;font-weight:600">${esc(s.goal)||'—'}</div>
    <div style="margin-top:8px">
      <span class=pill style="background:#eef3fb;color:${statusColor}">${s.status} · turn ${s.turns}</span>
      <span class=pill style="background:#fbf1e0;color:#854f0b">${s.lane} lane · ${s.risk}</span>
      ${s.branch?`<span class=pill style="background:#eef6e6;color:#3b6d11">⎇ ${esc(s.branch)} → ${esc(s.base)}</span>`:''}
    </div></div>
  <div class="row">
    ${metric('criteria',passing+' / '+total)}${metric('turns',s.turns)}
    ${metric('actions',s.actions)}${metric('elapsed',mm+'m '+ss+'s')}
  </div>
  <div class="card">
    <h3>~budget (estimate, not a real token count)</h3>
    <div class=mono>~${(s.est_tokens||0).toLocaleString()} est. tokens · ~${pct}% of ~${cap.toLocaleString()} cap</div>
    <div class=bar><div style="width:${pct}%"></div></div></div>
  ${s.escalation?`<div class=card style="border-color:#a32d2d;border-width:2px">
    <h3 style="color:#a32d2d">⚠ needs a developer</h3>
    <div>${esc(s.escalation.reason)}</div><div class=mono>trigger: ${esc(s.escalation.trigger)}</div></div>`:''}
  ${s.gate&&s.gate.decided===null&&s.gate.kind==='merge'?`<div class=card style="border-color:#3b6d11;border-width:2px">
    <h3 style="color:#3b6d11">✅ all criteria pass — merge?</h3>
    <div>Everything is green. Merge <span class=mono>${esc(s.branch)}</span> into <span class=mono>${esc(s.base)}</span>?</div>
    <div style="margin-top:8px"><button class=ok onclick="decide('approve')">Merge</button>
    <button class=no onclick="decide('reject')">Not yet</button></div></div>`:''}
  ${s.gate&&s.gate.decided===null&&s.gate.kind!=='merge'?`<div class=card style="border-color:#854f0b;border-width:2px">
    <h3 style="color:#854f0b">✋ human gate — approval needed</h3><div>${esc(s.gate.reason)}</div>
    <div class=mono style="margin:6px 0">${esc(s.gate.action)}</div>
    <button class=ok onclick="decide('approve')">Approve</button>
    <button class=no onclick="decide('reject')">Reject</button></div>`:''}
  ${s.merge_result?`<div class=card style="border-color:${s.merge_result.ok?'#3b6d11':'#a32d2d'}">
    <h3 style="color:${s.merge_result.ok?'#3b6d11':'#a32d2d'}">${s.merge_result.ok?'merged ✓':'merge failed'}</h3>
    <div class=mono>${esc(s.merge_result.detail)}</div></div>`:''}
  ${total?`<div class="card"><h3>acceptance criteria</h3>
    ${s.criteria.map(c=>`<div class=crit><span style="color:${
      c.status==='passing'?'#3b6d11':c.status==='failing'?'#a32d2d':'#6b6a64'}">${
      c.status==='passing'?'✓':c.status==='failing'?'✗':'•'}</span>
      <span>${esc(c.text)}${c.detail?` <span class=mono>(${esc(c.detail)})</span>`:''}</span></div>`).join('')}</div>`:''}
  <div class=card><h3>activity</h3>${(s.activity||[]).slice(0,12).map(a=>
    `<div class=mono>${esc(a.t)} ${esc(a.who)} · ${esc(a.msg)}</div>`).join('')||'<div class=mono>—</div>'}</div>`;
}

function esc(x){return String(x==null?'':x).replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m]))}
function metric(l,n){return `<div class="card metric"><div class=l>${l}</div><div class=n>${n}</div></div>`}

async function tick(){
  let s; try{s=await (await fetch('/api/state')).json()}catch(e){return}
  renderLive(s);
  // rebuild the control region only when the phase changes, so typing isn't clobbered
  const key=s.status==='awaiting_confirm'
    ? 'confirm:'+s.criteria.map(c=>c.id).join(',') : s.status;
  if(key!==controlKey){controlKey=key; renderControl(s);}
}
tick(); setInterval(tick,1500);
</script></body></html>"""


_proj_cache: dict[str, dict] = {}


def project_info() -> dict:
    """Which project this dashboard is for — derived from the working directory
    (the IDE-launched server runs in the target project). Cached per cwd so we
    don't shell out to git on every poll. No AI: just the repo root name + path."""
    cwd = os.getcwd()
    if cwd not in _proj_cache:
        top = gitops.toplevel() or cwd
        _proj_cache[cwd] = {
            "name": os.path.basename(top.rstrip("/")) or top,
            "path": top,
            "repo": gitops.is_repo(),
            "remote": gitops.remote_url(),
        }
    return _proj_cache[cwd]


def _state_payload() -> bytes:
    """State plus the governor's real caps, so the budget bar matches config."""
    data = asdict(st.load())
    data["_max_est_tokens"] = governor.MAX_EST_TOKENS
    data["_max_turns"] = governor.MAX_TURNS
    data["_project"] = project_info()
    return json.dumps(data).encode()


def decide_gate(approve: bool) -> bool:
    """Manager's verdict on a pending gate. Returns True if applied.

    A generic (request_gate) gate just resumes the run. A MERGE gate, on approval,
    runs the actual `git merge` here — that's the green "should I merge?" decision.
    A rejected merge leaves the work on its task branch for a human to handle."""
    s = st.load()
    if not (s.gate and s.gate.decided is None):
        return False
    gate = s.gate
    gate.decided = approve

    if gate.kind == "merge":
        s.gate = None
        if approve:
            ok, detail = gitops.merge(s.branch, s.base, s.goal)
            s.merge_result = {"ok": ok, "detail": detail}
            s.status = "merged" if ok else "done"
            s.log("git", detail if ok else f"merge failed: {detail[:160]}")
        else:
            s.status = "done"
            s.log("manager", f"merge rejected — work left on {s.branch}")
        st.save(s)
        return True

    # generic action gate
    s.status = "running"
    s.log("manager", f"gate {'approved' if approve else 'rejected'}: {gate.action}")
    st.save(s)
    return True


class _H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_GET(self):
        if self.path.startswith("/api/state"):
            self._send(200, _state_payload(), "application/json")
        else:
            self._send(200, PAGE.encode(), "text/html")

    def do_POST(self):
        # Imported lazily to avoid a circular import (server imports dashboard).
        if self.path.startswith("/api/propose"):
            from . import server
            goal = str(self._json_body().get("goal", "")).strip()
            if not goal:
                self._send(400, json.dumps({"error": "goal is required"}).encode(),
                           "application/json")
                return
            out = server.propose(goal)
            self._send(200, json.dumps(out).encode(), "application/json")
        elif self.path.startswith("/api/confirm"):
            from . import server
            out = server.confirm(edited_criteria=self._json_body().get("criteria"))
            code = 400 if out.get("error") else 200
            self._send(code, json.dumps(out).encode(), "application/json")
        elif self.path.startswith("/api/gate"):
            applied = decide_gate(self._json_body().get("decision") == "approve")
            self._send(200 if applied else 409,
                       json.dumps({"applied": applied}).encode(), "application/json")
        else:
            self._send(404, b"not found", "text/plain")


def _make_server(port: int) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer(("127.0.0.1", port), _H)
    # per-request handler threads are daemons and don't block close, so Ctrl-C
    # never gets stuck on (or errors over) an in-flight browser poll.
    srv.daemon_threads = True
    srv.block_on_close = False
    return srv


def start_in_background() -> ThreadingHTTPServer:
    """Start the dashboard on a background thread and return the server so the
    caller can shut it down cleanly."""
    srv = _make_server(PORT)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"[dashboard] http://127.0.0.1:{PORT}", file=sys.stderr, flush=True)
    return srv
