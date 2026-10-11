# -*- coding: utf-8 -*-
"""白板式画布的外壳（点阵背景 + 无限缩放平移）。

和上一版（网页网格列表）的区别：
    上一版是文档流，靠滚动看、靠改宽度缩放 —— 页面一多就得上下翻，找不到"全貌"。
    这一版是白板：所有元素绝对定位在一块大画布上，缩放平移看整体或看细节，
    缩到 20% 一眼看全，放大到 100% 看单屏。这是评审和汇报时更好用的形态。

两个坐标系别混：
    世界坐标（world）—— 元素在画布上的位置，由 build-canvas.py 算好写进内联样式
    屏幕坐标（screen）—— 世界经过 translate(vx,vy) scale(vs) 之后显示的位置
    缩放要**以鼠标为中心**，所以改 scale 时要同步反解 vx/vy，否则画面会往左上角跑。
"""

import json

CSS = """
:root{--bg:#0d1117;--dot:#1e2731;--card:#161b22;--card2:#0b0f14;--border:#2b333d;
      --text:#e6edf3;--muted:#8b949e;--green:#3fb950;--amber:#d29922;--red:#f85149;
      --accent:#58a6ff;--purple:#bc8cff;--teal:#39c5bb}
*{box-sizing:border-box}
html,body{margin:0;height:100%;overflow:hidden}
body{background:var(--bg);color:var(--text);font-size:13px;line-height:1.5;
     font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
     -webkit-font-smoothing:antialiased}

/* ---------------- 画布本体 ---------------- */
#board{position:fixed;inset:0;overflow:hidden;cursor:grab;touch-action:none}
#board.grabbing{cursor:grabbing}
#dots{position:absolute;inset:0;
      background-image:radial-gradient(circle,var(--dot) 1.15px,transparent 1.15px);
      background-size:24px 24px}
/* 世界层。⚠️ 这里**故意不写 will-change:transform**。
   写上的话 Chrome 会把整个世界层按「当时的缩放」光栅化成一张贴图，之后缩放只是放大这张贴图
   —— 于是在 fit 视图（0.44）光栅化，放大到 2 倍就是在放大 0.44 倍的图，糊得肉眼可见。
   实测（_diag_sharp.py）：去掉后同一视角清晰度指标 1.75 → 3.72（+113%）。
   拖拽期间再临时加上去换流畅度（见 JS），松手就撤掉，静止时一定是清晰的那一版。 */
#world{position:absolute;left:0;top:0;transform-origin:0 0}

/* ---------------- 元素 ---------------- */
.el{position:absolute;background:var(--card);border:1px solid var(--border);
    border-radius:9px;overflow:hidden;box-shadow:0 3px 12px rgba(0,0,0,.35)}
.hide{display:none!important}
.el-h{display:flex;align-items:center;gap:6px;height:28px;padding:0 9px;
      border-bottom:1px solid var(--border);background:#12171d;white-space:nowrap}
.el-ic{width:7px;height:7px;border-radius:2px;flex:none;background:var(--accent)}
.el-t{font-size:11.5px;font-weight:600;overflow:hidden;text-overflow:ellipsis}
.el-c{margin-left:auto;font-size:9.5px;border-radius:20px;padding:0 6px;flex:none}
.c-new{background:#132a1c;color:var(--green);border:1px solid #1d4429}
.c-rework{background:#2c2413;color:var(--amber);border:1px solid #4a3c18}
.c-var{background:#1c1428;color:var(--purple);border:1px solid #362a4d}
.c-todo{background:#241a1a;color:#c98b8b;border:1px solid #3d2626}
.el-img{position:relative;overflow:hidden;background:var(--card2)}
.el-img img{width:100%;display:block}
.el-f{display:flex;flex-wrap:wrap;gap:4px;padding:5px 8px;min-height:26px;align-items:center}
.br{font-family:ui-monospace,Consolas,monospace;font-size:9.5px;color:var(--muted);
    border:1px solid var(--border);border-radius:4px;padding:0 4px}
.br.p0{color:var(--red);border-color:#5a2a2c;background:#221214}
.el-wait{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:6px;
         color:#5b6672;font-size:12px;background:var(--card2);border-bottom:1px dashed #2b333d}
.el-wait span{font-size:11px;color:#4b5560;text-align:center;padding:0 18px;line-height:1.6}

/* 文档卡（说明/统计/图例）—— 与页面卡区分开，一眼知道那不是界面 */
.el.doc{background:#111820;border-color:#26313d}
.el.doc .el-h{background:#0d1319}
.el.doc .el-ic{background:var(--teal)}
.doc-b{padding:11px 13px;font-size:12px;line-height:1.75;color:#c3ccd6}
.doc-b h4{margin:0 0 7px;font-size:12.5px;color:var(--text)}
.doc-b b{color:#fff}
.doc-b code{background:#0b0f14;border:1px solid #212832;border-radius:4px;padding:0 4px;
            font-family:ui-monospace,Consolas,monospace;font-size:11px;color:#8fa3b5}
.doc-b .row{display:flex;gap:7px;padding:3px 0;border-bottom:1px dashed #1e2731}
.doc-b .row:last-child{border-bottom:0}
.doc-b .k{color:var(--muted);flex:none;width:82px}
.doc-b .v{color:#dfe6ee}
.doc-b .big{font-size:20px;font-weight:700;color:var(--green);line-height:1.3}
.doc-b ul{margin:5px 0 0;padding-left:16px}
.doc-b li{margin-bottom:3px}
.lg{display:flex;align-items:center;gap:7px;padding:3px 0}
.lg i{width:11px;height:11px;border-radius:3px;flex:none;border:1px solid}

/* 组标签（Figma 的 frame 名那种） */
.glab{position:absolute;color:#7d8794;font-size:12px;white-space:nowrap;
      display:flex;align-items:baseline;gap:8px}
.glab b{color:#c3ccd6;font-size:13px;font-weight:600}
.glab em{font-style:normal;color:var(--purple);font-size:10.5px;border:1px solid #3a2f4d;
         background:#1b1425;border-radius:20px;padding:0 7px}
.blab{position:absolute;color:#5f6a76;font-size:11px;white-space:nowrap}

/* ---------------- 双视图：技术信息开关 ----------------
   一条规则收起全部技术信息。业务视图是给领导/客户看的，路径、锚点名、页面文件
   这些出现在屏幕上只会转移注意力。

   ⚠️ 这条规则**必须靠自己的样本守住**。画布上的 .an 锚点框虽然也标了 .t-only，
   但它们另有 .an{display:none} 管着 —— 也就是说，就算把这整条规则删掉，
   业务视图看上去也「没有任何技术信息泄露」（因为锚点框默认就不显示）。
   所以校验里必须另外找一个**非锚点框**的 .t-only 元素（灯箱里的路径行、
   锚点清单、页面文件）来量，否则这条检查证明不了任何事。 */
body.biz .t-only{display:none!important}

/* ---------------- 锚点框 ---------------- */
.an{position:absolute;display:none;border:1.5px solid var(--red);
    background:rgba(248,81,73,.13);border-radius:3px;pointer-events:none}
body.anno .an{display:block}
body.anno .an::after{content:attr(data-i);position:absolute;left:0;top:0;
    font-family:ui-monospace,Consolas,monospace;font-size:9px;line-height:1;color:#fff;
    background:var(--red);padding:2px 4px;border-radius:0 0 3px 0}

/* ---------------- 浮动 UI ---------------- */
.hud{position:fixed;z-index:80;display:flex;align-items:center;gap:9px}
.hud.tl{left:14px;top:12px}
.hud.tr{right:14px;top:12px;flex-wrap:wrap;justify-content:flex-end;max-width:78vw}
.hud.br{right:14px;bottom:14px;gap:10px}
.hud.bl{left:14px;bottom:14px}
.panel{display:flex;align-items:center;gap:9px;background:rgba(17,22,29,.93);
       border:1px solid var(--border);border-radius:10px;padding:7px 11px;
       backdrop-filter:blur(9px);box-shadow:0 4px 16px rgba(0,0,0,.4)}
.logo{font-size:13.5px;font-weight:700}
.sub{font-size:11.5px;color:var(--muted)}
.seg{display:flex;border:1px solid var(--border);border-radius:7px;overflow:hidden}
.seg button{background:transparent;border:0;color:var(--muted);font:inherit;font-size:11.5px;
            padding:4px 10px;cursor:pointer}
.seg button+button{border-left:1px solid var(--border)}
.seg button.on{background:var(--accent);color:#0d1117;font-weight:700}
.seg button:hover:not(.on){background:#1d242e;color:var(--text)}
#q{background:#0b0f14;border:1px solid var(--border);border-radius:7px;color:var(--text);
   font:inherit;font-size:11.5px;padding:5px 10px;width:216px;outline:none}
#q:focus{border-color:var(--accent)}
#q::placeholder{color:#5b6672}
.btn{background:#0b0f14;border:1px solid var(--border);border-radius:7px;color:var(--muted);
     font:inherit;font-size:11.5px;padding:5px 10px;cursor:pointer;white-space:nowrap}
.btn:hover{color:var(--text);border-color:#4b5666}
.btn.on{background:var(--amber);border-color:var(--amber);color:#1a1a1a;font-weight:700}
.zbtn{width:28px;height:28px;display:flex;align-items:center;justify-content:center;
      font-size:15px;padding:0}
.zbtn[disabled]{opacity:.35;cursor:not-allowed}
.zbtn[disabled]:hover{color:var(--muted);border-color:var(--border)}
.zv{font-size:11.5px;color:var(--muted);min-width:40px;text-align:center;
    font-variant-numeric:tabular-nums;cursor:pointer}
.zv:hover{color:var(--text)}
/* 到了源图分辨率的极限就明说，而不是让用户放大到糊了才怀疑画布有问题 */
.zc{display:block;font-size:8.5px;line-height:1;color:var(--amber);margin-top:1px}

/* 小地图 */
.mini{width:196px;height:124px;background:rgba(11,15,20,.92);border:1px solid var(--border);
      border-radius:8px;position:relative;overflow:hidden;cursor:crosshair}
.mini i{position:absolute;background:#2c3644;border-radius:1px;display:block}
.mini i.doc{background:#2a4a52}
.mini i.todo{background:#3a2a2a}
.mini-vp{position:absolute;border:1.5px solid var(--accent);background:rgba(88,166,255,.13);
         border-radius:2px;pointer-events:none}
.mini-l{position:absolute;left:0;top:0;transform-origin:0 0}

/* 提示条 */
.tip{background:rgba(17,22,29,.9);border:1px solid var(--border);border-radius:10px;
     padding:6px 11px;font-size:11px;color:var(--muted);backdrop-filter:blur(9px)}
.tip b{color:#c3ccd6;font-weight:600}

/* ---------------- 灯箱 ---------------- */
.lb{position:fixed;inset:0;z-index:200;display:flex}
.lb[hidden]{display:none}
.lb-mask{position:absolute;inset:0;background:rgba(2,5,9,.88)}
.lb-wrap{position:relative;display:flex;width:100%;height:100%}
.lb-left{flex:1;min-width:0;display:flex;flex-direction:column}
.lb-bar{display:flex;align-items:center;gap:10px;padding:10px 16px;border-bottom:1px solid var(--border)}
.lb-t{font-size:14px;font-weight:600}
.lb-v{font-size:12px;color:var(--amber)}
.lb-nav{margin-left:auto;display:flex;gap:6px}
.lb-nav button,.lb-x{background:#0b0f14;border:1px solid var(--border);color:var(--text);
    font:inherit;font-size:12.5px;border-radius:6px;padding:4px 11px;cursor:pointer}
.lb-x:hover{background:var(--red);border-color:var(--red)}
.lb-img{flex:1;overflow:auto;padding:16px;display:flex;align-items:flex-start;justify-content:center}
.lb-img .imw{position:relative;max-width:100%}
.lb-img img{max-height:calc(100vh - 116px);width:auto;max-width:100%;display:block}
.lb-side{width:352px;flex:none;border-left:1px solid var(--border);overflow:auto;
         background:#10151c;padding:14px 16px 44px}
.lb-side h4{margin:15px 0 6px;font-size:11.5px;color:var(--muted);font-weight:700;
            letter-spacing:.5px;text-transform:uppercase}
.lb-side h4:first-child{margin-top:0}
.lb-goal{font-size:12.5px;line-height:1.75;color:#c3ccd6}
.lb-kv{display:flex;gap:8px;font-size:12px;padding:5px 0;border-bottom:1px solid #1b2129}
.lb-kv .k{color:var(--muted);flex:none;width:72px}
.lb-kv .v{color:var(--text);word-break:break-all}
.a-list{display:flex;flex-direction:column;gap:6px}
.a-it{background:#151b23;border:1px solid #212832;border-radius:7px;padding:7px 9px}
.a-it .an-n{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--red);font-weight:600}
.a-it .an-b{font-family:ui-monospace,Consolas,monospace;font-size:10px;color:var(--accent);margin-left:6px}
.a-it .an-l{font-size:11.5px;color:#c3ccd6;margin-top:3px;line-height:1.5}
.a-it.extra{border-style:dashed}
.a-it .an-x{font-size:10px;color:var(--purple);margin-left:6px}
.a-it.off{opacity:.46}
.a-it.cur{border-color:var(--amber);background:#1d1a10}
.lb-br{display:flex;flex-direction:column;gap:5px}
.br-it{display:flex;gap:7px;font-size:12px;align-items:baseline}
.br-it .c{font-family:ui-monospace,Consolas,monospace;font-size:10.5px;color:var(--red);flex:none}
.br-it .c.p1{color:var(--amber)}
.br-it .t{color:#c3ccd6}
.lb-src{font-family:ui-monospace,Consolas,monospace;font-size:10.5px;color:#6e7a87;
        background:#0b0f14;border:1px solid #212832;border-radius:5px;padding:2px 7px;
        display:inline-block;margin-top:3px}
"""

