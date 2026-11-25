// 대한항공 보너스 좌석 일괄 조회 — 평소 쓰는 크롬용 (자동화 브라우저가 막힐 때 대안)
// 사용법: 로그인한 상태로 보너스 좌석 조회 페이지에서 F12 → Console 탭 → 이 파일 내용 전체 붙여넣기 → Enter
//        (처음 한 번은 크롬이 붙여넣기를 막으면 'allow pasting' 이라고 입력 후 Enter)
// 끝나면 kal_bonus_*.json 파일이 다운로드됩니다 → python -m kal_award import <그 파일>
(async () => {
  const ORIGIN = 'ICN', DEST = 'CDG', FROM = '2027-08-01', DELAY_MS = 2000;
  const API = '/api/hmp/bonusSeatView/bonusSeatView';

  // 1) 세션 헤더(ksessionId)를 사이트 자신의 요청에서 읽기
  let ks = null;
  const oSet = XMLHttpRequest.prototype.setRequestHeader;
  XMLHttpRequest.prototype.setRequestHeader = function (k, v) {
    if (String(k).toLowerCase() === 'ksessionid') ks = v;
    return oSet.apply(this, arguments);
  };
  const oFetch = window.fetch;
  window.fetch = function (input, init) {
    try {
      const h = new Headers((init && init.headers) || (input && input.headers) || {});
      if (h.get('ksessionId')) ks = h.get('ksessionId');
    } catch (e) {}
    return oFetch.apply(this, arguments);
  };
  console.log('%c[kal] 페이지에서 [조회] 버튼을 한 번 눌러 주세요 (세션 확인용)', 'color:#06c;font-weight:bold');
  for (let i = 0; i < 120 && !ks; i++) await new Promise(r => setTimeout(r, 1000));
  XMLHttpRequest.prototype.setRequestHeader = oSet; window.fetch = oFetch;
  if (!ks) { console.error('[kal] 세션을 찾지 못했습니다. 로그인 후 다시 실행하세요.'); return; }

  // 2) 방향별로 월 단위 조회, 예약 가능 기간 끝에서 멈춤
  const ymd = d => d.toISOString().slice(0, 10).replace(/-/g, '');
  const records = [];
  for (const [o, t] of [[ORIGIN, DEST], [DEST, ORIGIN]]) {
    let [y, m] = FROM.split('-').map(Number);
    for (let i = 0; i < 14; i++) {
      if (records.length) await new Promise(r => setTimeout(r, DELAY_MS));
      const first = new Date(Date.UTC(y, m - 1, 1));
      const body = JSON.stringify({arrivalAirport: t, departureAirport: o, departureDate: ymd(first)});
      const r = await oFetch(API, {method: 'POST', credentials: 'same-origin', body,
        headers: {'Content-Type': 'application/json', 'Accept': 'application/json',
                  channel: 'pc', ksessionId: ks, timestamp: String(Date.now())}});
      const text = await r.text();
      let js = null; try { js = JSON.parse(text); } catch (e) {}
      if (r.status !== 200 || !js || !js.flightList) {
        console.error(`[kal] ${o}->${t} ${y}-${m}: HTTP ${r.status}`, text.slice(0, 300)); break;
      }
      records.push({url: location.origin + API, method: 'POST', status: r.status, resource_type: 'fetch',
                    request_post_data: body, response_json: js, response_text_preview: null});
      const days = js.flightList.map(d => d.departureDate).sort();
      const monthEnd = ymd(new Date(Date.UTC(y, m, 0)));
      console.log(`[kal] ${o}->${t} ${y}-${String(m).padStart(2, '0')}: ${days.length}일`);
      if (!days.length || days[days.length - 1] < monthEnd) break;
      [y, m] = m === 12 ? [y + 1, 1] : [y, m + 1];
    }
  }
  // 3) 파일로 저장
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([JSON.stringify({records}, null, 1)], {type: 'application/json'}));
  a.download = `kal_bonus_${ORIGIN}_${DEST}_${Date.now()}.json`;
  a.click();
  console.log(`%c[kal] 완료: ${records.length}건 → ${a.download}`, 'color:green;font-weight:bold');
})();
