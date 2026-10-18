'use strict';
const $ = id => document.getElementById(id);
let current = null, bootstrap = null, stale = false, busy = false, revealed = false, noteForDownload = null;
const controlIds = ['date','scenario','soil','heat','balance'];
function el(tag, text, cls) { const n = document.createElement(tag); if(text !== undefined) n.textContent = text; if(cls) n.className = cls; return n; }
function num(value, places=1) { return Number(value).toFixed(places); }
function percent(value) { return value === null ? '—' : num(value*100,1)+'%'; }
function readArgs() { return {date:$('date').value,scenario:$('scenario').value,soil:$('soil').value,heat_threshold:Number($('heat').value),balance_threshold:Number($('balance').value)}; }
function savedChecks() { try { const a=JSON.parse(localStorage.getItem('teaguard-checks-'+current.run_id)||'[]'); return new Set(Array.isArray(a)?a.filter(x=>typeof x==='string').slice(0,20):[]); } catch { return new Set(); } }
function updateCount() { $('done-count').textContent = document.querySelectorAll('#actions input:checked').length+' 项已复核'; }
function scenarioNote() { $('scenario-note').textContent = {historical:'保持公开数据原值。',hot_dry:'AI模拟：过去14天气温 +3°C，降雨 ×0.25。只检查输入敏感性。',wet:'AI模拟：过去14天气温 −1°C，降雨 ×1.8。只检查输入敏感性。'}[$('scenario').value]; $('heat-value').textContent=$('heat').value+'°C'; $('balance-value').textContent=$('balance').value+' mm'; }
function drawWeather(rows, threshold) {
  const host=$('weather-chart'); host.replaceChildren();
  const NS='http://www.w3.org/2000/svg'; const W=720,H=210,L=39,R=42,T=20,B=35;
  const svg=document.createElementNS(NS,'svg'); svg.setAttribute('viewBox',`0 0 ${W} ${H}`); svg.setAttribute('role','img'); svg.setAttribute('aria-label',`判断前14天天气，最高气温范围${num(Math.min(...rows.map(r=>r.tmax)))}至${num(Math.max(...rows.map(r=>r.tmax)))}摄氏度`);
  function shape(tag, attrs, text) {const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;svg.append(n);return n;}
  const min=Math.floor((Math.min(...rows.map(r=>r.tmax),threshold)-3)/5)*5;
  const max=Math.ceil((Math.max(...rows.map(r=>r.tmax),threshold)+3)/5)*5;
  const rainMax=Math.max(10,...rows.map(r=>r.rain));
  const x=i=>L+i*(W-L-R)/(rows.length-1), y=v=>T+(max-v)/(max-min)*(H-T-B);
  for(let v=min;v<=max;v+=5){shape('line',{x1:L,y1:y(v),x2:W-R,y2:y(v),stroke:'#e6eee8','stroke-width':1});shape('text',{x:L-8,y:y(v)+3,fill:'#788b83','font-size':10,'text-anchor':'end'},v+'°');}
  shape('text',{x:W-R+7,y:T+3,fill:'#7893a0','font-size':9},num(rainMax,0)+'mm');
  rows.forEach((r,i)=>{const rh=r.rain/rainMax*(H-T-B)*.7;shape('rect',{x:x(i)-7,y:H-B-rh,width:14,height:rh,rx:2,fill:'#aecbd6',opacity:.7});if(i%3===0||i===rows.length-1)shape('text',{x:x(i),y:H-11,fill:'#788b83','font-size':10,'text-anchor':'middle'},r.date.slice(5));});
  shape('line',{x1:L,y1:y(threshold),x2:W-R,y2:y(threshold),stroke:'#bc8b4f','stroke-width':1,'stroke-dasharray':'5 5'});
  shape('polyline',{points:rows.map((r,i)=>`${x(i)},${y(r.tmax)}`).join(' '),fill:'none',stroke:'#216858','stroke-width':2.5,'stroke-linejoin':'round'});
  rows.forEach((r,i)=>shape('circle',{cx:x(i),cy:y(r.tmax),r:i===rows.length-1?4:2.5,fill:'#216858',stroke:'#fff','stroke-width':1.5}));
  host.append(svg);
}
function renderActions() {
  const selected=savedChecks(); const host=$('actions');host.replaceChildren();
  for(const action of current.actions){const row=el('div',undefined,'action');const input=el('input');input.type='checkbox';input.id='action-'+action.id;input.dataset.action=action.id;input.checked=selected.has(action.id);row.classList.toggle('done',input.checked);const label=el('label');label.htmlFor=input.id;label.append(el('span',action.title,'action-title'),el('p',action.reason));const meta=el('div',undefined,'action-meta');meta.append(el('span',action.window),el('span',action.priority));label.append(meta);input.addEventListener('change',()=>{row.classList.toggle('done',input.checked);const ids=[...document.querySelectorAll('#actions input:checked')].map(n=>n.dataset.action);try{localStorage.setItem('teaguard-checks-'+current.run_id,JSON.stringify(ids));}catch{}updateCount();});row.append(input,label);host.append(row);}
  updateCount();
}
function renderVerification() {
  const host=$('verification');host.replaceChildren();host.hidden=!revealed;
  $('reveal').textContent=revealed?'收起事后天气':'展开事后天气';$('reveal').setAttribute('aria-expanded',String(revealed));
  if(!revealed)return;
  if(!current.verification){host.append(el('p','当前为AI模拟输入，没有对应的真实未来结果；不与历史实际天气混算效果。'));return;}
  const actual=current.verification.actual_targets;
  host.append(el('p',`事后核对：随后3日实际最高气温 ${num(actual[0])}°C；随后7日参考收支 ${num(actual[1])}mm。`, 'verification-target'));
  host.append(el('p','以下为回放日期之后的公开再分析资料，仅供事后核对，不进入本次预测特征。'));
  host.append(el('p',current.verification.future_weather.map(r=>`${r.date.slice(5)}：${num(r.tmax)}°C / 降雨${num(r.rain)}mm`).join('；')));
}
function render(result) {
  current=result;const heat=result.outlook[0];const sim=result.scenario!=='historical';
  $('evidence-tag').textContent=sim?'AI模拟 · 输入敏感性':'公开数据 · 历史回放';$('evidence-tag').classList.toggle('sim',sim);
  $('heat-estimate').textContent=num(heat.value);$('heat-interval').textContent=`${sim?'历史误差参考':'校准区间'} ${num(heat.lower)}—${num(heat.upper)}°C`;
  $('balance-estimate').textContent=(result.recent.balance_7d>0?'+':'')+num(result.recent.balance_7d);
  $('rain-detail').textContent=`参考蒸散 ${num(result.recent.et0_7d)} − 降雨 ${num(result.recent.rain_7d)} mm`;
  const hot=heat.upper>=heat.threshold;const dry=result.recent.balance_7d>=readArgs().balance_threshold;
  $('headline').textContent=hot&&dry?'先查热暴露，再核对土壤。':hot?'把高温复核放在前面。':dry?'近期少雨，先看土壤记录。':'保留记录，按常规巡查。';
  $('headline-detail').textContent=`${result.date} 的判断 · ${sim?'模拟输入，检查建议如何变化。':'气温区间'+(heat.status==='uncertain'?'跨过':'未跨过')+'所选阈值，结合当地预报与现场复核。'}`;
  drawWeather(result.history,heat.threshold);renderActions();renderVerification();
}
function metricTable(target, title, unit) {
  const group=el('div',undefined,'metric-group');group.append(el('h2',title));const table=el('table',undefined,'metric-table');
  const thead=el('thead'),hr=el('tr');['方法',`平均绝对误差 ${unit}`,`均方根误差 ${unit}`,'事件召回','误报 / 漏报'].forEach(t=>hr.append(el('th',t)));thead.append(hr);table.append(thead);const tbody=el('tbody');
  const names={selected:'验证集选出的模型',persistence:'延续近期天气',seasonal:'历史季节均值'};
  for(const k of ['seasonal','persistence','selected']){const m=bootstrap.evaluation.test_metrics[target][k];const tr=el('tr',undefined,k==='selected'?'row-selected':'');[names[k],num(m.mae,2),num(m.rmse,2),percent(m.recall),`${m.false_positive} / ${m.false_negative}`].forEach(v=>tr.append(el('td',v)));tbody.append(tr);}table.append(tbody);group.append(table);return group;
}
function renderEvidence() {
  const report=bootstrap.evaluation,host=$('metrics');host.replaceChildren();host.append(metricTable('heat_3d','未来3日最高气温 · 358个测试起点','°C'));
  const m=report.test_metrics.heat_3d;const improvement=(1-m.selected.mae/m.persistence.mae)*100;
  host.append(el('p',`平均绝对误差相对延续天气减少 ${num(improvement)}%。按35°C判断高温时，点预测召回 ${percent(m.selected.recall)}；低平均误差不等于所有高温都能识别。`,'small-note'));
  const policy=report.screening_policy.heat_35C_test;
  host.append(el('p',`工作台采用区间上界触发“人工复核”，在本次测试中召回 ${percent(policy.recall)}，误报 ${policy.false_positive} 个窗口、漏报 ${policy.false_negative} 个窗口。气温校准区间的实测覆盖为 ${percent(report.interval.test_coverage.heat_3d)}。`,'small-note'));
  host.append(metricTable('balance_7d','七日参考收支 · 探索性结果，未进入巡查决策','mm'));
  const p=bootstrap.provenance;const dl=$('provenance');dl.replaceChildren();
  for(const [k,v] of [['时间范围',`${p.start} — ${p.end} / ${p.rows}天`],['请求点','30.201°N, 120.103°E（梅家坞周边示意）'],['返回网格',`${p.returned_grid.latitude}°N, ${p.returned_grid.longitude}°E / ${p.model}`],['本地数据摘要',p.csv_sha256],['数据来源',p.provider],['资料获取时间',p.downloaded_at]])dl.append(el('dt',k),el('dd',v));
}
async function analyze() {
  if(busy)return;busy=true;$('analyze').disabled=true;controlIds.forEach(id=>$(id).disabled=true);$('status').textContent='正在计算并保留来源依据…';
  const abort=new AbortController();const timer=setTimeout(()=>abort.abort(),20000);
  try{const response=await fetch('/api/analyze',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(readArgs()),signal:abort.signal});const result=await response.json();if(!response.ok)throw new Error(result.error||'计算未完成');render(result);stale=false;$('export').disabled=false;$('status').textContent='已更新 · '+(result.scenario==='historical'?'公开数据回放':'AI模拟输入');try{localStorage.setItem('teaguard-controls',JSON.stringify(readArgs()));}catch{}}
  catch(error){stale=true;$('export').disabled=true;$('status').textContent=error.name==='AbortError'?'计算超时，请确认本地服务后重试。':error.message;}
  finally{clearTimeout(timer);busy=false;$('analyze').disabled=false;controlIds.forEach(id=>$(id).disabled=false);}
}
function exportNote() {
  if(!current||stale||busy)return;const result=current,heat=result.outlook[0];const checked=new Set([...document.querySelectorAll('#actions input:checked')].map(n=>n.dataset.action));
  const lines=['# 茶候 · 本次巡查单','',`判断日期：${result.date}`,`地点：${result.place}`,`资料类型：${result.scenario_label}`,`记录编号：${result.run_id}`,'',`3日最高气温展望：${num(heat.value)}°C；校准区间 ${num(heat.lower)}—${num(heat.upper)}°C。`,`过去7日参考收支：${num(result.recent.balance_7d)}mm（ET₀−降雨）。`,`当前情景阈值：高温${heat.threshold}°C；参考收支${readArgs().balance_threshold}mm。`,`模拟现场墒情：${{unknown:'尚未记录',dry:'偏干',moist:'湿润'}[result.soil_simulation]}`,'','## 巡查与复核'];
  for(const a of result.actions)lines.push(`- [${checked.has(a.id)?'x':' '}] ${a.title}`,`  - 时间：${a.window}；依据：${a.reason}`);
  lines.push('','## 来源与解释',`数据：Open-Meteo Historical Weather API / ERA5，2015—2025，CC BY4.0。`,`CSV SHA-256：${result.data_sha256}`,`输入情景：${JSON.stringify(result.scenario_assumptions)}`,'',...result.boundaries.map(t=>'- '+t),'','勾选表示本地演示者记录的复核状态，不构成真实农户试用或现场成效证明。');
  noteForDownload={content:lines.join('\n'),filename:`茶候_巡查单_${result.date}_${result.scenario}.md`};$('export-text').value=noteForDownload.content;$('export-dialog').showModal();$('status').textContent='已生成巡查单预览，包含假设与数据来源。';
}
function downloadNote(){if(!noteForDownload)return;const blob=new Blob([noteForDownload.content],{type:'text/markdown;charset=utf-8'});const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=noteForDownload.filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(link.href),1000);}
document.querySelectorAll('.nav').forEach(button=>button.addEventListener('click',()=>{document.querySelectorAll('.view').forEach(v=>v.hidden=v.id!==button.dataset.view);document.querySelectorAll('.nav').forEach(n=>{const active=n===button;n.classList.toggle('active',active);if(active)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');});window.scrollTo({top:0,behavior:'instant'});}));
controlIds.forEach(id=>$(id).addEventListener('input',()=>{scenarioNote();stale=true;$('export').disabled=true;$('status').textContent='参数已更改，请点击“更新巡查依据”。';}));
$('analyze').addEventListener('click',analyze);$('export').addEventListener('click',exportNote);$('reveal').addEventListener('click',()=>{revealed=!revealed;renderVerification();});
$('close-export').addEventListener('click',()=>$('export-dialog').close());$('download-export').addEventListener('click',downloadNote);
async function init(){try{const response=await fetch('/api/bootstrap');if(!response.ok)throw new Error('无法载入演示资料');bootstrap=await response.json();$('date').min=bootstrap.date_range[0];$('date').max=bootstrap.date_range[1];renderEvidence();render(bootstrap.default);scenarioNote();$('status').textContent='已载入公开天气回放';let saved=null;try{saved=JSON.parse(localStorage.getItem('teaguard-controls')||'null');}catch{}if(saved&&typeof saved==='object'&&typeof saved.date==='string'&&saved.date>=bootstrap.date_range[0]&&saved.date<=bootstrap.date_range[1]&&['historical','hot_dry','wet'].includes(saved.scenario)&&['unknown','dry','moist'].includes(saved.soil)&&Number.isFinite(saved.heat_threshold)&&saved.heat_threshold>=28&&saved.heat_threshold<=42&&Number.isFinite(saved.balance_threshold)&&saved.balance_threshold>=5&&saved.balance_threshold<=50){$('date').value=saved.date;$('scenario').value=saved.scenario;$('soil').value=saved.soil;$('heat').value=saved.heat_threshold;$('balance').value=saved.balance_threshold;scenarioNote();await analyze();}}catch(error){$('fatal').hidden=false;$('fatal').textContent=error.message+'。请确认本地服务正在运行，再刷新页面。';$('analyze').disabled=true;$('export').disabled=true;}}
init();
