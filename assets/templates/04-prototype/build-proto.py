# -*- coding: utf-8 -*-
"""原型生成器：一份页面定义 → 页面 HTML + PNG 视觉稿 + 元素坐标清单。

为什么坐标和截图要同一次渲染拿：
    标注阶段是「在图上画框」。如果坐标来自一次渲染、图来自另一次，两次布局稍有差异
    就会错位，而且错位是静默的 —— 图上看着对不上却没人知道是数据错了还是画错了。
    所以这里一次调用同时给 `--screenshot` 与 `--dump-dom`，坐标从**出图的那一次**读。

本机 Edge 无头的三个硬约束（实测标定，不是猜的）：
    · 视口宽 = 窗口宽 − 24，且最小 492（Windows 对窗口宽度有下限钳制）
    · 视口高 = 窗口高 − 92
    · --force-device-scale-factor 只放大像素，不改变 CSS 布局 → 坐标仍是 CSS px
所以：要 375 宽的手机帧，用 492 视口 + 帧居中；坐标一律记 CSS px，图上像素 = 坐标 × dpr。
"""

import base64
import json
import os
import re
import struct
import subprocess
import sys

import _png
import _proto_theme as TH
import _proto_ui as UI
import _proto_app as APP
import _proto_admin as ADM

HERE = os.path.dirname(os.path.abspath(__file__))
PAGES_DIR = os.path.join(HERE, 'pages')
SHOTS_DIR = os.path.join(HERE, 'shots')
MAP_OUT = os.path.join(HERE, 'element-map.json')
TOKENS = os.path.join(HERE, '..', '03-design', 'tokens.json')

EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if not os.path.exists(EDGE):
    EDGE = r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'

CHROME_W, CHROME_H = 24, 92          # 窗口 → 视口的损耗（实测）
MIN_VIEW_W = 492                     # 视口宽下限（Windows 对窗口宽度有下限钳制）
FRAME_W = 375                        # 小程序设计宽
ADMIN_W = 1440                       # 后台设计基准宽
ADMIN_H = 900                        # 后台出图视口高（按笔记本内容区高）

# ------------------------------------------------------------------ 锚点 → 需求号
with open(TOKENS, encoding='utf-8') as f:
    _TOK = json.load(f)
ANCHOR_BR = {}
ANCHOR_PAGE = {}
for _p in _TOK['pages']:
    for _a in _p['anchors']:
        ANCHOR_BR[_a['anchor']] = _a['br']
        ANCHOR_PAGE[_a['anchor']] = _p['id']

# ------------------------------------------------------------------ 探针
# 探针与「出图样式」都注入到文件末尾，且**样式必须在探针之前** ——
# 探针读的是缩放后的几何，顺序反了就会把未缩放的坐标写进坐标清单，
# 而且错得很隐蔽（数字看着都正常，只是比例不对）。
PROBE = """
<pre id="GEO" style="display:none">PENDING</pre>
<script>
(function(){
  function r(e){var b=e.getBoundingClientRect();
    return {x:Math.round(b.left*100)/100,y:Math.round(b.top*100)/100,
            w:Math.round(b.width*100)/100,h:Math.round(b.height*100)/100};}
  var sel=document.body.getAttribute('data-frame')||'.phone';
  var fr=document.querySelector(sel)||document.body;
  var f=r(fr), o=[], eo=[];
  function rel(a){return {rx:Math.round((a.x-f.x)*100)/100,
                          ry:Math.round((a.y-f.y)*100)/100};}
  // 需求落点：一条需求对一块区域
  document.querySelectorAll('[data-anchor]').forEach(function(e){
    var a=r(e), q=rel(a);
    o.push({anchor:e.getAttribute('data-anchor'),x:a.x,y:a.y,w:a.w,h:a.h,
            rx:q.rx,ry:q.ry});
  });
  // 交互点：一个具体元素（按钮 / 跳转入口 / tab / 开关 …）。05-annotation 的连线从这些出发。
  document.querySelectorAll('[data-el]').forEach(function(e){
    var a=r(e), q=rel(a);
    eo.push({el:e.getAttribute('data-el'),kind:e.getAttribute('data-kind')||'',
             label:e.getAttribute('data-label')||'',note:e.getAttribute('data-note')||'',
             x:a.x,y:a.y,w:a.w,h:a.h,rx:q.rx,ry:q.ry});
  });
  var out={viewport:{w:window.innerWidth,h:window.innerHeight},
           dpr:window.devicePixelRatio,frame:f,frameSel:sel,
           doc:{w:document.documentElement.scrollWidth,
                h:document.documentElement.scrollHeight},
           anchors:o,elements:eo};
  document.getElementById('GEO').textContent=
    btoa(unescape(encodeURIComponent(JSON.stringify(out))));
})();
</script>
"""

