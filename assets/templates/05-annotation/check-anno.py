# -*- coding: utf-8 -*-
"""05-annotation 校验。跑法：

    python check-anno.py            正常校验
    python check-anno.py --mutate   变异测试（内置）

## 这份校验要证明什么

用户的原话是「连接线不能遮挡其他原型」。这是一句**观感描述**，而观感描述没法
交给下一个人复验 —— 他说看不出遮挡，你说看得出，争论不出结果。
所以把它翻译成一条可判定的事实：

    把每一张页面卡片当成闭矩形，连线的每一段（引出段除外）与任何卡片求交都必须为空。

这条规则一旦成立，「没遮挡」就不再依赖谁的肉眼。这份脚本就是逐段求交的那一步。

## 为什么「引出段除外」不是放水

线要从按钮上出发，就必须先穿过按钮所在的那张卡片本身，否则线会飘在空中。
所以首段和末段（以及同卡片内的整条线）允许落在**它自己的**源卡/目标卡里 ——
只允许落在自己那张卡里，落在任何**别**的卡上照样判失败。

## 为什么必须有 --mutate

一个检查如果在「被检查的东西生效了」和「它压根没生效」两种世界状态下产出完全
一样的输出，那它什么都没证明，反而把「没生效」报告成了「通过」。
所以这里把障碍表整个清空、用同一套探针重跑一遍，**必须变红**才算这套检查有判别力。

## 期望值一律现算

条数、分类数、元素数、无出链元素集合、卡片矩形……全部从
annotations.json / element-map.json / prd.json / _interact.py 现读现算。
写死数字的后果是改一处忘一处，校验退化成「上次的数字」而不是「这次的事实」。
"""

import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PROJ = os.path.dirname(HERE)
PROTO = os.path.join(PROJ, '04-prototype')
PRD = os.path.join(PROJ, '02-prd', 'prd.json')
EMAP = os.path.join(PROTO, 'element-map.json')
ANNO = os.path.join(HERE, 'annotations.json')
HTML = os.path.join(HERE, 'annotate.html')

TOL = 1.5          # 端点落点容差（px）。浮点 + 四舍五入到 0.1，1.5 够宽松也不放水


def _b(card):
    """数据源里的卡片是 [x, y, w, h]，而求交函数要的是角点 (x0, y0, x1, y1)。

    ⚠️ 这两种写法长得太像，混用**不会报错**，只会让框悄悄变矮变窄：
    把 (x, y, w, h) 当 (x0, y0, x1, y1) 用，(240, 547) 这种卡片就变成
    「x 到 240、y 到 547」，竖着少掉一半 —— 于是水平走的线从卡片下方穿过去
    也判成"没压卡"。本文件**只允许**通过这一个函数取卡片角点。
    """
    x, y, w, h = card['rect']
    return (x, y, x + w, y + h)


def load_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


sys.path.insert(0, HERE)
sys.path.insert(0, PROTO)
B = load_mod('b_anno', os.path.join(HERE, 'build-anno.py'))
RT = B.RT

FAIL = []
WARN = []


def ck(name, ok, detail=''):
    print('  %s %s%s' % ('[ok]' if ok else '[!!]', name, ('  ' + detail) if detail else ''))
    if not ok:
        FAIL.append(name + ('  ' + detail if detail else ''))
    return ok


def sec(t):
    print('\n' + t)


# ------------------------------------------------------------------ 载入
def context():
    with open(ANNO, encoding='utf-8') as f:
        A = json.load(f)
    with open(EMAP, encoding='utf-8') as f:
        EM = json.load(f)
    with open(PRD, encoding='utf-8') as f:
        PR = json.load(f)
    return A, EM, PR


