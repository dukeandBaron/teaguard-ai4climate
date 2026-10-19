/** Local UI controller: one request at a time, explicit recovery, server history. */
import {createApiClient} from './api.js';
import {createGraphView} from './graph.js';
import {renderEvidence, renderData} from './views.js';
import {inspectionMarkdown, downloadRecord} from './export.js';

const $ = id => document.getElementById(id);
const make = (tag, text, className) => {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
};
const number = (value, places = 1) => Number(value).toFixed(places);
const labels = {unknown:'未知',moist:'湿润',dry:'偏干',present:'有遮阴',absent:'无遮阴',young_growth:'嫩梢阶段',mature:'成熟阶段',Tieguanyin:'铁观音',Longjing:'龙井（情境声明）'};
const flagLabels = {TASK_BASIS_CHANGED:'相关输入或依据已更新，原勾选事项需要重新核查',EXPLANATION_REJECTED:'解释中的数值或引用不一致，已回退',CONTEXT_CONFLICT_RETAINED:'气象与土壤反馈存在待核实差异'};
const caseNames = {N01:'湿润土壤与高温',N02:'偏干反馈与联合核查',N03:'未知条件保留',N04:'遮阴成对对照',N05:'生长阶段三种对照',N06:'跨作物处理拒用',N07:'方法与测量终点',N08:'时间、土层与尺度冲突',N09:'数值与引用冲突回退',N10:'任务去重与模拟反馈'};
const controls = ['weather-mode','date','soil','shade','growth','cultivar','soil-time','soil-depth','soil-method','species','setting','treatment','endpoint','claim'];
const api = createApiClient();
const graph = createGraphView({$, labels});
let bootstrap, current, versions = [];
let stale = false, busy = false, activeCase = 'LOCAL_CONTEXT', exportMarkdown = '';

function switchView(view) {
  document.querySelectorAll('.view').forEach(element => element.hidden = element.id !== view);
  document.querySelectorAll('.nav').forEach(element => {
    const selected = element.dataset.view === view;
    element.classList.toggle('active', selected);
    if (selected) element.setAttribute('aria-current', 'page');
    else element.removeAttribute('aria-current');
  });
  window.scrollTo({top:0, behavior:'instant'});
}

function setBusy(value) {
  busy = value;
  for (const id of [...controls, 'update', 'load-case', 'case', 'new-record']) $(id).disabled = value;
  $('date').disabled = value || $('weather-mode').value === 'synthetic';
  $('preview').disabled = value || stale || !current;
  $('reset-graph').disabled = value || !current;
  document.querySelectorAll('#tasks input, #version-list button').forEach(element => element.disabled = value || stale);
  $('workspace').setAttribute('aria-busy', String(value));
}

function showError(error) {
  $('status').textContent = error.message + (error.requestId ? ` 请求编号：${error.requestId}` : '');
  if (['RECORD_NOT_FOUND','VERSION_INCOMPATIBLE'].includes(error.code)) {
    $('status').textContent += ' 如需继续，可点击“独立分析”，明确开始无前序关联的记录。';
  }
}

async function run(operation) {
  if (busy) return;
  setBusy(true);
  try { await operation(); }
  catch (error) { showError(error); }
  finally { setBusy(false); }
}

function fillControls(context, mode, date) {
  $('weather-mode').value = mode;
  $('date').value = date;
  for (const [id, key] of [['soil','soil'],['shade','shade'],['growth','growth_stage'],['cultivar','cultivar'],['species','species'],['setting','setting'],['treatment','treatment'],['endpoint','endpoint'],['claim','requested_claim'],['soil-method','soil_method']]) {
    $(id).value = context[key] || 'unknown';
  }
  $('soil-depth').value = context.soil_depth_cm ?? '';
  $('soil-time').value = context.soil_time ? new Date(new Date(context.soil_time).getTime() - new Date(context.soil_time).getTimezoneOffset()*60000).toISOString().slice(0,16) : '';
  $('date').disabled = mode === 'synthetic';
}