# 出图专用样式：把设备框放大到正好填满视口宽度。
#
# 为什么这么做（而不是截完再裁左右）：
#   设计稿 375 宽、视口 492 宽，居中放会左右各留 58.5px 的舞台底色 ——
#   而 Windows 对窗口宽度有下限钳制（516），视口压不到 375，所以没法靠调窗口消掉。
#   改成把设备框 scale 到视口宽：左右一点不浪费，像素全用在内容上，
#   最终显示效果与「裁掉左右」完全一致，但源图分辨率高出 31%
#   （492×DSF 而不是 375×DSF）。
# 顺带把 body 底色去掉、阴影去掉：
#   截图会带 alpha（--default-background-color=00000000），设备框圆角外的像素透明，
#   放到白板的深色卡片上就是干净的圆角，不会出现一圈舞台底色的方框。
#   （用户 2026-10-07 反馈「每个页面后面那个灰蓝色卡片框看起来不舒服」就是这个底色。）
SHOT_CLIP = """
<script>
(function(){
  var d=document.body.getAttribute('data-frame')||'.phone';
  var css='';
  if(d==='.phone'){
    var s=window.innerWidth/%(frame_w)d;
    css+='body{background:transparent!important}'
        +'.stage{padding:0!important;justify-content:flex-start!important}'
        +'.phone{transform:scale('+s+');transform-origin:0 0;'
        +'box-shadow:none!important;margin:0!important}';
  }
  if(d==='.adm'){
    /* 后台没有设备框，页面本身就是视口，所以不需要缩放。
       但要把 min-height:100vh 收掉 —— 留着的话帧高会被撑到整个视口高，
       出图就变成「一大片空白 + 内容挤在上面」，页与页之间的高度差也被抹平了。
       收掉之后帧正好贴合内容，每页的 PNG 高多少就是内容高多少。 */
    css+='.adm{min-height:0!important}';
  }
  if(css){
    var st=document.createElement('style');
    st.textContent=css;
    document.head.appendChild(st);
  }
})();
</script>
"""

HTML_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>%(title)s · %(subtitle)s</title>
<style>
%(css)s
</style>
</head>
<body class="%(bodycls)s" data-frame="%(framesel)s">
<div class="stage">
<div class="phone" data-theme="%(theme)s" data-page="%(pid)s" data-variant="%(vkey)s">
%(statusbar)s
%(navbar)s
<div class="pagebody">
%(body)s
</div>
%(bottom)s
%(overlay)s
</div>
</div>
<div class="probe-meta" style="display:none">%(meta)s</div>
%(clip)s
%(probe)s
</body>
</html>
"""

# 后台端没有设备框 —— 页面本身就是视口，所以 `data-frame` 指到后台根节点，
# 探针量出来的「帧」就是整块内容区，坐标直接可在图上用。
ADMIN_TPL = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>%(title)s · %(subtitle)s</title>
<style>
%(css)s
</style>
</head>
<body class="proto-admin" data-frame=".adm">
<div class="adm">
%(nav)s
<div class="adm-main">
%(crumb)s
<div class="adm-body">
%(body)s
</div>
</div>
%(overlay)s
</div>
<div class="probe-meta" style="display:none">%(meta)s</div>
%(clip)s
%(probe)s
</body>
</html>
"""


def statusbar():
    return ('<div class="statusbar"><span>9:41</span>'
            '<span class="sig">▮▮▮ 5G ▰</span></div>')


