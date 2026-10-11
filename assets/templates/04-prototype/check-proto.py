# -*- coding: utf-8 -*-
"""原型校验：渲染 + 坐标 + 锚点闭环 + 双视图。

四层，从下往上：

1. 产物一致性（不碰浏览器）
   截图文件真的存在、真的是指定尺寸；坐标清单里的每个锚点都登记在设计规范里。
   这一层能抓住「改了页面忘了重跑生成器」这类静默漂移。

2. 坐标有效性
   锚点尺寸不得为 0（尺寸为 0 的框画出来是一条线，标注阶段会以为是元素太窄）；
   锚点必须落在手机帧内（溢出的框意味着量错了参照物）。

3. 锚点闭环
   设计规范里的锚点，原型里埋了几个、还差几个。差的部分必须能指名道姓地列出来 ——
   只报「20/43」这种数字没法干活。

4. 真渲染 + 双视图
   用系统 Edge 无头打开画布，先清掉 <script> 源码再计数 ——
   JS 字符串里含 `.pc` `.shot` 这些选择器，不清会把计数算多（踩过一次）。
   然后验证业务视图真的把技术信息藏住了、技术视图真的放出来了。

用法：python check-proto.py
"""

import base64
import json
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CANVAS = os.path.join(HERE, 'prototype-canvas.html')
EMAP = os.path.join(HERE, 'element-map.json')
TOKENS = os.path.join(ROOT, '03-design', 'tokens.json')

EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if not os.path.exists(EDGE):
    EDGE = r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'

fails, warns = [], []


def png_size(path):
    """只读 IHDR 里的宽高，不装 Pillow。PNG 头固定：8 字节签名 + 4 长度 + 4 类型 + 宽高各 4。"""
    with open(path, 'rb') as f:
        b = f.read(33)
    if b[:8] != b'\x89PNG\r\n\x1a\n' or b[12:16] != b'IHDR':
        return None
    return struct.unpack('>II', b[16:24])


# ------------------------------------------------------------------ 1. 产物一致性
def check_artifacts(emap, tok):
    anchors = {}
    for p in tok['pages']:
        for a in p['anchors']:
            anchors[a['anchor']] = (p['id'], a['br'], a.get('extra', ''))

    for s in emap['screens']:
        png = os.path.join(HERE, s['shot'])
        if not os.path.exists(png):
            fails.append('截图缺失：%s' % s['shot'])
            continue
        got = png_size(png)
        want = (s['img']['wpx'], s['img']['hpx'])
        if got != want:
            fails.append('%s 截图尺寸不符：实际 %s，清单记 %s' % (s['vkey'], got, want))
        # 裁剪的正确性。出图时沿右下角截掉了窗口余量，所以：
        #   ① 图就是裁剪后的尺寸（清单不能记着裁剪前的旧值）
        #   ② 右侧切掉的宽度必须正好等于「窗口宽 − 视口宽」× 倍率
        #      —— 切多了会啃到内容，切少了会留下一圈舞台底色（就是用户报的那圈灰蓝框）
        #   ③ 裁完的图宽必须等于帧宽。这一条把「坐标基准」钉死了：
        #      rx/img.w 里的分母、锚点坐标的参照物、图上像素三者从此同源。
        crop = s.get('crop')
        if not crop:
            fails.append('%s 清单里没有 crop 字段 —— 旧清单，需重跑 build-proto.py' % s['vkey'])
        else:
            if (crop['wpx'], crop['hpx']) != want:
                fails.append('%s crop 记录 %s 与 img %s 不一致'
                             % (s['vkey'], (crop['wpx'], crop['hpx']), want))
            margin = crop['fromPx'][0] - crop['wpx']
            frame_w = s['viewport']['w']
            if abs(margin - (crop['fromPx'][0] - frame_w * s['dpr'])) > s['dpr'] + 1:
                fails.append('%s 右侧裁掉的 %dpx 与「窗口宽−视口宽」×%d 对不上'
                             % (s['vkey'], margin, s['dpr']))
            if abs(s['img']['w'] - s['frame']['w']) > 0.6:
                fails.append('%s 裁剪后图宽 %.1f 与帧宽 %.1f 不等 —— '
                             '锚点百分比的分母会整体偏移'
                             % (s['vkey'], s['img']['w'], s['frame']['w']))
            if abs(s['img']['h'] - (s['frame']['y'] + s['frame']['h'])) > 0.6:
                fails.append('%s 裁剪后图高 %.1f 与帧底 %.1f 不等'
                             % (s['vkey'], s['img']['h'], s['frame']['y'] + s['frame']['h']))
        if os.path.getsize(png) < 4096:
            fails.append('%s 截图过小（%d 字节），可能是空图'
                         % (s['shot'], os.path.getsize(png)))
        for a in s['anchors']:
            if not a['inSpec']:
                fails.append('%s 的锚点 %s 未登记在 03-design 的页面规格里'
                             % (s['id'], a['anchor']))
    return anchors


