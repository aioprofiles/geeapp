"""HTML widgets (Bot API 10.4). Hard limits from the docs: <=32768 bytes HTML and <=4096 bytes after zlib level 9,
no network inside the widget, state strings <=1024 bytes, request data <=64 bytes. Widgets cannot hold audio/video:
audio goes out as a normal audio message, video/full sync lives in the Mini App."""
import zlib

KARAOKE = """<style>body{margin:0;padding:10px 12px}.t{font-weight:600}.h{color:var(--tg-theme-hint-color);font-size:13px}
.l{text-align:center;padding:8px 0;min-height:84px}.l div{min-height:1.4em;line-height:1.4}#c{font-size:1.2em;font-weight:600;color:var(--tg-theme-accent-text-color)}
.b{height:3px;border-radius:2px;margin:4px 0 8px;background:var(--tg-theme-secondary-bg-color)}.b i{display:block;height:3px;width:0;background:var(--tg-theme-button-color)}
.r{display:flex;gap:5px;justify-content:center;flex-wrap:wrap}button{padding:4px 9px}</style>
<div class=t id=t></div><div class=h id=a></div>
<div class=l><div class=h id=p></div><div id=c></div><div class=h id=n></div></div>
<div class=b><i id=f></i></div>
<div class=r><button id=m>-0.5</button><button id=g>&#9654;</button><button id=u>+0.5</button><button id=d>&#127911;</button><button id=v>&#127916;</button><button id=w>&#11015;</button></div>
<div class=h id=s></div>
<script>
const W=window.TelegramWidget,$=i=>document.getElementById(i);
let P={},L=[],R=-1,E=0,pos=0,on=0,t0=Date.now(),ask=0;
const J=s=>{try{return JSON.parse(s)}catch(e){return null}};
function rd(){if(!W)return;P=J(W.publicData)||P;const c=J(W.chatData);if(c&&c.r>R){R=c.r;L=c.L;E=c.e}$('t').textContent=P.t||'';$('a').textContent=P.a||''}
function req(d){if(!W)return;$('s').textContent='...';W.request(d).then(r=>{$('s').textContent=r.result||''},e=>{$('s').textContent=e.code})}
function dr(){let i=-1;for(let k=0;k<L.length;k++)if(L[k][0]<=pos)i=k;const g=k=>L[k]?L[k][1]:'';
$('p').textContent=g(i-1);$('c').textContent=g(i);$('n').textContent=g(i+1);$('f').style.width=Math.min(100,P.d?pos/P.d*100:0)+'%'}
setInterval(()=>{const n=Date.now();if(on)pos+=(n-t0)/1e3;t0=n;dr();const e=L.length?L[L.length-1][0]:0;
if(on&&!E&&L.length&&pos>e-8&&n-ask>6e3){ask=n;req('m:'+e)}},250);
$('g').onclick=()=>{on=!on;t0=Date.now();$('g').innerHTML=on?'&#10074;&#10074;':'&#9654;'};
$('m').onclick=()=>{pos=Math.max(0,pos-.5)};$('u').onclick=()=>{pos+=.5};
$('d').onclick=()=>req('a');$('w').onclick=()=>req('dl');
$('v').onclick=()=>{if(W&&P.u)W.openTelegramLink(P.u)};
if(W){W.onEvent('chatDataChanged',rd);W.onEvent('publicDataChanged',rd)}
rd();
</script>"""

BEAT = """<style>body{margin:0;padding:10px 12px;text-align:center}.h{color:var(--tg-theme-hint-color);font-size:13px}
#z{position:relative;height:34px;margin:10px 0;border-radius:8px;background:var(--tg-theme-secondary-bg-color)}
#x{position:absolute;left:44%;width:12%;top:0;bottom:0;border-radius:8px;background:var(--tg-theme-button-color);opacity:.35}
#d{position:absolute;top:7px;left:0;width:20px;height:20px;border-radius:50%;background:var(--tg-theme-accent-text-color)}
button{padding:8px 24px;font-size:1.1em}</style>
<div class=h id=s>Tap when the dot is in the bar</div><div id=z><div id=x></div><i id=d></i></div>
<button id=b>TAP</button><div id=o class=h></div>
<script>
const W=window.TelegramWidget,$=i=>document.getElementById(i);
let n=0,sc=0,t=0,sp=1.1,done=0;
const pos=()=>{const p=((Date.now()-t)/1e3*sp)%2;return p<1?p:2-p};
setInterval(()=>{$('d').style.left=(pos()*($('z').offsetWidth-20))+'px'},50);
$('b').onclick=()=>{
if(done){if(W)W.request('s:'+sc).then(r=>{$('o').textContent=r.result||'ok'},e=>{$('o').textContent=e.code});return}
const d=Math.abs(pos()-.5),p=d<.06?3:d<.15?2:d<.3?1:0;sc+=p;n++;sp+=.06;
$('o').textContent=['miss','ok','good','perfect'][p];$('s').textContent=n+'/20  score '+sc;
if(n>=20){done=1;$('b').textContent='Send score '+sc}};
</script>"""


def compressed_size(html: str) -> int:
    """Exactly how the server counts: zlib level 9."""
    return len(zlib.compress(html.encode("utf-8"), 9))


def check(html: str) -> tuple[int, int]:
    return len(html.encode("utf-8")), compressed_size(html)
