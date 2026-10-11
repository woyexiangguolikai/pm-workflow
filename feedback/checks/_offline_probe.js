// _offline_probe.js —— 离线包单文件 HTML 的真实渲染探针
//
// 为什么必须真渲染：原型是 Babel 在浏览器里现编译的 React 应用，
// 页面结构**不存在于 HTML 源码里**。对源码 grep `id="U-02"` 必然一个都找不到，
// 而运行时 23 个页面一个不少 —— 静态查会把「全通」报成「全断」。
//
// 而且**真有 id 也不能只看 id**：本项目的页面切换走
// `history.replaceState(null,"","#"+code)`，DOM 里根本没有对应 id。
// 「锚点通不通」只能靠：真导航过去，看渲染结果是否**确实变了**。
//
// 🔴 踩过的坑（否则会得到 23/23「全不动」的假红）：
//    从 A.html 导航到 A.html#X 只改 hash → **同文档导航**，
//    不触发 load、不重跑脚本。而应用只在 mount 时读 location.hash，
//    所以这种导航是无效的 —— 探针等 load 等到超时，采样到旧 DOM。
//    → 每次导航都带一个唯一的 `?wb_probe=N`，把「同文档」变成「跨文档」。
//
// 🔴 判别力自证：必须喂一个**不存在的 fragment**当反例。
//    它必须回到基线。若它也能让 DOM 变化，说明「变了」这个信号不可信，
//    整条判据失效 —— 必须报出来，不能当通过。
//
// 用法：node _offline_probe.js --file <绝对路径> --out <json> [--frags "U-02,U-04"]
const fs = require('fs');
const os = require('os');
const path = require('path');
const { spawn } = require('child_process');
const WebSocket = require('ws');

function argv(name, def) {
  const i = process.argv.indexOf('--' + name);
  return i >= 0 && process.argv[i + 1] !== undefined ? process.argv[i + 1] : def;
}

const FILE = argv('file', null);
const OUT = argv('out', null);
const FRAGS = (argv('frags', '') || '').split(',').map(s => s.trim()).filter(Boolean);
const INVALID = argv('invalid', 'WB-PROBE-INVALID-00');
const PORT = 9500 + (process.pid % 400);
const PROFILE = path.join(os.tmpdir(), 'wb_offline_probe_' + process.pid);
const MIN_SETTLE_MS = 1100;   // React 渲染实测 1s 内完成；留足余量再谈「稳定」

const sleep = ms => new Promise(r => setTimeout(r, ms));

const result = {
  ok: false, file: FILE, url: null, title: null,
  ids: [], links: [], errors: [],
  baseSig: null, baseSig2: null, baseStable: null,
  invalidSig: null, invalidDiffers: null,
  fragResults: {}, loads: 0, note: null,
};

let browser = null, killed = false;
function killTree() {
  if (killed || !browser) return;
  killed = true;
  try { spawn('taskkill', ['/PID', String(browser.pid), '/T', '/F'], { stdio: 'ignore' }); } catch (e) { }
}
function finish() {
  killTree();
  try { fs.rmSync(PROFILE, { recursive: true, force: true }); } catch (e) { }
  if (OUT) {
    try {
      fs.mkdirSync(path.dirname(OUT), { recursive: true });
      fs.writeFileSync(OUT, JSON.stringify(result, null, 2), 'utf8');
    } catch (e) { }
  }
  process.stdout.write(JSON.stringify(result));
  process.exit(0);
}
process.on('uncaughtException', e => {
  result.errors.push('FATAL: ' + (e && e.message));
  finish();
});

function findBrowser() {
  const cands = [
    'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
    'C:/Program Files/Google/Chrome/Application/chrome.exe',
    'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
  ];
  for (const c of cands) if (fs.existsSync(c)) return c;
  return null;
}

// 🔴 `#` 绝不能 encodeURIComponent（会变 %23 → 找不到）。只对路径段转义。
function toFileUrl(p) {
  const abs = path.resolve(p).replace(/\\/g, '/');
  return 'file:///' + abs.split('/').map((s, i) => i === 0 ? s : encodeURIComponent(s)).join('/');
}

