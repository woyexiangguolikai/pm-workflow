// _shots.js —— 需求卡片画布预览图（固定视角）
// ⚠️ --screenshot 与滚动/变换不兼容（截的永远是文档顶部），必须走 CDP。
// 视角通过引擎自己暴露的 window.__fit__ / window.__centerOn__ 设置 ——
// 在外部猜一个 transform 再写回 style 是错的：任何一次 apply() 都会覆盖它。
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const WebSocket = require('ws');

const HERE = __dirname;
const HTML = path.join(HERE, 'requirement-cards.html');
const OUT = path.join(HERE, 'preview');
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const PORT = 9400 + (process.pid % 400);

// ⚠️ 卡片视角不能对 `.card[data-cid=...]` 用 __centerOn__ ——
//    那张卡在**右侧栏**里，不是世界层元素，拿它算几何会把视角送到侧栏位置。
//    需求号的落点在画布上体现为 `.an[data-br=...]` 落点框（及卡片 data-boxes 的
//    世界坐标）。所以：先点卡片触发展开（会调 flyTo 用 boxes 取景），
//    再按 __getView__ 读回实际视角，必要时用 boxes 现算补正。
function flyCardView(br, k) {
  return '(function(){' +
    'var c=document.querySelector(\'[data-cid="' + br + '"]\'); if(!c) return "no-card";' +
    'var C=window.__CARDVIEW__;' +
    'if(!c.classList.contains("open")) c.querySelector(".ch").click();' +
    'var boxes=[]; try{boxes=JSON.parse(c.dataset.boxes||"[]");}catch(e){}' +
    'if(!boxes.length){ C.flyTo(c); return JSON.stringify(window.__getView__()); }' +
    // 用 boxes 的世界坐标包围盒现算（与 flyTo 同一套公式），保证取景对准落点
    'var x0=Math.min.apply(null,boxes.map(function(b){return b[0];}));' +
    'var y0=Math.min.apply(null,boxes.map(function(b){return b[1];}));' +
    'var x1=Math.max.apply(null,boxes.map(function(b){return b[0]+b[2];}));' +
    'var y1=Math.max.apply(null,boxes.map(function(b){return b[1]+b[3];}));' +
    'var bd=document.getElementById("board");' +
    'var pad=170;' +
    'var kk=' + k + ';' +
    'if(!kk){ kk=Math.min((bd.clientWidth-pad*2)/Math.max(1,x1-x0),(bd.clientHeight-pad*2)/Math.max(1,y1-y0)); kk=Math.max(0.35,Math.min(kk,1.6)); }' +
    'window.__setView__(kk, bd.clientWidth/2-(x0+x1)/2*kk, bd.clientHeight/2-(y0+y1)/2*kk);' +
    'document.querySelectorAll(".an.hi").forEach(function(a){a.classList.remove("hi")});' +
    'var n=0; document.querySelectorAll(\'.an[data-br="' + br + '"]\').forEach(function(a){a.classList.add("hi");n++});' +
    'if(!document.body.classList.contains("anno")) document.body.classList.add("anno");' +
    'return JSON.stringify(window.__getView__())+" hi="+n;' +
  '})()';
}

const VIEWS = [
  { n: '01-全貌', act: 'window.__fit__(60)' },
  { n: '02-小程序泳道-用户账户', act: 'window.__centerOn__(document.querySelector(\'.el.page[data-id="PG-A1"]\'),0.9)' },
  { n: '03-小程序泳道-下单支付', act: 'window.__centerOn__(document.querySelector(\'.el.page[data-id="PG-A4"]\'),0.75)' },
  { n: '04-后台泳道-员工与折扣', act: 'window.__centerOn__(document.querySelector(\'.el.page[data-id="PG-B6"]\'),0.62)' },
  { n: '05-后台泳道-对账结算', act: 'window.__centerOn__(document.querySelector(\'.el.page[data-id="PG-B9"]\'),0.7)' },
  { n: '06-卡片-BR601-落点', act: flyCardView('BR-601', 1.0) },
  { n: '07-卡片-BR101-落点', act: flyCardView('BR-101', 1.0) },
  { n: '08-卡片-BR803-落点', act: flyCardView('BR-803', 1.0) },
  // 元素总表：展开后点一个需求号 → 飞到落点；再点一个元素行 → 闪定位框
  { n: '09-元素总表', act: '(function(){var t=document.getElementById("elTable");if(!t)return "no-table";t.open=true;t.scrollIntoView({block:"start"});return "open rows="+t.querySelectorAll("tr.elrow").length;})()' },
  { n: '10-总表点元素行定位', act: '(function(){var t=document.getElementById("elTable");if(!t)return "no-table";t.open=true;var r=t.querySelector("tr.elrow[data-box]");r.querySelector("td").click();return "ok";})()' },
];

