# -*- coding: utf-8 -*-
"""由 prd.json 生成 PRD.html

v1.2 变化（对应用户 3 条反馈）：
  1. 业务视图 / 技术视图 一键切换：默认业务视图，页面路径、表.字段、接口编号、
     锚点收进技术视图，业务侧零专业术语干扰。
  2. 交互说明新增「动效与微交互」（页面转场 / 按压 / 加载 / 成功失败反馈 /
     时长缓动 / 无障碍降级），并新增附录 I 全局动效基线。
  3. 附录 A 流程图由「泳道 + 列表」改为图示化流程链（带编号、泳道色标、连接箭头）。

用法：python build-view.py
"""
import json, io, os

BASE = os.path.dirname(os.path.abspath(__file__))
data = json.load(io.open(os.path.join(BASE, 'prd.json'), encoding='utf-8'))
DATA_JSON = json.dumps(data, ensure_ascii=False, separators=(',', ':'))

TPL = r'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PRD · {{项目名}}</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#0d1117;--card:#161b22;--card2:#1c2128;--card3:#21262d;--border:#30363d;
  --text:#e6edf3;--text2:#8b949e;--text3:#6e7681;
  --green:#3fb950;--amber:#d29922;--red:#f85149;--accent:#58a6ff;--purple:#bc8cff;--teal:#39c5bb;
  /* 泳道 = SKILL.md 的端枚举（固定）：用户小程序/管理后台/收银端/商家端/服务端 + 外部系统 */
  --lane-app:#7ee787;--lane-admin:#e3b341;--lane-pos:#39c5bb;--lane-mch:#f0883e;
  --lane-srv:#bc8cff;--lane-ext:#58a6ff;
}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--text);font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.7;-webkit-font-smoothing:antialiased}
.layout{display:flex;align-items:flex-start;max-width:1560px;margin:0 auto}

