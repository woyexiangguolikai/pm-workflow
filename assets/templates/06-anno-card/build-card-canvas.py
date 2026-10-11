# -*- coding: utf-8 -*-
"""
build-card-canvas.py —— 需求卡片画布 + 侧栏（自包含单文件 HTML）

形态
----
* **画布**（复用 04-prototype/_canvas_html.render 的白板引擎）：20 页原型铺在两条
  泳道（小程序一行、后台一行）上，滚轮缩放、拖拽平移，与 05-annotation 同一种白板。
* **右侧栏**：按页面分组的 42 张需求卡片，手风琴展开（开一张收其它）。
* **联动**：点侧栏卡片 → 画布飞到该需求的落点框并高亮；点画布上的落点框 →
  侧栏滚到对应卡片并展开。

不画任何连线（用户明确：不需要连接线，卡片替代）。
「这条需求落在哪块」靠**落点框**表达 —— 框的坐标是几何事实，来自
element-map.json 的锚点，不是手画的。
"""

import base64
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PROTO = os.path.join(ROOT, '04-prototype')
EMAP = os.path.join(PROTO, 'element-map.json')
CARDS = os.path.join(HERE, 'cards.json')
PRD = os.path.join(ROOT, '02-prd', 'prd.json')
CARD_CSS = os.path.join(HERE, '_card_css.css')
CARD_JS = os.path.join(HERE, '_card_js.js')
OUT_JSON = os.path.join(HERE, 'card-canvas.json')
OUT_HTML = os.path.join(HERE, 'requirement-cards.html')

sys.path.insert(0, PROTO)
import _canvas_html as CH          # noqa: E402