function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  const prof = path.join(HERE, '_mut', 'edgeprof_' + process.pid);
  fs.mkdirSync(prof, { recursive: true });
  const child = spawn(EDGE, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    // 不加这些的话，新 profile 会弹「登录以同步数据」的首次运行对话框，
    // 截图截到的就是那个对话框 —— 而不是我们的页面。
    '--no-first-run', '--no-default-browser-check',
    '--disable-features=msEdgeIdentitySignIn,msSyncPromo,msEdgeSyncPromo',
    '--disable-sync', '--disable-background-networking',
    '--remote-debugging-port=' + PORT,
    '--user-data-dir=' + prof,
    '--window-size=1600,1000',
    '--force-device-scale-factor=1.4',
    'file:///' + HTML.replace(/\\/g, '/'),
  ], { stdio: 'ignore' });

  await sleep(4000);
  let list = [];
  for (let i = 0; i < 40; i++) {
    try {
      const r = await fetch('http://127.0.0.1:' + PORT + '/json/list');
      list = await r.json();
      if (list.find(t => t.type === 'page' && t.webSocketDebuggerUrl)) break;
    } catch (e) { /* not up yet */ }
    await sleep(500);
  }
  const tgt = list.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
  if (!tgt) { console.log('  [失败] 连不上 Edge'); child.kill(); process.exit(1); }

  const ws = new WebSocket(tgt.webSocketDebuggerUrl);
  let id = 0;
  const pend = new Map();
  const send = (method, params) => new Promise(res => {
    const i = ++id;
    pend.set(i, res);
    ws.send(JSON.stringify({ id: i, method, params: params || {} }));
  });
  ws.on('message', d => {
    const m = JSON.parse(d);
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id); }
  });
  await new Promise(r => ws.on('open', r));
  await send('Page.enable');
  await send('Runtime.enable');
  await sleep(1500);

  const ev = async (expr) => {
    const r = await send('Runtime.evaluate', { expression: expr, returnByValue: true });
    return r && r.result ? r.result.value : undefined;
  };

  const ready = await ev('!!(window.__fit__ && document.getElementById("world"))');
  console.log('  视角接口就绪：', ready);

  for (const v of VIEWS) {
    const r = await ev('(function(){try{var x=' + v.act + ';return x?JSON.stringify(x):"null";}catch(e){return "ERR:"+e.message}})()');
    await sleep(1000);
    const shot = await send('Page.captureScreenshot', { format: 'png' });
    if (shot && shot.data) {
      fs.writeFileSync(path.join(OUT, v.n + '.png'), Buffer.from(shot.data, 'base64'));
      console.log('  ✓ %s  %s', v.n, r);
    } else {
      console.log('  ✗ %s 截图失败', v.n);
    }
  }

  try { ws.close(); } catch (e) {}
  await killTree(child);
  console.log('  预览图 → %s', OUT);
}

// Edge 是 launcher + 子进程，child.kill() 只打死 launcher，
// 渲染/GPU 子进程会留下来占着调试端口（实测跑几轮攒了 30 个僵尸）。
function killTree(ch) {
  return new Promise(res => {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/PID', String(ch.pid), '/T', '/F'], { stdio: 'ignore' })
        .on('close', () => setTimeout(res, 400))
        .on('error', () => { try { ch.kill('SIGKILL'); } catch (e) {}; setTimeout(res, 400); });
    } else {
      try { ch.kill('SIGKILL'); } catch (e) {}
      setTimeout(res, 400);
    }
  });
}

main().catch(e => { console.error(e); process.exit(1); });