# ================================================================== 1 结构闭环
def check_structure(A, EM, PR):
    links, cards, els, st = A['links'], A['cards'], A['elements'], A['stats']
    ids = set(e['el'] for e in els)
    home = [e['el'] for e in els if e['home']]
    br_ids = set(r['id'] for r in PR['requirements'])

    sec('1 · 结构闭环（PRD ↔ 原型 ↔ 标注）')

    # 逐屏 id 唯一：元素 id 允许跨状态重复（同一个按钮的不同状态），
    # 但**同一张画面里**必须是唯一的，否则画线时取到哪个是随机的。
    seen = {}
    dup = []
    for e in els:
        k = (e['screen'], e['el'])
        if k in seen:
            dup.append('%s@%s' % (e['el'], e['screen']))
        seen[k] = 1
    ck('同屏元素 id 唯一', not dup, ('重复：%s' % dup[:4]) if dup else '%d 个 id / %d 处落位'
       % (len(ids), len(els)))

    ck('去重后每个 id 恰好一个 home', sorted(home) == sorted(set(home)) and len(home) == len(ids),
       '%d home / %d id' % (len(home), len(ids)))

    # 与 04-prototype 的原型清单交叉：标注里出现的元素，原型里必须有。
    # 这一条断了就说明「标注不是从原型出发的」——正是用户要求避免的事。
    proto = set()
    for s in EM['screens']:
        for e in s.get('elements', []):
            proto.add(e['el'])
    miss = sorted(set(x['fromEl'] for x in links) - proto)
    ck('连线起点都能在原型清单里找到', not miss, ('缺：%s' % miss[:5]) if miss else
       '%d 个起点 / 原型共 %d 个交互点' % (len(set(x['fromEl'] for x in links)), len(proto)))

    tos = [x['to'] for x in links]
    to_el = [t for t in tos if not t.startswith('#')]
    miss2 = sorted(set(to_el) - proto)
    ck('元素型终点都能在原型清单里找到', not miss2, ('缺：%s' % miss2[:5]) if miss2 else
       '%d 条终点为元素' % len(to_el))

    # 页面/状态型终点：必须能对上某个已知画面
    known = set()
    for c in cards:
        known.add('#%s' % c['pid'])
        known.add('#%s/%s' % (c['pid'], c['vkey']))
    bad_to = sorted(set(t for t in tos if t.startswith('#')) - known)
    ck('页面型终点都能对上已知画面', not bad_to, ('对不上：%s' % bad_to[:5]) if bad_to else
       '%d 条终点为页面/状态' % len([t for t in tos if t.startswith('#')]))

    bad_br = sorted(set(x['br'] for x in links) - br_ids)
    ck('连线携带的需求号都在 PRD 里', not bad_br, ('缺：%s' % bad_br[:5]) if bad_br else
       '%d 条连线覆盖 %d 条需求' % (len(links), len(set(x['br'] for x in links))))

    # 无出链元素：必须**全部**登记，且登记的必须真的存在。
    # 两边都现算。「样本为 0 判失败」在这里体现为：无出链集合为空说明连线清单压根没接上。
    froms = set(x['fromEl'] for x in links)
    dead = ids - froms
    reg = set(A['inplace'].keys())
    ck('无出链元素已全部登记', dead == reg,
       '未登记 %d 个 %s · 登记多余 %d 个 %s'
       % (len(dead - reg), sorted(dead - reg)[:3],
          len(reg - dead), sorted(reg - dead)[:3]))
    ck('无出链集合非空（否则说明连线没接上）', len(dead) > 0, '%d 个' % len(dead))

    # 每条登记的 inplace 都要有理由，否则它就是一个「绕过校验的后门」
    noreason = sorted(k for k, v in A['inplace'].items() if not v.get('reason'))
    ck('每个无出链登记都写了理由', not noreason, ('缺理由：%s' % noreason[:5]) if noreason else '')


