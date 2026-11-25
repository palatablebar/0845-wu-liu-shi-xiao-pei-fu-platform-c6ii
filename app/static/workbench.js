(function () {
  var state = { payload: null, kind: 'bars', run: null, approved: false };
  var $ = function (id) { return document.getElementById(id); };
  function esc(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (ch) {
      return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[ch];
    });
  }
  async function request(url, options) {
    var response = await fetch(url, Object.assign({headers: {'Content-Type': 'application/json'}}, options || {}));
    var data = await response.json().catch(function () { return {}; });
    if (!response.ok) throw new Error(data.error || ('HTTP ' + response.status));
    return data;
  }
  function setNotice(text) { $('notice').textContent = text || ''; }
  function renderIssues(data) {
    $('issue-count').textContent = data.issues.length + ' 条';
    $('issue-list').innerHTML = data.issues.length ? data.issues.map(function (item) {
      return '<li><span>' + esc(item.line || '-') + '</span><span>' + esc(item.key || '无主键') + '</span><code>' + esc(item.code) + '</code></li>';
    }).join('') : '<li class="empty">暂无异常</li>';
  }
  function renderBreakdown(items) {
    if (!items || !items.length) return '';
    return '<details><summary>' + items.length + ' 项</summary><ul>' + items.map(function (item) {
      return '<li>' + esc(item) + '</li>';
    }).join('') + '</ul></details>';
  }
  function renderRows(data) {
    var labels = Object.assign({label: '记录'}, state.resultColumns);
    var source = data.row_kind === 'source';
    var hasBreakdown = data.rows.some(function (row) { return row.breakdown && row.breakdown.length; });
    var keys = source ? state.inputColumns : Object.keys(labels).filter(function (key) {
      return data.rows.some(function (row) { return Object.hasOwn(row, key); });
    });
    $('row-count').textContent = source ? data.rows.length + ' 行预览' :
      data.summary.PASS + ' 通过 / ' + data.summary.REVIEW + ' 复核 / ' + data.summary.REJECT + ' 阻断';
    var tail = source ? '' : '<th>结论</th>' + (hasBreakdown ? '<th>计算分项</th>' : '');
    $('row-head').innerHTML = '<tr>' + keys.map(function (key) { return '<th>' + esc(labels[key] || key) + '</th>'; }).join('') + tail + '</tr>';
    $('row-body').innerHTML = data.rows.length ? data.rows.map(function (row) {
      var values = keys.map(function (key) { return '<td class="' + (typeof row[key] === 'number' ? 'num' : '') + '">' + esc(row[key]) + '</td>'; }).join('');
      var verdict = source ? '' : '<td><span class="verdict" data-v="' + esc(row.verdict) + '">' + esc(row.verdict || '') + '</span><br><small>' + esc(row.reason || '') + '</small></td>';
      var breakdown = hasBreakdown ? '<td>' + renderBreakdown(row.breakdown) + '</td>' : '';
      return '<tr>' + values + verdict + breakdown + '</tr>';
    }).join('') : '<tr><td class="empty" colspan="' + (keys.length + (source ? 0 : 1)) + '">没有可展示条目</td></tr>';
  }
  function renderLedger(data) {
    if (!data.ledger) { $('ledger-list').innerHTML = '<p class="empty">运行对账后显示</p>'; return; }
    var values = data.ledger;
    var counts = values.counts;
    $('ledger-list').innerHTML = [
      ['来源行', counts.input], ['采信行', counts.accepted], ['隔离行', counts.isolated],
      ['精确重复', counts.duplicates], ['忽略行', counts.ignored], ['无效暂停行', counts.invalid_pause || 0],
      ['其他整理隔离', counts.prepare_other || 0],
      ['入账行', counts.posted != null ? counts.posted : (counts.computed || 0)]
    ].map(function (row) { return '<div class="ledger-row"><span>' + row[0] + '</span><strong>' + row[1] + '</strong></div>'; }).join('') +
      '<div class="ledger-row"><span>' + esc(values.metric_field) + '</span><strong>' + esc(values.metric_total) + '</strong></div>' +
      values.checks.map(function (check) {
        return '<div class="ledger-row" title="' + esc(check.detail || '') + '"><span>' + esc(check.label) + '</span><strong class="' + (check.ok ? 'check-ok' : 'check-bad') + '">' + (check.ok ? '通过' : '异常') + '</strong></div>';
      }).join('');
  }
  function shortDigest(value) {
    return value ? String(value).slice(0, 12) : '--';
  }
  function renderVersion(data) {
    var source = data.source || {};
    var calc = data.calculation || {};
    var paused = (source.pauses || []).map(function (item) { return item.waybill_id + ':' + item.paused_hours; }).join(' ');
    var invalid = (source.invalid_pauses || []).map(function (item) { return item.waybill_id + '(' + item.code + ')'; }).join(' ');
    $('version-list').innerHTML = [
      ['来源摘要', '<code title="' + esc(source.digest) + '">' + esc(shortDigest(data.source_digest || source.digest)) + '</code>'],
      ['文件摘要', '<code title="' + esc(source.sha256) + '">' + esc(shortDigest(source.sha256)) + '</code>'],
      ['计算版本', '<code>' + esc(data.calc_version || calc.version || '--') + '</code>'],
      ['计算代次', calc.generation != null ? calc.generation : (data.generation != null ? data.generation : '--')],
      ['规则口径', esc(calc.algorithm || '--')],
      ['有效暂停', source.pause_valid != null ? source.pause_valid + ' 条 ' + esc(paused) : '--'],
      ['无效暂停', source.pause_invalid != null ? source.pause_invalid + ' 条 ' + esc(invalid) : '--']
    ].map(function (row) { return '<div class="ledger-row"><span>' + row[0] + '</span><strong>' + row[1] + '</strong></div>'; }).join('');
    var frozen = data.frozen || data.status === 'APPROVED';
    var label = frozen ? '已签发冻结' : (data.status === 'HELD' ? '已暂缓' : '草稿');
    $('freeze-state').textContent = label;
    $('freeze-state').className = 'hint ' + (frozen ? 'check-ok' : '');
  }
  function render(data) {
    state.payload = data;
    $('chart-label').textContent = Object.values(state.resultColumns)[0];
    $('m-input').textContent = data.counts.input;
    $('m-accepted').textContent = data.counts.accepted;
    $('m-isolated').textContent = data.counts.isolated + data.counts.duplicates;
    $('m-rejected').textContent = data.summary.REJECT;
    renderRows(data);
    renderIssues(data);
    renderLedger(data);
    renderVersion(data);
    window.renderChart($('chart'), data.chart && data.chart.length ? (state.kind || 'bars') : 'bars', data.chart || []);
  }
  function stageButtons(stages) {
    $('stage-nav').innerHTML = stages.map(function (stage, index) {
      return '<button type="button" data-stage="' + stage.id + '" aria-pressed="' + (index === 0 ? 'true' : 'false') + '">' + esc(stage.name) + '</button>';
    }).join('');
    Array.from(document.querySelectorAll('[data-stage]')).forEach(function (button) {
      button.addEventListener('click', function () {
        document.querySelectorAll('[data-stage]').forEach(function (other) { other.setAttribute('aria-pressed', String(other === button)); });
        loadStage(button.getAttribute('data-stage'));
      });
    });
  }
  async function loadStage(stage) {
    try {
      setNotice('');
      document.body.setAttribute('aria-busy', 'true');
      var payload = await request('/api/stages/' + stage, {method: 'POST', body: JSON.stringify({profile: $('profile').value})});
      render(payload);
    } catch (error) { setNotice(error.message); }
    finally { document.body.removeAttribute('aria-busy'); }
  }
  function parseCredentials() {
    var text = ($('credential').value || '').trim();
    if (!text) return null;
    var out = {};
    text.split(/[,，\n]+/).forEach(function (part) {
      var pair = part.split(/[:：]/);
      var key = (pair[0] || '').trim();
      if (!key) return;
      out[key] = (pair[1] || '').trim();
    });
    return out;
  }
  function applyRunState(run) {
    state.run = run;
    state.approved = run.status === 'APPROVED';
    render(run);
    $('run-status').textContent = run.status + ' · rev ' + run.revision + (run.generation ? ' · 代次 ' + run.generation : '');
    $('revision').textContent = 'rev ' + run.revision;
    $('sign').disabled = state.approved || (run.blockers && run.blockers.length > 0);
    $('hold').disabled = state.approved;
    $('credential-apply').disabled = state.approved;
    $('download').hidden = !state.approved;
    if (state.approved) $('download').href = '/api/runs/' + run.run_id + '/evidence';
  }
  async function runBatch() {
    try {
      setNotice('');
      $('run').disabled = true;
      var body = {profile: $('profile').value};
      var credentials = parseCredentials();
      if (credentials) body.credentials = credentials;
      var run = await request('/api/runs', {method: 'POST', body: JSON.stringify(body)});
      applyRunState(run);
      if (run.revalidated) setNotice('来源变化，草稿已重算至代次 ' + run.generation);
      else if (run.frozen) setNotice('该来源已签发，沿用原金额与来源摘要');
    } catch (error) { setNotice(error.message); }
    finally { $('run').disabled = false; }
  }
  async function addCredentials() {
    if (!state.run) return;
    var credentials = parseCredentials();
    if (!credentials) { setNotice('请填写暂停凭据'); return; }
    try {
      setNotice('');
      $('credential-apply').disabled = true;
      var result = await request('/api/runs/' + state.run.run_id + '/credentials', {
        method: 'POST', body: JSON.stringify({credentials: credentials})
      });
      applyRunState(result.run);
      if (result.recalculated) setNotice('凭据补齐，来源变化，草稿重算至代次 ' + result.run.generation);
      else if (result.reason === 'SIGNED_FROZEN') setNotice('批次已签发，保留原金额与来源摘要');
      else setNotice('凭据未改变来源摘要，沿用当前版本');
    } catch (error) { setNotice(error.message); }
    finally { $('credential-apply').disabled = state.approved; }
  }
  async function review(decision) {
    if (!state.run) return;
    try {
      var run = await request('/api/runs/' + state.run.run_id + '/review', {
        method: 'POST',
        body: JSON.stringify({decision: decision, comment: $('comment').value, expected_revision: state.run.revision})
      });
      applyRunState(run);
      $('sign').disabled = true;
      $('hold').disabled = true;
    } catch (error) { setNotice(error.message); }
  }
  async function boot() {
    try {
      var catalog = await request('/api/catalog');
      state.kind = catalog.chart;
      state.resultColumns = catalog.result_columns;
      state.inputColumns = catalog.columns;
      stageButtons(catalog.stages.slice(0, 5));
      document.querySelector('.rail-note').textContent = catalog.code + ' · ' + catalog.stages[6].name;
      await loadStage('intake');
    } catch (error) { setNotice(error.message); }
    $('run').addEventListener('click', runBatch);
    $('credential-apply').addEventListener('click', addCredentials);
    $('sign').addEventListener('click', function () { review('APPROVED'); });
    $('hold').addEventListener('click', function () { review('HELD'); });
    $('profile').addEventListener('change', function () {
      state.run = null; state.approved = false;
      $('sign').disabled = true; $('hold').disabled = true; $('credential-apply').disabled = true;
      $('download').hidden = true;
      $('run-status').textContent = '未执行批次'; $('revision').textContent = 'rev 0';
      loadStage('intake');
    });
  }
  document.addEventListener('DOMContentLoaded', boot);
})();