function collectRequest(independent) {
  const depth = $('soil-depth').value === '' ? null : Number($('soil-depth').value);
  if (depth !== null && (!Number.isFinite(depth) || depth < 0 || depth > 300)) throw new Error('土层深度应在0至300厘米之间。');
  const nullable = id => $(id).value === 'unknown' ? null : $(id).value;
  return {
    weather_mode:$('weather-mode').value, date:$('date').value, case_id:activeCase,
    previous_version_id:independent ? null : current?.version_id,
    context:{soil:nullable('soil'),shade:$('shade').value,growth_stage:$('growth').value,cultivar:nullable('cultivar'),species:$('species').value,setting:$('setting').value,treatment:$('treatment').value,endpoint:$('endpoint').value,requested_claim:$('claim').value,soil_method:nullable('soil-method'),soil_depth_cm:depth,soil_time:$('soil-time').value ? new Date($('soil-time').value).toISOString() : null}
  };
}

function markStale() {
  if ($('weather-mode').value === 'synthetic') $('date').value = '2025-07-15';
  stale = true;
  activeCase = 'LOCAL_CONTEXT';
  setBusy(busy);
  $('status').textContent = '条件已更改，请点击“更新核查依据”；原记录仍保留。';
}

function remember(result) {
  versions = versions.filter(version => version.id !== result.version_id);
  versions.push({id:result.version_id,date:result.weather.date,soil:result.context.soil ?? 'unknown',tasks:result.tasks.length});
  versions = versions.slice(-20);
  $('version-count').textContent = `· 最近${versions.length}条本机记录`;
  const host = $('version-list');
  host.replaceChildren();
  for (const version of [...versions].reverse()) {
    const row = make('div', undefined, 'version-row');
    row.append(make('span', `${version.date} · ${labels[version.soil] || version.soil} · ${version.tasks}项`), make('code',version.id.slice(0,12)));
    const button = make('button','查看','text-button');
    button.addEventListener('click', () => run(async () => {
      const record = await api('/api/record?version_id=' + encodeURIComponent(version.id));
      fillControls(record.context, record.weather_mode, record.weather.date);
      activeCase = record.case_id || 'LOCAL_CONTEXT';
      render(record);
      $('status').textContent = '已查看本机保留版本；地块反馈仍为AI情境。';
    }));
    row.append(button);
    host.append(row);
  }
}

function renderTasks() {
  $('task-count').textContent = `· ${current.tasks.length}项`;
  $('tasks').replaceChildren();
  for (const task of current.tasks) {
    const row = make('article', undefined, 'task-row');
    const check = make('input');
    check.type = 'checkbox';
    check.id = task.task_id;
    check.checked = task.status === 'SIMULATED_COMPLETION';
    row.classList.toggle('done', check.checked);
    const body = make('div', undefined, 'task-body');
    const label = make('label', task.title);
    label.htmlFor = check.id;
    body.append(label,make('p',task.next_check),make('small',check.checked ? '模拟反馈：已勾选' : '待核实 · 工程核查事项'));
    const citations = make('div',undefined,'task-citations');
    for (const id of task.evidence_card_ids) {
      if (!current.applicability.some(card => card.card_id === id)) continue;
      const button = make('button',id + ' · 查看依据');
      button.addEventListener('click', () => {switchView('evidence'); $('card-' + id)?.scrollIntoView({block:'center',behavior:'smooth'});});
      citations.append(button);
    }
    body.append(citations);
    check.addEventListener('change', () => {
      if (stale || busy) return renderTasks();
      const completed = check.checked;
      run(async () => {
        try {
          const result = await api('/api/feedback',{version_id:current.version_id,task_id:task.task_id,completed});
          render(result);
          $('status').textContent = '已保存模拟反馈版本，前序记录仍保留。';
        } catch (error) { renderTasks(); throw error; }
      });
    });
    row.append(check,body);
    $('tasks').append(row);
  }
}