# ================================================================== 2 几何
def geom(links, cards):
    """返回 (压卡失败列表, 结构失败列表, 端点失败列表)。"""
    idx_of = {}
    for c in cards:
        idx_of[c['pid'] + '|' + c['vkey']] = c
    scrub, bad_struct, bad_end = [], [], []

    boxes = [(_b(c), c) for c in cards]

    for lk in links:
        pts = [tuple(p) for p in lk['pts']]
        flags = lk['stubs']
        n = len(pts) - 1
        same = lk['fromScreen'] == lk['toScreen']

        # --- 可见性：连线必须真的画得出来。
        # 一个点、或者两个几乎重合的点，画出来就是"什么都没有" ——
        # 但数据源里这条连线还在，计数、清单、校验全都对得上，
        # 只有眼睛看不到它。tab bar 上两个相邻 tab 的间隙是 0，
        # 直肘退化成一个点就是这么来的，所以这条必须单独断。
        total = sum(abs(pts[i][0] - pts[i + 1][0]) + abs(pts[i][1] - pts[i + 1][1])
                    for i in range(n))
        if n < 1 or total < 8.0:
            bad_struct.append('%s 连线退化：%d 个顶点 / 总长 %.1fpx，画出来看不见'
                              % (lk['id'], len(pts), total))
        for i in range(n):
            if abs(pts[i][0] - pts[i + 1][0]) < 0.3 and abs(pts[i][1] - pts[i + 1][1]) < 0.3:
                bad_struct.append('%s 第 %d 段长度为 0' % (lk['id'], i))

        # --- 结构：外部连线恰好首尾两段是引出段；同卡连线整条都在卡内
        if same:
            if not all(flags):
                bad_struct.append('%s 同卡连线理应对每段都标引出段' % lk['id'])
        else:
            if not (flags[0] and flags[-1] and not any(flags[1:-1])):
                bad_struct.append('%s 引出段标记异常 %s' % (lk['id'], flags))

        # --- 自己的卡：引出段只准碰它。注意这里比的是**角点**，见 _b()
        own = set()
        for k in (lk['fromScreen'], lk['toScreen']):
            c = idx_of.get(k)
            if c:
                own.add(id(c))

        for i in range(n):
            p, q = pts[i], pts[i + 1]
            for box, c in boxes:
                if flags[i] and id(c) in own:
                    continue
                if RT.seg_rect_hit(p, q, box):
                    scrub.append('%s 第 %d 段（%s）压到卡片 %s|%s'
                                 % (lk['id'], i,
                                    '引出段' if flags[i] else '通道段',
                                    c['pid'], c['vkey']))

        # --- 端点必须落在矩形的边界上（不是浮在空中，也不是落在矩形内部深处）
        fr, tr = lk['fromRect'], lk['toRect']
        if not _on_border(pts[0], fr):
            bad_end.append('%s 起点 %s 不在源矩形 %s 边界上' % (lk['id'], pts[0], fr))
        if not _on_border(pts[-1], tr):
            bad_end.append('%s 终点 %s 不在目标矩形 %s 边界上' % (lk['id'], pts[-1], tr))

    return scrub, bad_struct, bad_end


def _on_border(p, rect):
    x, y, w, h = rect
    if x - TOL <= p[0] <= x + w + TOL and y - TOL <= p[1] <= y + h + TOL:
        # 在（外扩后的）矩形里，且贴着某一条边
        near = min(abs(p[0] - x), abs(p[0] - (x + w)), abs(p[1] - y), abs(p[1] - (y + h)))
        return near <= TOL
    return False