JS = """
var D=window.__CANVAS__;
var board=document.getElementById('board'), world=document.getElementById('world'),
    dots=document.getElementById('dots'), mini=document.getElementById('mini'),
    miniL=document.getElementById('miniL'), miniBox=document.getElementById('miniVP');
var vx=0, vy=0, vs=1;

function apply(){
  world.style.transform='translate('+vx+'px,'+vy+'px) scale('+vs+')';
  var g=24*vs;
  dots.style.backgroundSize=g+'px '+g+'px';
  dots.style.backgroundPosition=vx+'px '+vy+'px';
  var atMax=vs>=maxZ()-0.001;
  document.getElementById('zv').innerHTML=Math.round(vs*100)+'%'
    +(atMax?'<span class="zc">已达上限</span>':'');
  document.getElementById('zIn').disabled=atMax;
  miniVP();
}
/* 给校验脚本 / 出图脚本用的视角控制口。vx/vy/vs 是闭包变量，外部改不了，
   所以必须由引擎自己暴露 —— 在外部「猜」一个 transform 再写回 style 是错的：
   下次任何一次 apply()（缩放、拖拽、fit）都会把它覆盖掉。 */
window.__setView__=function(k,x,y){ vs=k; vx=x; vy=y; apply(); return {k:k,x:x,y:y}; };
window.__getView__=function(){ return {k:vs,x:vx,y:vy}; };
window.__fit__=function(pad){ fit(pad||56); return window.__getView__(); };
window.__centerOn__=function(el,k){
  if(!el) return null;
  var x=parseFloat(el.style.left||'0')+el.offsetWidth/2,
      y=parseFloat(el.style.top||'0')+el.offsetHeight/2;
  var b=board.getBoundingClientRect();
  var kk=k||vs;
  return window.__setView__(kk, b.width/2-x*kk, b.height/2-y*kk);
};
/* 缩放上限由**源图像素预算**决定，不是一个拍脑袋的常数。
   卡片把一张图显示成 clientWidth 宽，放到 z 倍时设备上要占 clientWidth*z*dpr 个像素；
   源图只有 naturalWidth 个像素。所以 z 的上界就是两者相等的地方 —— 越过它就是在放大
   像素，怎么调都是糊的。
   写死 3.2 的后果：笔记本 150% 缩放（dpr=1.5）时源图只够撑到 2.77，150% 以上必然糊。
   实测：1032px 源图 / (248px 卡片 × 2) = 2.08 → 在 2 倍屏上超过 208% 就没救了。 */
var _mz=0;
function maxZ(){
  if(_mz) return _mz;
  var im=document.querySelector('.el-img img');
  if(!im||!im.naturalWidth||!im.clientWidth) return 3.2;   // 图还没解码，先给个默认值，不缓存
  var dpr=Math.max(1,window.devicePixelRatio||1);
  _mz=Math.min(8,Math.max(1.2,im.naturalWidth/(im.clientWidth*dpr)));
  return _mz;
}
function zoomAt(cx,cy,f){
  var ns=Math.min(maxZ(),Math.max(0.04,vs*f));
  var k=ns/vs;
  /* 以鼠标为中心缩放：先把鼠标位置换算成世界坐标，再让它在缩放后仍落回原屏幕位置 */
  vx=cx-k*(cx-vx); vy=cy-k*(cy-vy); vs=ns; apply();
}
function zoomBy(f){zoomAt(board.clientWidth/2,board.clientHeight/2,f)}

function visEls(){
  return [].slice.call(document.querySelectorAll('.el:not(.hide)'));
}
function bounds(){
  var es=visEls(); if(!es.length) return null;
  var x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;
  es.forEach(function(e){
    var px=e.offsetLeft, py=e.offsetTop, pw=e.offsetWidth, ph=e.offsetHeight;
    if(px<x0)x0=px; if(py<y0)y0=py; if(px+pw>x1)x1=px+pw; if(py+ph>y1)y1=py+ph;
  });
  /* 组标签也算进来，否则 fit 之后标题会被挤出屏幕 */
  [].slice.call(document.querySelectorAll('.glab,.blab')).forEach(function(l){
    if(l.offsetParent===null) return;
    var px=l.offsetLeft, py=l.offsetTop;
    if(px<x0)x0=px; if(py<y0)y0=py;
    if(px+l.offsetWidth>x1)x1=px+l.offsetWidth;
    if(py+l.offsetHeight>y1)y1=py+l.offsetHeight;
  });
  return {x:x0,y:y0,w:x1-x0,h:y1-y0};
}
function fit(pad){
  var R=bounds(); if(!R) return;
  pad=pad==null?64:pad;
  var w=board.clientWidth, h=board.clientHeight;
  var s=Math.min((w-pad*2)/R.w,(h-pad*2)/R.h,1.8,maxZ());
  vs=Math.max(0.04,s);
  vx=(w-R.w*vs)/2-R.x*vs; vy=(h-R.h*vs)/2-R.y*vs;
  apply();
}

/* ---- 缩放小地图 ---- */
function miniK(){
  return Math.min((mini.clientWidth-4)/D.world.w,(mini.clientHeight-4)/D.world.h);
}
function miniVP(){
  if(!mini||!miniBox) return;
  var k=miniK();
  miniL.style.transform='translate(2px,2px) scale('+k+')';
  var wx=-vx/vs, wy=-vy/vs, ww=board.clientWidth/vs, wh=board.clientHeight/vs;
  miniBox.style.left=(2+wx*k)+'px'; miniBox.style.top=(2+wy*k)+'px';
  miniBox.style.width=(ww*k)+'px'; miniBox.style.height=(wh*k)+'px';
}
if(mini) mini.addEventListener('mousedown',function(e){
  e.stopPropagation();
  var r=mini.getBoundingClientRect(), k=miniK();
  var x=(e.clientX-r.left-2)/k, y=(e.clientY-r.top-2)/k;
  vx=board.clientWidth/2-x*vs; vy=board.clientHeight/2-y*vs; apply();
});

/* ---- 拖拽平移 / 点击元素 ---- */
/* will-change 只在拖拽期间挂上：拖的时候要流畅（交给合成器），松手立刻摘掉，
   让 Chrome 按当前缩放重新光栅化 —— 静止状态下看到的永远是清晰的那一版。
   代价是拖拽过程中可能短暂偏糊（正在动，本来也看不清），换来静止时始终锐利。 */
var pan=null, hit=null;
function setHi(on){world.style.willChange=on?'transform':''}
board.addEventListener('mousedown',function(e){
  if(e.button!==0) return;
  var el=e.target.closest('.el');
  if(el){hit={el:el,x:e.clientX,y:e.clientY,moved:0};return}
  pan={x:e.clientX,y:e.clientY,vx:vx,vy:vy};
  setHi(true);
  board.classList.add('grabbing');
});
window.addEventListener('mousemove',function(e){
  if(hit){hit.moved=Math.max(hit.moved,Math.abs(e.clientX-hit.x)+Math.abs(e.clientY-hit.y))}
  if(!pan) return;
  vx=pan.vx+(e.clientX-pan.x); vy=pan.vy+(e.clientY-pan.y); apply();
});
window.addEventListener('mouseup',function(){
  if(pan){pan=null;setHi(false);board.classList.remove('grabbing')}
  if(hit){
    /* 拖动超过 4px 当成平移手势，不触发灯箱 —— 否则想挪一下画布就弹窗 */
    if(hit.moved<4 && hit.el.classList.contains('page')) openLB(hit.el);
    hit=null;
  }
});
board.addEventListener('wheel',function(e){
  e.preventDefault();
  if(e.ctrlKey||Math.abs(e.deltaY)>Math.abs(e.deltaX)){
    zoomAt(e.clientX,e.clientY,Math.exp(-e.deltaY*0.0013));
  }else{
    vx-=e.deltaX; vy-=e.deltaY; apply();
  }
},{passive:false});

/* ---- 筛选 ---- */
var fEnd='all', fChg='all', kw='';
function applyFilter(){
  var shown=0;
  [].slice.call(document.querySelectorAll('.el.page,.el.todo')).forEach(function(c){
    var id=c.dataset.id||'';
    var on=(fEnd==='all'||c.dataset.end===fEnd)
        && (fChg==='all'||c.dataset.change===fChg)
        && (!kw||(c.dataset.key||'').toLowerCase().indexOf(kw)>=0);
    c.classList.toggle('hide',!on);
    if(on) shown++;
  });
  /* 一个分组里的页全被筛掉时，组标签也要跟着消失，否则画布上留下一堆空标题 */
  [].slice.call(document.querySelectorAll('.glab')).forEach(function(g){
    var any=[].slice.call(document.querySelectorAll(
      '.el[data-g="'+g.dataset.g+'"]')).some(function(c){return !c.classList.contains('hide')});
    g.classList.toggle('hide',!any);
  });
  var hv=document.getElementById('hitv'); if(hv) hv.textContent=shown;
  fit(56);
}
function bindSeg(id,cb){
  /* 有些消费方（如 06-anno-card）自带侧栏筛选、不挂这套 HUD 控件。
     这里必须允许「控件不存在」——否则 box 为 null，读 box.children 直接抛
     未捕获异常，把整个内联脚本后续的绑定（灯箱、锚点框、视角）全部中断。 */
  var box=document.getElementById(id); if(!box) return;
  [].slice.call(box.children).forEach(function(b){
    b.onclick=function(){
      [].slice.call(box.children).forEach(function(x){x.classList.remove('on')});
      b.classList.add('on'); cb(b.dataset.e||b.dataset.c); applyFilter();
    };
  });
}
bindSeg('fEnd',function(v){fEnd=v});
bindSeg('fChg',function(v){fChg=v});
var qt=null;
var qEl=document.getElementById('q');
if(qEl) qEl.oninput=function(){
  var v=this.value.trim().toLowerCase();
  clearTimeout(qt); qt=setTimeout(function(){kw=v;applyFilter()},260);
};

/* ---- 视图与锚点 ----
   ⚠️ 这些控件是「04/05 的 HUD」专属，06-anno-card 的 HUD 换成自己的按钮组、
   没有 #tView。取不到就必须跳过 —— 直接 .onclick= 会抛未捕获异常，
   把后面所有绑定（灯箱、键盘、锚点）连带打断。 */
function bindClick(id,fn){var e=document.getElementById(id); if(e) e.onclick=fn;}
function bindClickCtx(id,fn){var e=document.getElementById(id); if(e) e.onclick=function(){fn.call(this)};}
bindClickCtx('tView',function(){
  var biz=document.body.classList.toggle('biz');
  document.body.classList.toggle('tech',!biz);
  this.innerHTML='视图：<b>'+(biz?'业务':'技术')+'</b>';
  if(biz){document.body.classList.remove('anno');
    var ta=document.getElementById('tAnno'); if(ta) ta.classList.remove('on')}
});
bindClickCtx('tAnno',function(){
  document.body.classList.toggle('anno'); this.classList.toggle('on');
});
bindClick('zIn',function(){zoomBy(1.25)});
bindClick('zOut',function(){zoomBy(0.8)});
bindClick('zFit',function(){fit(56)});
bindClick('zv',function(){zoomAt(board.clientWidth/2,board.clientHeight/2,1/vs)});

/* ---- 灯箱 ---- */
var lb=document.getElementById('lb'), lbIdx=0, lbShots=[], lbPid='';
function openLB(el){
  lbPid=el.dataset.id;
  var grp=[].slice.call(document.querySelectorAll('.el.page[data-id="'+lbPid+'"]'));
  grp.sort(function(a,b){return (+a.dataset.vi)-(+b.dataset.vi)});
  lbShots=grp.map(function(e){return e});
  lbIdx=Math.max(0,lbShots.indexOf(el));
  renderLB(); lb.hidden=false;
}
function renderLB(){
  var pg=D.pages[lbPid], el=lbShots[lbIdx];
  var cap=el.dataset.vname||'主态';
  document.getElementById('lbT').textContent=pg.id+' · '+pg.name;
  document.getElementById('lbV').textContent=cap+'（第 '+(lbIdx+1)+'/'+lbShots.length+' 屏）';
  var im=el.querySelector('.el-img').cloneNode(true);
  im.style.height=''; im.classList.add('imw');
  document.getElementById('lbImg').innerHTML='<div class="imw">'+im.innerHTML+'</div>';
  var side=[];
  side.push('<h4>页面目标</h4><div class="lb-goal">'+esc(pg.goal)+'</div>');
  side.push('<h4>页面信息</h4>'+
    kv2('改/新',pg.change)+kv2('端',pg.platform==='app'?'小程序':'管理后台')+
    kv2('编号',pg.id,1)+kv2('路径',pg.path,1));
  side.push('<h4>覆盖需求（'+pg.refs.length+' 条）</h4><div class="lb-br">'+
    pg.refs.map(function(b){
      return '<div class="br-it"><span class="c'+(D.brPrio[b]==='P1'?' p1':'')+'">'+b+
        '</span><span class="t">'+esc(D.brTitle[b]||'')+'</span></div>';
    }).join('')+'</div>');
  var here={}, numOf={};
  el.querySelectorAll('.an').forEach(function(a){here[a.dataset.a]=1;numOf[a.dataset.a]=a.dataset.i});
  side.push('<section class="t-only"><h4>锚点（'+pg.anchors.length+' 处）</h4><div class="a-list">'+
    pg.anchors.map(function(a){
      var n=numOf[a.anchor];
      return '<div class="a-it'+(a.extra?' extra':'')+(here[a.anchor]?'':' off')+'">'+
        '<span class="an-n">'+(n?n+'. ':'— ')+a.anchor+'</span>'+
        '<span class="an-b">'+a.br+'</span>'+
        (a.extra?'<span class="an-x">附加落点</span>':'')+
        '<div class="an-l">'+esc(a.label)+'</div>'+
        (here[a.anchor]?'':'<div class="an-l" style="color:#7d8794">本屏未埋（在其它状态或其它屏）</div>')+
        '</div>';
    }).join('')+'</div></section>');
  side.push('<h4>本屏状态</h4><div class="a-list">'+lbShots.map(function(e,i){
    return '<div class="a-it'+(i===lbIdx?' cur':'')+'" data-j="'+i+'" style="cursor:pointer">'+
      '<span class="an-n">'+esc(e.dataset.vname||'主态')+(i===lbIdx?' ←':'')+'</span></div>';
  }).join('')+'</div>');
  side.push('<section class="t-only"><h4>页面文件</h4><code class="lb-src">'+
    (pg.mainFile||'')+'</code></section>');
  document.getElementById('lbSide').innerHTML=side.join('');
}
function kv2(k,v,t){
  return '<div class="lb-kv'+(t?' t-only':'')+'"><span class="k">'+k+
         '</span><span class="v">'+esc(v)+'</span></div>';
}
function esc(s){return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
document.addEventListener('click',function(e){
  var st=e.target.closest('.a-it[data-j]');
  if(st&&e.target.closest('.lb-side')){lbIdx=+st.dataset.j;renderLB()}
});
function closeLB(){lb.hidden=true}
bindClick('lbX',closeLB);
lb.querySelector('.lb-mask').onclick=closeLB;
bindClick('lbPrev',function(){lbIdx=(lbIdx-1+lbShots.length)%lbShots.length;renderLB()});
bindClick('lbNext',function(){lbIdx=(lbIdx+1)%lbShots.length;renderLB()});
document.addEventListener('keydown',function(e){
  if(e.key==='Escape'){if(!lb.hidden)closeLB();return}
  if(lb.hidden) return;
  if(e.key==='ArrowLeft'){var p=document.getElementById('lbPrev'); if(p)p.click()}
  if(e.key==='ArrowRight'){var n=document.getElementById('lbNext'); if(n)n.click()}
});

/* 面板上的按钮不该触发画布平移 */
[].slice.call(document.querySelectorAll('.hud')).forEach(function(h){
  h.addEventListener('mousedown',function(e){e.stopPropagation()});
});
window.addEventListener('resize',function(){apply()});
/* 图片解码完成后重算一次：maxZ() 依赖 naturalWidth，图没解码时只能给默认值。
   这一次重算同时也把「已达上限」的提示刷新出来。 */
window.addEventListener('load',function(){
  if(vs>maxZ()) zoomAt(board.clientWidth/2,board.clientHeight/2,maxZ()/vs);
  apply();
});
fit(56);
apply();
"""


