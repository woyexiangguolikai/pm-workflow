# -*- coding: utf-8 -*-
"""原型白板：把 9 页视觉稿 + 占位页铺在一块可缩放平移的大画布上。

为什么从「网页网格」改成「白板」：
    网格版要上下滚动才能看全，缩放只能整体改宽度 —— 页面一多就丢了空间感。
    白板版把每个元素绝对定位在世界坐标里，滚轮缩放、拖拽平移，
    缩到 40% 看全貌、放大到 100% 看单屏细节，和评审时「指着某一屏讨论」的动作一致。

世界坐标由本文件算好写进内联样式，屏幕坐标由 _canvas_html.py 的 transform 负责 ——
两边不交叉：本文件不碰 transform，那边不碰布局。
"""

import base64
import json
import os
import sys

import _canvas_html as CH

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
EMAP = os.path.join(HERE, 'element-map.json')
TOKENS = os.path.join(ROOT, '03-design', 'tokens.json')
PRD = os.path.join(ROOT, '02-prd', 'prd.json')
OUT = os.path.join(HERE, 'prototype-canvas.html')

CARD_W = 248          # 小程序端主态卡宽（竖屏缩略图）
ADMIN_CARD_W = 460    # 后台端主态卡宽 —— 后台页是 1440 宽的横屏，按 248 放会压成 98px 的细条，
                      # 既看不出结构也点不准；给到 460 之后高度约 180px，能看清区块划分
VAR_W = 192           # 补态卡宽（同一页的其它状态，小一号）
VAR_GAP = 12          # 主态与补态之间
GAP = 26              # 同一组内、页与页之间
GRP_GAP = 58          # 业务组之间
BAND_GAP = 104        # 端区之间
LABEL_H = 30          # 端标签占位高
GLAB_H = 26           # 组标签占位高
DOC_TOP_H = 384       # 顶部文档区高
BOT_PAD = 110
HEAD_H = 28           # 卡头
FOOT_H = 26           # 卡底

CARD_W_BY_END = {'app': CARD_W, 'admin': ADMIN_CARD_W}

GROUPS = [
    {'end': 'app', 'name': '一卡通账户', 'mods': 'M1', 'pages': ['PG-A1', 'PG-A2', 'PG-A3'],
     'note': '绑定、查看、解绑与换卡，围绕「一人一卡」的完整生命周期'},
    {'end': 'app', 'name': '下单与支付', 'mods': 'M2 · M3 · M6', 'pages': ['PG-A6', 'PG-A4', 'PG-A5'],
     'note': '按真实使用顺序排：购物车看折后价 → 收银台选一卡通 → 支付结果'},
    {'end': 'app', 'name': '员工身份', 'mods': 'M5', 'pages': ['PG-A7'],
     'note': '折扣的前提：能被识别成在职员工'},
    {'end': 'app', 'name': '订单与退款', 'mods': 'M4 · M8', 'pages': ['PG-A8', 'PG-A9'],
     'note': '支付之后发生的事：凭证、原路退回'},
    {'end': 'admin', 'name': '租户与通道配置', 'mods': 'M9 · M1 · M2',
     'pages': ['PG-B1', 'PG-B2', 'PG-B3'], 'note': '项目级开关：谁能用、走哪条通道'},
    {'end': 'admin', 'name': '员工与折扣', 'mods': 'M5 · M6 · M7',
     'pages': ['PG-B4', 'PG-B5', 'PG-B6', 'PG-B7'], 'note': '名单、等级、规则、流水，一条链'},
    {'end': 'admin', 'name': '退款管理', 'mods': 'M4', 'pages': ['PG-B8'], 'note': '退款申请、冲正与人工兜底'},
    {'end': 'admin', 'name': '对账结算与报表', 'mods': 'M8 · M9',
     'pages': ['PG-B9', 'PG-B10', 'PG-B11'], 'note': '钱对不对得上、最终什么时候到账'},
]