# ------------------------------------------------------------------ 2. 坐标有效性
def check_geometry(emap):
    n = 0
    for s in emap['screens']:
        fw, fh = s['frame']['w'], s['frame']['h']
        for a in s['anchors']:
            n += 1
            tag = '%s/%s %s' % (s['id'], s['vkey'], a['anchor'])
            if a['w'] <= 0 or a['h'] <= 0:
                fails.append('%s 尺寸为 0（%sx%s），标注画出来是一条线'
                             % (tag, a['w'], a['h']))
            if a['h'] < 12:
                warns.append('%s 高度仅 %spx，热区偏小' % (tag, a['h']))
            if a['rx'] < -0.5 or a['ry'] < -0.5:
                fails.append('%s 落在帧外（rx=%s ry=%s）' % (tag, a['rx'], a['ry']))
            if a['rx'] + a['w'] > fw + 0.5:
                fails.append('%s 右侧溢出帧：rx+w=%.1f > 帧宽 %s'
                             % (tag, a['rx'] + a['w'], fw))
            if a['ry'] + a['h'] > fh + 0.5:
                fails.append('%s 下方溢出帧：ry+h=%.1f > 帧高 %s'
                             % (tag, a['ry'] + a['h'], fh))
    return n


# ------------------------------------------------------------------ 3. 锚点闭环
def check_closure(emap, tok):
    placed = {}
    for s in emap['screens']:
        for a in s['anchors']:
            placed.setdefault(a['anchor'], []).append('%s/%s' % (s['id'], s['vkey']))

    app_design, admin_design = [], []
    for p in tok['pages']:
        for a in p['anchors']:
            (app_design if p['platform'] == 'app' else admin_design).append(a['anchor'])
    for tag, spec in (('小程序端', app_design), ('后台端', admin_design)):
        miss = [x for x in spec if x not in placed]
        if miss:
            fails.append('%s锚点未埋入：%s' % (tag, ', '.join(miss)))
    extra = [x for x in placed if x not in set(app_design) | set(admin_design)]
    if extra:
        fails.append('原型里埋了设计规范之外的锚点：%s' % ', '.join(sorted(extra)))
    return placed, app_design, admin_design


