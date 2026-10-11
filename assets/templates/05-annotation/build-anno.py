# -*- coding: utf-8 -*-
"""05-annotation：把「交互点」与「交互连线」画到原型上。

产物两份（双格式约定）：
    annotations.json —— 结构化数据源：每条连线的起止元素、交互方式、业务说明、需求号，
                        每个元素的热区与编号。下游（开发、测试用例、埋点清单）读它。
    annotate.html    —— 自包含视图：白板式画布 + 元素热区 + 正交连线 + 左侧交互清单。

## 这一版和 04-prototype 白板的区别

| | 04-prototype | 05-annotation |
|---|---|---|
| 画什么 | 每一屏长什么样 | 每个**能点的东西**在哪、点下去去哪 |
| 卡片尺寸 | 248 / 460（看结构） | 240 / 440（看元素，通道留得宽） |
| 图上叠加 | 锚点框（需求落点） | 元素热区 + 编号 + 正交连线 + 线上标签 |
| 排版 | 按端分两条带 | 组内自动折行，把画布压成接近方的比例 |
| 导航 | 搜索 + 筛选 | 左侧交互清单：点一条高亮那条线并飞过去 |

## 为什么连线要真的算路

用户的要求是「连接线不能遮挡其他原型」。25 屏里每张卡都是障碍物，
线只能走卡片之间的通道 —— 所以用正交网格 A*（见 `_route.py`），
拐弯处就是「这里必须让开」。标签也逐个候选段试位置，压到卡片或别的标签就换一段。

## 为什么左边要有一份清单

一张 2400×4800 的画布，缩到能看全时什么字都读不了，放大又只能看到局部。
只靠「用眼睛找线」是找不到的 —— 清单是导航：点一条，线高亮、画布飞过去，
这才是这套东西真正被用起来的方式。线上的标签解决的是「一眼知道这条线是什么」，
清单解决的是「怎么快速找到我要的那条」。
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
TOKENS = os.path.join(ROOT, '03-design', 'tokens.json')
PRD = os.path.join(ROOT, '02-prd', 'prd.json')
OUT_JSON = os.path.join(HERE, 'annotations.json')
OUT_HTML = os.path.join(HERE, 'annotate.html')

sys.path.insert(0, HERE)
sys.path.insert(0, PROTO)

import _canvas_html as CH          # noqa: E402
import _interact as I              # noqa: E402
import _route as RT                # noqa: E402


def _load_build_canvas():
    """分组定义只在 04-prototype/build-canvas.py 里写一份。
    抄过来的话，将来在那边加一页这边就悄悄少一块 —— 而画面上只是「少了个卡片」，
    没人会觉得是 bug。"""
    spec = importlib.util.spec_from_file_location(
        'bc_groups', os.path.join(PROTO, 'build-canvas.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BC = _load_build_canvas()
GROUPS = BC.GROUPS
END_LABEL = BC.END_LABEL

# ------------------------------------------------------------------ 布局参数
# 通道宽度不是审美问题：正交路由要能从卡片之间穿过去，横向通道至少得容下
# 「一条线 + 两侧各 CLEAR 的空隙」。LANE=130 时中间有 130−2×20 = 90px 的可走宽度，
# 足够让两条线并行还不打架。
APP_W, ADMIN_W, VAR_W = 240, 440, 186
LANE = 130          # 同组内相邻卡片之间的横向通道
ROWL = 190          # 组与组之间的纵向通道
BAND = 280          # 两端之间的纵向通道
HEAD_H = 28         # 卡片头高
ROW_MAX = 2760      # 一行最多放到多宽就折行
DOC_H = 300         # 顶部文档区
TOP_PAD = 24
BOT_PAD = 80

W_BY_END = {'app': APP_W, 'admin': ADMIN_W}


def esc(s):
    return (str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
            .replace('"', '&quot;'))


def b64(path):
    with open(path, 'rb') as f:
        return base64.b64encode(f.read()).decode('ascii')


def txt_w(s, fs=11.0):
    w = 0.0
    for ch in s:
        w += fs if ord(ch) > 0x2E80 else fs * 0.56
    return w + 18.0


# ------------------------------------------------------------------ 载入
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
            anchors=[dict(anchor=a['anchor'], br=a['br'], label=a['label'],
                          extra=a.get('extra', '')) for a in p['anchors']])
    return emap, pages, br_title, br_prio


# ------------------------------------------------------------------ 排版
def _group_width(g, end, by_page):
    w = 0
    for i, pid in enumerate(g['pages']):
        if i:
            w += LANE
        for j, s in enumerate(by_page.get(pid, [])):
            if j:
                w += 14                      # 主态与它自己的补态之间的小缝
            w += W_BY_END[end] if s['vkey'] == 'main' else VAR_W
    return w


def _make_screen(s, end, gx, y0, by_page):
    cw = W_BY_END[end] if s['vkey'] == 'main' else VAR_W
    ih = cw * s['img']['h'] / s['img']['w']
    rec = dict(pid=s['id'], vkey=s['vkey'], vname=s['vname'], x=gx, y=y0, w=cw,
               h=HEAD_H + ih, imgH=ih, shot=s['shot'], img=s['img'],
               frame=s['frame'], dpr=s['dpr'], page=s['pageFile'], vels=[])
    for e0 in s['elements']:
        e = dict(e0)
        # 元素在**世界坐标**里的矩形：卡片按宽度等比缩放，所以百分比就是唯一依据。
        # 不做这一步就得在画线的时候到处重复这套换算，迟早有一处用错分母
        # （用视口宽当分母会让所有框整体偏移，而且看起来是对的）。
        e['wx'] = gx + cw * e['rx'] / s['img']['w']
        e['wy'] = y0 + HEAD_H + ih * e['ry'] / s['img']['h']
        e['ww'] = cw * e['w'] / s['img']['w']
        e['wh'] = ih * e['h'] / s['img']['h']
        e['pid'] = s['id']
        e['vkey'] = s['vkey']
        e['screen'] = s['id'] + '|' + s['vkey']
        rec['vels'].append(e)
    return rec, cw


def layout(emap, pages):
    """按组折行铺开。返回 (screens[], placed[], world_w, world_h)。

    为什么按组折行、而不是一组一行：一组一行时小程序端占 4 行、后台端占 4 行，
    竖着排出来是 2400×5900 的细长条，fit 之后卡片只有 30px 宽、字全糊。
    按 ROW_MAX 折行能把小组合并到同一行，高度压到 4800 左右，比例接近方的。
    """
    by_page = {}
    for s in emap['screens']:
        by_page.setdefault(s['id'], []).append(s)
    for k in by_page:
        by_page[k].sort(key=lambda s: 0 if s['vkey'] == 'main' else 1)

    screens, placed = [], []
    y = TOP_PAD + DOC_H
    for end in ('app', 'admin'):
        gs = [g for g in GROUPS if g['end'] == end]
        wmap = {g['name']: _group_width(g, end, by_page) for g in gs}
        rows, cur = [], []
        for g in gs:
            if cur and sum(wmap[x['name']] for x in cur) + LANE + wmap[g['name']] > ROW_MAX:
                rows.append(cur)
                cur = []
            cur.append(g)
        if cur:
            rows.append(cur)

        y += 30                                        # 端标签占位
        for row in rows:
            y0 = y + 26                                # 组标签占位
            x = 0
            row_h = 0
            for g in row:
                gx = x
                gh = 0
                for i, pid in enumerate(g['pages']):
                    if i:
                        gx += LANE
                    for j, s in enumerate(by_page.get(pid, [])):
                        if j:
                            gx += 14
                        rec, cw = _make_screen(s, end, gx, y0, by_page)
                        screens.append(rec)
                        gh = max(gh, rec['h'])
                        gx += cw
                placed.append(dict(name=g['name'], mods=g['mods'], note=g['note'],
                                   x=x, y=y, n=len(g['pages'])))
                x = gx + LANE
                row_h = max(row_h, gh)
            y = y0 + row_h + ROWL
        y += BAND - ROWL
    world_w = max([s['x'] + s['w'] for s in screens] + [0]) + 140
    world_h = y + BOT_PAD
    return screens, placed, world_w, world_h


# ------------------------------------------------------------------ 元素归属
def element_index(screens):
    """元素 id → 它在哪张画面上的哪个矩形。

    同一个元素会在多个状态里出现（PG-A5 的主态与失败态都有「重新支付」），
    取**第一次出现**的那张当标准落位 —— 按页面顺序 + 主态优先，结果稳定可复现。
    """
    idx = {}
    for s in screens:
        for e in s['vels']:
            idx.setdefault(e['el'], e)
    return idx


def screen_index(screens):
    """精确到「某页的某状态」。两种分隔符都收：内部用 `|`（不会和页面路径里的 / 撞），
    连线清单里写 `#PG-A5/yikatong` 更接近 URL 习惯，读起来顺。"""
    exact, bypage = {}, {}
    for s in screens:
        exact[s['pid'] + '|' + s['vkey']] = s
        exact[s['pid'] + '/' + s['vkey']] = s
        bypage.setdefault(s['pid'], s)
    return exact, bypage


# ------------------------------------------------------------------ 连线
def build_links(screens, pages):
    idx = element_index(screens)
    exact, bypage = screen_index(screens)
    all_cards = [(s['x'], s['y'], s['w'], s['h']) for s in screens]
    router = RT.Router(all_cards)

    out = []
    for i, (a, b, act, label, note, br) in enumerate(I.LINKS):
        ea = idx[a]
        # 目标：元素 或 页面/页面状态
        if b.startswith('#'):
            ref = b[1:]
            tb = exact.get(ref) or bypage.get(ref.split('/')[0])
            if tb is None:
                out.append(dict(id=I.link_id(i), fromEl=a, to=b, action=act,
                                label=label, note=note, br=br, ok=False,
                                err='目标画面不存在：%s' % ref))
                continue
            eb_rect = None
            tb_card = tb
        else:
            eb = idx[b]
            eb_rect = (eb['wx'], eb['wy'], eb['ww'], eb['wh'])
            tb_card = exact[eb['screen']]

        sa = exact[ea['screen']]
        ra = (ea['wx'], ea['wy'], ea['ww'], ea['wh'])
        card_a = (sa['x'], sa['y'], sa['w'], sa['h'])
        card_b = (tb_card['x'], tb_card['y'], tb_card['w'], tb_card['h'])
        rb = eb_rect or card_b

        if sa is tb_card:
            pts, flags = RT.l_connect(ra, rb, card_a)
        else:
            side_a, side_b = RT.pick_side(card_a, card_b)
            got = router.route([(ra, side_a, card_a), (rb, side_b, card_b)])
            if not got:
                out.append(dict(id=I.link_id(i), fromEl=a, to=b, action=act,
                                label=label, note=note, br=br, ok=False,
                                err='路由失败（两端之间找不到通道）'))
                continue
            pts, flags = got
        out.append(dict(id=I.link_id(i), fromEl=a, to=b, action=act, label=label,
                        note=note, br=br, ok=True, fromPage=sa['pid'],
                        toPage=tb_card['pid'],
                        fromScreen=ea['screen'], toScreen=tb_card['pid'] + '|' + tb_card['vkey'],
                        pts=[[round(p[0], 1), round(p[1], 1)] for p in pts],
                        stubs=[bool(x) for x in flags],
                        fromRect=[round(v, 1) for v in ra],
                        toRect=[round(v, 1) for v in rb]))
    return out


def place_all_labels(links, screens):
    """标签落位。分两级，宁可退化、不可不标：

      1. 完整胶囊 —— 「交互方式 + 业务标签」，如「弹窗｜解绑二次确认」；
      2. 短胶囊   —— 只剩「交互方式」，如「弹窗」。

    为什么要有第 2 级：用户的要求是「连接线上要标注出交互方式」。如果放不下就整条不标，
    那么一多半的线上什么都没有，单独看那条线的人还是读不出它是弹窗还是跳转 ——
    要求就没落地。业务标签放不下可以退回左侧清单（那里每条都有），
    但**交互方式不能退** —— 它是线上的必要信息。
    """
    # ⚠️ 卡片在排版里是 [x, y, w, h]，而 place_label / _hits 要的是角点 (x0,y0,x1,y1)。
    # 这两种写法长得太像，混用不报错，只会让障碍框悄悄变矮变窄 ——
    # 于是标签看起来"没压卡片"，其实压在卡片上。转换只在这一行做。
    cards = [(s['x'], s['y'], s['x'] + s['w'], s['y'] + s['h']) for s in screens]
    taken = []
    for lk in links:
        if not lk['ok']:
            continue
        pts = [tuple(p) for p in lk['pts']]
        # 线上要写**交互方式**，不能只靠颜色 —— 单独看一条线的人应该读得出
        # 「这是弹窗还是跳转」，而不是去对照图例。业务标签跟在后面。
        act = I.ACTIONS[lk['action']]
        lk['labelAct'] = act['name']
        # 完整宽度 = 两段文字 - 一次内边距 + 中间 6px 间距（两段共用同一条胶囊）
        w_full = txt_w(act['name']) + txt_w(lk['label']) - 18.0 + 6.0
        w_short = txt_w(act['name'])

        # 同卡连线（tab→tab、开关→它控制的字段）整条都在自己那张卡里走，
        # l_connect 把每段都标成了引出段，于是 place_label 一个候选段都挑不出来。
        # 所以这类连线的标签只能落在**自己这张卡里** —— 它注释的就是这张卡内部的
        # 两个控件，落在别处反而读不懂。这是一条有边界的例外，不是放行：
        # 它仍然不许碰到任何别的卡片（下面 obstacles 里只去掉自己那一张）。
        same = lk['fromScreen'] == lk['toScreen']
        own = set()
        if same:
            for s in screens:
                if s['pid'] + '|' + s['vkey'] == lk['fromScreen']:
                    own.add((s['x'], s['y'], s['x'] + s['w'], s['y'] + s['h']))
        obs = [b for b in cards if b not in own]
        fl = [False] * len(lk['stubs']) if same else lk['stubs']

        pos, box, short = None, None, False
        for w, sh in ((w_full, False), (w_short, True)):
            pos, box = RT.place_label(pts, fl, w, 18.0, obs, taken)
            if pos:
                short = sh
                break
        if pos:
            lk['labelPos'] = [round(pos[0], 1), round(pos[1], 1)]
            lk['labelBox'] = [round(v, 1) for v in box]
            lk['labelW'] = round(w_full if not short else w_short, 1)
            lk['labelShort'] = short
            lk['labelInCard'] = bool(same)
    return links


# ------------------------------------------------------------------ 视图
ACT_CSS = ''.join(
    '.lk.a-%s polyline{stroke:%s}' % (k, v['color']) for k, v in I.ACTIONS.items())

EXTRA_CSS = """
%(actcss)s
#board{left:372px}
/* SVG 连线层。non-scaling-stroke 是**必须**的：画布缩到 fit 时是 0.15 倍，
   线宽跟着缩就只剩 0.3px，全貌视图上什么都看不见 —— 而全貌视图恰恰是
   唯一能看出「整体怎么串起来」的视角。屏幕像素定宽之后，
   缩到 15%% 看结构、放到 100%% 看细节，线都是一样清楚的一条。 */
