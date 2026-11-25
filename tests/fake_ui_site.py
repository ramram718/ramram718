"""Local stand-in for the award-seat page, built from the UI described by a
regular user of the site (roles/names, loader, kds-button_1 that swallows
normal clicks, two bonusSeatView POSTs, tabs with day-button labels).
All data is synthetic."""
import json, calendar
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
STATE = {"logged_in": True, "posts": []}
P_OPEN = {"ICN": {3, 17}, "CDG": {12, 25}}   # prestige award open
U_OPEN = {5, 6, 17}                          # prestige upgrade open (must be ignored)
HTML = r"""<!doctype html><html><head><meta charset=utf-8><style>
kds-button_1{display:inline-block;position:relative;padding:6px 12px;border:1px solid #333}
kds-button_1 .shield{position:absolute;inset:0;z-index:5}  /* swallows normal clicks */
dialog{display:block} [hidden]{display:none!important}</style></head><body>
<div id=loader>진행중 잠시만 기다려 주세요.</div>
<div id=cookie style="position:fixed;inset:0;z-index:99;background:rgba(0,0,0,.4)"><div style="background:#fff;margin:200px auto;width:500px">
<p>더 편리한 이용을 위해 쿠키를 사용합니다</p><button onclick="document.getElementById('cookie').remove()">쿠키 설정</button>
<button onclick="document.getElementById('cookie').remove()">필수 쿠키만 허용</button><button onclick="document.getElementById('cookie').remove()">모두 허용</button></div></div>
<main id=main hidden><h1 id=title>보너스 좌석 조회</h1>
<button aria-label="From 출발지" onclick="openAp('from')">출발지</button>
<button aria-label="To 도착지" onclick="openAp('to')">도착지</button>
<button aria-label="탑승월 가는 달 오는 달" onclick="mon.hidden=false">탑승월</button>
<kds-button_1 id=search role=button aria-label="조회"><span>조회</span><span class=shield></span></kds-button_1>
<div id=result></div></main>
<div id=ap hidden role=dialog><input role=combobox id=apq oninput="opts()"><ul role=listbox id=apl></ul></div>
<div id=mon hidden role=dialog><div role=group aria-label=2027>
 <button>8월</button><button>9월</button><button>10월</button></div>
 <kds-button_1 id=sel role=button aria-label="선택"><span>선택</span><span class=shield></span></kds-button_1></div>
<script>
const AP={ICN:'서울/인천, 대한민국 ICN',CDG:'파리/샤를 드 골, 프랑스 CDG',NRT:'도쿄/나리타, 일본 NRT'};
let side, st={from:null,to:null,months:[]};
setTimeout(()=>{loader.hidden=true;main.hidden=false;if(location.search.includes('broken'))title.remove(),document.querySelector('[aria-label="From 출발지"]').remove()},3000);
function openAp(s){side=s;ap.hidden=false;apq.value='';apq.setAttribute('aria-label',s=='from'?'출발지 검색':'도착지 검색');apl.innerHTML=''}
function opts(){apl.innerHTML='';for(const[k,v]of Object.entries(AP)){if(v.includes(apq.value.toUpperCase())){const li=document.createElement('li');li.setAttribute('role','option');li.textContent=v;li.onclick=()=>{st[side]=k;ap.hidden=true};apl.append(li)}}}
document.querySelectorAll('[aria-label="2027"] button').forEach(b=>b.onclick=()=>st.months.push(2027*100+parseInt(b.textContent)));
for(const el of [search, sel]){el.addEventListener('click',e=>{ if(!e.isTrusted&&false)return; el.dataset.hit=1; (el===sel?()=>{mon.hidden=true}:doSearch)()})}
async function doSearch(){
  const [om,im]=st.months.slice(-2); const ymd=m=>String(m)+'01';
  const legs=[[st.from,st.to,om],[st.to,st.from,im]]; const res=[];
  for(const[o,t,m]of legs){const r=await fetch('/api/hmp/bonusSeatView/bonusSeatView',{method:'POST',headers:{'Content-Type':'application/json',ksessionId:'K',channel:'pc'},body:JSON.stringify({arrivalAirport:t,departureAirport:o,departureDate:ymd(m)})});res.push(r.ok?await r.json():null)}
  if(!res[0])return; result.innerHTML='<div role=tablist><button role=tab>가는 날</button><button role=tab>오는 날</button></div><div id=cal></div>';
  const tabs=result.querySelectorAll('[role=tab]'); const show=i=>{cal.innerHTML='';for(const d of res[i].flightList){const day=+d.departureDate.slice(6);const kinds=[...new Set(d.flightDetailList.filter(x=>x.availableSeat).map(x=>({E:'일반석 보너스',P:'프레스티지석 보너스',U:'프레스티지석 좌석승급'})[x.frontBookingClass]))];const b=document.createElement('button');const wd='일월화수목금토'[new Date(d.departureDate.slice(0,4),d.departureDate.slice(4,6)-1,day).getDay()];b.setAttribute('aria-label',`${day}일, ${wd}요일 ${kinds.join(' ')}`);b.textContent=day;cal.append(b)}};
  tabs[0].onclick=()=>show(0);tabs[1].onclick=()=>show(1);show(0)}
</script></body></html>"""
class H(BaseHTTPRequestHandler):
    def log_message(self,*a): pass
    def do_GET(self):
        self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.end_headers(); self.wfile.write(HTML.encode())
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers["Content-Length"]))); STATE["posts"].append(body)
        if not STATE["logged_in"]:
            self.send_response(401); self.end_headers(); self.wfile.write(b'{"code":"NEED_LOGIN"}'); return
        s=body["departureDate"]; y,m=int(s[:4]),int(s[4:6]); n=calendar.monthrange(y,m)[1]
        fl=[{"departureDate":f"{y}{m:02d}{d:02d}","flightDetailList":[
            {"departureTime":"12:05","flightNumber":"KE901","availableSeat":True,"bookingClass":"X","frontBookingClass":"E"},
            {"departureTime":"12:05","flightNumber":"KE901","availableSeat":d in P_OPEN[body["departureAirport"]],"bookingClass":"O","frontBookingClass":"P"},
            {"departureTime":"12:05","flightNumber":"KE901","availableSeat":d in U_OPEN,"bookingClass":"Z","frontBookingClass":"U"}]} for d in range(1,n+1)]
        out=json.dumps({"departureAirport":body["departureAirport"],"arrivalAirport":body["arrivalAirport"],"flightList":fl}).encode()
        self.send_response(200); self.send_header("Content-Type","application/json"); self.end_headers(); self.wfile.write(out)
srv=ThreadingHTTPServer(("127.0.0.1",0),H)