END_LABEL = {'app': '小程序端 · 用户小程序', 'admin': '后台端 · 管理后台'}
END_NOTE = {
    'app': '改造 4 屏 · 新增 5 屏 ｜ 改造页沿用存量收银台与钱包版式，新增模块带「新增」标',
    'admin': '11 页全部为新增逻辑页（存量代码里没有对应实现）｜ 独立视觉，主色 #2563eb，设计基准宽 1440',
}


def check_groups(all_ids):
    """每个页面必须恰好属于一个分组 —— 漏归会让页面从白板上静默消失，
    重归会在两个分组里各出现一次，两种都不是肉眼能发现的，必须构建期拦住。"""
    seen = {}
    for g in GROUPS:
        for pid in g['pages']:
            seen.setdefault(pid, []).append(g['name'])
    errs = []
    dup = {k: v for k, v in seen.items() if len(v) > 1}
    if dup:
        errs.append('页面被归入多个分组：%s' % dup)
    miss = [x for x in all_ids if x not in seen]
    if miss:
        errs.append('页面未归入任何分组：%s' % miss)
    ghost = [x for x in seen if x not in all_ids]
    if ghost:
        errs.append('分组里写了不存在的页面：%s' % ghost)
    return errs


def load():
    with open(EMAP, encoding='utf-8') as f:
        emap = json.load(f)
    with open(TOKENS, encoding='utf-8') as f:
        tok = json.load(f)
    with open(PRD, encoding='utf-8') as f:
        prd = json.load(f)
    br_title = {r['id']: r.get('title', '') for r in prd['requirements']}
    br_prio = {r['id']: r.get('priority', '') for r in prd['requirements']}
    pages = {}
    for p in tok['pages']:
        pages[p['id']] = dict(
            id=p['id'], name=p['name'], path=p['path'], change=p['change'],
            goal=p['goal'], refs=p['prdRefs'], platform=p['platform'],
            prio_map={b: br_prio.get(b, '') for b in p['prdRefs']},
            anchors=[dict(anchor=a['anchor'], br=a['br'], label=a['label'],
                          extra=a.get('extra', '')) for a in p['anchors']])
    return emap, pages, br_title, br_prio


def b64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


# ------------------------------------------------------------------ 元素
def shot_area(s, page, width):
    """图片区。高度写死，避免图加载完成后元素尺寸跳变（白板上跳变很扎眼）。

    锚点框用百分比定位，分母是**图**尺寸。
    现在 img.w/img.h 就是视口（小程序端是设备框）的 CSS 尺寸 —— 截图在出图时已经
    沿右下角把窗口余量截掉了，所以不存在「图 vs 视口」两个分母的取舍问题。
    """
    img = s.get('img') or s['viewport']
    h = round(width * img['h'] / img['w'], 1)
    meta = {a['anchor']: a for a in page['anchors']}
    annos = []
    for i, a in enumerate(s['anchors'], 1):
        annos.append('<i class="an t-only" data-i="%d" '
                     'style="left:%.3f%%;top:%.3f%%;width:%.3f%%;height:%.3f%%" '
                     'data-a="%s" data-br="%s" title="%s · %s"></i>'
                     % (i, a['x'] / img['w'] * 100, a['y'] / img['h'] * 100,
                        a['w'] / img['w'] * 100, a['h'] / img['h'] * 100,
                        a['anchor'], a['br'], a['anchor'],
                        (meta.get(a['anchor'], {}).get('label') or '')))
    return ('<div class="el-img" style="height:%.1fpx">'
            '<img src="data:image/png;base64,%s" alt="%s %s" loading="lazy">%s</div>'
            % (h, b64(os.path.join(HERE, s['shot'])), esc(page['name']),
               esc(s['vname']), ''.join(annos))), h


