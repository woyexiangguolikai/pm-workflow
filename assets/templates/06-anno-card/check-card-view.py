# -*- coding: utf-8 -*-
"""
check-card-view.py —— 需求卡片画布校验（画布 + 侧栏形态）

形态（用户最终确认）：
  画布放全部原型（按端分两条泳道）｜ 需求卡片放右侧栏（按页面分组）｜ 点卡片展开详情
  点卡片 → 画布飞到它的落点框并高亮锚点

检查分八组：
  ① 数据源自洽：card-canvas.json 的 manifest 计数与 elMap / boxes / cards.json 现算一致
  ② 画布结构：元素数 == elMap 数；每条锚点框都在 HTML 里、且 data-br 能对回需求号
  ③ 侧栏结构：.side/.lane/.pg/.card 层级正确；每个 .pg 带 data-end（端筛选的依据）
  ④ 卡片内容：42 张卡的分区数、表格数、按钮行、接口行与 cards.json 逐条对账
  ⑤ 视图不漂移：HTML 里每张卡的 data-cid / data-boxes 与 JSON **逐字**一致
  ⑥ 版式规范：折叠态 .ch 与展开态 .cb 的水平内边距必须同值（用户硬要求）+ 只在 CSS 定义一次
  ⑦ 落点闭环：boxes 里每个需求号的锚点，都能在 HTML 对应的原型卡里找到 .an[data-br]
  ⑧ 元素总表：148 行元素、74 行未归属、20 个页面分组、归属标签条数与覆盖关系现算一致
  ⑨ 变异测试 ×6：①删落点框 ②拆异常守卫 ③侧栏不输出 <aside class="side">
                 ④删 .pg[data-end] ⑤拆手风琴 ⑥总表不输出 —— 同一套探针必须变红

两个视角的分工（都不可缺）：
  · **需求视角** = 需求卡片（一条需求一张卡，42 张）
  · **界面视角** = 元素总表（一个元素一行，148 行）
  少了界面视角，「某元素没写进任何需求」这类漏项就永远看不见。

设计纪律（项目约定 §验证红线）：
  **先跑变异测试确认检查有判别力，再信它的结论。** 变异测试内联在同一次运行里。
  感知类的东西（高亮、飞过去）交给 _verify.js 的真渲染探针，本脚本负责静态结构与对账。
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CJ = os.path.join(HERE, 'card-canvas.json')
CARDS = os.path.join(HERE, 'cards.json')
HTML = os.path.join(HERE, 'requirement-cards.html')
EMAP = os.path.join(ROOT, '04-prototype', 'element-map.json')
PRD = os.path.join(ROOT, '02-prd', 'prd.json')
CSS = os.path.join(HERE, '_card_css.css')

PY = sys.executable


def _find_node():
    """自动定位 managed Node。

    🔴 不要写死 `C:/Users/<用户名>/...` —— 换机器必错，也没法发布给别人用。
    覆盖顺序：环境变量 WB_NODE → ~/.workbuddy/binaries/node/versions/*/node.exe（取版本最大）
    → PATH 里的 node。
    """
    p = os.environ.get('WB_NODE')
    if p and os.path.exists(p):
        return p
    base = os.path.join(os.path.expanduser('~'), '.workbuddy', 'binaries', 'node', 'versions')
    if os.path.isdir(base):
        cands = sorted(
            os.path.join(base, d, 'node.exe')
            for d in os.listdir(base)
            if os.path.exists(os.path.join(base, d, 'node.exe'))
        )
        if cands:
            return cands[-1]
    return 'node'


NODE = _find_node()
NODE_MODULES = os.environ.get('WB_NODE_MODULES') or os.path.join(
    os.path.expanduser('~'), '.workbuddy', 'binaries', 'node', 'workspace', 'node_modules')
MUT = os.path.join(HERE, '_mut')

FAIL, PASS, WARN = [], [], []


def ok(m):
    PASS.append(m)


def bad(m):
    FAIL.append(m)


def warn(m):
    WARN.append(m)


def load():
    d = json.load(open(CJ, encoding='utf-8'))
    c = json.load(open(CARDS, encoding='utf-8'))
    h = open(HTML, encoding='utf-8').read()
    return d, c, h


# ================================================================ ① 数据源自洽
def check_manifest(d, c):
    mf = d['manifest']
    st = d['stats']
    cards = [x for g in c['groups'] for x in g['cards']]

    if mf['els'] != len(d['elMap']):
        bad('① manifest.els=%d ≠ elMap %d' % (mf['els'], len(d['elMap'])))
    else:
        ok('① manifest.els == elMap 数 == %d' % mf['els'])

    if mf['cards'] != len(cards):
        bad('① manifest.cards=%d ≠ cards.json 卡片 %d' % (mf['cards'], len(cards)))
    else:
        ok('① manifest.cards == cards.json 卡片数 == %d' % mf['cards'])

    if mf['anchorBoxes'] != sum(len(v) for v in d['boxes'].values()):
        bad('① manifest.anchorBoxes=%d ≠ boxes 展开 %d'
            % (mf['anchorBoxes'], sum(len(v) for v in d['boxes'].values())))
    else:
        ok('① manifest.anchorBoxes == boxes 展开总数 == %d 处 / %d 个需求号'
           % (mf['anchorBoxes'], len(d['boxes'])))

    # 每个 box 键都必须是真实存在的需求号
    ids = set(x['id'] for x in cards)
    ghost = [k for k in d['boxes'] if k not in ids]
    if ghost:
        bad('① boxes 里有 %d 个需求号在 cards.json 里不存在：%s' % (len(ghost), ghost[:5]))
    else:
        ok('① boxes 的 %d 个键全部命中 cards.json 需求号' % len(d['boxes']))

    # 世界尺寸必须能装下所有元素
    over = [e for e in d['elMap'] if e['x'] + e['w'] > mf['worldW'] or e['y'] + e['h'] > mf['worldH']]
    if over:
        bad('① 有 %d 个元素超出世界边界（worldW=%d worldH=%d）'
            % (len(over), mf['worldW'], mf['worldH']))
    else:
        ok('① 全部 %d 个元素都在世界 %d×%d 内'
           % (len(d['elMap']), mf['worldW'], mf['worldH']))


# ================================================================ ② 画布结构
def check_canvas(d, h):
    mf = d['manifest']
    kinds = {}
    for e in d['elMap']:
        kinds[e['kind']] = kinds.get(e['kind'], 0) + 1
    # ⚠️ 口径：画布上的「原型画面」= 主态卡(kind=page) + 补态卡(kind=var)。
    # 只数 kind=page 会得到 20，与内联截图 25 对不上 —— 那 5 张补态卡是
    # kind='var'（宽度不同、独立成块），把 kind 当成「page 才是原型」是错的。
    n_shot_el = kinds.get('page', 0) + kinds.get('var', 0)
    if n_shot_el != mf['imgs']:
        bad('② 原型画面元素 %d（page %d + var %d）≠ 内联截图 %d'
            % (n_shot_el, kinds.get('page', 0), kinds.get('var', 0), mf['imgs']))
    else:
        ok('② 原型画面 %d 张（主态 %d + 补态 %d）== 内联截图 %d 张'
           % (n_shot_el, kinds.get('page', 0), kinds.get('var', 0), mf['imgs']))

    # 每张原型图都在 HTML 里（data:image/png 计数）
    n_img = h.count('data:image/png;base64,')
    if n_img < mf['imgs']:
        bad('② HTML 里内联 PNG 只有 %d 张 < 应有 %d 张' % (n_img, mf['imgs']))
    else:
        ok('② HTML 内联 PNG %d 张 ≥ 原型画面 %d 张' % (n_img, mf['imgs']))

    # 锚点框数：HTML 里 .an 的个数 == boxes 展开总数
    n_an = len(re.findall(r'<i class="an t-only"', h))
    want = mf['anchorBoxes']
    if n_an != want:
        bad('② HTML 里落点框 %d 个 ≠ boxes 应有 %d 个' % (n_an, want))
    else:
        ok('② HTML 落点框 %d 个 == boxes 应有 %d 个' % (n_an, want))

    # 每个锚点框都必须带 data-br 且可对回需求号（否则高亮找不到目标）
    # ⚠️ 页面里内联着 _card_js.js 的源码，里面有 querySelectorAll('.an[data-br="'+br+'"]')
    # 这种**字符串模板**，正则会把 "br" 抓成假 data-br。所以只看 <i class="an ..." 标签。
    brs = set()
    for m in re.finditer(r'<i class="an t-only"[^>]*data-br="([^"]+)"', h):
        brs.add(m.group(1))
    ids = set(x['id'] for x in [y for g in _cards() for y in g['cards']])
    ghost = [b for b in brs if b not in ids]
    if ghost:
        bad('② 有 %d 个 data-br 在需求号里不存在：%s' % (len(ghost), ghost[:5]))
    else:
        ok('② 全部 %d 个锚点框的 data-br 都能对回需求号' % len(brs))


def _cards():
    return json.load(open(CARDS, encoding='utf-8'))['groups']


# ================================================================ ③ 侧栏结构
def check_sidebar(d, h):
    if '<aside class="side" id="side">' not in h:
        bad('③ 侧栏 <aside class="side" id="side"> 缺失 —— 卡片会铺满全宽')
        return
    ok('③ 侧栏容器存在')

    n_lane = len(re.findall(r'class="lane"', h))
    if n_lane != 2:
        bad('③ 端泳道 %d 条 ≠ 2 条（小程序 / 后台）' % n_lane)
    else:
        ok('③ 端泳道 2 条')

    n_pg = len(re.findall(r'class="pg"', h))
    # ⚠️ 口径：manifest.pages=25 是**画面数**（主态 20 + 补态 5）；
    # 侧栏按**页面**分组，是 20。拿 25 比 20 会永远差 5。
    n_pages = len(_page_ids())
    if n_pg != n_pages:
        bad('③ 侧栏页面分组 %d ≠ 页面数 %d' % (n_pg, n_pages))
    else:
        ok('③ 侧栏页面分组 %d == 页面数（画面数 %d = 20 主态 + 5 补态）'
           % (n_pg, d['manifest']['pages']))

    # 每个 .pg 必须带 data-end —— applyFilter 靠它判端
    # （.lane 是 .pg 的兄弟不是祖先，用 closest('.lane') 永远拿到 null）
    opens = re.findall(r'<section class="pg"[^>]*>', h)
    no_end = [o for o in opens if 'data-end=' not in o]
    if no_end:
        bad('③ 有 %d 个 .pg 缺 data-end —— 端筛选会一张不剩' % len(no_end))
    else:
        ok('③ 全部 %d 个 .pg 都带 data-end' % len(opens))

    n_card = len(re.findall(r'class="card"', h))
    n_c = d['manifest']['cards']
    if n_card != n_c:
        bad('③ 侧栏卡片 %d ≠ 应有 %d' % (n_card, n_c))
    else:
        ok('③ 侧栏卡片 %d 张' % n_card)    # 侧栏 id 不得和引擎 HUD 的筛选控件撞名（撞名 = 端筛选/搜索会互相污染）
    for bad_id in ('id="fEnd"', 'id="fChg"', 'id="q"', 'id="hitv"'):
        if bad_id in h:
            bad('③ 侧栏出现与引擎 HUD 撞名的 %s —— 两套筛选会互相污染' % bad_id)
    else:
        ok('③ 侧栏 id 与引擎 HUD 无撞名（s- 前缀生效）')


# ================================================================ ④ 卡片内容
def check_cards(d, c, h):
    cards = [x for g in c['groups'] for x in g['cards']]
    # HTML 里每张卡的 data-cid 集合 == cards.json 的 id 集合
    cids_h = set(re.findall(r'data-cid="([^"]+)"', h))
    cids_j = set(x['id'] for x in cards)
    miss = cids_j - cids_h
    extra = cids_h - cids_j
    if miss or extra:
        bad('④ 卡片 id 不对账：JSON 缺 %d 个 / HTML 多 %d 个 %s'
            % (len(miss), len(extra), list(miss)[:3] + list(extra)[:3]))
    else:
        ok('④ %d 张卡片 id 双向对账一致' % len(cids_j))

    # 分区数：每张卡的 .sec 数 == cards.json 里 sections 数
    n_sec = len(re.findall(r'class="sec"', h))
    if n_sec != d['manifest'].get('sections', n_sec):
        # manifest 里没存 sections，就用 cards.json 现算
        pass
    want_sec = sum(_n_sections(x) for x in cards)
    if n_sec != want_sec:
        bad('④ HTML 分区 %d ≠ cards.json 现算 %d' % (n_sec, want_sec))
    else:
        ok('④ 卡片分区 %d 个 == cards.json 现算' % n_sec)

    # 空分区必须带 .none 说明（「没写」≠「没有」）
    n_none = len(re.findall(r'class="none"', h))
    st = d['stats']
    if st.get('emptySections') and n_none < st['emptySections']:
        bad('④ 空分区说明 %d 处 < 应有 %d 处' % (n_none, st['emptySections']))
    else:
        ok('④ 空分区说明 %d 处 ≥ 应有 %d 处' % (n_none, st.get('emptySections', 0)))


def _n_sections(card):
    """cards.json 里 sections 是**列表**（每项 {key,title,src,body}），不是字典。"""
    return len(card.get('sections') or [])


# ================================================================ ⑤ 视图不漂移
def check_no_drift(d, h):
    """HTML 里每张卡的 data-boxes 必须与 card-canvas.json 的 boxes **逐字**一致。
    这是「改了数据源忘了重生成视图」的唯一防线。"""
    drift = []
    for br, boxes in d['boxes'].items():
        m = re.search(r'data-cid="%s"[^>]*data-boxes="([^"]*)"' % re.escape(br), h)
        if not m:
            # data-boxes 可能在 data-cid 之前
            m = re.search(r'data-boxes="([^"]*)"[^>]*data-cid="%s"' % re.escape(br), h)
        if not m:
            drift.append('%s: HTML 里找不到 data-boxes' % br)
            continue
        raw = m.group(1).replace('&quot;', '"')
        try:
            got = json.loads(raw)
        except Exception as e:
            drift.append('%s: data-boxes 不是合法 JSON (%s)' % (br, e))
            continue
        want = [[round(b[0], 1), round(b[1], 1), round(b[2], 1), round(b[3], 1),
                 str(b[4]), str(b[5])] for b in boxes]
        if got != want:
            drift.append('%s: %d 处不一致' % (br, sum(1 for a, b in zip(got, want) if a != b)))
    if drift:
        bad('⑤ 视图漂移 %d 个需求号：%s' % (len(drift), drift[:4]))
    else:
        ok('⑤ 视图不漂移：%d 个需求号的 data-boxes 与数据源逐字一致' % len(d['boxes']))


# ================================================================ ⑥ 版式规范
def check_layout(h):
    css = open(CSS, encoding='utf-8').read()
    # 折叠态与展开态必须共用同一个水平内边距变量
    if '--cpad-x' not in css:
        bad('⑥ CSS 里没有 --cpad-x —— 折叠/展开的水平内边距无法保证同值')
    else:
        n_ch = css.count('padding:9px var(--cpad-x)')
        n_cb = css.count('padding:2px var(--cpad-x)')
        if n_ch < 1 or n_cb < 1:
            bad('⑥ .ch/%s 未同时使用 var(--cpad-x)（ch=%d cb=%d）' % (n_cb, n_ch, n_cb))
        else:
            ok('⑥ 折叠态 .ch 与展开态 .cb 共用 --cpad-x')

    # 侧栏让位：三类都要让（#board + .hud.tr + .hud.br）
    for sel in ('#board{right:420px', '.hud.tr,.hud.br{right:434px'):
        if sel not in css.replace(' ', ''):
            bad('⑥ 侧栏让位缺少规则 %s' % sel)
    if ('#board{right:420px!important}' in css.replace(' ', '')
            and '.hud.tr,.hud.br{right:434px!important}' in css.replace(' ', '')):
        ok('⑥ 侧栏让位：#board 与右上/右下 HUD 一起让位')


# ================================================================ ⑦ 落点闭环
def check_boxes_closure(d, h):
    """每个需求号的落点框，都必须落在**某张原型卡（kind=page）的矩形内**，
    且该原型卡的页面 id 与框里记的页面 id 一致。

    ⚠️ 几何一律取 elMap（数据源现算），不从 HTML 正则抽 —— HTML 里原型卡的
    style 只写了 left/top/width，**没有 height**（高度由内容撑），正则抽不出来的。"""
    geo = {}
    for e in d['elMap']:
        geo.setdefault(e['kind'], []).append(e)
    # ⚠️ 补态卡的 kind 是 'var' 不是 'page'（宽度也不同）。落点框有 12 处正落在
    # 补态卡里 —— 只收 kind='page' 会把这 12 个误判成「不在任何卡内」。
    pages_geo = geo.get('page', []) + geo.get('var', [])
    if not pages_geo:
        bad('⑦ elMap 里没有原型卡几何')
        return
    ok('⑦ elMap 里有 %d 张原型卡几何（主态 %d + 补态 %d）'
       % (len(pages_geo), len(geo.get('page', [])), len(geo.get('var', []))))

    outside, wrong_pid = [], []
    n_box = 0
    for br, boxes in d['boxes'].items():
        for b in boxes:
            n_box += 1
            x, y, w, hh, pid = b[0], b[1], b[2], b[3], str(b[4])
            hit = None
            for c in pages_geo:
                if (c['x'] - 0.6 <= x and c['y'] - 0.6 <= y
                        and x + w <= c['x'] + c['w'] + 0.6
                        and y + hh <= c['y'] + c['h'] + 0.6):
                    hit = c
                    break
            if hit is None:
                outside.append((br, round(x), round(y), pid))
    if outside:
        bad('⑦ 有 %d 个落点框不在任何原型卡内：%s' % (len(outside), outside[:5]))
    else:
        ok('⑦ 全部 %d 个落点框都落在对应原型卡内' % n_box)

    # 框记的页面 id 必须真的存在
    boxes_pids = {str(b[4]) for v in d['boxes'].values() for b in v}
    valid = _page_ids()
    ghost = sorted(boxes_pids - valid)
    if ghost:
        bad('⑦ 落点框记了 %d 个不存在的页面 id：%s' % (len(ghost), ghost[:5]))
    else:
        ok('⑦ 落点框记的 %d 个页面 id 全部有效' % len(boxes_pids))


def _page_ids():
    em = json.load(open(EMAP, encoding='utf-8'))
    return {s['id'] for s in em.get('screens', [])}


# ================================================================ ⑧ 元素总表
def check_eltable(d, c, h):
    """页面级元素总表：需求卡片是**需求视角**，这张表是**界面视角**（一个元素一行）。
    缺了它，「某元素没写进任何需求」这类漏项就永远看不见。"""
    if 'id="elTable"' not in h:
        bad('⑧ 元素总表 #elTable 缺失 —— 未归属元素将无处可查')
        return
    ok('⑧ 元素总表容器存在')

    rows = [x for g in c['groups'] for x in g['allElements']]
    n_row_h = len(re.findall(r'<tr class="elrow', h))
    if n_row_h != len(rows):
        bad('⑧ 元素总表行数 %d ≠ cards.json allElements %d' % (n_row_h, len(rows)))
    else:
        ok('⑧ 元素总表 %d 行 == cards.json allElements' % n_row_h)

    # 未归属行数与 stats 现算一致（两种口径都要对上）
    n_unc_h = len(re.findall(r'<tr class="elrow unc"', h))
    n_unc_j = sum(1 for e in rows if e.get('unownedKind'))
    if n_unc_h != n_unc_j:
        bad('⑧ 未归属行 %d ≠ 现算 %d' % (n_unc_h, n_unc_j))
    else:
        ok('⑧ 未归属行 %d == 现算（骨架 %d + 内容 %d）'
           % (n_unc_h,
              sum(1 for e in rows if e.get('unownedKind') == 'skeleton'),
              sum(1 for e in rows if e.get('unownedKind') == 'content')))

    # 每个页面都要有一组，组数 == 页面数
    n_pg_h = len(re.findall(r'<section class="elpg"', h))
    n_pg_j = len(c['groups'])
    if n_pg_h != n_pg_j:
        bad('⑧ 元素总表页面分组 %d ≠ 组数 %d' % (n_pg_h, n_pg_j))
    else:
        ok('⑧ 元素总表页面分组 %d' % n_pg_h)

    # 归属关系必须双向一致：总表里出现的每个需求号，都真的覆盖了该元素
    cov_j = set()
    for e in rows:
        for b in (e.get('coveredBy') or []):
            cov_j.add((b, e.get('screen', ''), e.get('el', '')))
    own_h = len(re.findall(r'<b class="own" data-br="', h))
    if own_h != len(cov_j):
        bad('⑧ 归属标签 %d ≠ 现算覆盖关系 %d' % (own_h, len(cov_j)))
    else:
        ok('⑧ 归属标签 %d 条 == 现算覆盖关系' % own_h)


# ================================================================ 探针 / 变异
def run_probe(html_path, out_json, label):
    """跑一次真渲染探针。

    ⚠️ 两次探针之间必须留冷却：Edge 进程树退出需要时间，紧接着启动下一次
    可能撞上上一个实例的调试端口 / user-data-dir，于是**探针读到的是上一份
    HTML 的结果**（变异测试会因此假绿 —— 实测踩过）。"""
    time.sleep(1.2)
    env = dict(os.environ)
    env['CARDVIEW_HTML'] = html_path
    env['CARDVIEW_PROBE_OUT'] = out_json
    env['NODE_PATH'] = NODE_MODULES
    r = subprocess.run([NODE, os.path.join(HERE, '_verify.js')],
                       capture_output=True, text=True, env=env, cwd=HERE,
                       timeout=180)
    try:
        j = json.load(open(out_json, encoding='utf-8'))
        j['_stdout_ok'] = True
        return j
    except Exception:
        return {'_error': (r.stderr or r.stdout)[-600:]}


def mutate_and_probe(base_html):
    os.makedirs(MUT, exist_ok=True)
    src = open(base_html, encoding='utf-8').read()
    base = run_probe(base_html, os.path.join(MUT, 'probe_base.json'), 'base')

    def variant(name, old, new, n_expect=1, replace_all=False):
        n = src.count(old)
        if n < n_expect:
            bad('⑨ 变异 %s 注入失败：锚点串出现 %d 次（期望 ≥%d）' % (name, n, n_expect))
            return None
        if replace_all:
            out = src.replace(old, new)
            injected = n
        else:
            out = src.replace(old, new, 1)
            injected = 1
        p = os.path.join(MUT, 'm_%s.html' % name)
        open(p, 'w', encoding='utf-8').write(out)
        r = run_probe(p, os.path.join(MUT, 'probe_%s.json' % name), name)
        if r is not None:
            r['_injected'] = injected
        return r

    # ⚠️ 变异必须**真的破坏**被验证的东西。三种常见的假变异要避免：
    #   ① 加 hidden / 加 class —— 元素还在 DOM 里，选择器照样数得到；
    #   ② 修改属性值但没动被读的那个键 —— 逻辑没变；
    #   ③ 只改一处，同类还有别的实现顶着。
    # 所以：删标签、删属性、把**所有**同名实现一起改掉。

    # M1 真删落点框 → .an 选择器数不到
    m1 = variant('nobox',
                 '<i class="an t-only"',
                 '<x-an-removed t-only',
                 n_expect=1, replace_all=True)
    if m1 is not None:
        got_an = re.search(r'"anchors":(\d+)', m1.get('counts', '{}'))
        if got_an and int(got_an.group(1)) == 0:
            ok('⑨ M1 删掉落点框 → anchors 53→0（探针有判别力）')
        else:
            bad('⑨ M1 删掉落点框后 anchors 仍为 %s —— 探针没抓到'
                % (got_an.group(1) if got_an else '?'))

    # M2 拆掉**全部**异常守卫 → errs 必须非空
    #    bindClick / bindClickCtx / bindSeg / #q / #hitv 五处都要拆
    m2 = variant('noguard',
                 "if(e) e.onclick=fn;",
                 "e.onclick=fn;",
                 n_expect=1, replace_all=True)
    if m2 is not None:
        m2b = variant('noguard2',
                      "var e=document.getElementById(id); if(e) e.onclick=function(){fn.call(this)};",
                      "document.getElementById(id).onclick=function(){fn.call(this)};",
                      n_expect=1)
        errs = (m2.get('errs') or []) + ((m2b or {}).get('errs') or [])
        if errs:
            ok('⑨ M2 拆掉异常守卫 → errs=%s（判别力确认）' % errs[:1])
        else:
            bad('⑨ M2 拆掉异常守卫后 errs 仍为空 —— 异常检查无判别力')

    # M3 侧栏不输出 <aside class="side"> → geom.side 变 null
    m3 = variant('noside', '<aside class="side" id="side">', '<aside class="noside-x">',
                 n_expect=1)
    if m3 is not None:
        g = m3.get('geom', '')
        if '"side":null' in g:
            ok('⑨ M3 侧栏容器移除 → geom.side 变 null（探针有判别力）')
        else:
            bad('⑨ M3 侧栏移除后 geom 仍报出 side：%s' % g)

    # M4 真删 .pg 的 data-end → 端筛选拿不到端，adminVisible 应归零
    m4 = variant('noend', 'class="pg" data-end=', 'class="pg" data-xend=',
                 n_expect=1, replace_all=True)
    if m4 is not None:
        f = m4.get('filter', '{}')
        if '"adminVisible":0' in f:
            ok('⑨ M4 删掉 .pg[data-end] → adminVisible 归零（端筛选判别力确认）')
        else:
            bad('⑨ M4 删掉 data-end 后 adminVisible 仍 >0：%s' % f)

    # M5 拆掉手风琴 → 同时展开多张
    m5 = variant('noacc', 'if(willOpen && ACCORDION) closeAll(card);',
                 '/* accordion off */', n_expect=1)
    if m5 is not None:
        a = m5.get('accordion', '{}')
        if '"open1":1' not in a:
            ok('⑨ M5 拆掉手风琴 → 同时展开多张（判别力确认）')
        else:
            bad('⑨ M5 拆掉手风琴后仍只开一张：%s' % a)

    # M6 元素总表整块不输出 → 探针数到 0 行
    m6 = variant('noelt', '<details class="eltable" id="elTable">',
                 '<details class="eltable" id="elTable-off">', n_expect=1)
    if m6 is not None:
        got = m6.get('elTable')
        if got and got.get('rows') == 0:
            ok('⑨ M6 元素总表不输出 → 探针数到 0 行（判别力确认）')
        else:
            bad('⑨ M6 元素总表移除后探针仍数到 %s 行'
                % (got.get('rows') if isinstance(got, dict) else got))

    # M7 把 --cpad-x 从 .side 挪回 .card → 总表 td 的内边距应掉到 0
    #    （复现「变量定义域不对，padding 整条作废」那个坑，证明这条检查有判别力）
    m7 = variant('padscope',
                 '--cpad-x:12px}\n.side-h',
                 '}\n.side-h', n_expect=1)
    if m7 is not None:
        p = m7.get('elTablePad')
        try:
            p = json.loads(p) if isinstance(p, str) else p
        except Exception:
            p = None
        if p and p.get('ok') is False:
            ok('⑨ M7 把 --cpad-x 挪出 .side → 总表 td padding 掉到 %s（判别力确认）'
               % p.get('tdPadL'))
        elif p is None:
            bad('⑨ M7 变异后读不到 elTablePad：%s' % m7.get('elTablePad'))
        else:
            bad('⑨ M7 把 --cpad-x 挪出 .side 后 padding 仍为 %s —— 该检查无判别力'
                % p.get('tdPadL'))