def navbar(title, right='', back=True, pid=''):
    """返回键是**每一页都有**的交互点，所以锚点 id 由页面 id 派生（PG-A9 → a9-back）。

    放在这里由生成器统一产出，而不是每页手写：漏写一页就少一条「返回去哪」的连线，
    而画面上完全看不出来 —— 这种漏最好在结构上消灭掉，而不是靠记性。
    """
    b = ('<span class="back" data-el="%s-back" data-kind="icon" data-label="返回"'
         ' data-note="返回上一页。返回时保留上一页的滚动位置与已填内容，不重置表单">‹</span>'
         % pid.lower().replace('pg-', '')) if back else ''
    r = '<span class="caps">%s</span>' % UI.esc(right) if right else ''
    return '<div class="navbar">%s<span>%s</span>%s</div>' % (b, UI.esc(title), r)


def css_all(admin=False):
    if admin:
        return TH.css() + '\n' + ADM.ADMIN_CSS
    return TH.css() + '\n' + UI.CSS + '\n' + APP.APP_CSS


def html_for(p, body, overlay='', vkey='main', subtitle=None, clip=''):
    """clip 是「出图专用样式」，只注入到截图用的那份 HTML。
    pages/ 里留的是没有 clip 的版本 —— 那份是给人看的，带舞台底色更好看。"""
    if p.get('platform') == 'admin':
        # crumb 的签名是 crumb(name, *parents, right='')，而页面定义里 crumb 是
        # (页面名, 父级…) 的元组 —— 不能把整个元组当成 name 传进去。
        cn = p['crumb'][0]
        ps = p['crumb'][1:]
        return ADMIN_TPL % {
            'title': p['title'], 'subtitle': subtitle or p['name'],
            'css': css_all(admin=True), 'pid': p['id'], 'vkey': vkey,
            'nav': ADM.nav(p['nav']),
            'crumb': ADM.crumb(cn, *ps, right=p.get('crumb_right', '')),
            'body': body, 'overlay': overlay,
            'meta': '%s · %s · %s' % (p['path'], p['change'], p['name']),
            'probe': PROBE, 'clip': clip,
        }
    return HTML_TPL % {
        'title': p['title'], 'subtitle': subtitle or p['name'],
        'css': css_all(), 'theme': p['theme'], 'pid': p['id'], 'vkey': vkey,
        'bodycls': 'proto-app', 'framesel': '.phone',
        'statusbar': statusbar(),
        'navbar': navbar(p['title'], p['navbar_right'], pid=p['id']),
        'body': body, 'bottom': p['bottom'], 'overlay': overlay,
        'meta': '%s · %s · %s' % (p['path'], p['change'], p['name']),
        'probe': PROBE, 'clip': clip,
    }


# ------------------------------------------------------------------ Edge 调用
def run_edge(html_path, png_path, win_w, win_h, dsf=1, screenshot=True, alpha=False):
    url = 'file:///' + html_path.replace('\\', '/').replace(' ', '%20')
    cmd = [EDGE, '--headless=new', '--disable-gpu', '--no-sandbox', '--hide-scrollbars',
           '--window-size=%d,%d' % (win_w, win_h),
           '--virtual-time-budget=5000']
    if dsf and dsf != 1:
        cmd.append('--force-device-scale-factor=%d' % dsf)
    if alpha:
        # 让页面底色透明 → 截图带 alpha → 设备框圆角外是透明像素，不是舞台底色
        cmd.append('--default-background-color=00000000')
    if screenshot:
        cmd.append('--screenshot=' + png_path.replace('\\', '/'))
    cmd += ['--dump-dom', url]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8',
                       errors='replace')
    return r.stdout or ''


def geo_of(dom):
    m = re.search(r'id="GEO"[^>]*>([A-Za-z0-9+/=]*)<', dom)
    if not m or not m.group(1):
        return None
    try:
        return json.loads(base64.b64decode(m.group(1)).decode('utf-8'))
    except Exception:
        return None


def png_size(path):
    """读 PNG 的 IHDR 拿真实像素尺寸（不装 Pillow）。"""
    with open(path, 'rb') as f:
        b = f.read(33)
    if b[:8] != b'\x89PNG\r\n\x1a\n' or b[12:16] != b'IHDR':
        return None
    return struct.unpack('>II', b[16:24])


