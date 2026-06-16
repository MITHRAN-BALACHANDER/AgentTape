"""Self-contained static HTML viewer (no server required).

Generates a single HTML file with inlined CSS/JS that opens via ``file://``. The
cassette data is embedded as JSON; nothing is fetched and nothing leaves the
machine — consistent with the no-server principle. Supports a single-cassette
timeline view and a two-cassette side-by-side diff view.
"""

from __future__ import annotations

import json
from typing import Any

from .schema import Cassette


def render_html(cassette: Cassette, *, title: str = "AgentTape", second: Cassette | None = None) -> str:
    payload: dict[str, Any] = {
        "primary": cassette.to_dict(),
        "secondary": second.to_dict() if second is not None else None,
    }
    data_json = json.dumps(payload, ensure_ascii=False, default=str)
    # Escape </script> so the embedded JSON cannot break out of the script tag.
    data_json = data_json.replace("</", "<\\/")
    return _TEMPLATE.replace("__TITLE__", _escape(title)).replace("__DATA__", data_json)


def write_html(
    cassette: Cassette, out_path: str, *, title: str = "AgentTape", second: Cassette | None = None
) -> str:
    from pathlib import Path

    html = render_html(cassette, title=title, second=second)
    Path(out_path).write_text(html, encoding="utf-8")
    return out_path


def _escape(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ · AgentTape</title>
<style>
  :root { --bg:#0f1115; --panel:#181b22; --line:#2a2f3a; --fg:#e6e8ee; --muted:#9aa3b2;
          --llm:#4f9cf9; --tool:#f5a623; --http:#7ed321; --mem:#bd6bf5; --err:#f5564a; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--fg); font:14px/1.5 ui-monospace,Menlo,Consolas,monospace; }
  header { padding:16px 24px; border-bottom:1px solid var(--line); display:flex; gap:16px; align-items:baseline; }
  header h1 { font-size:18px; margin:0; }
  header .muted { color:var(--muted); }
  main { display:grid; grid-template-columns: 1fr; gap:0; }
  .twoup { grid-template-columns: 1fr 1fr; }
  .col { padding:16px 24px; border-right:1px solid var(--line); }
  .step { border:1px solid var(--line); border-radius:8px; margin:10px 0; overflow:hidden; }
  .step summary { cursor:pointer; padding:10px 12px; display:flex; gap:10px; align-items:center; list-style:none; }
  .step summary::-webkit-details-marker { display:none; }
  .badge { padding:2px 8px; border-radius:999px; font-size:11px; font-weight:700; color:#0b0d11; }
  .k-llm{background:var(--llm)} .k-tool{background:var(--tool)} .k-http{background:var(--http)}
  .k-memory_read,.k-memory_write{background:var(--mem)} .k-retrieval{background:var(--http)}
  .err { color:var(--err); }
  .bar { height:8px; background:var(--llm); border-radius:4px; }
  .meta { color:var(--muted); margin-left:auto; font-size:12px; }
  pre { background:#0b0d11; border:1px solid var(--line); border-radius:6px; padding:10px;
        overflow:auto; max-height:340px; white-space:pre-wrap; word-break:break-word; }
  .lbl { color:var(--muted); margin:8px 0 2px; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }
  .totals { padding:12px 24px; border-top:1px solid var(--line); color:var(--muted); }
  .row { display:flex; gap:8px; align-items:center; }
</style>
</head>
<body>
<header>
  <h1>🎞️ AgentTape</h1>
  <span class="muted" id="subtitle"></span>
</header>
<main id="root"></main>
<div class="totals" id="totals"></div>
<script id="data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
function esc(s){ return String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }
function pretty(v){ try { return JSON.stringify(v, null, 2); } catch(e){ return String(v); } }
function totalLatency(c){ return (c.interactions||[]).reduce((a,i)=>a+(i.latency_ms||0),0); }
function totalTokens(c){ return (c.interactions||[]).reduce((a,i)=>a+((i.usage&&i.usage.total_tokens)||0),0); }
function renderStep(i, maxLat){
  const kind = i.kind || 'tool';
  const name = i.boundary || kind;
  const lat = i.latency_ms || 0;
  const w = maxLat ? Math.max(2, Math.round(lat/maxLat*100)) : 2;
  const tok = (i.usage && i.usage.total_tokens) ? i.usage.total_tokens+' tok' : '';
  const isErr = !!i.error;
  const d = document.createElement('details'); d.className='step'; if(i.kind==='llm') d.open=true;
  const respLabel = isErr ? 'Error' : 'Response';
  const respVal = isErr ? pretty(i.error) : pretty(i.response);
  d.innerHTML =
    '<summary><span class="badge k-'+esc(kind)+'">'+esc(kind)+'</span>'
    + '<b>'+esc(name)+'</b>'
    + '<span class="row" style="flex:1"><span class="bar" style="width:'+w+'%"></span></span>'
    + '<span class="meta">'+lat.toFixed(1)+'ms '+esc(tok)+'</span></summary>'
    + '<div style="padding:0 12px 12px">'
    + '<div class="lbl">Request</div><pre>'+esc(pretty(i.request))+'</pre>'
    + '<div class="lbl '+(isErr?'err':'')+'">'+respLabel+'</div><pre class="'+(isErr?'err':'')+'">'+esc(respVal)+'</pre>'
    + '</div>';
  return d;
}
function renderColumn(c, label){
  const col = document.createElement('div'); col.className='col';
  const h = document.createElement('div'); h.className='lbl';
  h.textContent = label + ' · run ' + (c.run_id||'?');
  col.appendChild(h);
  const maxLat = Math.max(1, ...(c.interactions||[]).map(i=>i.latency_ms||0));
  (c.interactions||[]).forEach(i => col.appendChild(renderStep(i, maxLat)));
  return col;
}
const root = document.getElementById('root');
const primary = DATA.primary, secondary = DATA.secondary;
document.getElementById('subtitle').textContent =
  (secondary ? 'diff view · ' : 'timeline view · ') + (primary.interactions||[]).length + ' interactions';
if (secondary){
  root.className = 'twoup';
  root.appendChild(renderColumn(primary, 'A (' + (primary.meta&&primary.meta.model||'?') + ')'));
  root.appendChild(renderColumn(secondary, 'B (' + (secondary.meta&&secondary.meta.model||'?') + ')'));
} else {
  root.appendChild(renderColumn(primary, 'Timeline'));
}
let totals = 'Σ A: '+totalLatency(primary).toFixed(1)+'ms · '+totalTokens(primary)+' tokens';
if (secondary) totals += '    Σ B: '+totalLatency(secondary).toFixed(1)+'ms · '+totalTokens(secondary)+' tokens';
document.getElementById('totals').textContent = totals;
</script>
</body>
</html>
"""