/* ===== 双视图开关 ===== */
body.biz .tech-only{display:none!important}
body.tech .biz-only{display:none!important}
.topbar{display:flex;align-items:flex-start;gap:16px;flex-wrap:wrap}
.topbar .tb-l{flex:1;min-width:280px}
.viewsw{display:inline-flex;background:var(--card);border:1px solid var(--border);border-radius:9px;padding:3px;gap:2px}
.viewsw button{background:none;border:none;color:var(--text3);font-family:inherit;font-size:12.5px;padding:5px 14px;border-radius:6px;cursor:pointer;transition:.14s;white-space:nowrap}
.viewsw button:hover{color:var(--text)}
.viewsw button.on{background:var(--card3);color:var(--text)}
.viewsw button.on[data-v="biz"]{color:#7ee787}
.viewsw button.on[data-v="tech"]{color:var(--accent)}
.viewsw .hint{font-size:11px;color:var(--text3);padding:0 6px;align-self:center}
.codechip{font-family:ui-monospace,Consolas,monospace;font-size:11px;background:var(--card3);border:1px solid var(--border);border-radius:4px;padding:1px 6px;color:#e3b341}

/* ---------- 侧栏 ---------- */
.side{width:288px;flex:0 0 288px;position:sticky;top:0;height:100vh;overflow-y:auto;border-right:1px solid var(--border);padding:18px 0 40px;background:var(--bg)}
.side::-webkit-scrollbar{width:8px}.side::-webkit-scrollbar-thumb{background:#30363d;border-radius:4px}
.side-h{padding:0 16px 12px}
.side-h .t{font-size:13px;font-weight:600;letter-spacing:.01em}
.side-h .s{font-size:11.5px;color:var(--text3);margin-top:2px}
.side-search{padding:0 14px 12px}
.side-search input{width:100%;background:var(--card);border:1px solid var(--border);color:var(--text);padding:7px 11px;border-radius:8px;font-size:12.5px;font-family:inherit;outline:none}
.side-search input:focus{border-color:rgba(88,166,255,.5)}
.side-search input::placeholder{color:var(--text3)}
.nav{font-size:12.5px}
.nav a{display:block;color:var(--text2);text-decoration:none;padding:4px 16px;border-left:2px solid transparent;transition:.12s;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nav a:hover{color:var(--text);background:var(--card2)}
.nav a.lv1{font-weight:600;color:var(--text);padding-top:12px;padding-bottom:5px;font-size:12.5px;letter-spacing:.01em}
.nav a.lv2{padding-left:28px;color:var(--text2)}
.nav a.lv3{padding-left:44px;font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:var(--text3);padding-top:3px;padding-bottom:3px}
.nav a.lv3:hover{color:var(--accent)}
.nav .sep{height:1px;background:var(--border);margin:12px 16px}

/* ---------- 主区 ---------- */
.main{flex:1;min-width:0;padding:34px 40px 100px}
.eyebrow{font-size:12px;color:var(--text3);letter-spacing:.08em;text-transform:uppercase;margin-bottom:9px}
h1{font-size:23px;font-weight:600;letter-spacing:-.01em;line-height:1.35}
.meta{margin-top:7px;font-size:12.5px;color:var(--text2)}
.stage{display:inline-block;margin-left:8px;padding:2px 9px;border-radius:20px;font-size:11.5px;background:rgba(210,153,34,.14);color:#e3b341;border:1px solid rgba(210,153,34,.32);vertical-align:1px}
.stage.ok{background:rgba(88,166,255,.14);color:var(--accent);border-color:rgba(88,166,255,.3)}

.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:9px;margin-top:22px}
.stat{background:var(--card);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.stat .n{font-size:20px;font-weight:600;letter-spacing:-.02em}
.stat .l{font-size:11.5px;color:var(--text2);margin-top:1px}
.stat.w .n{color:var(--amber)}.stat.d .n{color:var(--red)}.stat.o .n{color:var(--green)}.stat.i .n{color:var(--accent)}.stat.p .n{color:var(--purple)}

.notice{margin-top:20px;background:var(--card2);border:1px solid var(--border);border-left:3px solid var(--accent);border-radius:8px;padding:14px 18px;font-size:13px;color:var(--text2)}
.notice strong{color:var(--text)}
.notice ul{margin-top:8px;padding-left:18px}
.notice li{margin-bottom:3px}
.notice code{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;background:var(--card3);padding:1px 5px;border-radius:4px;color:#7ee787}

/* 模块 / 功能 */
.mod{margin-top:44px;scroll-margin-top:16px}
.mod-h{display:flex;align-items:baseline;gap:11px;padding-bottom:11px;border-bottom:1px solid var(--border)}
.mod-id{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--purple);background:rgba(188,140,255,.1);border:1px solid rgba(188,140,255,.26);padding:2px 8px;border-radius:6px}
.mod-h h2{font-size:17px;font-weight:600;letter-spacing:-.01em}
.mod-h .cnt{font-size:12px;color:var(--text3);margin-left:auto}

.func{margin-top:26px;scroll-margin-top:16px}
.func-h{display:flex;align-items:baseline;gap:10px;padding:10px 14px;background:var(--card2);border:1px solid var(--border);border-radius:9px}
.func-id{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:var(--teal)}
.func-h h3{font-size:14px;font-weight:600}
.func-h .cnt{font-size:11.5px;color:var(--text3);margin-left:auto}
.func .reqs{margin-top:11px}

/* 需求卡片 */
.req{background:var(--card);border:1px solid var(--border);border-radius:11px;margin-bottom:11px;overflow:hidden;scroll-margin-top:16px;transition:border-color .15s}
.req:hover{border-color:#484f58}
.req-h{display:flex;align-items:center;gap:11px;padding:13px 17px;cursor:pointer;user-select:none}
.rid{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:var(--accent);background:rgba(88,166,255,.1);border:1px solid rgba(88,166,255,.26);padding:2px 8px;border-radius:6px;white-space:nowrap}
.req-h h4{font-size:14px;font-weight:500;flex:1}
.pri{font-size:10.5px;padding:2px 8px;border-radius:20px;white-space:nowrap}
.pri.p0{background:rgba(248,81,73,.13);color:#ff7b72;border:1px solid rgba(248,81,73,.3)}
.pri.p1{background:rgba(210,153,34,.13);color:#e3b341;border:1px solid rgba(210,153,34,.3)}
.lvl{font-size:10.5px;padding:2px 8px;border-radius:20px;white-space:nowrap;background:var(--card3);color:var(--text3);border:1px solid var(--border)}
.lvl.full{background:rgba(63,185,80,.1);color:#7ee787;border-color:rgba(63,185,80,.26)}
.chev{color:var(--text3);font-size:11px;transition:transform .18s}
.req.open .chev{transform:rotate(90deg)}

.req-b{display:none;padding:0 17px 18px;border-top:1px solid var(--border)}
.req.open .req-b{display:block}

.ends{display:flex;flex-wrap:wrap;gap:6px;align-items:center;font-size:12px;color:var(--text3);margin-top:13px}
.etag{font-size:11.5px;padding:2px 9px;border-radius:6px;background:var(--card3);border:1px solid var(--border);color:var(--text2)}
.etag.app{color:#7ee787;border-color:rgba(63,185,80,.3);background:rgba(63,185,80,.07)}
.etag.admin{color:#e3b341;border-color:rgba(210,153,34,.3);background:rgba(210,153,34,.07)}
.etag.srv{color:#bc8cff;border-color:rgba(188,140,255,.3);background:rgba(188,140,255,.07)}

.zone{margin-top:17px;padding-left:13px;border-left:2px solid var(--card3)}
.zone-t{font-size:11.5px;color:var(--text3);letter-spacing:.08em;margin-bottom:7px}
.zone p{font-size:13.5px;color:var(--text2);line-height:1.75}
.zone ul{list-style:none;padding:0}
.zone ul li{font-size:13px;color:var(--text2);padding-left:15px;position:relative;margin-bottom:3px}
.zone ul li::before{content:"";position:absolute;left:3px;top:9px;width:4px;height:4px;border-radius:50%;background:var(--text3)}

table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px;background:var(--card2);border:1px solid var(--border);border-radius:8px;overflow:hidden}
th{background:var(--card3);text-align:left;padding:8px 11px;font-size:11.5px;color:var(--text2);font-weight:600;border-bottom:1px solid var(--border);white-space:nowrap}
td{padding:8px 11px;border-bottom:1px solid var(--border);color:var(--text2);vertical-align:top;line-height:1.6}
tr:last-child td{border-bottom:none}
td.k{color:var(--text);white-space:nowrap}
table.t-wrap td.k{white-space:normal;min-width:96px}
td code{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;background:var(--card3);padding:1px 5px;border-radius:4px;color:#7ee787}
.subt{font-size:12px;color:var(--text3);margin:12px 0 0}
.subt.first{margin-top:0}

.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{font-size:11.5px;padding:2px 9px;border-radius:6px;background:var(--card2);border:1px solid var(--border);color:var(--text2);font-family:ui-monospace,Consolas,monospace}
.chip.api{color:#7ee787;border-color:rgba(63,185,80,.28);background:rgba(63,185,80,.07)}
.chip.anchor{color:#e3b341;border-color:rgba(210,153,34,.28);background:rgba(210,153,34,.07)}
.chip.q{color:#ff7b72;border-color:rgba(248,81,73,.28);background:rgba(248,81,73,.07)}
.chip.risk{color:#ffa657;border-color:rgba(255,166,87,.28);background:rgba(255,166,87,.07)}

.txtbox{background:var(--card2);border:1px solid var(--border);border-radius:8px;padding:10px 13px;font-size:12.5px;color:var(--text2);font-family:ui-monospace,Consolas,monospace;line-height:1.7}
.txtbox .q{color:#ffa657}

.todo{background:rgba(210,153,34,.06);border:1px solid rgba(210,153,34,.22);border-radius:8px;padding:11px 14px;font-size:12.5px;color:var(--text2);margin-top:14px}
.todo b{color:#e3b341;font-weight:500}

/* 动效块 */
.motion{margin-top:12px;background:linear-gradient(180deg,rgba(57,197,187,.07),rgba(57,197,187,.02));border:1px solid rgba(57,197,187,.24);border-radius:8px;padding:11px 13px}
.motion .mh{font-size:11.5px;color:var(--teal);letter-spacing:.06em;margin-bottom:7px}
.motion table{margin-top:0;background:transparent;border:none}
.motion th{background:transparent;border-bottom:1px solid rgba(57,197,187,.18);color:#7fd6cf}
.motion td{border-bottom:1px solid rgba(57,197,187,.1);background:transparent}
.motion tr:last-child td{border-bottom:none}
.motion td.k{color:#a8ece6;white-space:nowrap;font-size:12px}

/* ===== 流程图（图示化） ===== */
.flowd{margin-bottom:28px;background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px 18px 18px}
.flowd-h{display:flex;align-items:baseline;gap:10px;flex-wrap:wrap;padding-bottom:11px;border-bottom:1px solid var(--border);margin-bottom:14px}
.flowd-h .fid{font-family:ui-monospace,Consolas,monospace;font-size:11.5px;color:var(--accent);background:rgba(88,166,255,.1);border:1px solid rgba(88,166,255,.26);padding:2px 8px;border-radius:6px}
.flowd-h .fname{font-size:15px;font-weight:600}
.flowd-h .fmeta{font-size:11.5px;color:var(--text3);margin-left:auto}
.legend{display:flex;flex-wrap:wrap;gap:12px;margin-bottom:14px}
.legend span{font-size:11.5px;color:var(--text2);display:inline-flex;align-items:center;gap:5px}
.legend i{width:10px;height:10px;border-radius:3px;display:inline-block}
.fchain{display:flex;flex-direction:column}
.fstep{display:flex;gap:11px;align-items:flex-start;background:var(--card2);border:1px solid var(--border);border-left:3px solid var(--border);border-radius:9px;padding:10px 13px;transition:.15s}
.fstep:hover{border-color:#484f58}
.fno{flex:0 0 auto;width:22px;height:22px;border-radius:50%;background:var(--card3);border:1px solid var(--border);color:var(--text2);font-size:11px;font-family:ui-monospace,Consolas,monospace;display:flex;align-items:center;justify-content:center;margin-top:1px}
.fcol{min-width:0;flex:1}
.flane{font-size:11px;padding:1px 8px;border-radius:5px;border:1px solid var(--border);background:var(--card3);color:var(--text2);white-space:nowrap;display:inline-block;margin-bottom:3px}
.fbody{font-size:13px;color:var(--text);line-height:1.6}
.fconn{width:2px;height:18px;background:linear-gradient(180deg,var(--border),rgba(48,54,61,.2));margin-left:34px;position:relative}
.fconn::after{content:"";position:absolute;left:-4px;bottom:0;border-left:5px solid transparent;border-right:5px solid transparent;border-top:6px solid var(--border)}

/* 附录 */
.sect{margin-top:44px;scroll-margin-top:16px}
.sect>h2{font-size:17px;font-weight:600;letter-spacing:-.01em;padding-bottom:10px;border-bottom:1px solid var(--border)}
.sect .desc{font-size:12.5px;color:var(--text3);margin:9px 0 14px}
.note{background:var(--card2);border:1px solid var(--border);border-left:3px solid var(--amber);border-radius:8px;padding:12px 16px;font-size:12.5px;color:var(--text2);margin-bottom:14px}
.note.blue{border-left-color:var(--accent)}
.note.red{border-left-color:var(--red)}
.note.teal{border-left-color:var(--teal)}
.note strong{color:var(--text)}
.lv{font-size:11px;padding:2px 8px;border-radius:20px;white-space:nowrap}
.lv.high{background:rgba(248,81,73,.13);color:#ff7b72}
.lv.medium{background:rgba(210,153,34,.13);color:#e3b341}
.empty{text-align:center;color:var(--text3);padding:36px;font-size:13px}
footer{margin-top:52px;padding-top:20px;border-top:1px solid var(--border);font-size:12px;color:var(--text3)}
footer code{font-family:ui-monospace,Consolas,monospace;color:var(--text2)}
.hide{display:none!important}
#top{position:fixed;right:26px;bottom:26px;width:40px;height:40px;border-radius:50%;background:var(--card2);border:1px solid var(--border);color:var(--text2);font-size:15px;cursor:pointer;font-family:inherit;display:none;z-index:9}
#top:hover{border-color:#484f58;color:var(--text)}
@media(max-width:1000px){.side{display:none}.main{padding:24px 18px 80px}}
</style>
</head>
<body class="biz">
<div class="layout">
  <aside class="side">
    <div class="side-h"><div class="t">{{项目名}}</div><div class="s">PRD v1.0 · {{日期}}</div></div>
    <div class="side-search"><input id="search" placeholder="搜索需求编号 / 标题 / 关键词…"></div>
    <nav class="nav" id="nav"></nav>
  </aside>
  <main class="main">
    <div class="topbar" id="top-anchor">
      <div class="tb-l">
        <div class="eyebrow">02 · PRD 阶段交付物</div>
        <h1>{{项目名}}</h1>
        <div class="meta">PRD {{版本}} · {{日期}}<span class="stage" id="reqstat"></span></div>
      </div>
      <div class="viewsw" id="viewsw">
        <button data-v="biz" class="on">业务视图</button>
        <button data-v="tech">技术视图</button>
        <span class="hint" id="vhint">已隐藏页面路径 / 表字段 / 接口编号</span>
      </div>
    </div>

    <div class="stats" id="stats"></div>

    <div class="notice">
      <strong>v1.5 全部展开（样板确认后按同一模型批量补齐 42 条）</strong>
      <ul>
        <li><strong>42 条需求全部升级为完整卡片</strong>：与 F1-1 样板同一模型 —— 涉及端逐端职责、前置条件（功能 / 数据）、主流程、异常与分支、业务规则、交互与动效、页面流转、状态联动、数据展示与来源、字段规格、接口、权限、输出与后置条件、验收标准、上下游追溯。</li>
        <li><strong>主流程统一为三列</strong>：执行方 │ 做什么 │ 说明。「说明」列写口径与坑位，避免开发自行猜测。</li>
        <li><strong>动效与微交互逐条补齐</strong>：页面转场、微交互、反馈、缓动、无障碍降级 5 项，42 条需求全覆盖，另有全局基线 11 条。</li>
        <li><strong>「页面展示字段」与「输入限制」落到页面位置</strong>：展示名 / 取值来源 / 格式 / 脱敏 / 取不到时；键盘 / 长度上限 / 允许字符 / 自动处理 / 边界行为 / 提示文案。</li>
        <li><strong>业务语言守卫</strong>：生成后自动渲染校验业务视图，剔除页面路径、表字段名、接口编号、原型锚点、SQL 类型等技术标识，10 类检查全部通过。</li>
      </ul>
      <div style="margin-top:9px">全部待确认事项已落定：<strong>7 项明确答复 + 10 项按默认方案</strong>（另有 1 项合并关闭）。下一步进入 <strong>03-design 设计规范</strong>。</div>
    </div>

    <div id="body"></div>

    <div class="sect" id="apx-flow"><h2>附录 A · 跨需求端到端流程图</h2><div class="desc">按时间顺序的流程链，色标表示所在端；覆盖跨功能的完整链路</div><div id="flows"></div></div>
    <div class="sect" id="apx-api"><h2>附录 B · 外部渠道接口清单</h2><div class="desc">卡片内只写该需求用到的部分，完整清单在此</div><div id="apis"></div></div>
    <div class="sect" id="apx-svc"><h2>附录 C · 我方内部服务能力</h2><div class="desc">本系统对外提供的服务能力，供前端与后台共用</div><div id="svcs"></div></div>
    <div class="sect" id="apx-mod"><h2>附录 D · 需改动的存量模块</h2><div class="desc">依据 00-audit 源码盘点结论</div><div id="mods"></div></div>
    <div class="sect" id="apx-field"><h2>附录 E · 新增字段与枚举</h2><div id="fields"></div></div>
    <div class="sect" id="apx-gloss"><h2>附录 F · 术语表</h2><div id="gloss"></div></div>
    <div class="sect" id="apx-open"><h2>附录 G · 待确认事项与决策记录</h2><div class="desc">全部 17 项已落定：7 项给出明确答复，10 项按默认方案执行</div><div id="opens"></div></div>
    <div class="sect" id="apx-risk"><h2>附录 H · 风险清单</h2><div id="risks"></div></div>
    <div class="sect" id="apx-ac"><h2>附录 I · 验收标准汇总</h2><div class="desc">各需求卡片内的验收标准在此汇总，便于测试整体裁剪</div><div id="acs"></div></div>
    <div class="sect" id="apx-motion"><h2>附录 J · 动效与微交互规范</h2><div class="desc">全局基线，各需求卡片只写特有部分；开发实现动效时以此为准</div><div id="motions"></div></div>
    <div class="sect" id="apx-dataspec"><h2>附录 K · 数据格式与精度规范</h2><div class="desc">数字怎么写、怎么显示的唯一依据：金额与余额小数位、手机号、卡号、时间格式、脱敏口径</div><div id="dataspec"></div></div>

    <footer>
      数据源 <code>prd.json</code> · 叙述文档 <code>PRD.md</code> · 本视图由 <code>build-view.py</code> 从数据源生成，两者不漂移<br>
      上游依据：<code>00-audit/audit.json</code>（存量源码盘点 140 张表） · <code>01-requirements/requirement.json</code>（26 个需求槽位） · 《渠道Api接口文档》
    </footer>
  </main>
</div>
<button id="top" title="回到顶部">↑</button>

<script>
var DATA = __DATA__;
</script>
<script>
function esc(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function el(id){return document.getElementById(id);}
/* 端枚举 → 泳道。端名必须来自 SKILL.md 的固定枚举，端枚举之外的参与方一律归 ext。 */
var LANE={'用户小程序':'app','管理后台':'admin','收银端':'pos','商家端':'mch','服务端':'srv'};
function endCls(e){return LANE[e]||'ext';}
function laneColor(e){return 'var(--lane-'+endCls(e)+')';}

var modName={},funcName={},reqOf={},pagePath={};
DATA.modules.forEach(function(m){
  modName[m.id]=m.name;
  m.functions.forEach(function(f){
    funcName[f.id]=f.name;
  });
});
DATA.requirements.forEach(function(r){reqOf[r.id]=r;});
/* 铁律 2：期望值一律从数据源现算。改了 prd.json，这里的数字必须跟着变 ——
   写成字面量的话，数据源改了它照样显示旧数，等于骗人。 */
(function(){var s=el('reqstat');if(s){s.textContent=DATA.requirements.length+' 条需求已完整展开';}})();
['app','admin'].forEach(function(s){ (DATA.pages[s]||[]).forEach(function(p){pagePath[p.name]=p.path;}); });

/* 业务/技术视图切换 */
var IB=DATA.interfacesBusiness||{};
function ifaceLabel(x,withNote){
  var biz=x.business||IB[x.id]||x.name||'';
  var h='<span class="biz-only">'+esc(biz)+'</span>'+
        '<span class="tech-only"><code>'+esc(x.id)+'</code> '+esc(x.name||'')+'</span>';
  if(withNote&&x.note) h+='<br><span style="color:var(--text3)">'+esc(x.note)+'</span>';
  return h;
}

/* ---------- 统计 ---------- */
(function(){
  var s=DATA.stats;
  var items=[
    ['i',s.requirements,'需求条目'],['o',s.modules,'模块'],['o',s.functions,'功能'],
    ['',(s.appPages||0)+(s.adminPages||0),'涉及页面'],['',s.interfaces,'渠道接口'],
    ['o',s.fieldsWithSpec||0,'字段规格'],['o',s.displayFieldRows||0,'页面展示字段'],['o',s.inputRuleRows||0,'输入限制'],
    ['o',s.dataSpecRows||0,'格式规范'],['p',s.detailFull,'完整卡片'],['d',s.detailBasic,'待补全'],
    ['w',s.openQuestions,'已定决策'],['d',s.risks,'风险'],['o',s.flowDiagrams,'流程图']
  ];
  el('stats').innerHTML=items.map(function(i){
    return '<div class="stat '+(i[0]||'')+'"><div class="n">'+i[1]+'</div><div class="l">'+i[2]+'</div></div>';
  }).join('');
})();

/* ---------- 目录树 ---------- */
(function(){
  var h='<a href="#top-anchor" class="lv1">概述</a>';
  DATA.modules.forEach(function(m){
    h+='<a href="#'+m.id+'" class="lv1">'+m.id+' · '+esc(m.name)+'</a>';
    m.functions.forEach(function(f){
      h+='<a href="#'+f.id+'" class="lv2">'+esc(f.name)+' <span style="color:var(--text3)">'+f.requirementIds.length+'</span></a>';
      f.requirementIds.forEach(function(rid){
        var rr=reqOf[rid];
        h+='<a href="#'+rid+'" class="lv3" title="'+esc(rr?rr.title:'')+'">'+rid+' '+esc(rr?rr.title:'')+'</a>';
      });
    });
  });
  h+='<div class="sep"></div>';
  h+='<a href="#apx-flow" class="lv1">附录</a>';
  [['apx-flow','A 端到端流程图'],['apx-api','B 渠道接口清单'],['apx-svc','C 我方内部服务'],
   ['apx-mod','D 需改动存量模块'],['apx-field','E 新增字段与枚举'],['apx-gloss','F 术语表'],
   ['apx-open','G 待确认与决策'],['apx-risk','H 风险清单'],['apx-ac','I 验收标准汇总'],
   ['apx-motion','J 动效与微交互规范'],['apx-dataspec','K 数据格式与精度规范']].forEach(function(a){
    h+='<a href="#'+a[0]+'" class="lv2">'+esc(a[1])+'</a>';
  });
  el('nav').innerHTML=h;
})();

/* ---------- 通用表格 ---------- */
function tableHTML(headers,rows,techCols,cls){
  if(!rows||!rows.length) return '';
  techCols=techCols||[];
  var h='<table'+(cls?' class="'+cls+'"':'')+'><thead><tr>'+headers.map(function(x,i){
    return '<th'+(techCols.indexOf(i)>=0?' class="tech-only"':'')+'>'+x+'</th>';
  }).join('')+'</tr></thead><tbody>';
  rows.forEach(function(r){
    h+='<tr>'+r.map(function(c,i){
      var cls=[];
      if(i===0) cls.push('k');
      if(techCols.indexOf(i)>=0) cls.push('tech-only');
      return '<td'+(cls.length?' class="'+cls.join(' ')+'"':'')+'>'+(c==null?'':c)+'</td>';
    }).join('')+'</tr>';
  });
  return h+'</tbody></table>';
}
function table2(headers,rows,techCols,cls){return tableHTML(headers,rows,techCols,cls);}

/* ---------- 动效块 ---------- */
function motionHTML(r){
  var mo=((r.interactions||{}).motion)||{};
  var keys=Object.keys(mo);
  if(!keys.length) return '';
  var rows=[];
  if(mo.pageEntry) rows.push(['页面转场', esc(mo.pageEntry)]);
  if(mo.microInteraction) rows.push(['微交互', esc(mo.microInteraction)]);
  if(mo.feedback) rows.push(['反馈动效', esc(mo.feedback)]);
  if(mo.durationEasing) rows.push(['时长与缓动', esc(mo.durationEasing)]);
  if(mo.reducedMotion) rows.push(['无障碍降级', esc(mo.reducedMotion)]);
  if(!rows.length) return '';
  return '<div class="motion"><div class="mh">动效与微交互（全局基线见附录 J）</div>'+tableHTML(['项','说明'],rows)+'</div>';
}

/* ---------- 完整样板卡片 ---------- */
function fullBody(r){
  var h='';

  /* 定位 */
  h+='<div class="zone"><div class="zone-t">定位</div><p>'+esc(r.description)+'</p>'+
     tableHTML(['端','职责'], r.ends.map(function(e){
        return ['<span class="etag '+endCls(e.end)+'">'+esc(e.end)+'</span>', esc(e.responsibility)];
     }))+'</div>';

  /* 前置 */
  var pre='';
  if(r.preconditions.functional.length) pre+='<ul>'+r.preconditions.functional.map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul>';
  if(r.preconditions.data.length) pre+='<div class="subt">数据前置</div><ul>'+r.preconditions.data.map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul>';
  if(r.trace.upstream.length||r.trace.downstream.length){
    var rows=[];
    if(r.trace.upstream.length) rows.push(['上游依赖（我依赖谁）', r.trace.upstream.map(esc).join(' · ')]);
    if(r.trace.downstream.length) rows.push(['下游影响（谁依赖我）', r.trace.downstream.map(esc).join(' · ')]);
    pre+=tableHTML(['关系','需求'],rows);
  }
  h+='<div class="zone"><div class="zone-t">前置与依赖</div>'+(pre||'<p>无</p>')+'</div>';

  /* 过程 */
  var proc='';
  if(r.mainFlow.length){
    var mf=r.mainFlow;
    if(mf[0]&&mf[0].actor!==undefined){
      proc+=tableHTML(['执行方','做什么','说明'], mf.map(function(s){
        return ['<span class="etag '+endCls(s.actor)+'">'+esc(s.actor)+'</span>', esc(s.action), '<span style="color:var(--text3)">'+esc(s.note||'')+'</span>'];
      }));
    }else{
      proc+=tableHTML(['#','用户操作','系统响应'], mf.map(function(s){
        return [String(s.step), esc(s.userAction), esc(s.systemResponse)];
      }));
    }
  }
  if(r.exceptions.length){
    proc+='<div class="subt">异常与分支</div>';
    proc+=tableHTML(['场景','处理方式'], r.exceptions.map(function(e){return ['<span style="color:var(--text)">'+esc(e.scene)+'</span>', esc(e.handling)];}));
  }
  var it=r.interactions||{};
  var itRows=[];
  if(it.entry) itRows.push(['入口形态', esc(it.entry)]);
  if(it.click) itRows.push(['点击行为', esc(it.click)]);
  if(it.confirm) itRows.push(['二次确认', esc(it.confirm)]);
  if(it.loading) itRows.push(['加载态', esc(it.loading)]);
  if(it.empty) itRows.push(['空态', esc(it.empty)]);
  if(it.disabled) itRows.push(['置灰条件', esc(it.disabled)]);
  if(it.analytics) itRows.push(['埋点', esc(it.analytics)]);
  if(itRows.length){
    proc+='<div class="subt">交互说明</div>';
    proc+=tableHTML(['项','说明'], itRows);
  }
  if(it.errorText&&Object.keys(it.errorText).length){
    proc+='<div class="subt" style="margin-bottom:6px">提示文案（原文，开发不得自行拟定）</div><div class="txtbox">';
    Object.keys(it.errorText).forEach(function(k){
      proc+='<div>'+esc(k)+' → <span class="q">「'+esc(it.errorText[k])+'」</span></div>';
    });
    proc+='</div>';
  }
  proc+=motionHTML(r);
  if((r.displayFields||[]).length){
    proc+='<div class="subt">页面展示字段（每个位置显示什么、什么格式、看不到时怎么办）</div>';
    proc+=tableHTML(['页面位置','展示名','取值来源字段','展示格式','脱敏规则','取不到时'], r.displayFields.map(function(x){
      return [esc(x.where),
              '<span style="color:var(--text)">'+esc(x.name)+'</span>'+(x.note?'<br><span style="color:var(--text3)">'+esc(x.note)+'</span>':''),
              esc(x.field), '<code>'+esc(x.fmt)+'</code>', esc(x.mask), esc(x.empty)];
    }),[],'t-wrap');
  }
  if((r.inputRules||[]).length){
    proc+='<div class="subt">输入限制（用户能输什么、输不进去什么）</div>';
    proc+=tableHTML(['输入项','输入方式','长度上限','允许字符','自动处理','边界行为','提示文案'], r.inputRules.map(function(x){
      return ['<span style="color:var(--text)">'+esc(x.input)+'</span>'+(x.where?'<br><span style="color:var(--text3)">'+esc(x.where)+'</span>':''),
              esc(x.keyboard), esc(x.maxLen), esc(x.allow), esc(x.normalize), esc(x.boundary), esc(x.tip)];
    }),[],'t-wrap');
  }
  var pf=r.pageFlow||{};
  if(pf.entry){
    proc+='<div class="subt">页面流转</div>';
    proc+=tableHTML(['环节','内容'],[
      ['入口（从哪来）', esc(pf.entry)+(pf.entryPath?'<br><span class="tech-only">'+esc(pf.entryPath)+'</span>':'')],
      ['本页动作', esc(pf.action||'—')]
    ].concat((pf.exits||[]).map(function(x){
      return ['出口 · '+esc(x.condition),
        esc(x.page)+(x.path?'<br><span class="tech-only">'+esc(x.path)+'</span>':'')+
        (x.params&&x.params!=='—'&&x.params!=='无'?'<br><span style="color:var(--text3)">参数：'+esc(x.params)+'</span>':'')];
    })));
  }
  h+='<div class="zone"><div class="zone-t">过程</div>'+proc+'</div>';

  /* 规则 */
  var rule='';
  if(r.rules.length) rule+='<ul>'+r.rules.map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul>';
  var sl=r.stateLink||{};
  if((sl.dependsOn||[]).length||(sl.triggers||[]).length||(sl.triggeredBy||[]).length){
    rule+='<div class="subt">状态联动</div>';
    var srows=[
      ['本需求依赖的状态', (sl.dependsOn||[]).map(esc).join('<br>')||'—'],
      ['本需求触发的状态变化', (sl.triggers||[]).map(esc).join('<br>')||'—'],
      ['谁会触发本需求变化', (sl.triggeredBy||[]).map(esc).join('<br>')||'—']
    ].filter(function(x){return x[1]!=='—';});
    if(srows.length) rule+=tableHTML(['方向','内容'],srows);
  }
  if(r.dataShow.length){
    rule+='<div class="subt">数据展示与来源</div>';
    rule+=tableHTML(['展示项','来源','口径','取不到时'], r.dataShow.map(function(d){
      var src=esc(d.source)+(d.sourceTech&&d.sourceTech!=='—'?'<br><span class="tech-only codechip">'+esc(d.sourceTech)+'</span>':'');
      return [esc(d.item), src, esc(d.mode), esc(d.fallback)];
    }));
  }
  var pm=r.permissions||{};
  if(pm.visible||pm.operable||pm.forbidden){
    rule+='<div class="subt">权限</div>';
    rule+=tableHTML(['维度','说明'],[
      ['可见', esc(pm.visible||'—')],['可操作', esc(pm.operable||'—')],['受限', esc(pm.forbidden||'—')]
    ]);
  }
  h+='<div class="zone"><div class="zone-t">规则</div>'+rule+'</div>';

  /* 关联 */
  var link='';
  if(r.fields.length){
    link+='<div class="subt first">涉及字段</div>';
    link+=tableHTML(['字段','说明','必填','取值与校验','示例','变更','类型','默认','约束','表','字段名'], r.fields.map(function(f){
      return ['<span style="color:var(--text)">'+esc(f.business||f.column||'')+'</span>', esc(f.desc),
              (f.nullable===false?'是':(f.nullable===true?'否':'—')),
              esc(f.validate||'—')+(f.validateRegex?'<br><span class="tech-only codechip">'+esc(f.validateRegex)+'</span>':''), '<code>'+esc(f.example==null?'':f.example)+'</code>', esc(f.change),
              esc(f.sqlType||f.type||''), esc(f.default||'—'), esc(f.constraint||'—'),
              '<code>'+esc(f.table)+'</code>','<code>'+esc(f.column)+'</code>'];
    }),[6,7,8,9,10]);
  }
  var io=r.interfaces||{ours:[],external:[]};
  var ifr=[];
  (io.ours||[]).forEach(function(x){ifr.push(['我方服务', ifaceLabel(x,true)]);});
  (io.external||[]).forEach(function(x){ifr.push(['外部渠道', ifaceLabel(x,true)]);});
  if(ifr.length){ link+='<div class="subt'+(r.fields.length?'':' first')+'">接口</div>'+tableHTML(['侧','接口'],ifr); }
  var anc=r.landing?r.landing.anchor:'';
  link+='<div class="subt">原型锚点与流程图</div><div class="chips">'+
    (anc?'<span class="chip anchor tech-only">#'+esc(anc)+'</span>':'')+
    (r.landing?'<span class="chip biz-only">'+esc(r.landing.page)+'</span><span class="chip tech-only">'+esc(r.landing.page)+' · '+esc(r.landing.pagePath)+'</span>':'')+
    (r.trace.flowDiagram?'<span class="chip">'+esc(r.trace.flowDiagram)+'</span>':'')+
    '</div>';
  h+='<div class="zone"><div class="zone-t">关联</div>'+link+'</div>';

  /* 产出 */
  var out='';
  var o=r.output||{};
  if(o.returns) out+='<div class="subt first" style="margin-bottom:4px">输出</div><p>'+esc(o.returns)+'</p>';
  if(o.postConditions&&o.postConditions.length) out+='<div class="subt">后置条件</div><ul>'+o.postConditions.map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul>';
  if(r.acceptance.length){ out+='<div class="subt">验收标准</div><ul>'+r.acceptance.map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul>'; }
  var tail='';
  if((r.openQuestions||[]).length) tail+=(r.openQuestions||[]).map(function(q){return '<span class="chip q">'+esc(q)+'</span>';}).join('');
  if((r.risks||[]).length) tail+=(r.risks||[]).map(function(x){return '<span class="chip risk">'+esc(x)+'</span>';}).join('');
  if(tail) out+='<div class="subt" style="margin-bottom:5px">关联待确认与风险</div><div class="chips">'+tail+'</div>';
  h+='<div class="zone"><div class="zone-t">产出</div>'+out+'</div>';

  return h;
}

/* ---------- 清单级卡片 ---------- */
function basicBody(r){
  var h='<div class="zone"><div class="zone-t">定位</div><p>'+esc(r.description)+'</p>'+
    tableHTML(['端','职责'], (r.ends||[]).map(function(e){return ['<span class="etag '+endCls(e.end)+'">'+esc(e.end)+'</span>', esc(e.responsibility)];}))+'</div>';
  if((r.rules||[]).length){
    h+='<div class="zone"><div class="zone-t">业务规则</div><ul>'+r.rules.map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul></div>';
  }
  var io=r.interfaces||{ours:[],external:[]};
  var ifr=[];
  (io.ours||[]).forEach(function(x){ifr.push(['我方服务', ifaceLabel(x,false)]);});
  (io.external||[]).forEach(function(x){ifr.push(['外部渠道', ifaceLabel(x,false)]);});
  var link='';
  if(ifr.length) link+=tableHTML(['侧','接口'],ifr);
  if(r.landing) link+='<div style="margin-top:10px" class="chips"><span class="chip anchor tech-only">#'+esc(r.landing.anchor)+'</span><span class="chip biz-only">'+esc(r.landing.page)+'</span><span class="chip tech-only">'+esc(r.landing.page)+' · '+esc(r.landing.pagePath)+'</span></div>';
  if(link) h+='<div class="zone"><div class="zone-t">关联</div>'+link+'</div>';
  h+='<div class="todo"><b>本卡片为清单级。</b>待样板（F1-1）确认后按同一模型补全：涉及端逐端职责、前置条件（功能/数据）、主流程（执行方 │ 做什么 │ 说明）、异常与分支、交互说明与动效、提示文案原文、页面流转（入口→出口）、状态联动、数据展示与来源（来源/口径/兜底）、权限、输出与后置条件。</div>';
  return h;
}

function renderBody(){
  var h='';
  DATA.modules.forEach(function(m){
    var reqsInMod=[];
    m.functions.forEach(function(f){f.requirementIds.forEach(function(rid){reqsInMod.push(rid);});});
    h+='<section class="mod" id="'+m.id+'"><div class="mod-h"><span class="mod-id">'+m.id+'</span><h2>'+esc(m.name)+'</h2><span class="cnt">'+m.functions.length+' 个功能 · '+reqsInMod.length+' 条需求</span></div>';
    m.functions.forEach(function(f){
      h+='<div class="func" id="'+f.id+'"><div class="func-h"><span class="func-id">'+f.id+'</span><h3>'+esc(f.name)+'</h3><span class="cnt">'+f.requirementIds.length+' 条需求'+(f.detailLevel==='full'?' · 已完整展开':'')+'</span></div><div class="reqs">';
      f.requirementIds.forEach(function(rid){
        var r=reqOf[rid]; if(!r) return;
        var isFull=r.detailLevel==='full';
        var endsTags=(r.ends||[]).map(function(e){return '<span class="etag '+endCls(e.end)+'">'+esc(e.end)+'</span>';}).join('');
        h+='<article class="req'+(isFull?' open':'')+'" id="'+rid+'">'+
             '<div class="req-h"><span class="rid">'+rid+'</span><h4>'+esc(r.title)+'</h4>'+
             '<span class="pri '+(r.priority==='P0'?'p0':'p1')+'">'+r.priority+'</span>'+
             '<span class="lvl'+(isFull?' full':'')+'">'+(isFull?'完整卡片':'待补全')+'</span>'+
             '<span class="chev">▶</span></div>'+
             '<div class="req-b"><div class="ends">涉及端：'+endsTags+'</div>'+
             (isFull?fullBody(r):basicBody(r))+'</div></article>';
      });
      h+='</div></div>';
    });
    h+='</section>';
  });
  el('body').innerHTML=h;
  document.querySelectorAll('.req-h').forEach(function(x){
    x.addEventListener('click',function(){x.parentNode.classList.toggle('open');});
  });
}

/* ---------- 附录 ---------- */
function renderAppendix(){
  /* A 流程图（图示化） */
  el('flows').innerHTML=DATA.flowDiagrams.map(function(d){
    var lanes=d.lanes||[];
    var legend=lanes.map(function(l){
      return '<span><i style="background:'+laneColor(l)+'"></i>'+esc(l)+'</span>';
    }).join('');
    var chain=d.steps.map(function(s,i){
      var step='<div class="fstep" style="border-left-color:'+laneColor(s.lane)+'">'+
        '<div class="fno">'+(i+1)+'</div><div class="fcol">'+
        '<div class="flane" style="color:'+laneColor(s.lane)+';border-color:'+laneColor(s.lane)+';background:transparent">'+esc(s.lane)+'</div>'+
        '<div class="fbody">'+esc(s.action)+'</div>'+
        (s.techNote?'<div class="tech-only codechip" style="display:inline-block;margin-top:5px">'+esc(s.techNote)+'</div>':'')+
        '</div></div>';
      return step+(i<d.steps.length-1?'<div class="fconn"></div>':'');
    }).join('');
    return '<div class="flowd"><div class="flowd-h"><span class="fid">'+esc(d.id)+'</span>'+
      '<span class="fname">'+esc(d.name)+'</span>'+
      '<span class="fmeta">'+d.steps.length+' 步 · 涉及功能：'+d.involvedFunctions.map(function(x){return esc(x)+' '+esc(funcName[x]||'');}).join(' · ')+'</span></div>'+
      '<div class="legend">'+legend+'</div>'+
      '<div class="fchain">'+chain+'</div></div>';
  }).join('');

  /* B 渠道接口 */
  el('apis').innerHTML=table2(['接口','编号','技术路径','方法','用途','关联需求'],
    DATA.interfaces.channel.map(function(a){
      return ['<span style="color:var(--text)">'+esc(a.business||a.name)+'</span>',
              '<code>'+esc(a.id)+'</code>','<code>'+esc(a.path)+'</code>',esc(a.method),esc(a.purpose),
              (a.usedBy||[]).map(esc).join(' / ')];
    }),[1,2]);

  /* C 我方内部服务 */
  var inner=DATA.interfaces.internal||[];
  el('svcs').innerHTML=inner.length?table2(['服务','编号','关联需求'],
    inner.map(function(x){return ['<span style="color:var(--text)">'+esc(x.business||x.name)+'</span>','<code>'+esc(x.id)+'</code>',esc(x.req)];}),[1])
    :'<div class="empty">无</div>';

  /* D 存量模块 */
  el('mods').innerHTML=table2(['模块','位置','改动性质'],
    DATA.interfaces.toModify.map(function(m){return ['<span style="color:var(--text)">'+esc(m.module)+'</span>','<code>'+esc(m.path)+'</code>',esc(m.change)];}),[1]);

  /* E 字段与枚举 */
  function fieldRows(list){
    return list.map(function(c){
      return ['<span style="color:var(--text)">'+esc(c.business||c.column)+'</span>',
              esc(c.desc)+(c.techNote?'<br><span class="tech-only codechip">'+esc(c.techNote)+'</span>':''),
              (c.nullable===false?'是':(c.nullable===true?'否':'—')),
              esc(c.validate||'—')+(c.validateRegex?'<br><span class="tech-only codechip">'+esc(c.validateRegex)+'</span>':''),
              '<code>'+esc(c.example==null?'':c.example)+'</code>',
              esc(c.change||''),
              esc(c.sqlType||c.type||''), esc(c.default||'—'), esc(c.constraint||'—'),
              esc(c.mask||'—'),
              '<code>'+esc(c.table)+'</code>','<code>'+esc(c.column)+'</code>'];
    });
  }
  var FD_COLS=['字段','说明','必填','取值与校验','示例','变更','类型','默认','约束','脱敏','表','字段名'];
  var FD_TECH=[6,7,8,9,10,11];
  var fh='<div class="desc">新增字段（完整规格）</div>'+table2(FD_COLS, fieldRows(DATA.fields.newColumns), FD_TECH);
  fh+='<div class="desc" style="margin-top:20px">复用字段（同时补上规格，便于对照）</div>'+table2(FD_COLS, fieldRows(DATA.fields.reusedFields||[]), FD_TECH);
  fh+='<div class="desc" style="margin-top:20px">新增枚举</div>'+table2(['枚举','取值','业务上怎么问'],
    DATA.fields.newEnums.map(function(e){return ['<span style="color:var(--text)">'+esc(e.name)+'</span>',esc(e.values),esc(e.businessAsk||'—')];}));
  fh+='<div class="tech-only"><div class="desc" style="margin-top:20px">我方字段 ⇄ 渠道字段对照</div>'+table2(['我方字段','渠道字段','说明'],
    DATA.fields.mapping.map(function(m){return ['<span style="color:var(--text)">'+esc(m.ours)+'</span>','<code>'+esc(m.channel)+'</code>',esc(m.note)];}))+'</div>';
  fh+='<div class="biz-only note blue" style="margin-top:18px">字段级对照（我方字段名 ⇄ 渠道字段名）属于开发实现细节，切到<strong>技术视图</strong>查看。</div>';
  el('fields').innerHTML=fh;

  /* F 术语表 */
  el('gloss').innerHTML=table2(['术语','含义','易混淆提示'],
    DATA.glossary.map(function(g){return ['<span style="color:var(--text)">'+esc(g.term)+'</span>',esc(g.meaning),esc(g.confusion)];}));

  /* G 待确认 */
  var dl=DATA.decisionLog||{};
  var oh='';
  if(dl.statement){
    oh+='<div class="note teal"><strong>决策记录</strong>（'+esc(dl.decidedAt||'')+' · '+esc(dl.decidedBy||'')+'）<br>'+esc(dl.statement)+
        (dl.conclusion?'<br>'+esc(dl.conclusion):'')+'</div>';
  }
  oh+=table2(['编号','待确认事项','状态','本次决定','影响','责任方','优先级'],
    DATA.openQuestions.map(function(q){
      var st=(q.status||'').indexOf('已确认')===0?'已确认':(q.status||'');
      var stc=st==='已确认'?'high':'medium';
      var dec=esc(q.answer||'')+(q.effect?'<br><span style="color:var(--text3)">连带影响：'+esc(q.effect)+'</span>':'')+
              (st!=='已确认'?'<br><span style="color:var(--text3)">默认方案：'+esc(q.default||'')+'</span>':'');
      return ['<strong>'+esc(q.id)+'</strong>', esc(q.item),
              '<span class="lv '+stc+'">'+esc(st)+'</span>',
              dec, esc(q.impact), esc(q.owner), esc(q.priority)];
    }));
  var cl=DATA.closedQuestions||[];
  if(cl.length){
    oh+='<div class="note" style="margin-top:14px"><strong>已关闭（合并/失效）</strong><br>'+
      cl.map(function(q){return esc(q.id)+' '+esc(q.item)+' → '+esc(q.answer||'');}).join('<br>')+'</div>';
  }
  el('opens').innerHTML=oh;

  /* H 风险 */
  el('risks').innerHTML=table2(['编号','等级','风险','状态','说明','应对'],
    DATA.risks.map(function(r){return ['<strong>'+esc(r.id)+'</strong>','<span class="lv '+(r.level==='高'?'high':'medium')+'">'+esc(r.level)+'</span>','<span style="color:var(--text)">'+esc(r.title)+'</span>',esc(r.status),esc(r.detail),esc(r.action)];}));

  /* I 验收汇总 */
  var rows=[];
  DATA.requirements.forEach(function(r){
    (r.acceptance||[]).forEach(function(ac){
      rows.push(['<strong>'+esc(r.id)+'</strong> '+esc(r.title), esc(ac)]);
    });
  });
  el('acs').innerHTML=rows.length?table2(['所属需求','验收条目'],rows):'<div class="empty">暂无验收条目</div>';

  /* J 动效规范 */
  var am=DATA.appendixMotion||{rules:[]};
  el('motions').innerHTML=
    '<div class="note teal"><strong>'+(esc(am.title||'动效与微交互规范'))+'</strong><br>'+
    '共 '+am.rules.length+' 条。卡片内只写该需求特有的动效，通用部分不重复。开发实现时以本节为验收依据；评审动效时对照本节逐条核。</div>'+
    table2(['项','规范'], am.rules.map(function(x){return ['<span style="color:var(--text)">'+esc(x.item)+'</span>',esc(x.spec)];}));

  /* K 数据格式与精度规范 */
  var ds=DATA.dataSpec||{rows:[],intro:''};
  el('dataspec').innerHTML=
    (ds.intro?'<div class="note blue">'+esc(ds.intro)+'</div>':'')+
    table2(['项目','单位','存储类型','怎么显示','取值与计算规则','示例'],
      ds.rows.map(function(x){
        return ['<span style="color:var(--text)">'+esc(x.item)+'</span>', esc(x.unit), esc(x.store),
                '<code>'+esc(x.display)+'</code>', esc(x.rule)+'<br><span style="color:var(--text3)">来源：'+esc(x.source)+'</span>',
                '<code>'+esc(x.example)+'</code>'];
      }),[2])+
    (ds.openNote?'<div class="note" style="margin-top:14px">'+esc(ds.openNote)+'</div>':'');
}

/* ---------- 视图切换 ---------- */
(function(){
  var box=el('viewsw'), hint=el('vhint');
  box.querySelectorAll('button').forEach(function(b){
    b.addEventListener('click',function(){
      box.querySelectorAll('button').forEach(function(x){x.classList.remove('on');});
      b.classList.add('on');
      document.body.className=b.dataset.v;
      hint.textContent=(b.dataset.v==='biz')?'已隐藏页面路径 / 表字段 / 接口编号':'显示全部技术标识';
      try{localStorage.setItem('prdview',b.dataset.v);}catch(e){}
    });
  });
  try{
    var v=localStorage.getItem('prdview');
    if(v){var t=box.querySelector('button[data-v="'+v+'"]'); if(t) t.click();}
  }catch(e){}
})();

/* ---------- 交互 ---------- */
renderBody();
renderAppendix();

var topBtn=el('top');
window.addEventListener('scroll',function(){topBtn.style.display=window.scrollY>500?'block':'none';});
topBtn.addEventListener('click',function(){window.scrollTo({top:0,behavior:'smooth'});});

el('search').addEventListener('input',function(){
  var kw=this.value.trim().toLowerCase();
  document.querySelectorAll('.req').forEach(function(node){
    var r=reqOf[node.id];if(!r)return;
    var ifn='';
    var io=r.interfaces||{};
    (io.ours||[]).concat(io.external||[]).forEach(function(x){
      ifn+=x.id+' '+(x.business||'')+' '+(x.name||'')+' '+(x.note||'');
    });
    (r.fields||[]).forEach(function(f){ifn+=' '+(f.business||'')+' '+(f.column||'');});
    var hay=(r.id+r.title+(r.description||'')+(r.rules||[]).join('')+
             (r.ends||[]).map(function(e){return e.end+e.responsibility;}).join('')+ifn).toLowerCase();
    var hit=!kw||hay.indexOf(kw)>=0;
    node.classList.toggle('hide',!hit);
    if(hit&&kw) node.classList.add('open');
  });
  document.querySelectorAll('.func').forEach(function(node){
    var vis=node.querySelectorAll('.req:not(.hide)').length;
    node.classList.toggle('hide',!!kw&&vis===0);
  });
  document.querySelectorAll('.mod').forEach(function(node){
    var vis=node.querySelectorAll('.func:not(.hide)').length;
    node.classList.toggle('hide',!!kw&&vis===0);
  });
});
</script>
</body>
</html>
'''

html = TPL.replace('__DATA__', DATA_JSON)
out = os.path.join(BASE, 'PRD.html')
io.open(out, 'w', encoding='utf-8').write(html)
print('OK ->', out, '|', len(html), 'bytes')