def check_box_convention(A):
    """独立证明「卡片矩形」和「元素矩形」用的是一套约定。

    这一条是为了防住上面 _b() 注释里那个坑：如果卡片矩形被当成 [x0,y0,x1,y1] 用，
    框会凭空变小，而**「线不压纸卡」会照样报全绿**（框小了当然压不到）。
    元素矩形的坐标是 build-anno 从百分比现算的，卡片矩形的坐标来自排版，
    两者是分开算出来的 —— 所以「元素在自己卡片里」成立，就说明两份约定一致。
    """
    sec('2 · 几何：连线不遮挡原型')
    bykey = {}
    for c in A['cards']:
        bykey[c['pid'] + '|' + c['vkey']] = _b(c)
    out = []
    for e in A['elements']:
        cb = bykey.get(e['screen'])
        if cb is None:
            out.append('%s 找不到所属卡片' % e['el'])
            continue
        x, y, w, h = e['rectWorld']
        if x < cb[0] - 0.6 or y < cb[1] - 0.6 or x + w > cb[2] + 0.6 or y + h > cb[3] + 0.6:
            out.append('%s 的元素矩形 %s 越出卡片 %s'
                       % (e['el'], [round(v, 1) for v in (x, y, w, h)], cb))
    ck('每个元素矩形都落在自己卡片的矩形里（证明两份矩形约定一致）', not out,
       ('%d 处：%s' % (len(out), out[:3])) if out else '%d 个元素' % len(A['elements']))


def check_geom(links, cards, label=''):
    scrub, bad_struct, bad_end = geom(links, cards)
    ck('%s连线不压任何卡片（引出段只准碰自己的卡）' % label, not scrub,
       ('%d 处：%s' % (len(scrub), scrub[:4])) if scrub else
       '%d 条 × %d 段逐段与 %d 张卡片求交，全部在通道里'
       % (len(links), sum(len(x['pts']) - 1 for x in links), len(cards)))
    ck('%s引出段标记与可见长度都正常' % label, not bad_struct,
       ('%s' % bad_struct[:3]) if bad_struct else '')
    ck('%s两端都接在元素/卡片边界上' % label, not bad_end,
       ('%d 处：%s' % (len(bad_end), bad_end[:3])) if bad_end else '')
    return scrub, bad_struct, bad_end


# ================================================================== 3 标签
def check_clearance(A):
    """连线与卡片的**最小间距**。不遮挡只是及格线，贴着过去照样看不清。"""
    sec('2b · 间距：连线离卡片有多远')
    links, cards = A['links'], A['cards']
    boxes = [(_b(c), c) for c in cards]
    worst = []
    for lk in links:
        own = set()
        for k in (lk['fromScreen'], lk['toScreen']):
            for c in cards:
                if c['pid'] + '|' + c['vkey'] == k:
                    own.add(id(c))
        pts = [tuple(p) for p in lk['pts']]
        mn, who = 1e9, ''
        for i in range(len(pts) - 1):
            for box, c in boxes:
                if lk['stubs'][i] and id(c) in own:
                    continue                    # 引出段本来就要穿过自己的卡
                d = _seg_rect_dist(pts[i], pts[i + 1], box)
                if d < mn:
                    mn, who = d, '%s|%s' % (c['pid'], c['vkey'])
        worst.append((mn, lk['id'], who))
    worst.sort()
    mn = worst[0][0]
    # 理论下限：障碍外扩 CLEAR=20，格心最多偏半格 7 → 20 − 7 = 13px
    need = RT.CLEAR - RT.CELL / 2.0 - TOL
    ck('每条线离所有卡片都留出了间距（不小于 %.1fpx）' % need, mn >= need,
       '最小 %.1f px（%s 距 %s）· 最紧三条：%s'
       % (mn, worst[0][1], worst[0][2],
          ' '.join('%s %.0fpx' % (i, d) for d, i, _ in worst[:3])))