#links{position:absolute;left:0;top:0;overflow:visible;pointer-events:none;z-index:5}
#links polyline{fill:none;stroke-width:1.7;vector-effect:non-scaling-stroke;
    stroke-linejoin:round;stroke-linecap:round;opacity:.9}
#links .lk{pointer-events:stroke}
#links .lk.hl polyline{stroke-width:3.6;opacity:1}
#links .lk.dim{opacity:.16}
#links .mk{display:none}
#links .lk.hl .mk{display:block}
.eh{position:absolute;border:1.2px solid rgba(88,166,255,.55);
    background:rgba(88,166,255,.10);border-radius:3px;cursor:pointer}
.eh:hover{border-color:#fff;background:rgba(255,255,255,.22)}
.eh.hl{border-color:#fff;border-width:2px;background:rgba(255,255,255,.3);
    box-shadow:0 0 0 2px rgba(88,166,255,.6)}
.eh-n{position:absolute;left:-1px;top:-13px;font:9px/1 ui-monospace,Consolas,monospace;
    color:#0d1117;background:rgba(88,166,255,.92);padding:2px 4px;border-radius:3px 3px 0 0;
    white-space:nowrap}
body.nonum .eh-n{display:none}
.lbl{position:absolute;transform:translate(-50%%,-50%%);pointer-events:none;
    font-size:11px;line-height:1;padding:3px 7px;border-radius:20px;white-space:nowrap;
    background:rgba(13,17,23,.94);border:1px solid var(--border);color:#c3ccd6}
/* 交互方式在前、业务标签在后。交互方式用线本身那条颜色，一眼能看出
   「这条线说的是哪种交互」；业务标签压暗一档，避免两段一样重看不出主次。 */
.lbl b{font-weight:600;margin-right:6px}
.lbl i{font-style:normal;opacity:.82}
/* 降级形态：只写得出交互方式。压暗一档，读起来是"次要信息"，
   而不是"这条线没说明白"。 */
.lbl.short{padding:3px 6px}
.lbl.short b{margin-right:0;opacity:.9}
.lbl.hl{color:#fff;border-color:#fff;background:rgba(20,26,34,.98)}
.lbl.hl i{opacity:1}

/* ---------------- 左侧交互清单 ---------------- */
.ixp{position:fixed;left:0;top:0;bottom:0;width:372px;z-index:70;
     background:#0d1319;border-right:1px solid var(--border);display:flex;flex-direction:column}
.ixp-h{padding:11px 13px 9px;border-bottom:1px solid var(--border)}
.ixp-h b{font-size:13.5px}
.ixp-h span{display:block;font-size:11px;color:var(--muted);margin-top:3px}
.ixp-f{padding:9px 11px;border-bottom:1px solid var(--border);display:flex;
       flex-direction:column;gap:7px}
.ixp-f input{background:#0b0f14;border:1px solid var(--border);border-radius:7px;
    color:var(--text);font:inherit;font-size:11.5px;padding:5px 9px;outline:none}
.ixp-f input:focus{border-color:var(--accent)}
.ixp-f .seg{flex-wrap:wrap}
.ixp-f .seg button{padding:3px 8px;font-size:11px}
.ixp-b{flex:1;overflow:auto;padding:6px 0 40px}
.ixg-t{padding:9px 13px 5px;font-size:11px;color:var(--muted);letter-spacing:.5px;
       position:sticky;top:0;background:#0d1319;z-index:2}
.ixp-pg{border-bottom:1px dashed #1e2731}
.ixp-t{display:flex;align-items:baseline;gap:7px;padding:7px 13px 4px;font-size:12.5px;
       font-weight:600;color:#dfe6ee}
.ixp-t em{font-style:normal;font-family:ui-monospace,Consolas,monospace;font-size:10px;
          color:var(--muted)}
.ixp-t s{margin-left:auto;text-decoration:none;font-size:10.5px;color:#5b6672;
         font-weight:400}
.ixl{display:flex;align-items:center;gap:7px;padding:5px 13px 5px 20px;font-size:11.5px;
     cursor:pointer;color:#c3ccd6}
.ixl:hover{background:#141b23}
.ixl.on{background:#18222e}
.ixl .dt{width:7px;height:7px;border-radius:50%%;flex:none}
.ixl .fr{color:#e6edf3;flex:0 1 auto;overflow:hidden;text-overflow:ellipsis;
         white-space:nowrap;max-width:118px}
.ixl .to{color:var(--muted);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;
         flex:1;min-width:0}
.ixl .ac{flex:none;font-size:10px;border-radius:20px;padding:1px 6px;border:1px solid}
.ixl .br{flex:none;font-family:ui-monospace,Consolas,monospace;font-size:9.5px;
         color:#6e7a87}
.ixi{display:flex;align-items:center;gap:7px;padding:4px 13px 4px 20px;font-size:11px;
     color:#7d8794;cursor:pointer}
.ixi:hover{background:#141b23}
.ixi .tg{flex:none;font-size:9.5px;border-radius:20px;padding:1px 6px;
         border:1px solid #2b333d;color:#8b949e}
.ixi .nm{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ixi.on{background:#18222e;color:#c3ccd6}
.ixi .nt{display:none;padding:0 13px 6px 40px;font-size:11px;color:#8b949e;line-height:1.7}
.ixi.open+.ixi .nt,.ixi .nt.open{display:block}
.ix-note{padding:8px 13px 2px;font-size:11px;color:#7d8794;line-height:1.7}

/* 图例：交互方式靠颜色区分，色块要给足面积 —— 做成 11px 的小方点，
   在小图上根本分不出蓝和青。改成 20×3 的短横更稳。 */
.lgx{display:flex;flex-wrap:wrap;gap:6px 10px;margin:2px 0 2px}
.lgx .li{display:flex;align-items:center;gap:6px;font-size:12px;color:#c3ccd6;
         border:1px solid var(--border);border-radius:20px;padding:3px 10px 3px 7px}
.lgx .li i{width:20px;height:3px;border-radius:2px;flex:none}
.lgx .li b{margin-left:2px;color:#fff;font-family:ui-monospace,Consolas,monospace}
"""

EXTRA_JS = """
/* ================= 05-annotation 专用逻辑 ================= */
/* 飞到一个世界坐标包围盒。fit() 只能适应「全部可见元素」，这里要看的是**某一条线**，
   所以自己算一次 translate/scale。上限仍走 maxZ()，不然飞过去就是一片糊。 */
function focusBox(x0,y0,x1,y1,pad){
  pad=pad==null?140:pad;
  var w=board.clientWidth,h=board.clientHeight;
  var bw=Math.max(1,x1-x0+pad*2), bh=Math.max(1,y1-y0+pad*2);
  var s=Math.min(w/bw,h/bh,maxZ());
  vs=Math.max(0.04,Math.min(2.4,s));
  vx=w/2-(x0+x1)/2*vs; vy=h/2-(y0+y1)/2*vs;
  apply();
}
function clearHL(){
  [].slice.call(document.querySelectorAll('.lk.hl,.eh.hl,.lbl.hl'))
    .forEach(function(e){e.classList.remove('hl')});
  [].slice.call(document.querySelectorAll('.ixl.on,.ixi.on'))
    .forEach(function(e){e.classList.remove('on')});
}
function markLink(id){
  var g=document.getElementById('g'+id);
  if(g){g.classList.remove('dim'); g.classList.add('hl')}
  var lb=document.querySelector('.lbl[data-lk="'+id+'"]');
  if(lb) lb.classList.add('hl');
  var row=document.querySelector('.ixl[data-lk="'+id+'"]');
  if(row) row.classList.add('on');
}
function markEl(id){
  [].slice.call(document.querySelectorAll('.eh[data-el="'+id+'"]'))
    .forEach(function(h){h.classList.add('hl')});
  var row=document.querySelector('.ixi[data-el="'+id+'"]');
  if(row) row.classList.add('on');
}
function hlLink(id,fly){
  clearHL();
  var A=ANNO.links[id]; if(!A) return;
  markLink(id);
  [A.fromEl,A.toEl].forEach(function(e){ if(e) markEl(e) });
  if(fly===false) return;
  var x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;
  A.pts.forEach(function(p){
    if(p[0]<x0)x0=p[0]; if(p[1]<y0)y0=p[1];
    if(p[0]>x1)x1=p[0]; if(p[1]>y1)y1=p[1]});
  focusBox(x0,y0,x1,y1,180);
}
function hlEl(id,fly){
  clearHL();
  markEl(id);
  var ids=(ANNO.byEl[id]||[]).slice();
  ids.forEach(markLink);
  if(fly===false) return;
  var x0=1e9,y0=1e9,x1=-1e9,y1=-1e9;
  function add(r){ if(r[0]<x0)x0=r[0]; if(r[1]<y0)y0=r[1];
                   if(r[0]+r[2]>x1)x1=r[0]+r[2]; if(r[1]+r[3]>y1)y1=r[1]+r[3] }
  (ANNO.elRect[id]||[]).forEach(add);
  ids.forEach(function(lid){
    if(!ANNO.links[lid]) return;
    ANNO.links[lid].pts.forEach(function(p){
      if(p[0]<x0)x0=p[0]; if(p[1]<y0)y0=p[1];
      if(p[0]>x1)x1=p[0]; if(p[1]>y1)y1=p[1]});
  });
  if(x0>1e8) return;
  focusBox(x0,y0,x1,y1,220);
}
document.addEventListener('click',function(e){
  var row=e.target.closest('.ixl');
  if(row && e.target.closest('.ixp')){hlLink(row.dataset.lk,true);return}
  var ir=e.target.closest('.ixi');
  if(ir && e.target.closest('.ixp')){
    var nt=document.getElementById('n'+ir.dataset.el);
    if(nt) nt.classList.toggle('open');
    hlEl(ir.dataset.el,true); return;
  }
  var h=e.target.closest('.eh');
  if(h){ hlEl(h.dataset.el,true) }
});
document.getElementById('tNum').onclick=function(){
  document.body.classList.toggle('nonum'); this.classList.toggle('on');
};
document.getElementById('tDim').onclick=function(){
  var on=this.classList.toggle('on');
  [].slice.call(document.querySelectorAll('.lk')).forEach(function(g){
    if(!g.classList.contains('hl')) g.classList.toggle('dim',on)});
};
/* 清单按交互方式 / 关键词过滤。画布上的线也跟着隐掉 —— 两边不同步的话，
   清单里选「只看弹窗」而图上还有一堆蓝线，会让人以为是漏了。 */
var ixAct='all';
function ixKw(){
  var el=document.getElementById('ixq');
  return ((el&&el.value)||'').trim().toLowerCase();
}
function ixFilter(){
  var kw=ixKw(), vis={}, visEl={};
  [].slice.call(document.querySelectorAll('.ixl')).forEach(function(r){
    var A=ANNO.links[r.dataset.lk]||{};
    var ok=(ixAct==='all'||r.dataset.a===ixAct)&&(!kw||(A.key||'').indexOf(kw)>=0);
    r.style.display=ok?'':'none';
    if(ok) vis[r.dataset.lk]=1;
  });
  [].slice.call(document.querySelectorAll('.ixi')).forEach(function(r){
    var ok=(ixAct==='all'||ixAct==='inplace')&&
           (!kw||(r.dataset.key||'').indexOf(kw)>=0);
    r.style.display=ok?'':'none';
    var nt=document.getElementById('n'+r.dataset.el);
    if(nt&&!ok) nt.classList.remove('open');
    if(ok) visEl[r.dataset.el]=1;
  });
  [].slice.call(document.querySelectorAll('.ixp-pg')).forEach(function(pg){
    var any=[].slice.call(pg.querySelectorAll('.ixl,.ixi')).some(function(r){
      return r.style.display!=='none'});
    pg.style.display=any?'':'none';
  });
  /* 画布上的线：按交互方式 + 它自己的检索键。
     注意用 vis[] 而不是重新算一遍条件 —— 两处各算一次，迟早有一处漂移。 */
  [].slice.call(document.querySelectorAll('.lk')).forEach(function(g){
    g.style.display=(ixAct==='all'||g.dataset.a===ixAct)&&
                    (!kw||vis[g.dataset.lk])?'':'none';
  });
  [].slice.call(document.querySelectorAll('.lbl')).forEach(function(l){
    l.style.display=(l.dataset.lk in vis)||(ixAct==='all'&&!kw)?'':'none';
  });
}
(function(){
  var box=document.getElementById('ixA');
  [].slice.call(box.children).forEach(function(b){
    b.onclick=function(){
      [].slice.call(box.children).forEach(function(x){x.classList.remove('on')});
      b.classList.add('on'); ixAct=b.dataset.a; ixFilter();
    };
  });
  var q=document.getElementById('ixq');
  if(q) q.addEventListener('input',ixFilter);
})();
"""


def render_panel(screens, links, pages, br_title):
    """左侧交互清单：按页面列出「有去向的交互」与「就地/外部」两类。"""
    idx = element_index(screens)
    by_page_from, by_page_el = {}, {}
    for lk in links:
        if lk.get('fromPage'):
            by_page_from.setdefault(lk['fromPage'], []).append(lk)
    for s in screens:
        for e in s['vels']:
            by_page_el.setdefault(s['pid'], {})[e['el']] = e
    out = ['<div class="ixp">',
           '<div class="ixp-h"><b>交互清单</b><span>%d 条连线 · %d 个交互点 · '
           '点一条会高亮那条线并飞过去</span></div>' % (len(links), len(idx)),
           '<div class="ixp-f">',
           '<input id="ixq" placeholder="搜元素 / 页面 / 需求号">',
           '<div class="seg" id="ixA">'
           '<button class="on" data-a="all">全部</button>']
    for k in I.ACTION_ORDER:
        out.append('<button data-a="%s">%s</button>' % (k, I.ACTIONS[k]['name']))
    out.append('</div></div><div class="ixp-b">')
    for end in ('app', 'admin'):
        out.append('<div class="ixg-t">%s</div>' % END_LABEL[end])
        for s in screens:
            pid = s['pid']
            if pages[pid]['platform'] != end or s['vkey'] != 'main':
                continue
            rowslk = by_page_from.get(pid, [])
            elmap = by_page_el.get(pid, {})
            key = ' '.join([pid, pages[pid]['name']] +
                           list(elmap) + [x['label'] for x in rowslk] +
                           [x['br'] for x in rowslk] +
                           [e.get('label', '') for e in elmap.values()]).lower()
            out.append('<div class="ixp-pg" data-key="%s" data-end="%s">' % (esc(key), end))
            out.append('<div class="ixp-t"><em>%s</em>%s<s>%d 个交互点</s></div>'
                       % (pid, esc(pages[pid]['name']), len(elmap)))
            for lk in rowslk:
                if lk['fromPage'] != pid:
                    continue
                act = I.ACTIONS[lk['action']]
                tolabel = _to_label(lk, idx, pages)
                out.append(
                    '<div class="ixl" data-lk="%s" data-a="%s">'
                    '<i class="dt" style="background:%s"></i>'
                    '<span class="fr">%s</span><span class="to">→ %s</span>'
                    '<span class="ac" style="color:%s;border-color:%s">%s</span>'
                    '<span class="br">%s</span></div>'
                    % (lk['id'], lk['action'], act['color'],
                       esc(idx[lk['fromEl']]['label']), esc(tolabel),
                       act['color'], act['color'], act['name'], lk['br']))
            for e in elmap.values():
                if not e['home']:
                    continue
                tag, note = I.INPLACE.get(e['el'], ('', ''))
                if not tag:
                    continue
                out.append(
                    '<div class="ixi" data-el="%s" data-a="inplace" data-key="%s">'
                    '<span class="tg">%s</span><span class="nm">%s</span></div>'
                    '<div class="nt" id="n%s">%s</div>'
                    % (e['el'],
                       esc((' '.join([e['el'], e['label'] or '', note or '', tag, pid,
                                      pages[pid]['name']])).lower()),
                       tag, esc(e['label'] or e['el']), e['el'], esc(note)))
            out.append('</div>')
    out.append('</div></div>')
    return ''.join(out)


def _to_label(lk, idx, pages):
    if lk['to'].startswith('#'):
        ref = lk['to'][1:]
        pid = ref.split('/')[0]
        suffix = ref.split('/')[1] if '/' in ref else ''
        nm = pages[pid]['name']
        return '「%s」%s' % (nm, '· ' + suffix if suffix else '')
    e = idx[lk['to']]
    return e['label']


def build():
    emap, pages, br_title, br_prio = load()
    screens, placed, world_w, world_h = layout(emap, pages)

    # 把「编号」也回填到 emap 的同名元素上：annotations.json 里要一份自洽的元素表
    idx = element_index(screens)
    for s in screens:
        for i, e in enumerate(s['vels'], 1):
            e['no'] = '%s-%d' % (e['pid'].replace('PG-', ''), i)
            e['num'] = i

    links = build_links(screens, pages)
    bad = [x for x in links if not x.get('ok')]
    if bad:
        print('  [连线失败]')
        for x in bad:
            print('    - %s %s → %s：%s' % (x['id'], x['fromEl'], x['to'], x['err']))
        sys.exit(1)
    place_all_labels(links, screens)

    # ---- 世界层
    els = []
    for s in screens:
        els.append(card_el(s, pages, links))
    for g in placed:
        els.append('<div class="glab" data-g="%s" style="left:%.0fpx;top:%.0fpx">'
                   '<b>%s</b><em>%s</em><span>%s</span></div>'
                   % (esc(g['name']), g['x'], g['y'], esc(g['name']), esc(g['mods']),
                      esc(g['note'])))
    els.append(doc_el(0, 0, 560,
                      '这块画布怎么看',
                      '<b>左边清单</b>是入口：点一条连线，画布会高亮那条线并飞过去。'
                      '点画布上的<b>蓝色小方块</b>看它自己的说明。'
                      '<br><br>连线上的胶囊写着两件事：<b>前半是交互方式</b>'
                      '（跳转 / 提交 / 弹窗 / 切换 / 返回 / 生效，颜色与线型同它一致），'
                      '后半是这条交互的一组短标签。'
                      '放不下完整胶囊时只写交互方式 —— <b>每条线上都有交互方式</b>，'
                      '这是单独看一条线时必须读得到的信息。'
                      '<br><br>线走的是卡片之间的通道 —— 全程避开页面，'
                      '所以不会把要评审的界面糊掉。'
                      '<br><br>滚轮缩放、拖住空白平移、点卡片看大图。'
                      '缩到 15% 看整体怎么串，放到 100% 看某个按钮长在哪。'))
    lgs = ''.join(
        '<span class="li"><i style="background:%s"></i>%s<b>%d</b></span>'
        % (I.ACTIONS[k]['color'], I.ACTIONS[k]['name'],
           len([x for x in links if x['action'] == k]))
        for k in I.ACTION_ORDER)
    els.append(doc_el(576, 0, 470, '交互方式图例与数量',
                      '<div class="lgx">%s</div>' % lgs))
    n_anchor = sum(len(s['anchors']) for s in emap['screens'])
    els.append(doc_el(1062, 0, 470, '两层标注，别混',
                      '<div class="row"><span class="k">交互点</span>'
                      '<span class="v">蓝色小方块，一个按钮 / 入口 / tab 就是一个</span></div>'
                      '<div class="row"><span class="k">需求落点</span>'
                      '<span class="v">红色框，一条需求落在一整块区域上</span></div>'
                      '<div class="row"><span class="k">本节交付</span>'
                      '<span class="v">%d 条连线 · %d 个交互点 · %d 处需求落点</span></div>'
                      '<br>交互点解决「开发该在哪个元素上挂事件」，'
                      '需求落点解决「这条需求落在哪一块、验收时看哪」。'
                      '两者不能互换，也不能只留一个。'
                      % (len(links), len(idx), n_anchor)))

    svg = render_svg(links, world_w, world_h)
    labels = render_labels(links)

    # ---- HUD
    hud_left = ('<span class="logo">交互标注</span>'
                '<span class="sub">校园订餐 · 一卡通支付与员工折扣 · 05-annotation</span>')
    hud_right = (
        '<div class="panel">'
        '<div class="seg" id="fEnd">'
        '<button class="on" data-e="all">全部端</button>'
        '<button data-e="app">小程序</button><button data-e="admin">后台</button></div>'
        '<div class="seg" id="fChg"><button class="on" data-c="all">全部</button>'
        '<button data-c="new">新增</button><button data-c="rework">改造</button></div>'
        '<input id="q" type="search" placeholder="搜页面 / 元素 / 需求号">'
        '<button class="btn" id="tNum">编号</button>'
        '<button class="btn" id="tDim">只看高亮</button>'
        '<button class="btn" id="tView">视图：<b>业务</b></button></div>')
    mini = ''.join('<i class="page" style="left:%.1fpx;top:%.1fpx;width:%.1fpx;'
                   'height:%.1fpx"></i>' % (s['x'], s['y'], s['w'], s['h'])
                   for s in screens)
    hud_br = (
        '<div class="panel">'
        '<button class="btn zbtn" id="zOut" title="缩小">−</button>'
        '<span class="zv" id="zv" title="点击回到 100%%">100%%</span>'
        '<button class="btn zbtn" id="zIn" title="放大">+</button>'
        '<button class="btn" id="zFit">适应</button>'
        '<button class="btn" id="tAnno">锚点框</button></div>'
        '<div class="mini" id="mini"><div class="mini-l" id="miniL">%s</div>'
        '<div class="mini-vp" id="miniVP"></div></div>')
    hud_bl = ('<div class="tip">交互点 <b id="hitv">%d</b> 页 ｜ '
              '颜色＝交互方式 · 线上的胶囊＝从哪到哪 ｜ 点左边清单定位</div>'
              % len(screens))

    payload = dict(
        world=dict(w=world_w, h=world_h),
        pages={k: dict(v, mainFile='') for k, v in pages.items()},
        brTitle=br_title, brPrio=br_prio, groups=GROUPS, endLabel=END_LABEL,
        manifest=dict(
            els=len(els), cards=len(screens), links=len(links),
            linksOk=len([x for x in links if x.get('ok')]),
            elements=len(idx),
            labelled=len([x for x in links if x.get('labelPos')]),
            hotspots=sum(len(s['vels']) for s in screens),
            anchorBoxes=sum(len(s['anchors']) for s in emap['screens']),
            worldW=world_w, worldH=world_h,
        ),
    )
    for k, v in payload['pages'].items():
        v['mainFile'] = ''
    for s in screens:
        if s['vkey'] == 'main':
            payload['pages'][s['pid']]['mainFile'] = s['page']

    anno = dict(
        links={x['id']: dict(fromEl=x['fromEl'], toEl=(None if x['to'].startswith('#')
                                                       else x['to']),
                             toRef=x['to'], action=x['action'], label=x['label'],
                             note=x['note'], br=x['br'],
                             # key 给面板搜索用：把这条线身上所有能找到它的词都拼进去。
                             # 放在数据源里算，而不是在 JS 里从头拼 —— JS 里拼一遍、
                             # 面板标签拼一遍，两处不同步就会出现「看得见却搜不到」。
                             key=' '.join([x['fromEl'], x['label'], x['note'], x['br'],
                                           x.get('fromPage', ''), x.get('toPage', ''),
                                           idx[x['fromEl']]['label'],
                                           (pages[x.get('toPage')]['name']
                                            if x.get('toPage') in pages else '')]
                                          ).lower(),
                             pts=x['pts'], stubs=x['stubs'],
                             fromRect=x['fromRect'], toRect=x['toRect'])
               for x in links},
        byEl={},
        elRect={},
    )
    for x in links:
        anno['byEl'].setdefault(x['fromEl'], []).append(x['id'])
        anno['elRect'].setdefault(x['fromEl'], []).append(x['fromRect'])
    for k in idx:
        v = idx[k]
        anno['elRect'].setdefault(k, []).append(
            [round(v['wx'], 1), round(v['wy'], 1), round(v['ww'], 1), round(v['wh'], 1)])

    extra_js = ('<script>var ANNO=%s;</script>\n<script>%s</script>'
                % (json.dumps(anno, ensure_ascii=False), EXTRA_JS))

    panel = render_panel(screens, links, pages, br_title)
    doc = CH.render(''.join(els), payload, None, hud_left, hud_right,
                    hud_br % mini, hud_bl,
                    extra_css=EXTRA_CSS % dict(actcss=ACT_CSS),
                    extra_js=extra_js, bodycls='biz',
                    title='交互标注 · 一卡通支付与员工折扣',
                    world_extra=svg + labels, body_extra=panel)
    with open(OUT_HTML, 'w', encoding='utf-8') as f:
        f.write(doc)

    # ---- annotations.json
    elements = []
    for s in screens:
        for e in s['vels']:
            tag, note = I.INPLACE.get(e['el'], ('', ''))
            elements.append(dict(
                el=e['el'], no=e['no'], kind=e['kind'],
                label=e['label'], note=e['note'],
                noGo=tag, noGoReason=note,
                page=e['pid'], screen=e['screen'],
                home=bool(e['home']),
                rectWorld=[round(e['wx'], 1), round(e['wy'], 1),
                           round(e['ww'], 1), round(e['wh'], 1)],
                rectFrame=[e['rx'], e['ry'], e['w'], e['h']]))
    # 卡片矩形必须落在数据源里：check-anno.py 要拿它做「连线不压卡片」的逐段求交。
    # 让校验脚本自己去 layout 一遍是最糟的做法 —— 校验器和生成器各算一遍，
    # 两边一旦漂移，校验就变成"验证另一个实现"，而不是验证产物。
    cards = [dict(pid=s['pid'], vkey=s['vkey'], vname=s['vname'], page=s['page'],
                  rect=[round(s['x'], 1), round(s['y'], 1),
                        round(s['w'], 1), round(s['h'], 1)],
                  frame=s['frame'], dpr=s['dpr'])
             for s in screens]
    data = dict(
        schema='pm-workflow/annotations/v1',
        project=emap['project'],
        note='连线一律从**具体元素**出发。toEl 为空表示目标是页面（toRef 形如 #PG-A3 或 '
             '#PG-A5/yikatong）。stubs[i]=true 表示 pts[i]→pts[i+1] 是引出段，'
             '只有引出段允许落在卡片内部 —— 其余段一律走卡片之间的通道，'
             '所以「连接线不遮挡原型」是可校验的事实，不是观感描述。',
        actions={k: dict(name=v['name'], color=v['color']) for k, v in I.ACTIONS.items()},
        stats=dict(links=len(links), elements=len(idx),
                   hotspots=sum(len(s['vels']) for s in screens),
                   cards=len(screens),
                   byAction={k: len([x for x in links if x['action'] == k])
                             for k in I.ACTION_ORDER},
                   labelled=len([x for x in links if x.get('labelPos')]),
                   labelledShort=len([x for x in links if x.get('labelShort')])),
        links=[{k: v for k, v in x.items() if k != 'ok'} for x in links],
        cards=cards,
        elements=elements,
        inplace={k: dict(tag=v[0], reason=v[1]) for k, v in I.INPLACE.items()},
        world=dict(w=world_w, h=world_h),
    )
    with open(OUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    st = data['stats']
    print('[交互标注] %s + annotations.json' % os.path.basename(OUT_HTML))
    print('  世界画布 %d × %d ｜ 卡片 %d 张 ｜ 交互点 %d 个（热区 %d 处）'
          % (world_w, world_h, len(screens), st['elements'], st['hotspots']))
    print('  连线 %d 条：%s'
          % (len(links), ' · '.join('%s %d' % (I.ACTIONS[k]['name'], v)
                                    for k, v in st['byAction'].items())))
    print('  带标签 %d/%d 条（其中 %d 条只标了交互方式，业务标签见左侧清单）'
          % (st['labelled'], len(links), st['labelledShort']))
    print('  文件 %.1f MB' % (os.path.getsize(OUT_HTML) / 1048576.0))
    print('  [生成通过]')


# ------------------------------------------------------------------ 片段
def card_el(s, pages, links):
    p = pages[s['pid']]
    vr = '' if s['vkey'] == 'main' else ('<span class="el-c c-var">%s</span>'
                                         % esc(s['vname']))
    cls = 'new' if p['change'] == '新增' else 'rework'
    ehs = []
    for e in s['vels']:
        ehs.append('<div class="eh" data-el="%s" data-pg="%s" data-kind="%s" '
                   'title="%s" style="left:%.3f%%;top:%.3f%%;width:%.3f%%;height:%.3f%%">'
                   '<span class="eh-n">%s</span></div>'
                   % (esc(e['el']), esc(e['pid']), esc(e['kind']),
                      esc('%s ｜ %s' % (e['label'], e['note'])),
                      100.0 * e['rx'] / s['img']['w'], 100.0 * e['ry'] / s['img']['h'],
                      100.0 * e['ww'] / s['w'], 100.0 * e['wh'] / s['imgH'],
                      esc(e['no'])))
    key = ' '.join([s['pid'], p['name'],
                    ' '.join(e['el'] + ' ' + e['label'] for e in s['vels'])]).lower()
    return ('<div class="el page" id="c%s_%s" data-id="%s" data-vi="%s" data-end="%s" '
            'data-change="%s" data-vname="%s" data-key="%s" '
            'style="left:%.0fpx;top:%.0fpx;width:%.0fpx">'
            '<div class="el-h"><i class="el-ic"></i><span class="el-t">%s</span>%s'
            '<span class="el-c c-%s">%s</span></div>'
            '<div class="el-img" style="height:%.1fpx">'
            '<img src="data:image/png;base64,%s">%s</div></div>'
            % (s['pid'].replace('-', ''), s['vkey'], esc(s['pid']),
               {'main': 0}.get(s['vkey'], 1), esc(p['platform']),
               esc(p['change']), esc(s['vname']), esc(key),
               s['x'], s['y'], s['w'],
               esc(p['name']), vr, cls, esc(p['change']),
               s['imgH'], b64(os.path.join(PROTO, s['shot'])), ''.join(ehs)))


def doc_el(x, y, w, title, body):
    return ('<div class="el doc" style="left:%.0fpx;top:%.0fpx;width:%.0fpx">'
            '<div class="el-h"><i class="el-ic"></i><span class="el-t">%s</span></div>'
            '<div class="doc-b">%s</div></div>' % (x, y, w, esc(title), body))


MARKERS = """
<defs>%s</defs>
"""


def render_svg(links, w, h):
    defs = []
    for k, v in I.ACTIONS.items():
        defs.append(
            '<marker id="ar-%s" viewBox="0 0 12 12" refX="10" refY="6" '
            'markerWidth="11" markerHeight="11" markerUnits="userSpaceOnUse" '
            'orient="auto"><path d="M1 1 L11 6 L1 11 z" fill="%s"/></marker>'
            % (k, v['color']))
    out = ['<svg id="links" width="%.0f" height="%.0f">' % (w, h),
           MARKERS % ''.join(defs)]
    for lk in links:
        act = I.ACTIONS[lk['action']]
        pts = ' '.join('%.1f,%.1f' % (p[0], p[1]) for p in lk['pts'])
        dash = ' stroke-dasharray="%s"' % act['dash'] if act['dash'] else ''
        # 源点：一个小实心圆，明确「这条线是从这个元素出来的」
        p0 = lk['pts'][0]
        out.append(
            '<g class="lk a-%s" id="g%s" data-lk="%s" data-a="%s">'
            '<polyline points="%s" stroke="%s"%s'
            ' marker-end="url(#ar-%s)"/>'
            '<circle class="mk" cx="%.1f" cy="%.1f" r="4" fill="%s"/></g>'
            % (lk['action'], lk['id'], lk['id'], lk['action'],
               pts, act['color'], dash, lk['action'], p0[0], p0[1], act['color']))
    out.append('</svg>')
    return ''.join(out)


def render_labels(links):
    out = []
    for lk in links:
        if not lk.get('labelPos'):
            continue
        act = I.ACTIONS[lk['action']]
        # 短胶囊只写交互方式（业务标签放不下时的降级形态），完整胶囊两段都写
        inner = ('<b style="color:%s">%s</b>' % (act['color'], esc(act['name']))
                 if lk.get('labelShort') else
                 '<b style="color:%s">%s</b><i>%s</i>'
                 % (act['color'], esc(act['name']), esc(lk['label'])))
        out.append('<div class="lbl%s" data-lk="%s" style="left:%.1fpx;top:%.1fpx;'
                   'border-color:%s">%s</div>'
                   % (' short' if lk.get('labelShort') else '',
                      lk['id'], lk['labelPos'][0], lk['labelPos'][1],
                      act['color'], inner))
    return ''.join(out)


if __name__ == '__main__':
    build()