# ------------------------------------------------------------------ 出图规格
# 两端各出一套。差异只在这几点：视口宽、截图倍率、帧选择器、窗口高度是否自适应。
SPECS = {
    'app': dict(
        frame_sel='.phone', win_w=MIN_VIEW_W + CHROME_W, dsf=3, auto_h=True, min_h=400,
        win_h=1400,
        note='设计宽 375，出图时缩放填满视口；窗口高按内容自适应'),
    'admin': dict(
        frame_sel='.adm', win_w=ADMIN_W + CHROME_W, dsf=2, auto_h=True, min_h=720,
        win_h=1400,
        note='后台无设备框，页面即视口；设计基准宽 1440，高按内容自适应'),
}


def build(jobs=None, platforms=('app', 'admin')):
    os.makedirs(PAGES_DIR, exist_ok=True)
    os.makedirs(SHOTS_DIR, exist_ok=True)

    screens = []
    if 'app' in platforms:
        for p in APP.PAGES:
            screens.append(dict(pid=p['id'], name=p['name'], path=p['path'],
                                change=p['change'], platform='app', vkey='main',
                                vname='主态', body=p['body'], overlay='', pdef=p))
            for v in p['variants']:
                screens.append(dict(pid=p['id'], name=p['name'], path=p['path'],
                                    change=p['change'], platform='app', vkey=v['key'],
                                    vname=v['name'], body=v.get('body') or p['body'],
                                    overlay=v.get('overlay', ''), pdef=p))
    if 'admin' in platforms:
        for p in ADM.PAGES:
            screens.append(dict(pid=p['id'], name=p['name'], path=p['path'],
                                change=p['change'], platform='admin', vkey='main',
                                vname='主态', body=p['body'], overlay='', pdef=p))

    if jobs:
        screens = [s for s in screens if s['vkey'] in jobs or s['vkey'] == 'main']

    records, fails = [], []
    for s in screens:
        spec = SPECS[s['platform']]
        slug = '%s-%s' % (s['pid'].lower(), s['vkey'] if s['vkey'] != 'main' else 'main')
        hp = os.path.join(PAGES_DIR, slug + '.html')
        sh = os.path.join(HERE, '_shot.html')
        pp = os.path.join(SHOTS_DIR, slug + '.png')
        sub = None if s['vkey'] == 'main' else s['vname']

        # ① 给人看的版本：不带出图样式（保留舞台底色，单开好看）
        with open(hp, 'w', encoding='utf-8') as f:
            f.write(html_for(s['pdef'], s['body'], s['overlay'], s['vkey'], sub))
        # ② 出图版本：注入出图样式 + 探针，坐标与图都从这一份来
        clip = SHOT_CLIP % dict(frame_w=FRAME_W)
        with open(sh, 'w', encoding='utf-8') as f:
            f.write(html_for(s['pdef'], s['body'], s['overlay'], s['vkey'], sub, clip))

        # 量一次几何，确定窗口高度（两端都自适应；固定视口那端留作后备）
        dom1 = run_edge(sh, pp, spec['win_w'], spec['win_h'],
                        dsf=spec['dsf'], screenshot=False)
        g1 = geo_of(dom1)
        if not g1:
            fails.append('%s 探针无输出（页面未渲染成功）' % slug)
            continue
        if spec['auto_h']:
            need_h = int(g1['frame']['h'] + g1['frame']['y'] + 24 + 2) + CHROME_H
            need_h = max(need_h, spec['min_h'] + CHROME_H)
        else:
            need_h = spec['win_h']

        # 同一次渲染出图 + 出坐标（窗口尺寸与上一次只差高度，宽度布局完全一致）
        dom2 = run_edge(sh, pp, spec['win_w'], need_h, dsf=spec['dsf'], alpha=True)
        g2 = geo_of(dom2)
        if not g2:
            fails.append('%s 第二次探针无输出' % slug)
            continue
        os.remove(sh)

        px = png_size(pp)
        if not px:
            fails.append('%s 截图不是有效 PNG' % slug)
            continue

        # ③ 沿右下角截断：去掉右侧「窗口宽−视口宽」和底部窗口余量。
        #    这一步同时把舞台底色/右侧空白一起切掉 —— 就是用户看到的那圈灰蓝框。
        #    裁多少完全由**实测值**算：视口宽来自探针，帧高来自探针，不用任何魔数。
        dsf = spec['dsf']
        crop_w = int(round(g2['viewport']['w'] * dsf))
        crop_h = int(round((g2['frame']['y'] + g2['frame']['h']) * dsf))
        if crop_w >= px[0] and crop_h >= px[1]:
            fails.append('%s 不需要裁剪（图 %s，要裁到 %s×%s），说明视口或帧的实测值有问题'
                         % (slug, px, crop_w, crop_h))
            continue
        cw, ch = _png.truncate(pp, pp, crop_w, crop_h)

        img = dict(wpx=cw, hpx=ch, w=round(cw / float(dsf), 2), h=round(ch / float(dsf), 2))
        anchors = []
        for a in g2['anchors']:
            a = dict(a)
            a['br'] = ANCHOR_BR.get(a['anchor'], '')
            a['inSpec'] = a['anchor'] in ANCHOR_BR
            anchors.append(a)
        zero = [a['anchor'] for a in anchors if a['w'] <= 0 or a['h'] <= 0]
        if zero:
            fails.append('%s 锚点尺寸为 0：%s' % (slug, ', '.join(zero)))
        nospec = [a['anchor'] for a in anchors if not a['inSpec']]
        if nospec:
            fails.append('%s 锚点不在设计规范清单里：%s' % (slug, ', '.join(nospec)))

        elements = [dict(e) for e in g2.get('elements', [])]
        # 同一画面内元素 id 必须唯一。重名会让连线连到错的那个元素上，
        # 而画面上两处看着都对 —— 这种错必须在这里拦住，不能等到标注阶段靠眼睛发现。
        seen = {}
        for e in elements:
            seen.setdefault(e['el'], 0)
            seen[e['el']] += 1
        dupe = sorted(k for k, v in seen.items() if v > 1)
        if dupe:
            fails.append('%s 元素锚点 id 重复：%s' % (slug, ', '.join(dupe)))
        ezero = [e['el'] for e in elements if e['w'] <= 0 or e['h'] <= 0]
        if ezero:
            fails.append('%s 元素尺寸为 0（连线找不到落点）：%s' % (slug, ', '.join(ezero)))
        # 元素必须落在帧内 —— 帧外元素的坐标是负的或超出帧宽高，连线会画到卡片外面
        eout = [e['el'] for e in elements
                if e['rx'] < -0.6 or e['ry'] < -0.6
                or e['rx'] + e['w'] > g2['frame']['w'] + 0.6
                or e['ry'] + e['h'] > g2['frame']['h'] + 0.6]
        if eout:
            fails.append('%s 元素跑出帧范围：%s' % (slug, ', '.join(eout)))
        nokind = [e['el'] for e in elements if not e['kind']]
        if nokind:
            fails.append('%s 元素缺 data-kind：%s' % (slug, ', '.join(nokind)))
        nolabel = [e['el'] for e in elements if not e['label']]
        if nolabel:
            fails.append('%s 元素缺 data-label（连线上要写是什么元素）：%s'
                         % (slug, ', '.join(nolabel)))
        # 帧必须贴着图的左上角 —— 否则所有锚点百分比都会整体偏移
        if abs(g2['frame']['x']) > 0.6 or abs(g2['frame']['y']) > 0.6:
            fails.append('%s 帧没贴在视口左上角（x=%.1f y=%.1f），'
                         '裁剪后坐标会整体偏移'
                         % (slug, g2['frame']['x'], g2['frame']['y']))

        records.append(dict(
            id=s['pid'], name=s['name'], path=s['path'], change=s['change'],
            platform=s['platform'], vkey=s['vkey'], vname=s['vname'],
            pageFile='pages/' + slug + '.html', shot='shots/' + slug + '.png',
            shotSize=dict(w=cw, h=ch), img=img, dpr=dsf,
            frame=g2['frame'], viewport=g2['viewport'],
            crop=dict(wpx=crop_w, hpx=crop_h, fromPx=[px[0], px[1]]),
            anchors=anchors, elements=elements))

        print('  %-22s %-14s 帧 %4.0fx%-6.0f 图 %5dx%-5d 锚点 %d 元素 %d'
              % (slug, s['vname'], g2['frame']['w'], g2['frame']['h'],
                 cw, ch, len(anchors), len(elements)))

    return records, fails