function render(result) {
  current = result;
  stale = false;
  $('source-label').textContent = result.data_role_label;
  $('heat-point').textContent = number(result.weather.heat_point_c) + '°C';
  $('heat-range').textContent = `${number(result.weather.heat_lower_c)}—${number(result.weather.heat_upper_c)}°C · 回放参考区间`;
  $('balance-value').textContent = (result.weather.reference_balance_mm > 0 ? '+' : '') + number(result.weather.reference_balance_mm) + ' mm';
  $('explanation').textContent = result.explanation;
  $('result-title').textContent = result.claim_review.status === 'WITHHELD' ? '先核对证据范围，再判断能否引用。' : result.context.soil === 'moist' ? '天气与土壤反馈，先保留差异。' : result.context.soil === 'dry' ? '把热与水分条件放在一起核查。' : '先补齐现场条件，再形成判断。';
  $('next-question').textContent = result.questions[0]?.question || '现有条件仍需现场核实';
  $('flags').replaceChildren(...result.flags.map(flag => make('span',flagLabels[flag] || flag,'flag')));
  renderTasks();
  graph.render(result);
  renderEvidence(result,$,make);
  remember(result);
}

async function update(independent = false) {
  await run(async () => {
    stale = true;
    const request = collectRequest(independent);
    const previousHash = current?.weather_hash;
    $('status').textContent = '正在读取本机资料并更新核查依据…';
    const result = await api('/api/analyze', request);
    render(result);
    $('status').textContent = independent ? '已开始无前序关联的独立分析。' : (previousHash === result.weather_hash ? '天气数值保持一致，' : '') + '情境、依据与任务已更新。';
  });
}

function renderProgress(status) {
  const host = $('project-progress');
  for (const item of status.capabilities) {
    const article = make('article');
    article.append(make('strong',item.label),make('span',item.status === 'IMPLEMENTED_LOCAL' ? '本机已实现' : item.status === 'FROZEN_BASELINE' ? '原冻结基线' : item.status === 'SIMULATION_ONLY' ? 'AI模拟范围' : '尚未核验'),make('p',item.detail));
    host.append(article);
  }
}

controls.forEach(id => $(id).addEventListener('input', markStale));
document.querySelectorAll('.nav').forEach(element => element.addEventListener('click', () => switchView(element.dataset.view)));
$('update').addEventListener('click', () => update());
$('new-record').addEventListener('click', () => update(true));
$('reset-graph').addEventListener('click', () => graph.reset());
$('load-case').addEventListener('click', async () => {
  if (busy) return;
  const id = $('case').value;
  fillControls({...bootstrap.default.context,soil:null,shade:'unknown',growth_stage:'unknown',cultivar:null,requested_claim:'context_review',...bootstrap.presets[id]},'synthetic','2025-07-15');
  activeCase = id;
  await update();
});
$('preview').addEventListener('click', () => {
  if (stale || busy) return;
  exportMarkdown = inspectionMarkdown(current);
  $('export-text').value = exportMarkdown;
  $('export-dialog').showModal();
});
$('close-export').addEventListener('click', () => $('export-dialog').close());
$('download-md').addEventListener('click', () => downloadRecord(exportMarkdown,`茶候_自然情境_${current.version_id}.md`,'text/markdown;charset=utf-8'));
$('download-json').addEventListener('click', () => downloadRecord(JSON.stringify(current,null,2),`TeaGuard_Nature_${current.version_id}.json`,'application/json;charset=utf-8'));

async function init() {
  setBusy(true);
  try {
    bootstrap = await api('/api/bootstrap');
    versions = [...bootstrap.records].reverse();
    $('date').min = bootstrap.dates[0];
    $('date').max = bootstrap.dates.at(-1);
    fillControls(bootstrap.default.context,'historical','2025-07-15');
    renderData(bootstrap,$,make,number,caseNames);
    renderProgress(bootstrap.project_status);
    render(bootstrap.default);
    $('status').textContent = '已载入本机历史回放；地块条件为AI情境，记录保存在本机。';
  } catch (error) {showError(error); stale = true;}
  finally {setBusy(false);}
}
init();
