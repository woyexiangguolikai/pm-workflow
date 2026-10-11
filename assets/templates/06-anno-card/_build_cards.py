# -*- coding: utf-8 -*-
"""
_build_cards.py —— 需求卡片数据模型

把 02-prd/prd.json 的 42 条需求 + 04-prototype/element-map.json 的 163 个交互元素
装配成「以页面为分组、以需求为卡片」的视图数据源 cards.json。

设计原则
--------
1. **单一来源**：卡片所有内容都从 prd.json / element-map.json 现算，本文件不写死业务文案。
   唯一手写的部分是「分区标题与顺序」以及「按钮的位置分组规则」——前者是版式、后者是几何。
2. **分区可追溯**：每个分区带 `src`，写明它来自 prd.json 的哪个键，便于校验与排错。
3. **空分区要显式**：分区为空时不静默丢弃，而是带 `empty=` 说明为什么不适用，
   否则「没写」与「没有」会被读成同一件事（引用 §验证红线）。
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRD = os.path.join(ROOT, '02-prd', 'prd.json')
EMAP = os.path.join(ROOT, '04-prototype', 'element-map.json')
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cards.json')

# ---------------------------------------------------------------- 排版规范
# 全部版式常量集中在此，CSS 由这些值现算，避免「同一个间距在两个文件里各写一遍」。
# 单位 px。校验脚本会读回这一组值，断言 CSS 里不出现硬编码的其它数值。
LAYOUT = {
    # —— 结构骨架
    'pagePadX':      28,    # 主内容区左右内边距
    'pagePadY':      22,    # 主内容区上下内边距
    'cardGap':       14,    # 卡片之间的竖直间距
    'cardPadX':      18,    # 卡片内左右内边距（折叠态与展开态必须一致）
    'cardPadY':      14,    # 卡片头部上下内边距
    'cardBodyPadT':  2,     # 头部与正文之间
    'cardBodyPadB':  16,    # 正文底部
    'secGap':        14,    # 分区之间的竖直间距
    'secTitleGap':   7,     # 分区标题与分区内容之间
    'secPadX':       12,    # 分区块内的左右内边距
    'secPadY':       10,    # 分区块内的上下内边距
    'rowGap':        6,     # 同一分区内条目之间的间距
    'cellPadY':      7,     # 表格单元格上下内边距
    'cellPadX':      9,     # 表格单元格左右内边距
    'radiusCard':    10,
    'radiusSec':     7,
    # —— 字号层级（六大级，页面内不再出现第六种字号）
    'fsPageTitle':   19,    # 页面标题
    'fsTocTitle':    15,    # 目录标题
    'fsCardTitle':   15,    # 卡片标题
    'fsBody':        13,    # 正文
    'fsSub':         12,    # 次级正文 / 表格
    'fsSecTitle':    12,    # 分区标题
    'fsMeta':        11,    # 序号 / 优先级 / 标签
    'fsMicro':       10,    # 微标（胶囊、徽标）
    # —— 装饰性内边距：统一收敛为三档，不再逐处随手写
    'chipPadX':      8,     # 胶囊类（计数微标、平台标签）
    'chipPadY':      2,
    'tagPadX':       6,     # 徽标类（优先级、按钮类型、归属）
    'tagPadY':       1,
    'tocItemPadX':   8,     # 目录条目
    'tocItemPadY':   5,
    'tocHeadPadX':   18,    # 目录头部
    # —— 行高
    'lhBody':        1.72,  # 正文行高
    'lhCell':        1.62,  # 表格行高
}


def _load(p):
    with open(p, encoding='utf-8') as f:
        return json.load(f)


def esc(s):
    if s is None:
        return ''
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


# ---------------------------------------------------------------- 元素定位
# 按元素在卡片里的相对位置分左右，用于「按钮布局」一列。
# 依据：元素矩形相对页面帧宽度的水平位置——左 1/3 / 中 1/3 / 右 1/3。
def _h_slot(rect_frame, frame_w):
    if not frame_w:
        return '—'
    cx = rect_frame[0] + rect_frame[2] / 2.0
    r = cx / float(frame_w)
    if r < 0.34:
        return '左'
    if r > 0.66:
        return '右'
    return '中'


def _v_slot(rect_frame, frame_h):
    if not frame_h:
        return '—'
    cy = rect_frame[1] + rect_frame[3] / 2.0
    r = cy / float(frame_h)
    if r < 0.18:
        return '页头'
    if r > 0.86:
        return '页尾'
    return '页中'


# 交互方式：从「元素自身 kind」推导向。不依赖已被移除的连线清单，
# 而是按各界面的通行语义给出，并在 note 里保留原型上写的原因。
KIND_CN = {
    'button': '按钮', 'entry': '入口', 'tab': '页签', 'tabbar': '底部标签',
    'field': '输入项', 'switch': '开关', 'link': '链接', 'modal': '弹窗',
    'step': '步骤', 'chip': '筛选片', 'row': '行', 'icon': '图标', 'form': '表单',
}


def main():
    prd = _load(PRD)
    emap = _load(EMAP)

    reqs = {x['id']: x for x in prd['requirements']}

    # 画面索引：pid|vkey -> screen
    screens = {}
    for s in emap['screens']:
        screens['%s|%s' % (s['id'], s['vkey'])] = s

    # 元素索引：page(pid) -> [element]
    els_by_page = {}
    for s in emap['screens']:
        els_by_page.setdefault(s['id'], []).extend(s['elements'])

    # 元素坐标表：el -> element（含 rectFrame，用于算布局位置）
    el_geo = {}
    for s in emap['screens']:
        for e in s['elements']:
            el_geo.setdefault(e['el'], dict(e, frame=s['frame'], pageName=s['name'],
                                            platform=s['platform']))

    # 需求 -> 元素：按「锚点所在画面」归属。
    # 一个需求可能对应多个元素（主落点 + 同页补充），全部收进来。
    anchors_by_req = {}
    for s in emap['screens']:
        for a in s['anchors']:
            anchors_by_req.setdefault(a['br'], []).append(dict(a, page=s['id'],
                                                               pageName=s['name'],
                                                               platform=s['platform']))

    # 页面 -> 画面（主态），用于卡片缩略图
    page_main = {}
    for s in emap['screens']:
        if s['vkey'] == 'main':
            page_main[(s['platform'], s['name'])] = s

    # ------------------------------------------------------------ 分组
    groups = []

    # 「未归属任何需求锚点」的元素分三类，理由不同、处置也不同：
    #   skeleton —— 返回/保存/取消/筛选/页签/重试：页面骨架操作。需求叙事里
    #               通常不会单独写一条需求，所以天生没有锚点。属于**合理缺省**。
    #   content  —— 充值/提现/优惠券/积分/菜品/FAQ：真实业务内容。没有锚点
    #               意味着**这块内容没有被任何需求描述到**，是真实的规格缺口。
    #   none     —— 判不出来，保守归到这里，需要人看一眼。
    # 不分的话 74 个元素全被打成同一个红标签，「骨架按钮」的噪声会把
    # 「内容缺口」这个真问题淹掉。
    _SKELETON_RE = re.compile(
        r'^(返回|保存|取消|提交|重置|试算|清空筛选|筛选|页签|刷新|刷新结果|重试|'
        r'处理中|测试连接|重新校验|重新支付|去配置|上一页|下一页|关闭|'
        r'确认|新增|编辑|删除|导出|导入|搜索|展开|收起)')

    def _unowned_kind(e, frame):
        lb = (e.get('label') or '').strip()
        if _SKELETON_RE.match(lb):
            return 'skeleton'
        # label 为空、或 kind 是纯展示类（图标/行内文本），也没有内容语义
        if not lb:
            return 'skeleton'
        return 'content'

    def _all_elems(platform, name):
        """页面上全部交互元素（含各状态画面去重，取首次出现的画面）。
        这是「页面级事实」，与某条需求无关 —— 放在目录节点下，不塞进卡片。
        同时标出「未被任何需求锚点覆盖」的元素：这些是页面公共操作区
        （保存 / 取消 / 试算之类），它们不属于某一条需求，但**必须被看见** ——
        早期版本直接按几何筛掉，结果整页的「保存」按钮在报告里彻底消失。"""
        # 先算出本页所有锚点框（用于判断元素是否被需求覆盖）
        anchors = []
        for s in emap['screens']:
            if s['platform'] != platform or s['name'] != name:
                continue
            for a in s['anchors']:
                anchors.append((a['x'], a['y'], a['w'], a['h'], a['br'], a['anchor']))

        seen, out = set(), []
        for s in emap['screens']:
            if s['platform'] != platform or s['name'] != name:
                continue
            for e in s['elements']:
                # 元素 id 跨状态可重复，取首次出现（home）那一份
                if e['el'] in seen:
                    continue
                seen.add(e['el'])
                fr = s['frame']
                cx, cy = e['x'] + e['w'] / 2.0, e['y'] + e['h'] / 2.0
                covered = []
                for ax, ay, aw, ah, br, anc in anchors:
                    if (ax - 6 <= cx <= ax + aw + 6) and (ay - 6 <= cy <= ay + ah + 6):
                        covered.append(br)
                out.append({
                    'el': e['el'], 'kind': e['kind'],
                    'kindCn': KIND_CN.get(e['kind'], e['kind']),
                    'label': e.get('label', ''), 'note': e.get('note', ''),
                    'slotH': _h_slot([e['x'], e['y'], e['w'], e['h']], fr.get('w')),
                    'slotV': _v_slot([e['x'], e['y'], e['w'], e['h']], fr.get('h')),
                    'screen': '%s|%s' % (s['id'], s['vkey']),
                    'vname': s['vname'],
                    'noGo': e.get('noGo', ''), 'noGoReason': e.get('noGoReason', ''),
                    'coveredBy': sorted(set(covered)),
                    'unownedKind': ('' if covered else _unowned_kind(e, s['frame'])),
                })
        # 排序：按页面纵向位置（页头 → 页中 → 页尾），同类内按横向
        order_v = {'页头': 0, '页中': 1, '页尾': 2, '—': 3}
        order_h = {'左': 0, '中': 1, '右': 2, '—': 3}
        out.sort(key=lambda e: (order_v.get(e['slotV'], 9), order_h.get(e['slotH'], 9), e['el']))
        return out

    def _mk_group(platform, name, path, brs):
        main = None
        for s in emap['screens']:
            if s['platform'] == platform and s['name'] == name and s['vkey'] == 'main':
                main = s
                break
        variants = [s for s in emap['screens']
                    if s['platform'] == platform and s['name'] == name]
        return {
            'key': '%s::%s' % (platform, name),
            'platform': platform,
            'platformCn': '用户小程序' if platform == 'app' else '管理后台',
            'page': name,
            'path': path,
            'shot': main['shot'] if main else '',
            'shotSize': main['shotSize'] if main else None,
            'img': main['img'] if main else None,
            'variantCount': len(variants) - 1 if main else 0,
            'variantNames': [v['vname'] for v in variants if v['vkey'] != 'main'],
            'reqs': brs,
            'cards': [],
            'allElements': _all_elems(platform, name),
        }

    # 先按 pages 定义建立页面骨架（保证顺序稳定、且没需求的页也出现）
    for platform, key in (('app', 'app'), ('admin', 'admin')):
        for p in prd['pages'][key]:
            # 同页需求去重保序
            seen, brs = set(), []
            for b in p['requirements']:
                if b not in seen:
                    seen.add(b)
                    brs.append(b)
            groups.append(_mk_group(platform, p['name'], p['path'], brs))

    group_by_key = {g['key']: g for g in groups}

    # 需求里若有 landing 页不在 pages 定义中，补一个分组，防漏
    for rid, x in reqs.items():
        L = x.get('landing') or {}
        plat, page = L.get('client'), L.get('page')
        if not plat or not page:
            continue
        k = '%s::%s' % (plat, page)
        if k not in group_by_key:
            g = _mk_group(plat, page, L.get('pagePath', ''), [rid])
            groups.append(g)
            group_by_key[k] = g

    # ------------------------------------------------------------ 卡片
    def build_card(rid):
        x = reqs[rid]
        L = x.get('landing') or {}
        inter = x.get('interactions') or {}
        motion = inter.get('motion') or {}
        pf = x.get('pageFlow') or {}
        sl = x.get('stateLink') or {}
        out = x.get('output') or {}
        perm = x.get('permissions') or {}
        itf = x.get('interfaces') or {}

        # 本需求在本页上的交互元素（元素通过「页内锚点」与该需求关联）
        els = []
        for a in anchors_by_req.get(rid, []):
            els.append(a)
        # 元素级：原型上带 data-el 的元素（03-design 页面规格定义的交互点）
        # 归属规则：同一页面的元素若落在该需求的锚点区域内，算作该需求的交互元素。
        page_els = []
        for a in anchors_by_req.get(rid, []):
            ax, ay, aw, ah = a['x'], a['y'], a['w'], a['h']
            for e in els_by_page.get(a['page'], []):
                ex, ey, ew, eh = e['x'], e['y'], e['w'], e['h']
                # 元素中心落在锚点框内（含少量容差）
                cx, cy = ex + ew / 2.0, ey + eh / 2.0
                if (ax - 6 <= cx <= ax + aw + 6) and (ay - 6 <= cy <= ay + ah + 6):
                    page_els.append(e)
        # 去重（同一元素可能落在多个锚点里）
        seen, uniq = set(), []
        for e in page_els:
            if e['el'] in seen:
                continue
            seen.add(e['el'])
            uniq.append(e)

        # ---- 按钮与入口
        buttons = []
        for e in uniq:
            if e['kind'] not in ('button', 'entry', 'link', 'tab', 'switch', 'chip'):
                continue
            g = el_geo.get(e['el'], {})
            fr = g.get('frame') or {}
            buttons.append({
                'el': e['el'],
                'kind': e['kind'],
                'kindCn': KIND_CN.get(e['kind'], e['kind']),
                'label': e.get('label', ''),
                'note': e.get('note', ''),
                'slotH': _h_slot([e['x'], e['y'], e['w'], e['h']], fr.get('w')),
                'slotV': _v_slot([e['x'], e['y'], e['w'], e['h']], fr.get('h')),
                'noGo': e.get('noGo', ''),
                'noGoReason': e.get('noGoReason', ''),
                'rectFrame': [e['x'], e['y'], e['w'], e['h']],
            })

        # ---- 跳转去向（从 pageFlow.exits 现算，不另写）
        exits = []
        for ex in (pf.get('exits') or []):
            exits.append({
                'condition': ex.get('condition', ''),
                'page': ex.get('page', ''),
                'params': ex.get('params', ''),
                'path': ex.get('path', ''),
            })

        # ---- 分区装配。顺序即版式顺序。
        secs = []

        def sec(key, title, src, body, empty=''):
            """body 为 None/空 时输出带 empty 的空分区（显式说明为什么没有）。"""
            secs.append({'key': key, 'title': title, 'src': src,
                         'body': body or [], 'empty': '' if body else empty})

        # 1 定位与职责
        sec('ends', '涉及端与职责', 'requirements[].ends',
            [{'end': e.get('end', ''), 'resp': e.get('responsibility', '')}
             for e in (x.get('ends') or [])],
            '本条未逐端拆分职责')

        # 2 字段：展示 / 来源 / 限制 三张表放在同一个「字段」分区下，用子标题区分
        df = [{'where': d.get('where', ''), 'name': d.get('name', ''),
               'field': d.get('field', ''), 'fmt': d.get('fmt', '—'),
               'mask': d.get('mask', '—'), 'empty': d.get('empty', '—'),
               'note': d.get('note', '')}
              for d in (x.get('displayFields') or [])]
        ds = [{'item': d.get('item', ''), 'source': d.get('source', ''),
               'tech': d.get('sourceTech', ''), 'mode': d.get('mode', ''),
               'fallback': d.get('fallback', '')}
              for d in (x.get('dataShow') or [])]
        ir = [{'input': d.get('input', ''), 'where': d.get('where', ''),
               'keyboard': d.get('keyboard', '—'), 'maxLen': d.get('maxLen', '—'),
               'allow': d.get('allow', '—'), 'normalize': d.get('normalize', '—'),
               'boundary': d.get('boundary', '—'), 'tip': d.get('tip', '—')}
              for d in (x.get('inputRules') or [])]
        sec('fields', '字段：展示 / 来源 / 限制', 'displayFields + dataShow + inputRules',
            ([{'sub': '页面展示字段', 'rows': df}] if df else []) +
            ([{'sub': '字段来源与口径', 'rows': ds}] if ds else []) +
            ([{'sub': '输入限制', 'rows': ir}] if ir else []),
            '本条不涉及新字段')

        # 3 交互说明与动效
        iv = []
        for k, cn in (('entry', '入口形态'), ('click', '点击行为'), ('confirm', '二次确认'),
                      ('loading', '加载态'), ('empty', '空态'), ('disabled', '禁用态'),
                      ('analytics', '埋点')):
            v = inter.get(k)
            if v and v != '无':
                iv.append({'k': cn, 'v': v})
        for k, v in (inter.get('errorText') or {}).items():
            iv.append({'k': '提示文案 · %s' % k, 'v': v, 'quote': True})
        mv = []
        for k, cn in (('pageEntry', '转场'), ('microInteraction', '微交互'),
                      ('feedback', '操作反馈'), ('durationEasing', '时长与缓动'),
                      ('reducedMotion', '无障碍降级')):
            v = motion.get(k)
            if v:
                mv.append({'k': cn, 'v': v})
        sec('interact', '交互说明与动效', 'interactions + interactions.motion',
            ([{'sub': '交互说明', 'rows': iv}] if iv else []) +
            ([{'sub': '动效与微交互', 'rows': mv}] if mv else []),
            '本条无独立交互说明')

        # 4 触发机制与风险
        st = []
        if sl.get('dependsOn'):
            st.append({'k': '依赖什么', 'v': '；'.join(sl['dependsOn'])})
        if sl.get('triggers'):
            st.append({'k': '会触发什么', 'v': '；'.join(sl['triggers'])})
        if sl.get('triggeredBy'):
            st.append({'k': '被什么触发', 'v': '；'.join(sl['triggeredBy'])})
        rk = [{'v': r} for r in (x.get('risks') or [])]
        ex_ = [{'scene': e.get('scene', ''), 'handling': e.get('handling', '')}
               for e in (x.get('exceptions') or [])]
        sec('trigger', '触发机制 · 异常 · 风险', 'stateLink + exceptions + risks',
            ([{'sub': '状态联动（触发 / 被触发）', 'rows': st}] if st else []) +
            ([{'sub': '异常与分支', 'rows': ex_}] if ex_ else []) +
            ([{'sub': '风险', 'rows': rk}] if rk else []),
            '本条无状态联动')

        # 5 输入 / 输出
        io = []
        if out.get('returns'):
            io.append({'k': '输出 · 返回什么', 'v': out['returns']})
        for p in (out.get('postConditions') or []):
            io.append({'k': '后置条件', 'v': p})
        sec('io', '输入 / 输出', 'output',
            ([{'sub': '输出与后置条件', 'rows': io}] if io else []),
            '本条无输出')

        # 6 按钮与布局跳转
        # 只说清一件事：本条需求的按钮是本页全部元素的一部分。
        # 归属靠锚点几何现算，不手写清单 —— 手写会随原型改动立刻过期。
        page_all = _all_elems(L.get('client', ''), L.get('page', ''))
        hit = {b['el'] for b in buttons}
        others = [e for e in page_all if e['el'] not in hit]
        # 拆两类：被别的需求覆盖的（有归属），以及谁也没覆盖的（页面公共操作区）
        unowned = [e for e in others if not e.get('coveredBy')]
        sec('buttons', '按钮与布局跳转', 'element-map.json 的元素锚点 + pageFlow.exits',
            [{'buttons': buttons, 'exits': exits,
              'entry': pf.get('entry', ''), 'action': pf.get('action', ''),
              'pageTotal': len(page_all), 'pageOthers': others,
              'pageUnowned': unowned}]
            if (buttons or exits) else [],
            '本页无归属本条的按钮，全部交互元素见左侧目录节点')

        # 7 规则
        sec('rules', '业务规则', 'requirements[].rules',
            [{'rows': [{'v': r} for r in (x.get('rules') or [])]}]
            if x.get('rules') else [],
            '本条无业务规则')

        # 8 关联字段
        fd = [{'business': f.get('business', ''), 'column': '%s.%s' % (f.get('table', ''), f.get('column', '')),
               'type': f.get('type', ''), 'desc': f.get('desc', ''), 'change': f.get('change', '')}
              for f in (x.get('fields') or [])]
        sec('dbfields', '关联字段（数据层）', 'requirements[].fields',
            [{'sub': '涉及的库表字段', 'rows': fd}] if fd else [],
            '本条不涉及数据层字段')

        # 9 接口
        iw = [{'id': i.get('id', ''), 'name': i.get('name', ''),
               'business': i.get('business', ''), 'note': i.get('note', ''), 'own': True}
              for i in (itf.get('ours') or [])]
        iw += [{'id': i.get('id', ''), 'name': i.get('name', ''),
                'business': i.get('business', ''), 'note': i.get('note', ''), 'own': False}
               for i in (itf.get('external') or [])]
        sec('apis', '接口', 'requirements[].interfaces',
            [{'sub': '我方接口 / 甲方接口', 'rows': iw}] if iw else [],
            '本条无接口调用')

        # 10 权限
        pm = []
        for k, cn in (('visible', '可见'), ('operable', '可操作'), ('forbidden', '不可用 / 例外')):
            if perm.get(k):
                pm.append({'k': cn, 'v': perm[k]})
        sec('perm', '权限', 'requirements[].permissions',
            [{'sub': '可见与可操作范围', 'rows': pm}] if pm else [],
            '本条无权限限制')

        # 11 前置条件
        pre = x.get('preconditions') or {}
        pv = []
        if pre.get('functional'):
            pv.append({'k': '功能前置', 'v': '；'.join(pre['functional'])})
        if pre.get('data'):
            pv.append({'k': '数据前置', 'v': '；'.join(pre['data'])})
        sec('pre', '前置条件', 'requirements[].preconditions',
            [{'sub': '进入本条之前必须成立的事', 'rows': pv}] if pv else [],
            '本条无特别前置')

        # 12 主流程
        mf = x.get('mainFlow') or []
        sec('flow', '主流程', 'requirements[].mainFlow',
            [{'rows': [{'actor': s.get('actor', ''), 'action': s.get('action', ''),
                        'note': s.get('note', '')} for s in mf]}] if mf else [],
            '本条无主流程')

        # 13 验收
        sec('accept', '验收标准', 'requirements[].acceptance',
            [{'rows': [{'v': a} for a in (x.get('acceptance') or [])]}]
            if x.get('acceptance') else [],
            '本条无验收标准')

        # 折叠态微标：只挑四个最能反映「这条有多重」的计数
        chips = []
        if df:
            chips.append({'k': '字段', 'v': len(df)})
        if len(buttons):
            chips.append({'k': '按钮', 'v': len(buttons)})
        if len(exits):
            chips.append({'k': '跳转', 'v': len(exits)})
        if iw:
            chips.append({'k': '接口', 'v': len(iw)})

        return {
            'id': rid,
            'no': '',
            'title': x.get('title', ''),
            'priority': x.get('priority', ''),
            'moduleId': x.get('moduleId', ''),
            'functionId': x.get('functionId', ''),
            'description': x.get('description', ''),
            'landing': {'client': L.get('client', ''), 'page': L.get('page', ''),
                        'path': L.get('pagePath', ''), 'anchor': L.get('anchor', ''),
                        'action': L.get('action', '')},
            'trace': x.get('trace') or {},
            'chips': chips,
            'sections': secs,
            'counts': {
                'fields': len(df), 'sources': len(ds), 'inputs': len(ir),
                'buttons': len(buttons), 'exits': len(exits), 'rules': len(x.get('rules') or []),
                'dbfields': len(fd), 'apis': len(iw), 'flow': len(mf),
                'exceptions': len(ex_),
            },
        }

    # 逐分组装配卡片，并顺次编号（与目录树一致）
    seq = 0
    for g in groups:
        for rid in g['reqs']:
            if rid not in reqs:
                continue
            seq += 1
            c = build_card(rid)
            c['no'] = '%s-%d' % ('A' if g['platform'] == 'app' else 'B', seq)
            g['cards'].append(c)

    # ------------------------------------------------------------ 输出
    all_cards = [c for g in groups for c in g['cards']]
    all_els = [e for g in groups for e in g['allElements']]
    out = {
        'schema': 'pm-workflow/anno-cards/v1',
        'project': prd['project'],
        'note': '需求卡片数据源：按页面分组，卡片内容全部从 02-prd/prd.json 与 04-prototype/element-map.json 现算。',
        'layout': LAYOUT,
        'kindCn': KIND_CN,
        'groups': groups,
        'stats': {
            'groups': len(groups),
            'cards': len(all_cards),
            'pageElements': len(all_els),
            'cardsWithButtons': sum(1 for c in all_cards if c['counts']['buttons']),
            'cardsWithApis': sum(1 for c in all_cards if c['counts']['apis']),
            'cardsWithInputs': sum(1 for c in all_cards if c['counts']['inputs']),
            'totalSections': sum(len(c['sections']) for c in all_cards),
            'emptySections': sum(1 for c in all_cards for s in c['sections'] if not s['body']),
            'totalButtons': sum(c['counts']['buttons'] for c in all_cards),
            'totalExits': sum(c['counts']['exits'] for c in all_cards),
            'coveredElements': sum(1 for e in all_els if e['coveredBy']),
            'unownedElements': sum(1 for e in all_els if not e['coveredBy']),
            'unownedSkeleton': sum(1 for e in all_els if e.get('unownedKind') == 'skeleton'),
            'unownedContent': sum(1 for e in all_els if e.get('unownedKind') == 'content'),
            'unownedPages': sum(1 for g in groups
                                if any(not e['coveredBy'] for e in g['allElements'])),
        },
    }

    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    s = out['stats']
    print('[需求卡片数据源] %s' % OUT)
    print('  页面分组 %d 个 ｜ 卡片 %d 张 ｜ 分区 %d 个（其中空分区 %d 个，均带说明）' % (
        s['groups'], s['cards'], s['totalSections'], s['emptySections']))
    print('  页面级交互元素共 %d 个（去重后）' % s['pageElements'])
    print('    其中被需求锚点覆盖 %d 个 ｜ 未归属 %d 个（骨架操作 %d，内容项 %d）' % (
        s['coveredElements'], s['unownedElements'],
        s['unownedSkeleton'], s['unownedContent']))
    print('    有未归属元素的页面 %d/%d 个' % (s['unownedPages'], s['groups']))
    print('  卡片内按钮共 %d 个 ｜ 跳转去向共 %d 条' % (s['totalButtons'], s['totalExits']))
    print('  含按钮 %d 张 ｜ 含接口 %d 张 ｜ 含输入限制 %d 张' % (
        s['cardsWithButtons'], s['cardsWithApis'], s['cardsWithInputs']))
    return out


if __name__ == '__main__':
    main()