# ------------------------------------------------------------------ 4. 渲染 + 双视图
PROBE = """
<pre id="CHK" style="display:none">PENDING</pre>
<script>
(function(){
  var errs=[];
  window.onerror=function(m){errs.push(String(m))};
  var R={};
  try{
    /* 先清掉 <script> 源码：JS 字符串里含 .pc / .shot / data-j 这些选择器，
       不清就会把计数算多 —— 这是 03-design 那轮踩过的坑。 */
    [].slice.call(document.querySelectorAll('script')).forEach(function(s){s.textContent=''});
    var q=function(s){return document.querySelectorAll(s).length};
    R.page=q('.el.page'); R.todo=q('.el.todo'); R.doc=q('.el.doc');
    R.glab=q('.glab'); R.anno=q('.an'); R.tOnly=q('.t-only');
    R.imgs=q('img[src^="data:image/png"]');
    R.bodyClass=document.body.className;
    /* 构建期声明的「我打算画成什么样」。期望值从这儿取，不在校验脚本里写死 ——
       写死的话分组数一改（比如从 8 组变 9 组），校验要么误报、要么被顺手改成新数字，
       后者更糟：期望值跟着实现漂了，检查就只剩个仪式。 */
    R.manifest=(window.__CANVAS__&&window.__CANVAS__.manifest)||null;
    /* 白板的核心是「真的能缩放平移」，不是只有几个按钮长得像。所以：
       ① 世界层必须挂着 transform（fit 之后不该是 none）
       ② 点阵要跟着 scale 走，否则缩放时网格不动，穿帮
       ③ 点一下放大按钮，transform 必须真的变 —— 这条是判据，UI 存在不算证据 */
    var wd=document.getElementById('world'), dt=document.getElementById('dots');
    var t0=getComputedStyle(wd).transform;
    R.worldTransform=t0;
    R.dotSize=getComputedStyle(dt).backgroundSize;
    R.worldBox={w:wd.offsetWidth,h:wd.offsetHeight};
    R.elsPos=[].slice.call(document.querySelectorAll('.el')).filter(function(e){
      return e.style.left&&e.style.top}).length;
    document.getElementById('zIn').click();
    R.zoomWorks=(getComputedStyle(wd).transform!==t0);
    document.getElementById('zOut').click();
    /* 滚轮缩放与拖拽平移要**真的派事件**去测，而不是看有没有绑定 handler ——
       handler 绑上了但计算写错，页面照样"看起来有缩放"，只是鼠标没反应。

       而且光看「transform 变了」还不够：平移把 dx 写成 -dx 也会变，缩放写成
       Math.exp(+deltaY) 也会变 —— 变的方向错了，肉眼在真机上要滚好几下才发现。
       所以这里把 matrix 拆出来，**比对位移量**（鼠标走 69/43，世界层就该走 69/43）
       与**缩放方向**（deltaY 为负 = 向上滚 = 放大，scale 必须变大）。 */
    var mat=function(){
      var m=getComputedStyle(wd).transform.match(/matrix\\(([^)]+)\\)/);
      if(!m) return null;
      var v=m[1].split(',').map(function(x){return parseFloat(x)});
      return {s:v[0], x:v[4], y:v[5]};
    };
    var m1=mat();
    board.dispatchEvent(new WheelEvent('wheel',{clientX:420,clientY:320,deltaY:-240,
      bubbles:true,cancelable:true}));
    var m2=mat();
    R.wheelZoom=!!(m1&&m2&&m2.s>m1.s+1e-6);
    R.wheelScale=[m1?m1.s:null, m2?m2.s:null];
    var m3=mat();
    board.dispatchEvent(new MouseEvent('mousedown',{clientX:520,clientY:420,button:0,bubbles:true}));
    window.dispatchEvent(new MouseEvent('mousemove',{clientX:589,clientY:463,bubbles:true}));
    window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
    var m4=mat();
    R.dragPan=!!(m3&&m4&&Math.abs((m4.x-m3.x)-69)<0.6&&Math.abs((m4.y-m3.y)-43)<0.6);
    R.dragDelta=[m3?Math.round((m4.x-m3.x)*10)/10:null,
                 m3?Math.round((m4.y-m3.y)*10)/10:null];
    fit(56);
    /* 清晰度预算：放大到上限时，源图仍必须**够像素**。
       这条是「放大后糊」的根因判据，而不是「有没有缩放按钮」那种表面检查。
       判据本身很简单：卡片把图显示成 clientWidth 宽，放到 z 倍、屏幕 dpr 倍之后
       设备上要占 clientWidth*z*dpr 个像素；源图只有 naturalWidth 个。要求
       naturalWidth >= clientWidth*z*dpr（留 1px 取整余量）。
       同时校验两件事：
         ① maxZ() 的上限本身没有超过预算（即上限是算出来的，不是拍脑袋的常数）
         ② 一路放大到底之后，实际达到的 vs 仍然满足预算
       如果哪天有人把 will-change 加回世界层、或者把上限改回写死的 3.2，
       第①条不一定报，但**清晰度**会掉 —— 那个只能靠 _verify_sharp.py 的图像指标守。 */
    var firstImg=document.querySelector('.el-img img');
    var dprZ=Math.max(1,window.devicePixelRatio||1);
    R.sharpDpr=dprZ;
    R.sharpNatural=firstImg?firstImg.naturalWidth:0;
    R.sharpClient=firstImg?firstImg.clientWidth:0;
    R.sharpBudget=(R.sharpClient&&R.sharpNatural)
      ? R.sharpNatural/(R.sharpClient*dprZ) : 0;
    for(var i=0;i<80;i++) zoomBy(1.25);          // 一路顶到上限
    R.sharpMaxZ=vs;
    R.sharpAtMaxOk=!!(R.sharpNatural&&R.sharpClient
      && R.sharpClient*vs*dprZ<=R.sharpNatural+1);
    R.sharpCapHonest=!!(R.sharpBudget&&vs<=R.sharpBudget+0.01);
    fit(56);
    /* 图真的解码了吗 —— naturalWidth 为 0 说明 base64 坏了或路径不对。
       这个和技术视图无关，但下面「锚点框是否溢出」必须先让框显示出来才能量，
       所以两项都挪到切完视图之后再算。display:none 的元素 rect 全是 0，
       在业务视图下量会把每个框都算成溢出 —— 假报警，上一版就栽在这儿。 */
    R.imgBroken=[].slice.call(document.querySelectorAll('img')).filter(function(i){
      return !i.naturalWidth}).length;
    /* 「点开看细节」是白板除缩放之外的第二条主线，而它靠拖拽结束时那个 4px 阈值 ——
       最容易写成「按一下就开」或「怎么点都不开」。所以真的派 mousedown/mouseup 走一遍：
       位移 0 应当开灯箱，且灯箱里要真的有图、有需求清单。

       ⚠️ 必须在量双视图**之前**打开。灯箱侧栏是页面上唯一会渲染技术信息的地方
       （路径行 / 锚点清单 / 页面文件），不开灯箱就没有样本可量 —— 而画布上的 .an
       锚点框虽然也带 .t-only，却另有 .an{display:none} 管着，拿它们量会得到
       「业务视图零泄露」的假绿灯，哪怕 body.biz .t-only 这条规则根本不存在。 */
    var pgEl=document.querySelector('.el.page[data-id="PG-A4"]');
    R.lbOpen=false; R.lbImgs=0; R.lbAnno=0;
    if(pgEl){
      pgEl.dispatchEvent(new MouseEvent('mousedown',{clientX:10,clientY:10,button:0,bubbles:true}));
      window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));
      var lbe=document.getElementById('lb');
      R.lbOpen=!!lbe&&getComputedStyle(lbe).display!=='none'&&!lbe.classList.contains('hide');
      R.lbImgs=document.querySelectorAll('#lb img').length;
      R.lbAnno=document.querySelectorAll('#lb .br-it').length;
    }
    /* 双视图。样本只取**非锚点框**的 .t-only —— 理由同上看。 */
    var tAll=[].slice.call(document.querySelectorAll('.t-only'));
    R.tOnly=tAll.length;
    R.tOnlyAn=tAll.filter(function(e){return e.classList.contains('an')}).length;
    /* 锚点框分两处：画布上的缩略图里一套，灯箱主图上又画了一套（放大看细节时框更准）。
       合在一起报数字会跟「画布锚点框 53」对不上，看着像漏算了 5 个 —— 拆开报。 */
    R.anWorld=document.querySelectorAll('#world .an').length;
    R.anLb=document.querySelectorAll('#lb .an').length;
    var probe=tAll.filter(function(e){return !e.classList.contains('an')});
    R.tOnlyOther=probe.length;
    R.bizHidden=probe.filter(function(e){
      return getComputedStyle(e).display==='none'}).length;
    R.bizProbed=probe.length;
    /* 切技术视图。注意顺序：锚点框是技术视图下的一个可选开关，
       要先把 anno 打开再统计，否则 30 个 .an 全是 display:none，
       会误报成「技术视图有信息没放出来」。 */
    document.body.classList.remove('biz'); document.body.classList.add('tech');
    document.body.classList.add('anno');
    R.techShown=probe.filter(function(e){
      return getComputedStyle(e).display!=='none'}).length;
    R.annoOn=[].slice.call(document.querySelectorAll('.an')).filter(function(a){
      return getComputedStyle(a).display!=='none'}).length;
    R.techAn=document.querySelector('.an')?getComputedStyle(document.querySelector('.an')).display:'';
    R.anOut=[].slice.call(document.querySelectorAll('.an')).filter(function(a){
      var p=a.parentElement.getBoundingClientRect(), r=a.getBoundingClientRect();
      return r.left<p.left-0.6||r.top<p.top-0.6||r.right>p.right+0.6||r.bottom>p.bottom+0.6;
    }).length;
    R.errs=errs;
  }catch(x){ R.fatal=String(x&&x.message||x); }
  R.done=1;
  document.getElementById('CHK').textContent=
    btoa(unescape(encodeURIComponent(JSON.stringify(R))));
})();
</script>
"""