def check_labels(A):
    links, cards = A['links'], A['cards']
    sec('3 · 标签')
    oncard, off = [], []
    boxes, owners = [], []          # 两个平行列表：矩形 + 它的连线号
    for lk in links:
        lb = lk.get('labelBox')
        if not lb:
            continue
        box = tuple(lb)
        # 同卡连线的标签允许落在**自己那张卡**里（它注释的就是这张卡内部的两个控件），
        # 但仍然不许碰到任何别的卡片。判断依据是数据源里的 labelInCard，
        # 而不是"看它有没有压到卡" —— 后者会把例外变成"随便压"。
        same = lk['fromScreen'] == lk['toScreen']
        for c in cards:
            if same and c['pid'] + '|' + c['vkey'] == lk['fromScreen']:
                continue
            if RT._hits(box, [_b(c)]):
                oncard.append('%s 标签压到 %s|%s' % (lk['id'], c['pid'], c['vkey']))
        for j, other in enumerate(boxes):
            if RT._hits_any(box, [other]):
                oncard.append('%s 标签与 %s 标签重叠' % (lk['id'], owners[j]))
        boxes.append(box)
        owners.append(lk['id'])
        # 标签必须**压在自己那条线上**（相切也算）—— 这是「标注在连接线上」的可判定形式。
        # 不要求中心落在线上：胶囊可以贴着线错开一档（相邻两条共线的连线必须靠这个错开），
        # 但它的一条边必须压在线中心上，绝不能飘到别处去。
        if not any(_seg_rect_dist(tuple(lk['pts'][i]), tuple(lk['pts'][i + 1]), box) <= 0.5
                   for i in range(len(lk['pts']) - 1)):
            off.append(lk['id'])

    ck('标签不压卡片、不互相重叠', not oncard, ('%s' % oncard[:4]) if oncard else
       '%d 个标签' % len(boxes))
    ck('每个标签都压在自己那条线上', not off, ('%s' % off[:4]) if off else '')

    # 用户的要求是「连接线上要标注出交互方式」，所以这一条不是"覆盖率不为 0"，
    # 而是**每条线都要有**。业务标签可以退回左侧清单（那里每条都有），
    # 交互方式不行 —— 它是线上的必要信息。
    labelled = len([x for x in links if x.get('labelPos')])
    ck('每条连线都在线上标出了交互方式', labelled == len(links),
       '%d/%d 条' % (labelled, len(links)))
    short = len([x for x in links if x.get('labelShort')])
    full = labelled - short
    if short:
        WARN.append('其中 %d 条只标了交互方式（完整胶囊放不下），业务标签见左侧清单'
                    % short)
    print('  标签：完整 %d 条 · 仅交互方式 %d 条' % (full, short))


def _pt_seg(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    if L < 1e-9:
        return ((px - ax) ** 2 + (py - ay) ** 2) ** 0.5
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
    return ((px - (ax + t * dx)) ** 2 + (py - (ay + t * dy)) ** 2) ** 0.5


def _pt_rect(px, py, r):
    dx = max(r[0] - px, px - r[2], 0.0)
    dy = max(r[1] - py, py - r[3], 0.0)
    return (dx * dx + dy * dy) ** 0.5


def _seg_rect_dist(p, q, r):
    """线段到矩形的距离。相交返回 0。

    为什么要算距离而不是只判相交：断言「不遮挡」只挡住"压上去"，
    挡不住"离边缘 1px 蹭着过去" —— 那种也算没遮挡，但看起来就是糊在一起。
    引出段是斜的（法线与格心差半格），所以不能只在水平/垂直两种情形上分支，
    必须给一般线段一个正确的答案。
    """
    x0, y0, x1, y1 = r
    # 端点在矩形内 → 相交
    for (px, py) in (p, q):
        if x0 <= px <= x1 and y0 <= py <= y1:
            return 0.0
    # 线段是否穿过四条边之一
    for (a, b) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)),
                   ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
        if _seg_cross(p, q, a, b):
            return 0.0
    # 否则取「两端点到矩形」与「四角到线段」的最小值
    d = min(_pt_rect(p[0], p[1], r), _pt_rect(q[0], q[1], r))
    for c in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
        d = min(d, _pt_seg(c[0], c[1], p, q))
    return d


def _seg_cross(p, q, a, b):
    def o(x, y, z):
        v = (y[1] - x[1]) * (z[0] - x[0]) - (y[0] - x[0]) * (z[1] - x[1])
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)
    o1, o2 = o(p, q, a), o(p, q, b)
    o3, o4 = o(a, b, p), o(a, b, q)
    return o1 != o2 and o3 != o4