def main():
    print('[原型生成] 小程序端 + 后台端')
    recs, fails = build()
    if fails:
        print()
        print('  [生成失败]')
        for x in fails:
            print('    - ' + x)
        sys.exit(1)

    covered = sorted({a['anchor'] for r in recs for a in r['anchors']})
    spec_app = sorted(x for x in ANCHOR_BR if ANCHOR_PAGE[x].startswith('PG-A'))
    spec_adm = sorted(x for x in ANCHOR_BR if ANCHOR_PAGE[x].startswith('PG-B'))
    # 元素去重口径：同一个元素会在同页的多个状态里各出现一次（如 PG-A5 主态与失败态都
    # 有「重新支付」），那是**同一个元素的两个状态**，不是两个元素。所以：
    #   elementRecords = 各画面出现次数之和（含跨状态重复）
    #   elementsPlaced = 去重后的元素数
    # 两个数分开报，别让「记录数 > 元素数」看起来像出错（锚点那边踩过同一个坑）。
    el_all = [e['el'] for r in recs for e in r['elements']]
    el_uniq = sorted(set(el_all))
    kinds = {}
    for r in recs:
        for e in r['elements']:
            kinds[e['kind']] = kinds.get(e['kind'], 0) + 1
    # 每个元素的**标准落位**：按画面顺序取第一次出现的那张，
    # 05-annotation 画热区框与连线端点一律用它，避免同一个元素在两处各画一个框。
    el_home = {}
    for r in recs:
        for e in r['elements']:
            el_home.setdefault(e['el'], '%s|%s' % (r['id'], r['vkey']))
    for r in recs:
        for e in r['elements']:
            e['home'] = (el_home[e['el']] == '%s|%s' % (r['id'], r['vkey']))
    out = {
        'schema': 'pm-workflow/element-map/v1',
        'project': _TOK['project'],
        'note': '坐标与截图来自同一次浏览器渲染。视口左上角 = 截图左上角（实测 padX=padY=0），'
                '所以「图上像素 = 视口坐标 × dpr」。截图已在生成时沿右下角截断掉窗口余量，'
                '所以 img.w/img.h 就是**视口**（小程序端是设备框）的 CSS 尺寸，'
                '不再需要「拿图当分母、拿视口当分母」的取舍。'
                'rx/ry 是相对帧左上角的坐标，帧已贴在视口左上角，'
                '因此标注画框一律用 rx/img.w、ry/img.h 算百分比。',
        'deviceScale': {'app': SPECS['app']['dsf'], 'admin': SPECS['admin']['dsf']},
        'frameWidth': {'app': FRAME_W, 'admin': ADMIN_W},
        'specs': {k: {kk: vv for kk, vv in v.items() if kk != 'note'} | {'note': v['note']}
                  for k, v in SPECS.items()},
        'screens': recs,
        'stats': {
            'screens': len(recs), 'mainScreens': len([r for r in recs if r['vkey'] == 'main']),
            'variantScreens': len([r for r in recs if r['vkey'] != 'main']),
            'anchorsPlaced': len(covered),
            'anchorsInSpecApp': len(spec_app),
            'anchorsInSpecAdmin': len(spec_adm),
            'anchorsMissing': [x for x in (spec_app + spec_adm) if x not in covered],
            'elementRecords': len(el_all),
            'elementsPlaced': len(el_uniq),
            'elementsByKind': dict(sorted(kinds.items())),
            'elements': el_uniq,
        },
    }
    with open(MAP_OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    st = out['stats']
    print()
    print('  画面 %d 张（主态 %d · 状态 %d）'
          % (st['screens'], st['mainScreens'], st['variantScreens']))
    for tag, spec, n in (('小程序端', spec_app, st['anchorsInSpecApp']),
                         ('后台端', spec_adm, st['anchorsInSpecAdmin'])):
        hit = len([x for x in spec if x in covered])
        print('  %s锚点 %d/%d 已埋入%s'
              % (tag, hit, n,
                 '' if hit == n else '，缺 ' + ', '.join(
                     x for x in spec if x not in covered)))
    print('  坐标清单 -> element-map.json（%d 条锚点记录）'
          % sum(len(r['anchors']) for r in recs))
    print('  交互点 %d 个（累计落位 %d 次）：%s'
          % (st['elementsPlaced'], st['elementRecords'],
             ' · '.join('%s %d' % (k, v) for k, v in st['elementsByKind'].items())))
    print('  [生成通过]')


if __name__ == '__main__':
    main()