def render_check():
    with open(CANVAS, encoding='utf-8') as f:
        html = f.read()
    tmp = os.path.join(HERE, '_check-canvas.html')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(html.replace('</body>', PROBE + '</body>'))
    url = 'file:///' + tmp.replace('\\', '/').replace(' ', '%20')
    r = subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--no-sandbox',
                        '--window-size=1600,1000', '--virtual-time-budget=8000',
                        '--dump-dom', url], capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    os.remove(tmp)
    m = re.search(r'id="CHK"[^>]*>([A-Za-z0-9+/=]*)<', r.stdout or '')
    if not m or not m.group(1):
        return None
    try:
        return json.loads(base64.b64decode(m.group(1)).decode('utf-8'))
    except Exception:
        return None


def check_render(emap, tok):
    R = render_check()
    if not R:
        fails.append('画布渲染失败：探针无输出（页面可能没打开或脚本报错）')
        return
    if R.get('fatal'):
        fails.append('画布脚本抛异常：%s' % R['fatal'])
    if R.get('errs'):
        fails.append('画布运行时报错：%s' % '; '.join(R['errs'][:3]))

    shot_pages = len({s['id'] for s in emap['screens']})
    total_pages = len(tok['pages'])
    n_shots = len(emap['screens'])
    mf = R.get('manifest')
    if not mf:
        fails.append('画布没有携带构建期 manifest —— 期望值无从对起，需重跑 build-canvas.py')
        return
    want = {
        'page': (R['page'], mf['pages'], '页面元素（含补态）'),
        'todo': (R['todo'], mf['todos'], '待生成占位元素'),
        'doc': (R['doc'], mf['docs'], '文档卡'),
        'glab': (R['glab'], mf['groups'], '业务分组标签'),
        'anno': (R['anno'], mf['anchorBoxes'], '锚点框'),
        'imgs': (R['imgs'], mf['imgs'], '内联图片'),
    }
    # 构建期声明与实际数据源也要对得上，否则「渲染 == 声明」可能是一起错了
    if mf['pages'] != n_shots:
        fails.append('manifest 声明 %d 个页面元素，但 element-map 有 %d 张画面'
                     % (mf['pages'], n_shots))
    if mf['imgs'] != n_shots:
        fails.append('manifest 声明 %d 张图，清单有 %d 张画面' % (mf['imgs'], n_shots))
    if mf['todos'] != total_pages - shot_pages:
        fails.append('manifest 声明 %d 个待生成，按数据源应为 %d'
                     % (mf['todos'], total_pages - shot_pages))
    if mf['anchorBoxes'] != sum(len(s['anchors']) for s in emap['screens']):
        fails.append('manifest 声明的锚点框数与清单不符')
    print()
    for k, (got, want_v, label) in want.items():
        flag = 'OK ' if got == want_v else '!! '
        print('    %s%s：渲染 %d，期望 %d' % (flag, label, got, want_v))
        if got != want_v:
            fails.append('画布 %s 渲染数不符：%d ≠ %d' % (label, got, want_v))

    if R['imgBroken']:
        fails.append('有 %d 张缩略图未解码成功（base64 损坏）' % R['imgBroken'])
    if R['anOut']:
        fails.append('有 %d 个锚点框溢出了图片容器' % R['anOut'])

    print()
    print('  白板：世界 %d×%d px ｜ 元素绝对定位 %d/%d 个'
          % (R['worldBox']['w'], R['worldBox']['h'], R['elsPos'], R['page'] + R['todo'] + R['doc']))
    if R['worldTransform'] == 'none':
        fails.append('世界层没有 transform —— 白板的缩放平移都没生效')
    else:
        print('    OK 世界层 transform 已应用')
    if not R['dotSize'] or R['dotSize'] == 'auto':
        fails.append('点阵没有跟随缩放（background-size = %s）' % R['dotSize'])
    else:
        print('    OK 点阵跟随缩放（background-size %s）' % R['dotSize'])
    if not R['zoomWorks']:
        fails.append('点了放大按钮但世界层 transform 没变 —— 缩放是假的')
    else:
        print('    OK 缩放按钮真的改变了世界层 transform')
    ws = R.get('wheelScale') or [None, None]
    if not R.get('wheelZoom'):
        fails.append('滚轮向上滚没有放大（scale %s → %s）—— 派了 wheel 事件但缩放方向或计算不对'
                     % (ws[0], ws[1]))
    else:
        print('    OK 滚轮缩放生效且方向正确（scale %.4f → %.4f）' % (ws[0], ws[1]))
    dd = R.get('dragDelta') or [None, None]
    if not R.get('dragPan'):
        fails.append('拖拽平移量与鼠标位移不符（鼠标走 69/43，世界层走 %s/%s）—— '
                     'handler 在但计算写错了' % (dd[0], dd[1]))
    else:
        print('    OK 拖拽平移量精确匹配鼠标位移（%s / %s px）' % (dd[0], dd[1]))
    print('  清晰度预算：源图 %d px ｜ 卡片显示 %d CSS px ｜ dpr %s ｜ 撑到 %.2fx 才到 1:1'
          % (R.get('sharpNatural', 0), R.get('sharpClient', 0),
             R.get('sharpDpr'), R.get('sharpBudget', 0)))
    if not R.get('sharpAtMaxOk'):
        need = R.get('sharpClient', 0) * R.get('sharpMaxZ', 0) * R.get('sharpDpr', 1)
        fails.append('放大到上限 %.2fx 时源图像素不够（需要 %.0f px，只有 %d px）'
                     '—— 这就是「放大后糊」的根因'
                     % (R.get('sharpMaxZ', 0), need, R.get('sharpNatural', 0)))
    else:
        print('    OK 顶到上限 %.2fx 仍在源图分辨力之内（需 %.0f ≤ 有 %d px）'
              % (R.get('sharpMaxZ', 0),
                 R.get('sharpClient', 0) * R.get('sharpMaxZ', 0) * R.get('sharpDpr', 1),
                 R.get('sharpNatural', 0)))
    if not R.get('sharpCapHonest'):
        fails.append('缩放上限 %.2fx 超过了源图预算 %.2fx —— 上限不是算出来的，会糊'
                     % (R.get('sharpMaxZ', 0), R.get('sharpBudget', 0)))
    if R['elsPos'] != R['page'] + R['todo'] + R['doc']:
        fails.append('有元素没有写绝对坐标（%d/%d）'
                     % (R['elsPos'], R['page'] + R['todo'] + R['doc']))

    print()
    print('  点开看细节：灯箱 图 %d 张 · 覆盖需求 %d 条'
          % (R.get('lbImgs', 0), R.get('lbAnno', 0)))
    if not R.get('lbOpen'):
        fails.append('点了页面元素但灯箱没开 —— 「查看细节」这条路径走不通')
    elif not R.get('lbImgs'):
        fails.append('灯箱开了但里面没有图')
    else:
        print('    OK 点击页面元素能打开灯箱，且灯箱内有图')
    if R.get('lbOpen') and not R.get('lbAnno'):
        fails.append('灯箱开了但需求清单是空的')
    elif R.get('lbOpen'):
        print('    OK 灯箱内覆盖需求清单已渲染')

    print()
    print('  双视图：默认 body="%s"，.t-only 共 %d 处（画布锚点框 %d · 灯箱锚点框 %d · 其它 %d）'
          % (R['bodyClass'], R['tOnly'], R.get('anWorld', 0), R.get('anLb', 0),
             R.get('tOnlyOther', 0)))
    if R.get('anWorld', 0) + R.get('anLb', 0) != R.get('tOnlyAn', 0):
        fails.append('锚点框计数对不上：画布 %d + 灯箱 %d ≠ 合计 %d'
                     % (R.get('anWorld', 0), R.get('anLb', 0), R.get('tOnlyAn', 0)))
    if R.get('anWorld', 0) != mf['anchorBoxes']:
        fails.append('画布上的锚点框 %d 个，构建期声明 %d 个'
                     % (R.get('anWorld', 0), mf['anchorBoxes']))
    if 'biz' not in R['bodyClass']:
        fails.append('画布默认不是业务视图（body="%s"）' % R['bodyClass'])
    # 样本有效性 —— 这一条是防「假绿灯」的。画布上的锚点框也带 .t-only，
    # 但它们由 .an{display:none} 管着：把它俩混在一起量，就算 body.biz .t-only
    # 这条规则整条删掉，结果照样全绿。所以只认非锚点框的样本，
    # 样本为 0 时直接判失败，而不是「无事通过」。
    if not R.get('tOnlyOther'):
        fails.append('业务视图检查没有有效样本 —— 非锚点框的 .t-only 为 0 处，'
                     '这条检查证明不了任何事（锚点框另有 .an{display:none} 管着，'
                     '拿它当样本是自证循环）')
    elif R['bizProbed'] and R['bizHidden'] != R['bizProbed']:
        fails.append('业务视图下仍有 %d 处技术信息可见'
                     % (R['bizProbed'] - R['bizHidden']))
    if R['bizProbed'] and R['techShown'] != R['bizProbed']:
        fails.append('技术视图下仍有 %d 处技术信息没放出来'
                     % (R['bizProbed'] - R['techShown']))
    if R['bizProbed']:
        print('    OK 业务视图隐藏 %d/%d 处技术信息（样本为非锚点框的非技术信息）'
              % (R['bizHidden'], R['bizProbed']))
        print('    OK 技术视图放出 %d/%d 处技术信息'
              % (R['techShown'], R['bizProbed']))
    if R['techAn'] != 'block':
        fails.append('技术视图打开了锚点框，但 .an 的 display 是 %s' % R['techAn'])
    else:
        print('    OK 锚点框可显示（%d 个可见）' % R['annoOn'])