# ================================================================== 4 计数
def check_stats(A):
    links, cards, els, st = A['links'], A['cards'], A['elements'], A['stats']
    sec('4 · 计数（期望值全部现算）')
    n_from_src = len(B.I.LINKS)
    ck('连线条数与连线清单一致', st['links'] == len(links) == n_from_src,
       'stats %d · json %d · _interact %d' % (st['links'], len(links), n_from_src))
    ck('分类计数之和等于总条数',
       sum(st['byAction'].values()) == len(links),
       ' '.join('%s %d' % (k, v) for k, v in st['byAction'].items()))
    ck('分类集合与连线用到的 action 完全一致',
       set(st['byAction']) == set(x['action'] for x in links))
    ck('元素去重数与统计一致', st['elements'] == len(set(e['el'] for e in els)),
       '%d' % st['elements'])
    ck('热区数等于各屏元素数之和', st['hotspots'] == len(els),
       '%d 处 / %d 条记录' % (st['hotspots'], len(els)))
    ck('卡片数与数据源一致', st['cards'] == len(cards), '%d' % st['cards'])
    ck('带标签数与实际一致',
       st['labelled'] == len([x for x in links if x.get('labelPos')]),
       '%d' % st['labelled'])


# ================================================================== 5 视图不漂移
def check_html(A):
    sec('5 · 视图与数据源不漂移')
    if not os.path.exists(HTML):
        ck('annotate.html 存在', False)
        return
    with open(HTML, encoding='utf-8') as f:
        h = f.read()
    got = re.findall(r'<polyline points="([^"]+)"', h)
    links = A['links']
    ck('HTML 里 polyline 条数等于数据源条数', len(got) == len(links),
       'html %d / json %d' % (len(got), len(links)))
    diff = []
    for i, (g, lk) in enumerate(zip(got, links)):
        want = ' '.join('%.1f,%.1f' % (p[0], p[1]) for p in lk['pts'])
        if g != want:
            diff.append('%s' % lk['id'])
    ck('每条线的顶点坐标与数据源逐字一致', not diff, ('漂移：%s' % diff[:4]) if diff else
       '%d 条逐字比对通过' % min(len(got), len(links)))
    # 交互方式必须落在线上：颜色 + 线型由 action 决定，改 action 必须改画面
    miss = [lk['id'] for lk in links
            if ('stroke="%s"' % A['actions'][lk['action']]['color']) not in h]
    ck('线上确实带了交互方式的颜色/线型', not miss, ('缺：%s' % miss[:4]) if miss else '')
    # 元素热区
    n_eh = len(re.findall(r'class="eh"', h))
    ck('元素热区数与数据源一致', n_eh == len(A['elements']),
       'html %d / json %d' % (n_eh, len(A['elements'])))

    # ---- 线上必须写出交互方式（用户要求：「连接线上要标注出交互方式」）
    # 只靠颜色/线型是不够的：单独看一条线的人读不出「这是弹窗还是跳转」，
    # 得回去对照图例才知道。所以胶囊里必须有交互方式的**文字**。
    pills = dict((m.group(1), m.group(2))
                 for m in re.finditer(r'<div class="lbl[^"]*" data-lk="(LK-\d+)"[^>]*>(.*?)</div>',
                                      h))
    want = dict((x['id'], x) for x in links if x.get('labelPos'))
    badpill = []
    for lid, lk in want.items():
        inner = pills.get(lid, '')
        act = A['actions'][lk['action']]['name']
        if ('>%s</b>' % act) not in inner:
            badpill.append('%s 线上没写交互方式，实得 %s' % (lid, inner[:40]))
        elif not lk.get('labelShort') and ('<i>%s</i>' % B.esc(lk['label'])) not in inner:
            badpill.append('%s 完整胶囊缺业务标签，实得 %s' % (lid, inner[:40]))
    ck('每个线上标签都写着交互方式（完整胶囊还带业务标签）', not badpill,
       ('%d 处：%s' % (len(badpill), badpill[:3])) if badpill else
       '%d 个标签都带交互方式文字' % len(want))
    ck('画布上的标签与数据源一一对应（不多不少）', set(pills) == set(want),
       '多 %s · 少 %s' % (sorted(set(pills) - set(want))[:4],
                          sorted(set(want) - set(pills))[:4]))