(async () => {
  const BIN = findBrowser();
  if (!BIN) { result.errors.push('FATAL: 找不到 Edge / Chrome'); return finish(); }
  if (!FILE || !fs.existsSync(FILE)) {
    result.errors.push('FATAL: 文件不存在 ' + FILE); return finish();
  }

  fs.mkdirSync(PROFILE, { recursive: true });
  browser = spawn(BIN, [
    '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
    '--no-first-run', '--no-default-browser-check', '--disable-sync',
    '--disable-extensions', '--disable-background-networking',
    '--disable-features=msEdgeIdentitySignIn,msSyncPromo,msEdgeSyncPromo',
    '--remote-debugging-port=' + PORT, '--user-data-dir=' + PROFILE,
    '--allow-file-access-from-files', '--window-size=1600,1000',
    'about:blank',
  ], { stdio: 'ignore' });

  let target = null;
  for (let i = 0; i < 60; i++) {
    try {
      const l = await (await fetch('http://127.0.0.1:' + PORT + '/json/list')).json();
      target = l.find(t => t.type === 'page' && t.webSocketDebuggerUrl);
      if (target) break;
    } catch (e) { }
    await sleep(300);
  }
  if (!target) { result.errors.push('FATAL: 连不上调试端口'); return finish(); }

  const ws = new WebSocket(target.webSocketDebuggerUrl, { maxPayload: 256 * 1024 * 1024 });
  let id = 0; const pend = new Map();
  const send = (m, q) => new Promise(r => {
    const i = ++id; pend.set(i, r);
    ws.send(JSON.stringify({ id: i, method: m, params: q || {} }));
  });

  const errs = [];
  let at = -1;
  ws.on('message', d => {
    const m = JSON.parse(d);
    if (m.id && pend.has(m.id)) { pend.get(m.id)(m.result); pend.delete(m.id); return; }
    if (m.method === 'Runtime.exceptionThrown') {
      const ed = m.params.exceptionDetails || {};
      const desc = (ed.exception && (ed.exception.description || ed.exception.value)) || '';
      const st = ((ed.stackTrace && ed.stackTrace.callFrames) || []).slice(0, 4)
        .map(f => `${f.functionName || '(anon)'}@${f.lineNumber + 1}:${f.columnNumber + 1}`).join(' <- ');
      errs.push('EXC: ' + (ed.text || '')
        + (desc ? ' | ' + String(desc).split('\n')[0] : '') + (st ? ' | ' + st : ''));
    }
    if (m.method === 'Runtime.consoleAPICalled' && m.params.type === 'error') {
      const t = (m.params.args || [])
        .map(a => a.value !== undefined ? a.value : (a.description || a.type)).join(' ');
      errs.push('CONSOLE: ' + String(t).slice(0, 300));
    }
    if (m.method === 'Log.entryAdded') {
      const e = m.params.entry || {};
      if (e.level === 'error') errs.push('LOG: ' + (e.text || '') + (e.url ? ' @' + e.url : ''));
    }
    if (m.method === 'Page.loadEventFired') at = 1;
  });

  await new Promise(r => ws.on('open', r));
  await send('Page.enable'); await send('Runtime.enable'); await send('Log.enable');

  const ev = async e => {
    const r = await send('Runtime.evaluate', { expression: e, returnByValue: true, awaitPromise: true });
    if (!r || r.exceptionDetails) return null;
    return r.result ? r.result.value : null;
  };

  // 签名：元素数 + 正文长度 + 前 60 字 + 后 70 字。
  // 只用元素数不够（不同页面可能等长），加上首尾文字才能区分「换了页面」。
  const SIG = `(function(){
      var b=document.body; if(!b) return 'no-body';
      var t=(b.innerText||'').replace(/\\s+/g,' ').trim();
      return document.querySelectorAll('*').length+'|'+t.length+'|'+t.slice(0,60)+'|'+t.slice(-70);
    })()`;

  async function settle() {
    await sleep(MIN_SETTLE_MS);
    let prev = -1, stable = 0;
    for (let i = 0; i < 12; i++) {
      const n = await ev('document.querySelectorAll("*").length') || 0;
      if (n > 0 && n === prev) { if (++stable >= 1) return; }
      else stable = 0;
      prev = n;
      await sleep(150);
    }
  }

  // 🔴 每次都换 `?wb_probe=N`，强制跨文档导航（见文件头说明）
  let loadNo = 0;
  result.timing = [];
  async function load(frag) {
    loadNo++; result.loads = loadNo;
    const t0 = Date.now();
    at = -1;
    await send('Page.navigate', {
      url: result.url + '?wb_probe=' + loadNo + (frag ? '#' + frag : ''),
    });
    let tw = 0;
    for (let i = 0; i < 90 && at < 0; i++) { await sleep(100); tw += 100; }
    const t1 = Date.now();
    await settle();
    result.timing.push({ frag: frag || null, waitLoadMs: t1 - t0, settleMs: Date.now() - t1, totalMs: Date.now() - t0 });
  }

  result.url = toFileUrl(FILE);

  // ---- 1. 基线（无 hash）----
  await load(null);
  result.title = await ev('document.title');
  result.ids = JSON.parse(await ev(
    'JSON.stringify(Array.from(document.querySelectorAll("[id]")).map(function(e){return e.id}))'
  ) || '[]');
  result.links = JSON.parse(await ev(
    `JSON.stringify(Array.from(document.querySelectorAll('a[href]')).map(function(a){
        var r=a.getBoundingClientRect();
        return { href:a.getAttribute('href'),
                 text:(a.textContent||'').replace(/\\s+/g,' ').trim().slice(0,50),
                 visible:r.width>0&&r.height>0 }; }))`) || '[]');
  result.baseSig = await ev(SIG);

  // ---- 2. 确定性自证：再加载一次无 hash 的基线，签名必须一模一样 ----
  // 这是「differs 这个信号可信」的前提。基线本身就不稳定的话，
  // 后面任何「变了 / 没变」的判断都是噪声。
  await load(null);
  result.baseSig2 = await ev(SIG);
  result.baseStable = (result.baseSig === result.baseSig2);

  // ---- 3. 附带证据：喂一个不存在的 fragment 看应用怎么处理 ----
  // ⚠️ 仅供报告，不作判据：应用**合法地**可以把未知 fragment 渲染出来
  //    （本项目的原型就是回落到默认页，但别的实现可能不是）。
  if (FRAGS.length) {
    await load(INVALID);
    result.invalidSig = await ev(SIG);
    result.invalidDiffers = result.invalidSig !== result.baseSig;
  }

  // ---- 4. 逐个 fragment ----
  for (const f of FRAGS) {
    await load(f);
    const sig = await ev(SIG);
    result.fragResults[f] = { sig, differs: sig !== result.baseSig };
  }

  result.errors = errs;
  result.ok = errs.length === 0;
  finish();
})();