def _load_build_canvas():
    """分组定义只在 04-prototype/build-canvas.py 里写一份。抄过来的话，
    将来在那边加一页这边就悄悄少一块 —— 而画面上只是「少了个卡片」，
    没人会觉得是 bug。"""
    spec = importlib.util.spec_from_file_location(
        'bc_groups', os.path.join(PROTO, 'build-canvas.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BC = _load_build_canvas()
GROUPS = BC.GROUPS
END_LABEL = BC.END_LABEL
END_NOTE = BC.END_NOTE

CARD_W = BC.CARD_W
ADMIN_CARD_W = BC.ADMIN_CARD_W
VAR_W = BC.VAR_W
VAR_GAP = BC.VAR_GAP
GAP = BC.GAP
GRP_GAP = BC.GRP_GAP
BAND_GAP = BC.BAND_GAP
LABEL_H = BC.LABEL_H
GLAB_H = BC.GLAB_H
DOC_TOP_H = BC.DOC_TOP_H
BOT_PAD = BC.BOT_PAD
HEAD_H = BC.HEAD_H
FOOT_H = BC.FOOT_H
CARD_W_BY_END = BC.CARD_W_BY_END


def esc(s):
    if s is None:
        return ''
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def escq(s):
    return esc(s).replace('"', '&quot;')


def b64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')


def load():
    emap = json.load(open(EMAP, encoding='utf-8'))
    cards_d = json.load(open(CARDS, encoding='utf-8'))
    prd = json.load(open(PRD, encoding='utf-8'))
    return emap, cards_d, prd


def page_meta(emap, prd):
    """页面定义。⚠️ 页面 id（PG-A1…）只在 element-map.json 里有；
    prd.pages 是按端分组的列表、只有 name/path/requirements。
    所以 id 从 emap 取，其余属性从 prd 按 name 对上 —— 每类信息只有一个来源。"""
    br_prio = {x['id']: x.get('priority', '') for x in prd['requirements']}
    pm = {}
    for end in ('app', 'admin'):
        for x in prd.get('pages', {}).get(end, []):
            pm[x['name']] = dict(name=x['name'], path=x.get('path', ''),
                                 platform=end, change=x.get('change') or '改造',
                                 refs=x.get('requirements') or [])
    pages = {}
    for s in emap['screens']:
        if s['vkey'] != 'main' or s['id'] in pages:
            continue
        meta = pm.get(s['name'], {})
        pages[s['id']] = dict(
            id=s['id'], name=s['name'],
            path=meta.get('path') or s.get('path', ''),
            platform=s['platform'],
            change=meta.get('change', '改造'),
            refs=meta.get('refs') or [],
            prio_map=br_prio)
    return pages


# ---------------------------------------------------------------- 世界层
def shot_el(page, s, x, y, width, el_map):
    """一个截图 = 一个元素；锚点框按**页面百分比**定位，分母是图尺寸。"""
    img = s.get('img') or s['viewport']
    ih = round(width * img['h'] / img['w'], 1)
    h = round(HEAD_H + ih + FOOT_H, 1)
    is_var = s['vkey'] != 'main'
    chg = 'new' if page['change'] == '新增' else 'rework'
    badge = ('<span class="el-c c-var">补态</span>' if is_var
             else '<span class="el-c c-%s">%s</span>' % (chg, page['change']))
    title = ('%s · %s' % (page['id'], page['name'])) if not is_var \
        else ('%s · %s' % (page['id'], s['vname']))
    brs = ''.join('<span class="br%s">%s</span>'
                  % (' p0' if page['prio_map'].get(b) == 'P0' else '', b)
                  for b in page['refs'])
    annos = []
    for i, a in enumerate(s['anchors'], 1):
        annos.append('<i class="an t-only" data-i="%d" data-br="%s" data-anchor="%s" '
                     'style="left:%.3f%%;top:%.3f%%;width:%.3f%%;height:%.3f%%" '
                     'title="%s · %s"></i>'
                     % (i, escq(a['br']), escq(a['anchor']),
                        a['x'] / img['w'] * 100, a['y'] / img['h'] * 100,
                        a['w'] / img['w'] * 100, a['h'] / img['h'] * 100,
                        escq(a['br']), escq(a['anchor'])))
    el_map.append(dict(x=x, y=y, w=width, h=h, kind='var' if is_var else 'page'))
    return ('<div class="el page" data-id="%s" data-end="%s" data-vkey="%s" '
            'style="left:%.0fpx;top:%.0fpx;width:%dpx">'
            '<div class="el-h"><span class="el-ic"></span>'
            '<span class="el-t">%s</span>%s</div>'
            '<div class="el-img" style="height:%.1fpx">'
            '<img src="data:image/png;base64,%s" alt="%s" loading="lazy">%s</div>'
            '<div class="el-f">%s</div></div>'
            % (escq(page['id']), page['platform'], escq(s['vkey']),
               x, y, width, esc(title), badge, ih,
               b64(os.path.join(PROTO, s['shot'])), escq(title),
               ''.join(annos), brs)), h


# ---------------------------------------------------------------- 侧栏零件
def render_sec(s):
    """一个分区 → HTML。

    ⚠️ 每个分区的 body 里 row 的形状都不一样，逐 key 处理。早期版本用一套
    通用 read（r.get('source') / r.get('constraint')）去套所有分区，结果
    字段表整张渲染成「—」—— 数据源里根本没有这两个键名。
    形状必须对着 cards.json 一个个核，不能猜。
    """
    key = s['key']
    body = s.get('body') or []
    parts = []

    # ⚠️ ends 的 body 是**裸列表**（[{end,resp},…]），其余分区是
    # [{'sub':…, 'rows':[…]}]。统一成后者，后面就不用到处判形状了。
    # 这是把「猜形状」变成「先查形状再归一」—— 猜一次就会整张表渲染成「—」，
    # 而且画面上看不出是 bug。
    if body and isinstance(body[0], dict) and 'end' in body[0]:
        body = [{'rows': body}]

    for blk in body:
        sub = blk.get('sub')
        if sub:
            parts.append('<div class="sub">%s</div>' % esc(sub))
        rows = blk.get('rows') or []

        if key == 'ends':
            # ends 的 body 是**直接一个列表**（不是 {'rows': ...}）
            pass

        if key == 'buttons':
            if blk.get('buttons'):
                parts.append(''.join(
                    '<div class="btn-row"><b>%s</b><span class="tag">%s</span>'
                    '<span class="go">%s</span></div>'
                    % (esc(b.get('label') or '(无标签)'), esc(b.get('kindCn', '')),
                       esc(b.get('exit') or b.get('slotV', '') + ' · ' + b.get('slotH', '')))
                    for b in blk['buttons']))
            if blk.get('exits'):
                parts.append('<div class="sub">本条涉及的去向</div>')
                parts.append(''.join(
                    '<div class="exit"><b>%s</b> → %s<span class="tag">%s</span></div>'
                    % (esc(x.get('condition', '')), esc(x.get('page', '')),
                       esc(x.get('params') or '—'))
                    for x in blk['exits']))
            tot = blk.get('pageTotal')
            if tot:
                parts.append('<div class="note-line">本页共 %d 个交互元素；'
                             '其中 <b>%d</b> 个未被任何需求落点覆盖（骨架操作 %d · 内容缺口 %d）。'
                             '完整的页面级元素表见 06 的 <code>card-canvas.json</code>。</div>'
                             % (tot, len(blk.get('pageUnowned') or []),
                                sum(1 for e in (blk.get('pageUnowned') or [])
                                    if e.get('unownedKind') == 'skeleton'),
                                sum(1 for e in (blk.get('pageUnowned') or [])
                                    if e.get('unownedKind') == 'content')))
        elif key == 'trigger' and rows and 'scene' in rows[0]:
            # 异常与分支：{scene, handling}
            parts.append('<table class="ft"><thead><tr>'
                         '<th>场景</th><th>怎么处理</th></tr></thead><tbody>'
                         + ''.join('<tr><td><b>%s</b></td><td>%s</td></tr>'
                                   % (esc(r.get('scene', '')), esc(r.get('handling', '')))
                                   for r in rows)
                         + '</tbody></table>')
        elif key == 'fields':
            if rows and 'where' in rows[0]:
                parts.append('<table class="ft"><thead><tr>'
                             '<th>位置</th><th>字段</th><th>展示格式</th>'
                             '<th>脱敏</th><th>取不到时</th></tr></thead><tbody>'
                             + ''.join(
                                 '<tr><td>%s</td><td><b>%s</b> %s</td><td>%s</td>'
                                 '<td>%s</td><td>%s</td></tr>'
                                 % (esc(r.get('where', '')), esc(r.get('name', '')),
                                    esc(r.get('field', '')), esc(r.get('fmt', '—')),
                                    esc(r.get('mask', '—')), esc(r.get('empty', '—')))
                                 for r in rows)
                             + '</tbody></table>')
            elif rows and 'item' in rows[0]:
                parts.append('<table class="ft"><thead><tr>'
                             '<th>字段</th><th>来源</th><th>口径 / 兜底</th></tr></thead><tbody>'
                             + ''.join(
                                 '<tr><td><b>%s</b></td><td>%s%s</td><td>%s</td></tr>'
                                 % (esc(r.get('item', '')),
                                    esc(r.get('source', '')),
                                    ('<span class="tag">%s</span>' % esc(r.get('mode', '')))
                                    if r.get('mode') else '',
                                    esc(r.get('fallback', '—')))
                                 for r in rows)
                             + '</tbody></table>')
        elif key in ('rules', 'accept'):
            if rows:
                parts.append('<ul class="ul %s">%s</ul>'
                             % ('ul-acc' if key == 'accept' else 'ul-rule',
                                ''.join('<li>%s</li>' % esc(r.get('v', '')) for r in rows)))
        elif key == 'flow':
            if rows:
                parts.append('<table class="ft"><thead><tr>'
                             '<th>执行方</th><th>做什么</th><th>说明</th></tr></thead><tbody>'
                             + ''.join(
                                 '<tr><td><b>%s</b></td><td>%s</td><td>%s</td></tr>'
                                 % (esc(r.get('actor', '')), esc(r.get('action', '')),
                                    esc(r.get('note', '') or '—'))
                                 for r in rows)
                             + '</tbody></table>')
        elif key == 'dbfields':
            if rows:
                parts.append(''.join(
                    '<div class="kv"><span class="k">%s</span>'
                    '<span class="v"><code>%s</code> %s<br>%s</span></div>'
                    % (esc(r.get('business', '')), esc(r.get('column', '')),
                       esc(r.get('type', '')), esc(r.get('desc', '')))
                    for r in rows))
        elif key == 'apis':
            if rows:
                parts.append(''.join(
                    '<div class="api"><span class="own %s">%s</span>'
                    '<b>%s</b><span class="note">%s</span></div>'
                    % ('w' if r.get('own') else 'e', '我方' if r.get('own') else '甲方',
                       esc(r.get('name', '')), esc(r.get('business', '')))
                    for r in rows))
        else:
            # ends / interact / trigger / io / perm / pre / stateLink
            # 形状：{'end','resp'} 或 {'k','v'}
            for r in rows:
                if r.get('end'):
                    parts.append('<div class="kv"><span class="k">%s</span>'
                                 '<span class="v">%s</span></div>'
                                 % (esc(r.get('end', '')), esc(r.get('resp', ''))))
                elif r.get('k'):
                    parts.append('<div class="kv"><span class="k">%s</span>'
                                 '<span class="v">%s</span></div>'
                                 % (esc(r.get('k', '')), esc(r.get('v', ''))))
                elif r.get('v'):
                    parts.append('<div class="pp">%s</div>' % esc(r.get('v', '')))
    if not parts:
        return '<div class="none">%s</div>' % esc(s.get('empty') or '—')
    return ''.join(parts)



def card_html(c, gkey, anchors_by_br):
    chips = []
    for k, cn in (('fields', '字段'), ('buttons', '按钮'),
                  ('exits', '跳转'), ('apis', '接口'), ('inputs', '输入')):
        v = c['counts'].get(k)
        if v:
            chips.append('<span class="chip">%s <b>%d</b></span>' % (cn, v))
    secs = []
    for s in c['sections']:
        if not s.get('body') and not s.get('empty'):
            continue
        secs.append('<div class="sec" data-sec="%s">'
                    '<div class="st">%s<span class="src">%s</span></div>'
                    '<div class="sb">%s</div></div>'
                    % (escq(s['key']), esc(s['title']), esc(s.get('src', '')),
                       render_sec(s)))
    # 落点框 id：card-canvas.json 里给每个需求号算了框的 world 坐标
    lds = anchors_by_br.get(c['id']) or []
    # 框是 [x, y, w, h, 页面id, 状态key]：前四个是数、后两个是串，
    # 不能统一 round。分开序列化。
    boxes_json = json.dumps(
        [[round(b[0], 1), round(b[1], 1), round(b[2], 1), round(b[3], 1),
          str(b[4]), str(b[5])] for b in lds], ensure_ascii=False)
    return ('<article class="card" id="card-%s" data-cid="%s" data-g="%s" '
            'data-br="%s" data-boxes="%s">'
            '<header class="ch">'
            '<span class="cid">%s</span><h3 class="ct">%s</h3>'
            '<span class="cpri %s">%s</span><span class="caret"></span></header>'
            '<div class="cb" hidden>'
            '<p class="cdesc">%s</p>'
            '<div class="cmeta">%s</div>%s</div></article>'
            % (escq(c['id']), escq(c['id']), escq(gkey), escq(c['id']),
               escq(boxes_json),
               esc(c['id']), esc(c['title']),
               'p0' if c['priority'] == 'P0' else 'p1', esc(c['priority']),
               esc(c['description'] or ''),
               ''.join(chips), ''.join(secs)))


def eltable_html(cards_d, el_box, pid_of):
    """页面级元素总表。

    这张表回答「页面上的每个交互点，被哪条需求管着」——需求卡片是**需求视角**
    （一条需求一张卡），这张表是**界面视角**（一个元素一行）。两个视角都要有，
    否则「某元素没写进任何需求」这类漏项永远看不见。

    ⚠️ 两种计数不能混用（项目约定 §2.6）：
      · 去重落位数 = 148（同屏 id 唯一）
      · 各画面累计  = 148（本项目恰好相等，但代码不写死：各自现算）
    """
    by_page = {}
    for g in cards_d['groups']:
        by_page.setdefault(g['page'], []).append(g)

    rows_total = 0
    unc_total = 0
    body = []
    for page_name, gs in by_page.items():
        rows = []
        for g in gs:
            for e in g['allElements']:
                rows.append((g, e))
        if not rows:
            continue
        n_unc = sum(1 for _, e in rows if e.get('unownedKind'))
        rows_total += len(rows)
        unc_total += n_unc
        pid = pid_of.get(page_name, '')
        items = []
        for g, e in rows:
            cov = e.get('coveredBy') or []
            unk = e.get('unownedKind') or ''
            scr = e.get('screen', '')
            sid, _, vkey = scr.partition('|')
            key = '%s|%s|%s' % (sid, vkey, e.get('el', ''))
            box = el_box.get(key) or []
            # 归属：有需求号就写需求号（可点，点了飞到落点框）；
            # 没有就标「未归属」，并按骨架/内容分类 —— 「没写」≠「没有」。
            if cov:
                own = ''.join('<b class="own" data-br="%s" title="跳到 %s 的落点框">%s</b>'
                              % (escq(b), escq(b), esc(b)) for b in cov)
            else:
                cn = '骨架' if unk == 'skeleton' else ('内容' if unk == 'content' else '未分类')
                own = '<i class="unc" data-uk="%s">未归属 · %s</i>' % (escq(unk), esc(cn))
            items.append(
                '<tr class="elrow%s"%s>'
                # 侧栏只有 420px，五列（元素/类型/标签/位置/归属）会把每列
                # 挤到竖排换行。改成三列：① 元素名 + 类型徽标（同格两行）
                # ② 标签 + 位置（同格两行）③ 归属。位置信息降级为副标题，
                # 不占独立列 —— 它本来就是辅助信息，不需要扫读。
                '<td class="el-n"><span class="el-el" title="%s">%s</span>'
                '<span class="el-k">%s</span></td>'
                '<td class="el-l">%s<span class="el-p">%s</span></td>'
                '<td class="el-o">%s</td></tr>'
                % (' unc' if unk else '',
                   # data-box 用**单引号**包围、内部 JSON 用双引号 —— 属性值里就不会
                   # 出现裸双引号。将来 box 里若加了字符串字段也不会把属性切断。
                   (" data-box='%s'" % escq(json.dumps(box, ensure_ascii=False))) if box else '',
                   escq(e.get('el', '')),
                   esc(e.get('el', '')),
                   esc(e.get('kindCn') or e.get('kind') or ''),
                   esc(e.get('label') or ''),
                   esc('%s · %s' % (e.get('slotH', ''), e.get('slotV', ''))),
                   own))
        body.append(
            '<section class="elpg" data-page="%s">'
            '<header class="elpg-h"><span class="elpg-id">%s</span>'
            '<h3 class="elpg-n">%s</h3>'
            '<span class="elpg-c">%d 个元素<em>·</em>%s</span></header>'
            '<table class="elt"><thead><tr>'
            '<th>元素 / 类型</th><th>标签 / 位置</th><th>归属需求</th>'
            '</tr></thead><tbody>%s</tbody></table></section>'
            % (escq(page_name), esc(pid), esc(page_name), len(rows),
               ('<b class="warn">%d 未归属</b>' % n_unc) if n_unc else '<b class="fine">全部归属</b>',
               ''.join(items)))

    st = cards_d['stats']
    return (
        '<details class="eltable" id="elTable">'
        '<summary class="elt-sum">'
        '<span class="elt-t">页面级元素总表</span>'
        '<span class="elt-s">%d 个元素 · %d 未归属（骨架 %d · 内容 %d）</span>'
        '<span class="caret"></span></summary>'
        '<div class="elt-b">%s</div></details>'
        % (rows_total, unc_total,
           st.get('unownedSkeleton', 0), st.get('unownedContent', 0),
           ''.join(body)))


def sidebar(cards_d, pages, groups, anchors_by_br, pid_of):
    o = []
    o.append('<aside class="side" id="side">')
    o.append('<div class="side-h">'
             '<div class="sh-t">需求卡片</div>'
             '<div class="sh-s"><b id="sNShown">%d</b> / %d 张 · 点卡片看详情，画布会飞到它的落点</div>'
             '<input id="sQ" type="search" placeholder="搜需求号 / 页面 / 标题 / 正文">'
             '<div class="seg" id="sFEnd">'
             '<button class="on" data-e="all">全部端</button>'
             '<button data-e="app">小程序</button>'
             '<button data-e="admin">后台</button></div>'
             '<div class="sh-a"><button class="mini-btn" id="sExpandAll">全部展开</button>'
             '<button class="mini-btn" id="sCollapseAll">全部收起</button></div></div>'
             % (cards_d['stats']['cards'], cards_d['stats']['cards']))
    o.append('<div class="side-b" id="sideBody">')

    by_page = {}
    for g in cards_d['groups']:
        for c in g['cards']:
            by_page.setdefault(g['page'], []).append(c)

    for end in ('app', 'admin'):
        gs = [g for g in groups if g['end'] == end]
        # ⚠️ .lane 是 .pg 的**兄弟**，不是祖先。JS 里用 closest('.lane') 拿不到端，
        # 所以端直接写到每个 .pg 的 data-end 上 —— 别让 JS 去猜层级。
        o.append('<div class="lane" data-end="%s">%s</div>' % (end, esc(END_LABEL[end])))
        for g in gs:
            for pid in g['pages']:
                page = pages[pid]
                cds = by_page.get(page['name'], [])
                if not cds:
                    continue
                o.append('<section class="pg" data-end="%s" data-g="%s" data-pid="%s" data-name="%s">'
                         '<header class="pgh"><span class="pgid">%s</span>'
                         '<h2 class="pgn">%s</h2>'
                         '<span class="pgn-n">%d 条</span></header>%s</section>'
                         % (end, escq(g['name']), escq(pid), escq(page['name']),
                            esc(pid), esc(page['name']), len(cds),
                            ''.join(card_html(c, g['name'], anchors_by_br) for c in cds)))
    # 元素总表跟在卡片流末尾（在 .side-b 里，跟着一起滚）：
    # 它是查阅型内容，默认折叠只占一行，不该单独占一个固定区。
    o.append('<div class="side-f">%s</div>' % eltable_html(cards_d, EL_BOX, pid_of))
    o.append('</div>')
    o.append('</aside>')
    return ''.join(o)


# ---------------------------------------------------------------- 落点框世界坐标
def build_box_map(emap, el_map):
    """需求号 → [世界坐标框]。

    ⚠️ 锚点的坐标是**页面百分比**（分母是图尺寸），要转成世界坐标必须知道
    那一屏缩略图在世界里的位置。这里用 shot_el 记下的几何反算 ——
    不要在 JS 里用 getBoundingClientRect 现算：那时世界已经带了 transform，
    量出来的是屏幕坐标，再回去定位会差一个 transform。
    """
    geo = {}
    for e in el_map:
        if e['kind'] in ('page', 'var'):
            geo[e['x']] = e          # 按 left 索引，shot_el 里 x 唯一
    out = {}
    for s in emap['screens']:
        img = s.get('img') or s['viewport']
        # 找到这一屏对应的世界元素：靠 (x, y, w, h) 同时匹配
        cand = None
        for e in el_map:
            if e['kind'] not in ('page', 'var'):
                continue
            if abs(e['w'] - 0) > 1e9:
                continue
        # 由 SHOT_GEO 提供（shot_el 里填）
        g = SHOT_GEO.get((s['id'], s['vkey']))
        if not g:
            continue
        card_x, card_y, card_w, ih = g
        for a in s['anchors']:
            fx = a['x'] / img['w'] * card_w
            fy = a['y'] / img['h'] * ih
            fw = a['w'] / img['w'] * card_w
            fh = a['h'] / img['h'] * ih
            out.setdefault(a['br'], []).append(
                [round(card_x + fx, 1), round(card_y + HEAD_H + fy, 1),
                 round(fw, 1), round(fh, 1), s['id'], s['vkey']])
    return out


SHOT_GEO = {}
# 「页面id|状态key|元素名」→ 世界坐标框。布局期算好（build_el_box_map）。
EL_BOX = {}


def build_el_box_map(emap, el_map):
    """「页面id|状态key|元素名」→ [世界坐标框]（页面级元素总表用）。

    坐标系与锚点完全一样（页面百分比，分母是图尺寸），所以复用 SHOT_GEO
    反算成世界坐标 —— 千万别在 JS 里现算：那时世界已经带了 transform。
    """
    out = {}
    for s in emap['screens']:
        img = s.get('img') or s['viewport']
        g = SHOT_GEO.get((s['id'], s['vkey']))
        if not g:
            continue
        card_x, card_y, card_w, ih = g
        for e in s.get('elements', []):
            fx = e['x'] / img['w'] * card_w
            fy = e['y'] / img['h'] * ih
            fw = e['w'] / img['w'] * card_w
            fh = e['h'] / img['h'] * ih
            out['%s|%s|%s' % (s['id'], s['vkey'], e['el'])] = [
                round(card_x + fx, 1), round(card_y + HEAD_H + fy, 1),
                round(fw, 1), round(fh, 1)]
    return out


# ---------------------------------------------------------------- 构建
def build():
    emap, cards_d, prd = load()
    pages = page_meta(emap, prd)

    missing = [i for g in GROUPS for i in g['pages'] if i not in pages]
    if missing:
        print('  [分组引用了不存在的页面] %s' % missing)
        sys.exit(1)
    orphan = sorted(set(pages) - {i for g in GROUPS for i in g['pages']})
    if orphan:
        print('  [有页面没归入任何泳道分组，会从画布消失] %s' % orphan)
        sys.exit(1)

    by_page = {}
    for s in emap['screens']:
        by_page.setdefault(s['id'], []).append(s)
    for k in by_page:
        by_page[k].sort(key=lambda s: 0 if s['vkey'] == 'main' else 1)

    els, el_map = [], []
    st = cards_d['stats']

    # ---- 顶部文档卡
    els.append('<div class="el doc" style="left:0;top:0;width:470px">'
               '<div class="el-h"><span class="el-ic"></span>'
               '<span class="el-t">这块画布怎么看</span></div><div class="doc-b">'
               '<b>左边是原型，右边是需求卡片。</b>'
               '点右侧任意一张卡片，画布会飞到这条需求的<b>落点框</b>上并高亮 ——'
               '「这条需求落在哪一块」是几何事实，来自原型埋的锚点，不是手画的。'
               '<br><br>端分两条泳道：<b>上一行小程序</b>、<b>下一行后台</b>。'
               '缩到 40% 看整体结构，放到 100% 看单屏细节。'
               '<br><br>滚轮缩放（以鼠标位置为中心）· 拖住空白平移 · 点原型看大图。'
               '<br><br>右下角「锚点框」可开合落点框；右上角可隐藏本侧栏。'
               '</div></div>')
    el_map.append(dict(x=0, y=0, w=470, h=DOC_TOP_H, kind='doc'))

    els.append('<div class="el doc" style="left:496px;top:0;width:440px">'
               '<div class="el-h"><span class="el-ic"></span>'
               '<span class="el-t">本轮进度</span></div><div class="doc-b">'
               '<div class="big">%d 张需求卡片 · %d 个页面</div>'
               '<div class="row"><span class="k">原型画面</span><span class="v">%d 张（主态 %d · 补态 %d）</span></div>'
               '<div class="row"><span class="k">需求落点框</span><span class="v">%d 处</span></div>'
               '<div class="row"><span class="k">卡片内按钮</span><span class="v">%d 个</span></div>'
               '<div class="row"><span class="k">跳转去向</span><span class="v">%d 条</span></div>'
               '<div class="row"><span class="k">页面级交互元素</span><span class="v">%d 个</span></div>'
               '<div class="row"><span class="k">　覆盖 / 未覆盖</span>'
               '<span class="v">%d / <b style="color:#f0837d">%d</b>（骨架 %d · 内容缺口 %d）</span></div>'
               '</div></div>'
               % (st['cards'], st['groups'], len(emap['screens']),
                  len([s for s in emap['screens'] if s['vkey'] == 'main']),
                  len([s for s in emap['screens'] if s['vkey'] != 'main']),
                  sum(len(s['anchors']) for s in emap['screens']),
                  st['totalButtons'], st['totalExits'], st['pageElements'],
                  st['coveredElements'], st['unownedElements'],
                  st['unownedSkeleton'], st['unownedContent']))
    el_map.append(dict(x=496, y=0, w=440, h=DOC_TOP_H, kind='doc'))

    els.append('<div class="el doc" style="left:962px;top:0;width:500px">'
               '<div class="el-h"><span class="el-ic"></span>'
               '<span class="el-t">卡片里有什么 · 以及两个已知缺口</span></div><div class="doc-b">'
               '卡片自上而下：<b>编号 · 标题 · 优先级</b>、需求描述、计数微标，'
               '再按固定顺序展开分区 —— 涉及端 / 字段展示与来源与限制 / 交互说明与动效 / '
               '触发与风险 / 输入输出 / 按钮与布局跳转 / 业务规则 / 关联字段 / 接口 / '
               '权限 / 前置条件 / 页面流转 / 验收标准。'
               '<br><b>没有内容的分区不会被藏起来</b>，会写明「为什么没有」——'
               '「没写」和「没有」是两件事。'
               '<br><br><b style="color:#f0837d">缺口一（内容级）</b>：'
               '%d 个页面上的真实业务内容（充值、优惠券、菜品、FAQ…）'
               '没有被任何需求描述到，卡片里也没有对应分区。'
               '<br><b style="color:#8b95a8">缺口二（骨架级）</b>：'
               '%d 个骨架操作（返回、保存、筛选、页签…）同样没有落点。'
               '需求叙事通常不单独写这类需求，属合理缺省，已在页面级元素表列出。'
               '</div></div>'
               % (st['unownedContent'], st['unownedSkeleton']))
    el_map.append(dict(x=962, y=0, w=500, h=DOC_TOP_H, kind='doc'))

    # ---- 两条泳道
    y = DOC_TOP_H + BAND_GAP
    for end in ('app', 'admin'):
        gs = [g for g in GROUPS if g['end'] == end]
        n_pg = sum(len(g['pages']) for g in gs)
        n_shot = sum(1 for i in (i for g in gs for i in g['pages']) if i in by_page)
        els.append('<div class="blab" style="left:0;top:%.0fpx">%s ｜ %d 页 · 已出图 %d ｜ %s</div>'
                   % (y, esc(END_LABEL[end]), n_pg, n_shot, esc(END_NOTE[end])))
        el_map.append(dict(x=0, y=y, w=1560, h=LABEL_H, kind='blab'))
        y += LABEL_H
        row_y = y + GLAB_H
        x = 0
        row_h = 0
        for g in gs:
            els.append('<div class="glab" data-g="%s" style="left:%.0fpx;top:%.0fpx">'
                       '<b>%s</b><em>%s</em><span>%s</span>'
                       '<span style="color:#4b5560">%d 页</span></div>'
                       % (escq(g['name']), x, y, esc(g['name']), esc(g['mods']),
                          esc(g['note']), len(g['pages'])))
            gx = x
            for pid in g['pages']:
                page = pages[pid]
                cw = CARD_W_BY_END.get(page['platform'], CARD_W)
                shots = by_page.get(pid, [])
                for vi, s in enumerate(shots):
                    w_ = cw if s['vkey'] == 'main' else VAR_W
                    html_, hh = shot_el(page, s, gx, row_y, w_, el_map)
                    els.append(html_)
                    SHOT_GEO[(s['id'], s['vkey'])] = (gx, row_y, w_, hh - HEAD_H - FOOT_H)
                    row_h = max(row_h, hh)
                    gx += w_ + (VAR_GAP if vi == 0 and len(shots) > 1 else GAP)
            x = gx - GAP + GRP_GAP
        y = row_y + row_h + BAND_GAP

    world_w = max([0] + [e['x'] + e['w'] for e in el_map]) + 120
    world_h = y - BAND_GAP + BOT_PAD

    anchors_by_br = build_box_map(emap, el_map)

    payload = dict(
        world=dict(w=world_w, h=world_h),
        pages={k: dict(v) for k, v in pages.items()},
        groups=GROUPS, endLabel=END_LABEL,
        # 需求号 → 落点框（世界坐标）。侧栏点击后飞到这里。
        boxes=anchors_by_br,
        manifest=dict(
            els=len(el_map),
            docs=len([e for e in el_map if e['kind'] == 'doc']),
            pages=len([e for e in el_map if e['kind'] in ('page', 'var')]),
            cards=st['cards'],
            anchorBoxes=sum(len(s['anchors']) for s in emap['screens']),
            boxKeys=len(anchors_by_br),
            imgs=len(emap['screens']),
            worldW=world_w, worldH=world_h,
        ),
    )

    hud_left = ('<span class="logo">需求卡片画布</span>'
                '<span class="sub">{{项目名}} · 06-anno-card</span>')
    hud_right = ('<div class="panel">'
                 '<button class="btn" id="tAnno">锚点框</button>'
                 '<button class="btn" id="tDim">弱化原型</button>'
                 '<button class="btn" id="tSide">收起侧栏</button></div>')
    mini = ''.join('<i class="%s" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;height:%.1fpx"></i>'
                   % (e['kind'], e['x'], e['y'], e['w'], e['h']) for e in el_map)
    hud_br = ('<div class="panel">'
              '<button class="btn zbtn" id="zOut" title="缩小">−</button>'
              '<span class="zv" id="zv" title="点击回到 100%">100%</span>'
              '<button class="btn zbtn" id="zIn" title="放大">+</button>'
              '<button class="btn" id="zFit">适应</button></div>'
              '<div class="mini" id="mini"><div class="mini-l" id="miniL">__MINI__</div>'
              '<div class="mini-vp" id="miniVP"></div></div>')
    hud_bl = ('<div class="tip">滚轮缩放 · 拖拽平移 · 点卡片飞到落点</div>')

    # 元素总表的落点坐标必须在 SHOT_GEO 填完之后算（上面布局循环刚填完）。
    global EL_BOX
    EL_BOX = build_el_box_map(emap, el_map)
    pid_of = {p['name']: pid for pid, p in pages.items()}
    panel = sidebar(cards_d, pages, GROUPS, anchors_by_br, pid_of)
    doc = CH.render(''.join(els), payload, None, hud_left, hud_right,
                    hud_br.replace('__MINI__', mini), hud_bl,
                    extra_css=open(CARD_CSS, encoding='utf-8').read(),
                    extra_js='<script>%s</script>' % open(CARD_JS, encoding='utf-8').read(),
                    bodycls='biz',
                    title='需求卡片画布 · {{项目名}}',
                    world_extra='', body_extra=panel)

    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(doc)
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(dict(manifest=payload['manifest'], elMap=el_map,
                       boxes=anchors_by_br, stats=st),
                  f, ensure_ascii=False, indent=1)

    print('[需求卡片画布] %s' % OUT_HTML)
    print('  世界 %d × %d ｜ 元素 %d（原型 %d · 文档 %d）'
          % (world_w, world_h, len(el_map), payload['manifest']['pages'],
             payload['manifest']['docs']))
    print('  页面 %d ｜ 卡片 %d ｜ 内联截图 %d 张 ｜ 落点框 %d 处 / %d 个需求号'
          % (len(pages), st['cards'], len(emap['screens']),
             payload['manifest']['anchorBoxes'], payload['manifest']['boxKeys']))
    print('  文件 %.1f MB' % (os.path.getsize(OUT_HTML) / 1024.0 / 1024.0))





if __name__ == "__main__":
    build()