def page_el(pid, page, s, x, y, width, vi, el_map):
    """一个截图 = 一个元素。同一页的补态是独立元素但共用 data-id，
    这样灯箱里能按 data-id 把所有状态串起来翻，白板上也保持「一排」的读法。"""
    img = s.get('img') or s['viewport']
    area, ih = shot_area(s, page, width)
    h = round(HEAD_H + ih + FOOT_H, 1)
    is_var = s['vkey'] != 'main'
    chg = 'new' if page['change'] == '新增' else 'rework'
    badge = ('<span class="el-c c-var">补态</span>' if is_var
             else '<span class="el-c c-%s">%s</span>' % (chg, page['change']))
    title = ('%s · %s' % (pid, page['name'])) if not is_var else ('%s · %s' % (pid, s['vname']))
    brs = ''.join('<span class="br%s">%s</span>'
                  % (' p0' if page['prio_map'].get(b) == 'P0' else '', b)
                  for b in page['refs'])
    key = ' '.join([page['name'], page['path'], pid, s['vname']] + page['refs'] +
                   [a['anchor'] for a in page['anchors']])
    el_map.append(dict(x=x, y=y, w=width, h=h, kind='var' if is_var else 'page'))
    return ('<div class="el page" data-id="%s" data-end="%s" data-change="%s" '
            'data-vi="%d" data-vname="%s" data-key="%s" '
            'style="left:%.0fpx;top:%.0fpx;width:%dpx">'
            '<div class="el-h"><span class="el-ic"></span>'
            '<span class="el-t">%s</span>%s</div>%s'
            '<div class="el-f">%s</div></div>'
            % (pid, page['platform'], chg, vi, esc(s['vname']), esc(key),
               x, y, width, esc(title), badge, area, brs))


def todo_el(pid, page, x, y, width, el_map):
    h = round(width * 1.52)
    chg = 'new' if page['change'] == '新增' else 'rework'
    brs = ''.join('<span class="br%s">%s</span>'
                  % (' p0' if page['prio_map'].get(b) == 'P0' else '', b)
                  for b in page['refs'])
    total = HEAD_H + h + FOOT_H
    el_map.append(dict(x=x, y=y, w=width, h=total, kind='todo'))
    return ('<div class="el todo" data-id="%s" data-end="admin" data-change="%s" '
            'data-key="%s" style="left:%.0fpx;top:%.0fpx;width:%dpx">'
            '<div class="el-h"><span class="el-ic" style="background:#5b6672"></span>'
            '<span class="el-t">%s · %s</span><span class="el-c c-todo">待生成</span></div>'
            '<div class="el-wait" style="height:%dpx">待生成'
            '<span>本轮先出小程序端样板，确认视觉后按同一套组件与 Token 补齐</span></div>'
            '<div class="el-f">%s</div></div>'
            % (pid, chg, esc(' '.join([page['name'], page['path'], pid] + page['refs'])),
               x, y, width, pid, esc(page['name']), h, brs))


def doc_el(eid, title, x, y, w, html, el_map):
    h = None
    el_map.append(dict(x=x, y=y, w=w, h=DOC_TOP_H, kind='doc'))
    return ('<div class="el doc" data-doc="%s" style="left:%.0fpx;top:%.0fpx;width:%dpx">'
            '<div class="el-h"><span class="el-ic"></span>'
            '<span class="el-t">%s</span></div>'
            '<div class="doc-b">%s</div></div>' % (eid, x, y, w, esc(title), html))


def glab(gid, name, mods, note, x, y, cnt):
    return ('<div class="glab" data-g="%s" style="left:%.0fpx;top:%.0fpx">'
            '<b>%s</b><em>%s</em><span>%s</span><span style="color:#4b5560">%d 页</span></div>'
            % (esc(name), x, y, esc(name), esc(mods), esc(note), cnt))


def blab(text, x, y):
    return '<div class="blab" style="left:%.0fpx;top:%.0fpx">%s</div>' % (x, y, esc(text))


