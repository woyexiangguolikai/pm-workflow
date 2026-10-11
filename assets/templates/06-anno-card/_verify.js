// _verify.js —— 真实渲染校验（CDP）
// 项目红线：不证明判别力的检查等于没有检查。所以每条断言都要能变红。
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const WebSocket = require('ws');

const HERE = __dirname;
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const HTML = process.env.CARDVIEW_HTML || path.join(HERE, 'requirement-cards.html');
const OUT = process.env.CARDVIEW_PROBE_OUT || path.join(HERE, '_probe.json');
const PORT = 9333 + (process.pid % 500);

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

(async () => {
  const prof = path.join(HERE, '_mut', 'vp_' + process.pid);
  fs.mkdirSync(prof, { recursive: true });
  const ch = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    '--no-first-run', '--no-default-browser-check', '--disable-sync',
    '--disable-features=msEdgeIdentitySignIn,msSyncPromo',
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + prof,
    '--window-size=1600,1000',
    'file:///' + HTML.replace(/\\/g, '/'),
  ], { stdio: 'ignore' });

  await sleep(4000);
  let list = [];
  for (let i = 0; i < 40; i++) {
    try {
      list = await (await fetch('http://127.0.0.1:' + PORT + '/json/list')).json();
      if (list.find(t => t.type === 'page' && t.webSocketDebuggerUrl)) break;
    } catch (e) { }
    await sleep(500);
  }
  const t = list.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
  if (!t) { console.log('连不上 Edge'); process.exit(1); }

  const ws = new WebSocket(t.webSocketDebuggerUrl);
  let id = 0; const pend = new Map();
  const send = (m, q) => new Promise(r => {
    const i = ++id; pend.set(i, r);
    ws.send(JSON.stringify({ id: i, method: m, params: q || {} }));
  });
  const logs = [];
  ws.on('message', d => {
    const m = JSON.parse(d);
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id); }
    if (m.method === 'Runtime.exceptionThrown') {
      const ed = m.params.exceptionDetails || {};
      const desc = (ed.exception && (ed.exception.description || ed.exception.value)) || '';
      const st = (ed.stackTrace && ed.stackTrace.callFrames || [])
        .slice(0, 4)
        .map(f => `${f.functionName || '(anon)'}@${f.lineNumber + 1}:${f.columnNumber + 1}`)
        .join(' <- ');
      logs.push('EXC:' + (ed.text || '') + (desc ? ' | ' + String(desc).split('\n')[0] : '')
        + (st ? ' | ' + st : ''));
    }
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
      logs.push('ERR:' + JSON.stringify(m.params.args.map(a => a.value)));
    }
  });
  await new Promise(r => ws.on('open', r));
  await send('Runtime.enable');
  await send('Page.enable');
  await sleep(1800);

  const ev = async (e) => {
    const r = await send('Runtime.evaluate', { expression: e, returnByValue: true });
    return r && r.result ? r.result.value : undefined;
  };

  const R = {};
  R.errs = logs.slice();

  // ---- 静态计数
  R.counts = await ev(`JSON.stringify({
    cards: document.querySelectorAll('.card').length,
    pages: document.querySelectorAll('.pg').length,
    lanes: document.querySelectorAll('.lane').length,
    protos: document.querySelectorAll('.el.page').length,
    anchors: document.querySelectorAll('.an').length,
    sections: document.querySelectorAll('.sec').length,
    tables: document.querySelectorAll('.ft').length,
    imgs: document.querySelectorAll('.el-img img').length,
    tocCards: document.querySelectorAll('.card[id^="card-"]').length
  })`);

  // ---- 手风琴
  R.accordion = await ev(`(function(){
    var C = window.__CARDVIEW__; if(!C) return 'no-api';
    var open0 = C.openCount();
    C.cards[3].querySelector('.ch').click();
    var open1 = C.openCount();
    C.cards[7].querySelector('.ch').click();
    var open2 = C.openCount();
    C.cards[7].querySelector('.ch').click();   // 再点一次应折叠
    var open3 = C.openCount();
    return JSON.stringify({open0:open0, open1:open1, open2:open2, open3:open3,
      acc:C.accordion(), after:C.cards[7].classList.contains('open')});
  })()`);

  // ---- 点卡片 → 画布视角变化 + 落点框高亮
  R.fly = await ev(`(function(){
    var C = window.__CARDVIEW__;
    var before = window.__getView__();
    var card = C.cards.filter(function(c){return c.dataset.cid==='BR-601';})[0];
    if(!card) return 'no-card';
    card.querySelector('.ch').click();
    var after = window.__getView__();
    // 点 BR-601 之后，画布应该移到后台那一片，且至少有一个 .an 高亮
    return JSON.stringify({before:before, after:after,
      moved: Math.abs(after.x-before.x)>1 || Math.abs(after.y-before.y)>1,
      hi: document.querySelectorAll('.an.hi').length});
  })()`);

  // ---- 点画布锚点框 → 侧栏对应卡片展开
  R.clickAnchor = await ev(`(function(){
    var C = window.__CARDVIEW__;
    C.cards.forEach(function(c){ c.querySelector('.cb').hidden = true; c.classList.remove('open'); });
    var an = document.querySelector('.an[data-br]');
    if(!an) return 'no-an';
    var br = an.dataset.br;
    an.click();
    var card = document.querySelector('.card[data-cid="'+br+'"]');
    return JSON.stringify({br:br, open: card?card.classList.contains('open'):null,
      openCount: C.openCount()});
  })()`);

  // ---- 搜索
  R.search = await ev(`(function(){
    var q = document.getElementById('sQ');
    q.value = '折扣'; q.dispatchEvent(new Event('input'));
    var n1 = document.querySelectorAll('.card:not(.hide)').length;
    var shown1 = document.getElementById('sNShown').textContent;
    q.value = 'BR-803'; q.dispatchEvent(new Event('input'));
    var n2 = document.querySelectorAll('.card:not(.hide)').length;
    q.value = ''; q.dispatchEvent(new Event('input'));
    var n3 = document.querySelectorAll('.card:not(.hide)').length;
    return JSON.stringify({q1:n1, shown1:shown1, q2:n2, q3:n3});
  })()`);

  // ---- 端筛选
  R.filter = await ev(`(function(){
    var b = document.querySelector('#sFEnd button[data-e="admin"]');
    b.click();
    var nAdmin = document.querySelectorAll('.card:not(.hide)').length;
    var lanesHidden = [].slice.call(document.querySelectorAll('.lane')).map(function(l){
      return l.classList.contains('hide'); });
    document.querySelector('#sFEnd button[data-e="all"]').click();
    return JSON.stringify({adminVisible:nAdmin, lanesHidden:lanesHidden});
  })()`);

  // ---- 全部展开 / 收起
  R.expandAll = await ev(`(function(){
    var C = window.__CARDVIEW__;
    document.getElementById('sExpandAll').click();
    var n = C.openCount(), acc = C.accordion();
    document.getElementById('sCollapseAll').click();
    return JSON.stringify({openAfterExpandAll:n, accAfterExpandAll:acc,
      openAfterCollapse:C.openCount()});
  })()`);

  // ---- 侧栏让位：画布右边界不能压到侧栏
  R.geom = await ev(`JSON.stringify((function(){
    function R2(s){var e=document.querySelector(s);if(!e)return null;var b=e.getBoundingClientRect();
      return {x:Math.round(b.x),w:Math.round(b.width)};}
    return {win:innerWidth, board:R2('#board'), side:R2('.side'),
            hudTR:R2('.hud.tr'), hudBR:R2('.hud.br')};})())`);

  // ---- 版式一致性：折叠态与展开态的水平内边距
  R.layout = await ev(`(function(){
    var card = document.querySelector('.card.open') || document.querySelector('.card');
    var ch = card.querySelector('.ch'), cb = card.querySelector('.cb');
    var a = getComputedStyle(ch).paddingLeft, b = getComputedStyle(cb).paddingLeft;
    return JSON.stringify({headPad:a, bodyPad:b, same:a===b});
  })()`);

  // ---- 页面级元素总表 ----
  R.elTable = await ev(`(function(){
    var t = document.getElementById('elTable'); if(!t) return {rows:0, missing:true};
    var rows = t.querySelectorAll('tr.elrow');
    return JSON.stringify({
      open0: t.open,
      rows: rows.length,
      unc: t.querySelectorAll('tr.elrow.unc').length,
      own: t.querySelectorAll('.own[data-br]').length,
      pages: t.querySelectorAll('section.elpg').length,
      boxRows: t.querySelectorAll('tr.elrow[data-box]').length
    });
  })()`);

  // 元素总表的**单元格内边距必须真的生效**。
  // ⚠️ --cpad-x 曾只定义在 .card 上，而总表不在 .card 里 → var() 解析失败 →
  //    padding 整条声明作废（td 拿到 0px，文字贴边）。这类「变量定义域不对」
  //    的错误不会报错，只会让版式悄悄退化，所以必须实测内边距数值。
  R.elTablePad = await ev(`(function(){
    var t = document.getElementById('elTable'); if(!t) return 'no-table';
    t.open = true;
    var td = t.querySelector('tr.elrow td.el-n');
    var th = t.querySelector('.elt thead th');
    if(!td) return 'no-row';
    var cs = getComputedStyle(td), csh = getComputedStyle(th);
    var pl = parseFloat(cs.paddingLeft), pr = parseFloat(cs.paddingRight);
    var tbl = t.querySelector('.elt').getBoundingClientRect();
    return JSON.stringify({
      tdPadL: cs.paddingLeft, tdPadR: cs.paddingRight,
      thPadL: csh.paddingLeft,
      ok: pl >= 8 && pr >= 8,
      tableW: Math.round(tbl.width),
      overflowX: Math.round(t.querySelector('.elt').scrollWidth - t.querySelector('.elt').clientWidth)
    });
  })()`);

  // 点总表里的需求号 → 应展开侧栏对应卡片 + 画布高亮落点框
  R.elTableFly = await ev(`(function(){
    var t = document.getElementById('elTable'); if(!t) return 'no-table';
    t.open = true;
    var own = t.querySelector('.own[data-br]'); if(!own) return 'no-own';
    var br = own.dataset.br;
    var before = window.__getView__();
    own.click();
    var after = window.__getView__();
    var card = document.querySelector('.card[data-cid="'+br+'"]');
    return JSON.stringify({br:br,
      moved: Math.abs(after.x-before.x)>1 || Math.abs(after.y-before.y)>1,
      hi: document.querySelectorAll('.an.hi').length,
      cardOpen: card ? card.classList.contains('open') : null});
  })()`);

  // 点元素行 → 应出现临时定位框（.an.flash-hi）
  R.elTableEl = await ev(`(function(){
    var t = document.getElementById('elTable'); if(!t) return 'no-table';
    t.open = true;
    var row = t.querySelector('tr.elrow[data-box]'); if(!row) return 'no-row';
    var before = window.__getView__();
    var td = row.querySelector('td');
    td.click();
    var after = window.__getView__();
    return JSON.stringify({
      moved: Math.abs(after.x-before.x)>1 || Math.abs(after.y-before.y)>1,
      flash: document.querySelectorAll('.an.flash-hi').length});
  })()`);

  // ⚠️ 收尾必须杀**整棵进程树**。
  //    Edge 是 launcher + 子进程的形态，ch.kill() 只打死 launcher，
  //    渲染/GPU/网络子进程会留下来（实测连跑几次攒了 30 个僵尸进程），
  //    它们占着 user-data-dir 和调试端口，下一次探针可能连到**旧实例** ——
  //    结果是「换了一份 HTML，探针却报上一份的结果」，变异测试因此假绿。
  try { ws.close(); } catch (e) {}
  await shutdown(ch);
  fs.writeFileSync(OUT, JSON.stringify(R, null, 1), 'utf-8');
  console.log(JSON.stringify(R, null, 1));
  await sleep(600);
})().catch(e => { console.error(e); process.exit(1); });

function shutdown(ch){
  return new Promise(function(res){
    try {
      if (process.platform === 'win32') {
        spawn('taskkill', ['/PID', String(ch.pid), '/T', '/F'], { stdio: 'ignore' })
          .on('close', function(){ setTimeout(res, 250); })
          .on('error', function(){ try{ch.kill('SIGKILL')}catch(e){}; setTimeout(res, 250); });
      } else {
        try { ch.kill('SIGKILL'); } catch (e) {}
        setTimeout(res, 250);
      }
    } catch (e) { res(); }
  });
}