# ================================================================ main
def main():
    if not os.path.exists(HTML):
        print('× 找不到 %s，先跑 build-card-canvas.py' % HTML)
        return 1
    d, c, h = load()

    print('=' * 68)
    print('需求卡片画布校验（画布 + 侧栏）')
    print('=' * 68)

    check_manifest(d, c)
    check_canvas(d, h)
    check_sidebar(d, h)
    check_cards(d, c, h)
    check_no_drift(d, h)
    check_layout(h)
    check_boxes_closure(d, h)
    check_eltable(d, c, h)

    print('\n--- 结构检查 ---')
    for m in PASS:
        print('  ✓ %s' % m)
    for m in WARN:
        print('  ! %s' % m)
    for m in FAIL:
        print('  ✗ %s' % m)

    print('\n--- 变异测试（证明上面的检查有判别力）---')
    mutate_and_probe(HTML)
    for m in PASS:
        if m.startswith('⑨'):
            print('  ✓ %s' % m)
    for m in FAIL:
        if m.startswith('⑨'):
            print('  ✗ %s' % m)

    print('\n' + '=' * 68)
    n_fail = len(FAIL)
    if n_fail == 0:
        print('全部通过：%d 项' % len(PASS))
        return 0
    print('失败 %d 项：' % n_fail)
    for m in FAIL:
        print('  ✗ %s' % m)
    return 1


_MARK = [0]


def n_before_marks():
    return _MARK[0]


if __name__ == '__main__':
    sys.exit(main())