# ------------------------------------------------------------------ 主流程
def main():
    with open(EMAP, encoding='utf-8') as f:
        emap = json.load(f)
    with open(TOKENS, encoding='utf-8') as f:
        tok = json.load(f)

    print('[原型校验]')
    print()
    print('[1] 产物一致性（截图尺寸 · 锚点登记）')
    anchors = check_artifacts(emap, tok)
    print('    OK 截图 %d 张尺寸与清单一致' % len(emap['screens']))

    print()
    print('[2] 坐标有效性')
    n = check_geometry(emap)
    print('    OK 锚点记录 %d 条，无零尺寸、无溢出帧' % n)

    print()
    print('[3] 锚点闭环')
    placed, app_design, admin_design = check_closure(emap, tok)
    for tag, spec in (('小程序端', app_design), ('后台端  ', admin_design)):
        hit = len([x for x in spec if x in placed])
        print('    %s %d/%d 已埋入' % (tag, hit, len(spec)))
    print('    设计锚点合计 %d 处 ｜ 去重落位 %d 处 ｜ 各画面累计落位 %d 次'
          % (len(app_design) + len(admin_design), len(placed),
             sum(len(s['anchors']) for s in emap['screens'])))

    print()
    print('[4] 画布渲染与双视图')
    check_render(emap, tok)

    print()
    if warns:
        print('[提示]')
        for w in warns:
            print('    - ' + w)
    if fails:
        print('[校验失败]')
        for x in fails:
            print('    - ' + x)
        sys.exit(1)
    print('=' * 72)
    print('[校验通过] 截图与清单同源、坐标无零尺寸无溢出、锚点闭环无遗漏、'
          '业务视图技术信息清零、技术视图信息完整')


if __name__ == '__main__':
    main()