# ------------------------------------------------------------------ 布局
def build():
    emap, pages, br_title, br_prio = load()
    errs = check_groups(sorted(pages))
    if errs:
        for e in errs:
            print('  [分组校验失败] ' + e)
        sys.exit(1)

    by_page = {}
    for s in emap['screens']:
        by_page.setdefault(s['id'], []).append(s)
    for k in by_page:
        by_page[k].sort(key=lambda s: 0 if s['vkey'] == 'main' else 1)

    shot_pages = len(by_page)
    total_pages = len(pages)
    n_shots = len(emap['screens'])
    # ⚠️ 这里有两个不同的数，不能混用：
    #   n_records —— 锚点在**各画面里出现的次数**。同一页的主态和补态会各算一次
    #                （PG-A3 的解绑入口在主态和确认弹窗里都要框），所以它比锚点数大。
    #   n_placed  —— **去重后**真正落位的锚点数，才是能跟设计清单对齐的那个数。
    # 早先拿 n_records 去比设计总数，界面上出现「53/43 已埋」这种看起来像出错的数字。
    n_records = sum(len(s['anchors']) for s in emap['screens'])
    placed = {a['anchor'] for s in emap['screens'] for a in s['anchors']}
    n_placed = len(placed)
    n_anchors = sum(len(p['anchors']) for p in pages.values())
    spec_all = {a['anchor'] for p in pages.values() for a in p['anchors']}
    miss_anchor = sorted(spec_all - placed)
    ghost_anchor = sorted(placed - spec_all)
    if miss_anchor or ghost_anchor:
        print('  [锚点校验失败] 未落位 %s ｜ 多出 %s' % (miss_anchor, ghost_anchor))
        sys.exit(1)

    els, el_map = [], []

    # ---- 顶部文档区：先讲怎么用，再给进度与图例
    doc_gap = 26
    els.append(doc_el('intro', '这块白板怎么用', 0, 0, 452, """
<b>滚轮</b>缩放（以鼠标位置为中心），<b>拖住空白</b>平移，<b>点任意页面</b>打开大图看细节。
右上角可以按端、按「新增/改造」筛，也能搜页面名、锚点名和需求号（如 <code>BR-302</code>）；
右下角是缩放控制与小地图 —— 缩到 40% 看全貌，放大到 100% 看待审的那一屏。
<br><br>
<code>视图</code> 默认<b>业务</b>：给领导和客户看时只有「这屏长什么样、覆盖哪条需求」。
切到<b>技术</b>会放出页面路径、锚点名，还能打开<b>锚点框</b> —— 那是给开发对落点用的。
""", el_map))
    els.append(doc_el('stats', '本轮进度', 452 + doc_gap, 0, 430, """
<div class="big">%d / %d 页已出图</div>
<div class="row"><span class="k">画面总数</span><span class="v">%d 张（主态 %d · 补态 %d）</span></div>
<div class="row"><span class="k">锚点已埋</span><span class="v">%d 处 / 设计共 %d 处</span></div>
<div class="row"><span class="k">锚点落位</span><span class="v">%d 次（补态里重复出现的另计）</span></div>
<div class="row"><span class="k">新增 / 改造</span><span class="v">%d / %d</span></div>
<div class="row"><span class="k">两端</span><span class="v">小程序端 9 页 · 后台端 11 页</span></div>
<div style="margin-top:9px;color:#8b949e;font-size:11.5px;line-height:1.7">
两端锚点已全部落位，可直接对照 PRD 核对落点；下一阶段在图上出标注与交互连线。</div>
""" % (shot_pages, total_pages, n_shots,
       len([s for s in emap['screens'] if s['vkey'] == 'main']),
       len([s for s in emap['screens'] if s['vkey'] != 'main']),
       n_placed, n_anchors, n_records,
       len([p for p in pages.values() if p['change'] == '新增']),
       len([p for p in pages.values() if p['change'] == '改造'])), el_map))
    els.append(doc_el('legend', '图例', 452 * 2 + doc_gap * 2, 0, 396, """
<div class="lg"><i class="c-rework" style="background:#2c2413;border-color:#4a3c18"></i>
<span><b>改造</b> · 在存量页面上动，沿用原有版式</span></div>
<div class="lg"><i class="c-new" style="background:#132a1c;border-color:#1d4429"></i>
<span><b>新增</b> · 全新页面</span></div>
<div class="lg"><i class="c-var" style="background:#1c1428;border-color:#362a4d"></i>
<span><b>补态</b> · 同一页的其它状态（弹窗、失败、处理中）</span></div>
<div style="margin-top:9px;color:#8b949e;font-size:11.5px;line-height:1.7">
需求号 <span class="br p0" style="font-size:10px">P0</span> 是要害条款，标红底；
打开「锚点框」后图上的红框序号，与右侧大图信息栏里的锚点序号一一对应。<br>
小程序端是竖屏设备框，后台端是 1440 宽的横屏页面，所以两端的卡片宽度不同 ——
按各自的分辨率取宽，缩略图才既看得出结构又不失真。</div>
""", el_map))

    y = DOC_TOP_H + BAND_GAP
    for end in ('app', 'admin'):
        gs = [g for g in GROUPS if g['end'] == end]
        n_pg = sum(len(g['pages']) for g in gs)
        ok = len([p for g in gs for p in g['pages'] if p in by_page])
        els.append(blab('%s ｜ %d 页 · 已出图 %d ｜ %s'
                        % (END_LABEL[end], n_pg, ok, END_NOTE[end]), 0, y))
        y += LABEL_H
        row_y = y + GLAB_H
        x = 0
        row_h = 0
        for g in gs:
            els.append(glab(g['name'], g['name'], g['mods'], g['note'], x, y,
                            len(g['pages'])))
            gx = x
            for pid in g['pages']:
                # 卡宽按**页面自己的端**取，不按所在组的端 —— 万一哪天有页被归错组，
                # 画面也不会变形，只是排在了不对的分组里（这个 check_groups 拦不住）。
                cw = CARD_W_BY_END.get(pages[pid]['platform'], CARD_W)
                if pid in by_page:
                    for vi, s in enumerate(by_page[pid]):
                        w = cw if s['vkey'] == 'main' else VAR_W
                        els.append(page_el(pid, pages[pid], s, gx, row_y, w, vi, el_map))
                        row_h = max(row_h, HEAD_H + round(w * (s['img']['h'] / s['img']['w']), 1)
                                    + FOOT_H)
                        gx += w + (VAR_GAP if vi == 0 and len(by_page[pid]) > 1 else GAP)
                else:
                    els.append(todo_el(pid, pages[pid], gx, row_y, cw, el_map))
                    row_h = max(row_h, HEAD_H + round(cw * 1.52) + FOOT_H)
                    gx += cw + GAP
            x = gx - GAP + GRP_GAP
        y = row_y + row_h + BAND_GAP

    world_w = max([0] + [e['x'] + e['w'] for e in el_map]) + 120
    world_h = y - BAND_GAP + BOT_PAD

    # ---- HUD
    hud_left = ('<span class="logo">原型白板</span>'
                '<span class="sub">校园订餐 · 一卡通支付与员工折扣 · 04-prototype</span>')
    hud_right = (
        '<div class="panel"><div class="seg" id="fEnd">'
        '<button class="on" data-e="all">全部端</button>'
        '<button data-e="app">小程序</button><button data-e="admin">后台</button></div>'
        '<div class="seg" id="fChg"><button class="on" data-c="all">全部</button>'
        '<button data-c="new">新增</button><button data-c="rework">改造</button></div>'
        '<input id="q" type="search" placeholder="搜页面 / 锚点 / 需求号">'
        '<button class="btn" id="tView">视图：<b>业务</b></button></div>')
    hud_br = (
        '<div class="panel">'
        '<button class="btn zbtn" id="zOut" title="缩小">−</button>'
        '<span class="zv" id="zv" title="点击回到 100%%">100%%</span>'
        '<button class="btn zbtn" id="zIn" title="放大">+</button>'
        '<button class="btn" id="zFit">适应</button>'
        '<button class="btn" id="tAnno">锚点框</button></div>'
        '<div class="mini" id="mini">'
        '<div class="mini-l" id="miniL">%s</div>'
        '<div class="mini-vp" id="miniVP"></div></div>')
    hud_bl = ('<div class="tip">当前显示 <b id="hitv">%d</b> 页 ｜ '
              '滚轮缩放 · 拖拽平移 · 点击页面看大图</div>'
              % shot_pages)

    mini = ''.join('<i class="%s" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;height:%.1fpx"></i>'
                   % (e['kind'], e['x'], e['y'], e['w'], e['h']) for e in el_map)

    payload = dict(
        world=dict(w=world_w, h=world_h),
        pages={k: dict(v) for k, v in pages.items()},
        brTitle=br_title, brPrio=br_prio, groups=GROUPS, endLabel=END_LABEL,
        # 构建期「我打算画成什么样」。校验脚本读它来跟**渲染结果**对账，
        # 这样分组数、文档卡数这些数字只有一处定义 —— 写死在两边迟早改一处漏一处，
        # 而漏掉的表现是校验悄悄放行（期望值跟着实现一起漂了）。
        manifest=dict(
            els=len(el_map),
            docs=len([e for e in el_map if e['kind'] == 'doc']),
            pages=len([e for e in el_map if e['kind'] in ('page', 'var')]),
            todos=len([e for e in el_map if e['kind'] == 'todo']),
            groups=len(GROUPS),
            anchorBoxes=sum(len(s['anchors']) for s in emap['screens']),
            imgs=n_shots,
            worldW=world_w, worldH=world_h,
        ),
    )
    for k, v in payload['pages'].items():
        v['mainFile'] = by_page[k][0]['pageFile'] if k in by_page else ''

    stats = dict(shotPages=shot_pages, totalPages=total_pages, shots=n_shots,
                 placed=n_placed, anchors=n_anchors, els=len(el_map),
                 worldW=world_w, worldH=world_h)

    doc = CH.render(''.join(els), payload, stats, hud_left, hud_right,
                    hud_br % mini, hud_bl)
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write(doc)

    print('[原型白板] %s' % os.path.basename(OUT))
    print('  世界画布 %d × %d px ｜ 元素 %d 个（页面 %d · 文档卡 %d）'
          % (world_w, world_h, len(el_map),
             len([e for e in el_map if e['kind'] in ('page', 'var', 'todo')]),
             len([e for e in el_map if e['kind'] == 'doc'])))
    print('  画面 %d 张（主态 %d · 补态 %d）｜ 未出图 %d 页'
          % (n_shots, len([s for s in emap['screens'] if s['vkey'] == 'main']),
             len([s for s in emap['screens'] if s['vkey'] != 'main']),
             total_pages - shot_pages))
    for end in ('app', 'admin'):
        ids = [p['id'] for p in pages.values() if p['platform'] == end]
        ok = [i for i in ids if i in by_page]
        print('  %s：%d/%d 页已出图' % (END_LABEL[end].split(' · ')[0], len(ok), len(ids)))
    print('  锚点 %d/%d 已埋（各画面累计落位 %d 次）' % (n_placed, n_anchors, n_records))
    print('  文件 %.1f MB（缩略图已 base64 内联，双击可开）'
          % (os.path.getsize(OUT) / 1048576.0))
    print('  [生成通过]')


if __name__ == '__main__':
    build()
