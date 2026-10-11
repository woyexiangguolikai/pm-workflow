/* ================= 需求卡片画布：侧栏交互 =================
   只做三件事：
     ① 手风琴（开一张收其它）
     ② 点卡片 → 画布飞到它的落点框并高亮
     ③ 搜索 / 端筛选 / 全部展开收起
   不重画世界层、不碰布局 —— 位置全在数据源里算好。 */
(function(){
  var D = window.__CANVAS__;
  var sideBody = document.getElementById('sideBody');
  var cards = [].slice.call(document.querySelectorAll('.card'));
  var pages = [].slice.call(document.querySelectorAll('.pg'));
  var ACCORDION = true;

  function setOpen(card, open){
    var body = card.querySelector('.cb');
    card.classList.toggle('open', open);
    if(body) body.hidden = !open;
  }
  function closeAll(except){
    cards.forEach(function(c){ if(c !== except) setOpen(c, false); });
  }
  function openCard(card){
    var willOpen = !card.classList.contains('open');
    if(willOpen && ACCORDION) closeAll(card);
    setOpen(card, willOpen);
    return willOpen;
  }

  /* ---- ② 飞到落点框 ----
     取景逻辑抽成通用函数：卡片（按需求号高亮整片落点框）与元素总表里的
     单个元素（只高亮它自己那一小块）走的是同一套算法，别写两份。 */
  function flyToBoxes(boxes, hlSel, appearAnno){
    [].slice.call(document.querySelectorAll('.an.hi')).forEach(function(x){
      x.classList.remove('hi');
    });
    if(!boxes.length) return 0;

    // 高亮：不按几何反算（世界层带着 transform，反算容易差一个 scale），
    // 直接按**需求号**在对应原型卡里找框 —— 锚点自带 data-br，这是最可靠的键。
    var nHi = 0;
    if(hlSel){
      [].slice.call(document.querySelectorAll(hlSel))
        .forEach(function(a){ a.classList.add('hi'); nHi++; });
    }

    // 视角：用框的世界坐标取包围盒
    var x0 = Math.min.apply(null, boxes.map(function(b){return b[0];}));
    var y0 = Math.min.apply(null, boxes.map(function(b){return b[1];}));
    var x1 = Math.max.apply(null, boxes.map(function(b){return b[0]+b[2];}));
    var y1 = Math.max.apply(null, boxes.map(function(b){return b[1]+b[3];}));
    var b = document.getElementById('board');
    var pad = 150;
    var k = Math.min((b.clientWidth - pad*2) / Math.max(1, x1-x0),
                     (b.clientHeight - pad*2) / Math.max(1, y1-y0));
    k = Math.max(0.35, Math.min(k, 1.6));
    if(window.__setView__){
      window.__setView__(k, b.clientWidth/2 - (x0+x1)/2*k,
                            b.clientHeight/2 - (y0+y1)/2*k);
    }
    // 高亮框必须能看见：没开锚点框就自动打开
    if(appearAnno && nHi && !document.body.classList.contains('anno')){
      document.body.classList.add('anno');
      var tb = document.getElementById('tAnno');
      if(tb) tb.classList.add('on');
    }
    return nHi;
  }

  function flyTo(card){
    var boxes = [];
    try { boxes = JSON.parse(card.dataset.boxes || '[]'); } catch(e){ boxes = []; }
    var br = card.dataset.cid;
    return flyToBoxes(boxes, '.an[data-br="' + br + '"]', true) > 0;
  }

  /* ---- ① 点卡片：展开 + 飞过去 ---- */
  cards.forEach(function(card){
    var head = card.querySelector('.ch');
    if(!head) return;
    head.addEventListener('click', function(){
      var opened = openCard(card);
      if(opened) flyTo(card);
    });
  });

  /* ---- 点画布上的落点框 → 侧栏定位到对应卡片 ---- */
  document.addEventListener('click', function(e){
    var an = e.target.closest ? e.target.closest('.an') : null;
    if(!an) return;
    var br = an.dataset.br;
    if(!br) return;
    var card = cards.filter(function(c){ return c.dataset.cid === br; })[0];
    if(!card) return;
    // 侧栏跟着滚（画布不回飞 —— 用户是「在画布上点了一下想读它」，
    // 这时候把画布再动一次会把人晃走）
    closeAll(card);
    setOpen(card, true);
    card.scrollIntoView({block:'center', behavior:'smooth'});
    cards.forEach(function(c){ c.classList.remove('hi'); });
    card.classList.add('hi');
    setTimeout(function(){ card.classList.remove('hi'); }, 2200);
  });

  /* ---- ③ 搜索 / 筛选 ---- */
  function applyFilter(){
    var q = (document.getElementById('sQ').value || '').trim().toLowerCase();
    var onBtn = document.querySelector('#sFEnd button.on');
    var end = onBtn ? onBtn.dataset.e : 'all';
    var shown = 0;
    pages.forEach(function(pg){
      // 端读 .pg 自己的 data-end —— .lane 是它的兄弟不是祖先，
      // 用 closest('.lane') 永远拿到 null（这个 bug 表现为「点后台一张都不剩」）
      var pgEnd = pg.dataset.end || 'all';
      var okE = (end === 'all') || (pgEnd === end);
      var vis = 0;
      [].slice.call(pg.querySelectorAll('.card')).forEach(function(c){
        var txt = (c.dataset.cid + ' ' + c.textContent).toLowerCase();
        var ok = okE && (!q || txt.indexOf(q) >= 0);
        c.classList.toggle('hide', !ok);
        if(ok) vis++;
      });
      pg.classList.toggle('hide', vis === 0);
      shown += vis;
    });
    // 端泳道标题只在「本端一张都没显示」时藏起来
    [].slice.call(document.querySelectorAll('.lane')).forEach(function(l){
      var e = l.dataset.end;
      var any = pages.some(function(p){
        return p.dataset.end === e && !p.classList.contains('hide');
      });
      l.classList.toggle('hide', !any);
    });
    var n = document.getElementById('sNShown');
    if(n) n.textContent = shown;
  }
  var qi = document.getElementById('sQ');
  if(qi) qi.addEventListener('input', applyFilter);
  var fe = document.getElementById('sFEnd');
  if(fe) fe.addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('button') : null;
    if(!b) return;
    [].slice.call(fe.querySelectorAll('button')).forEach(function(x){
      x.classList.toggle('on', x === b);
    });
    applyFilter();
  });

  var ea = document.getElementById('sExpandAll');
  if(ea) ea.addEventListener('click', function(){
    ACCORDION = false;
    cards.forEach(function(c){ if(!c.classList.contains('hide')) setOpen(c, true); });
  });
  var ca = document.getElementById('sCollapseAll');
  if(ca) ca.addEventListener('click', function(){
    ACCORDION = true;
    closeAll(null);
  });

  /* ---- HUD 开关 ---- */
  var tSide = document.getElementById('tSide');
  if(tSide) tSide.addEventListener('click', function(){
    document.body.classList.toggle('noside');
    tSide.textContent = document.body.classList.contains('noside') ? '展开侧栏' : '收起侧栏';
    window.dispatchEvent(new Event('resize'));
  });
  var tDim = document.getElementById('tDim');
  if(tDim) tDim.addEventListener('click', function(){
    document.body.classList.toggle('dim');
    tDim.classList.toggle('on');
  });
  var tAnno = document.getElementById('tAnno');
  if(tAnno) tAnno.addEventListener('click', function(){
    document.body.classList.toggle('anno');
    tAnno.classList.toggle('on');
  });

  /* ---- ④ 页面级元素总表 ----------------------------------------------
     这张表是**界面视角**：一个元素一行。两个动作：
       · 点归属需求号 → 同卡片一样，飞到那条需求的落点框
       · 点元素行     → 飞到该元素在原型上的位置（元素自己那一小块）
     总表在卡片流末尾，不参与手风琴；<details> 由浏览器自己管开合。 */
  var elTable = document.getElementById('elTable');
  if(elTable){
    elTable.addEventListener('click', function(e){
      var t = e.target;
      // ① 归属需求号
      var own = t.closest ? t.closest('.own[data-br]') : null;
      if(own){
        e.preventDefault(); e.stopPropagation();
        var br = own.dataset.br;
        var card = cards.filter(function(c){ return c.dataset.cid === br; })[0];
        var boxes = [];
        if(card){
          try { boxes = JSON.parse(card.dataset.boxes || '[]'); } catch(err){ boxes = []; }
        }
        flyToBoxes(boxes, '.an[data-br="' + br + '"]', true);
        if(card){
          // 侧栏里也带过去：这张元素属于哪条需求，人得能接着读它的卡片
          closeAll(card);
          setOpen(card, true);
          card.scrollIntoView({block:'center', behavior:'smooth'});
          card.classList.add('hi');
          setTimeout(function(){ card.classList.remove('hi'); }, 2200);
        }
        return;
      }
      // ② 元素行本身 → 飞到它在原型上的位置
      var row = t.closest ? t.closest('tr.elrow[data-box]') : null;
      if(row){
        var box = [];
        try { box = JSON.parse(row.dataset.box || '[]'); } catch(err){ box = []; }
        if(box.length){
          // 元素框很小（可能只有十几像素），放大到 1.6 倍才看得清；
          // 用 flyToBoxes 的通用取景会缩得太后，所以这里直接给固定倍率与站位。
          var b = document.getElementById('board');
          var k = Math.min(1.6, Math.max(0.9,
                 Math.min(b.clientWidth/ Math.max(1, box[2]) / 6,
                          b.clientHeight / Math.max(1, box[3]) / 6)));
          window.__setView__(k,
            b.clientWidth/2 - (box[0] + box[2]/2) * k,
            b.clientHeight/2 - (box[1] + box[3]/2) * k);
          // 给这一小块描个闪一下的框：直接复用锚点高亮的样式，
          // 用一个临时 .an 把目标位置圈出来（元素本身在原型图里没有独立 DOM）
          flashAt(box);
        }
      }
    });
  }

  // 在指定世界坐标处闪一个高亮框，告诉人「就是这里」
  var flashTmp = null;
  function flashAt(box){
    var w = document.getElementById('world');
    if(!w) return;
    if(flashTmp && flashTmp.parentNode) flashTmp.parentNode.removeChild(flashTmp);
    flashTmp = document.createElement('i');
    flashTmp.className = 'an flash-hi';
    flashTmp.style.cssText = 'left:' + box[0] + 'px;top:' + box[1] + 'px;width:'
      + box[2] + 'px;height:' + box[3] + 'px;display:block';
    w.appendChild(flashTmp);
    setTimeout(function(){
      if(flashTmp && flashTmp.parentNode) flashTmp.parentNode.removeChild(flashTmp);
      flashTmp = null;
    }, 2600);
  }

  /* ---- 给校验脚本 / 出图脚本用的观察口 ---- */
  window.__CARDVIEW__ = {
    cards: cards,
    accordion: function(){ return ACCORDION; },
    openCount: function(){
      return cards.filter(function(c){ return c.classList.contains('open'); }).length;
    },
    flyTo: flyTo,
    flyToBoxes: flyToBoxes,
    flashAt: flashAt,
    applyFilter: applyFilter,
    setAccordion: function(v){ ACCORDION = !!v; }
  };

  // 初始：打开第一张（否则侧栏是一堆标题，看不出卡片里有什么）
  if(cards.length) setOpen(cards[0], true);
})();