def render(world_html, payload, stats, hud_left, hud_right, hud_br, hud_bl,
           extra_css='', extra_js='', bodycls='biz', title='原型白板',
           world_extra='', body_extra=''):
    """extra_css / extra_js 给同阶段的其他画布复用：另一套画布要在世界层里再插一个
    自己的图层、加一批元素热区，但缩放平移、灯箱、双视图这套引擎一模一样。
    复制一份 _canvas_html 出来改是最糟的做法 —— 引擎一改就得改两处，
    而漏改的那一处不会报错，只会在某个视角下看着不对。

    world_extra 放在 #world 末尾：SVG 连线层要盖在卡片上面。
    """
    doc = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>%s</title>
<style>%s
%s</style>
</head>
<body class="%s">
<div id="board">
  <div id="dots"></div>
  <div id="world" style="width:%dpx;height:%dpx">%s%s</div>
</div>

%s

<div class="hud tl"><div class="panel">%s</div></div>
<div class="hud tr">%s</div>
<div class="hud br">%s</div>
<div class="hud bl">%s</div>
<div class="lb" id="lb" hidden>
  <div class="lb-mask"></div>
  <div class="lb-wrap">
    <div class="lb-left">
      <div class="lb-bar"><span class="lb-t" id="lbT"></span><span class="lb-v" id="lbV"></span>
        <div class="lb-nav"><button id="lbPrev">‹ 上一屏</button>
          <button id="lbNext">下一屏 ›</button></div>
        <button class="lb-x" id="lbX">✕ 关闭</button>
      </div>
      <div class="lb-img" id="lbImg"></div>
    </div>
    <aside class="lb-side" id="lbSide"></aside>
  </div>
</div>

<script>window.__CANVAS__=%s;window.pm={mainFile:%s};</script>
<script>%s</script>
%s
</body>
</html>
""" % (title, CSS, extra_css, bodycls, payload['world']['w'], payload['world']['h'],
       world_html, world_extra, body_extra,
       hud_left, hud_right, hud_br, hud_bl,
       json.dumps(payload, ensure_ascii=False),
       json.dumps(payload.get('mainFile', '')), JS, extra_js)
    return doc