# ================================================================== 变异测试
def mutate():
    """两处变异，两处都必须变红。

    判别力在这里的意思很具体：如果「动了它」之后「不压卡片」还是全绿，
    那这条检查检验的就不是避让算法，而是别的什么（比如压根没算几何、或者矩形约定搞反了）。

    变异一 —— 图省事的画法：从元素边直接拉一条直线到目标（不绕任何东西）。
             这是最容易被写出来的实现，也是「遮挡原型」最经典的成因。
    变异二 —— 保留端点，但搜索时看不见障碍（等价于把卡片从地图上抹掉）。
     """
    sec('6 · 变异测试（同一套探针必须变红）')
    emap, pages, _t, _p = B.load()
    screens, placed, w, h = B.layout(emap, pages)
    cards = [dict(pid=s['pid'], vkey=s['vkey'], rect=[s['x'], s['y'], s['w'], s['h']])
             for s in screens]

    def report(tag, links):
        ok = [x for x in links if x.get('ok')]
        scrub, _bs, _be = geom(ok, cards)
        print('  %s：%d/%d 条成功 · %d 段 · 压卡 %d 处'
              % (tag, len(ok), len(links), sum(len(x['pts']) - 1 for x in ok), len(scrub)))
        ck('%s 必须出现压卡' % tag, len(scrub) > 0,
           ('压卡 %d 处，例如 %s' % (len(scrub), scrub[:3])) if scrub else '压卡 0 处 —— 本检查没有判别力')
        ck('%s 必须真的算出连线（否则是"没跑"而不是"跑了没压"）' % tag, len(ok) > 0,
           '%d 条' % len(ok))

    # ---- 变异一：直线连接
    orig_route = RT.Router.route

    def naive_route(self, elements):
        (ra, sa, _ca), (rb, sb, _cb) = elements
        p0, p1 = RT._edge_point(ra, sa), RT._edge_point(rb, sb)
        pts = RT._dedupe([p0, p1])
        return pts, [True] * max(0, len(pts) - 1)

    RT.Router.route = naive_route
    try:
        links1 = B.build_links(screens, pages)
    finally:
        RT.Router.route = orig_route
    report('变异一 直线连接', links1)

    # ---- 变异二：搜索时看不见障碍
    orig_raster = RT.Router._raster

    def free_raster(self, box):
        c = self.cell
        x0, y0, x1, y1 = box
        ix0, iy0 = int(x0 // c) - 1, int(y0 // c) - 1
        ix1, iy1 = int(x1 // c) + 1, int(y1 // c) + 1
        ww, hh = ix1 - ix0 + 1, iy1 - iy0 + 1
        return bytearray(ww * hh), ix0, iy0, ww, hh     # 全空：没有障碍

    RT.Router._raster = free_raster
    try:
        links2 = B.build_links(screens, pages)
    finally:
        RT.Router._raster = orig_raster
    report('变异二 抹掉障碍', links2)


# ================================================================== main
def run():
    A, EM, PR = context()
    print('=' * 68)
    print('05-annotation 校验 · 交互标注')
    print('=' * 68)
    check_structure(A, EM, PR)
    check_box_convention(A)
    check_geom(A['links'], A['cards'])
    check_clearance(A)
    check_labels(A)
    check_stats(A)
    check_html(A)
    mutate()

    print('\n' + '=' * 68)
    if WARN:
        for w in WARN:
            print('  [提示] %s' % w)
    if FAIL:
        print('  [未通过] %d 项：' % len(FAIL))
        for f in FAIL:
            print('    - %s' % f)
        print('=' * 68)
        sys.exit(1)
    print('  [全部通过]')
    print('=' * 68)


if __name__ == '__main__':
    run()
