# -*- coding: utf-8 -*-
"""正交连线路由：走空地、少拐弯、不压卡片。

## 为什么要真的算路，而不是画一条直线或贝塞尔

用户的原话是「连接线不能遮挡其他原型」。在一张 25 屏的白板上：
- 直线会从十几个页面卡上穿过去，正好把要评审的内容糊掉；
- 贝塞尔好看但更糟 —— 曲线覆盖面更大，而且曲率朝哪边完全不可控。

所以做正交（横平竖直）路由，并且**把每一张卡片当成障碍物**，线只能走卡片之间的通道。
正交还有一个好处：线拐弯的地方就是「这里必须让开」，评审一眼能看出算法做了什么。

## 三件事分开做

1. **引出段（stub）**：从元素边界到卡片外的一个空位。这是唯一允许落在卡片内部的线段 ——
   线要从按钮上出发，就必须先穿过卡片本身。stub 是直线，紧贴着法线方向，几乎看不出斜。
2. **通道段**：在卡片外做 A* 搜索，网格化，4 邻域，**转弯罚分**（拐一次 ≈ 多走 9 格）。
   转弯罚分不是为了好看：没有它，A* 会在等长路径里随机挑一条满是阶梯的，
   画出来像锯齿。加了之后自然收敛成「少数几段长直线」。
3. **标签落位**：在最长的那段直线上放一个胶囊标签，逐个候选段试到不压卡片、
   不与其他标签重叠为止。

## 搜索范围

只在两端包围盒 + MARGIN 的范围内建网格。跨端的长连线（后台开关 → 用户端收银台）
要横穿大半个白板，所以找不到路时把 MARGIN 放大一倍再试一次 ——
但**必须先有小范围的结果**，否则每条线都在全图上搜，43 条线能把构建时间撑到几分钟。

## 🔴 矩形约定（本模块最容易踩的坑，出错时完全静默）

只有两种写法，**不要混**：

| 写法 | 长什么样 | 谁用 |
|---|---|---|
| `(x, y, w, h)` | 和排版、element-map 一致 | `_probe` 的 card、`_edge_point`、`l_connect`、`Router.__init__` 的入参 |
| `(x0, y0, x1, y1)` | 角点 | `Router` 内部的 `obstacles/inflated/free`、`seg_rect_hit`、`_hits`、`_hits_any`、`place_label` 的 obstacles |

转换只发生在两个地方：`Router.__init__`（入参 w,h → 出参角点）和 `_probe` 的表头。
这两个数字对**窄卡片**（240 宽）来说恰好长得像（240 是宽，也是"x 到 240"），
混用不会抛异常，只会让框悄悄变矮变窄 —— 于是"不压卡片"全绿而其实在压。
写这套代码时 `_probe` 就踩过一次：`x0, y0, x1, y1 = card` 把宽度当成右边缘，
所有卡片的探测起点都落在同一个 x 上，线从隔壁卡片身上横穿过去。
"""

import heapq
import math

CELL = 14           # 路由网格边长（px）。14 在「够细」和「搜得快」之间
CLEAR = 20          # 障碍外扩。保证线离卡片至少 CLEAR − CELL/2 ≈ 13px
TURN = 9            # 转弯罚分（格）。拐一次 ≈ 多走 126px，换「少拐几个弯」
MARGIN = 420        # 首次搜索的包围盒外扩
MARGIN_BIG = 1400   # 找不到路时的第二次外扩
MAX_STEP = 4000     # 沿法线找一个空位最远找多远
INF = float('inf')


def _dirs(axis):
    return ((1, 0), (-1, 0)) if axis == 0 else ((0, 1), (0, -1))


class Router:
    """一次构建，反复使用 —— 障碍表不变时没必要每条线都重新光栅化。"""

    def __init__(self, obstacles, pad=CLEAR, cell=CELL):
        self.cell = cell
        self.pad = pad
        self.obstacles = [(x, y, x + w, y + h) for (x, y, w, h) in obstacles]
        self.inflated = [(x - pad, y - pad, x1 + pad, y1 + pad)
                         for (x, y, x1, y1) in self.obstacles]

    # -------------------------------------------------------------- 自由空间
    def free(self, px, py):
        for (x0, y0, x1, y1) in self.inflated:
            if x0 <= px <= x1 and y0 <= py <= y1:
                return False
        return True

    # -------------------------------------------------------------- 栅格
    def _raster(self, box):
        c = self.cell
        x0, y0, x1, y1 = box
        ix0 = int(x0 // c) - 1
        iy0 = int(y0 // c) - 1
        ix1 = int(x1 // c) + 1
        iy1 = int(y1 // c) + 1
        w = ix1 - ix0 + 1
        h = iy1 - iy0 + 1
        g = bytearray(w * h)
        for (ox0, oy0, ox1, oy1) in self.inflated:
            # 判定标准是「格子中心是否落在障碍里」：格 i 的中心是 i*c + c/2，
            # 所以 i_min = ceil((x0 − c/2)/c)，i_max = floor((x1 − c/2)/c)。
            # ⚠️ 下界必须是 ceil 而不是 floor。用 floor 会让障碍**每边多占一格**：
            # 目标元素紧贴通道时，它的那一格被判成障碍 → A* 直接判定终点不可达
            # → 表现是「两端都好好的，却说找不到通道」，而且只对某些线发生。
            a = max(ix0, int(math.ceil((ox0 - c / 2.0) / c)))
            b = min(ix1, int(math.floor((ox1 - c / 2.0) / c)))
            p = max(iy0, int(math.ceil((oy0 - c / 2.0) / c)))
            q = min(iy1, int(math.floor((oy1 - c / 2.0) / c)))
            for j in range(p, q + 1):
                row = (j - iy0) * w
                for i in range(a, b + 1):
                    g[row + (i - ix0)] = 1
        return g, ix0, iy0, w, h

    # -------------------------------------------------------------- 空位探测
    def _probe(self, card, side, anchor, box):
        """沿法线方向从卡片边缘往外找第一个**格心为空**的位置。

        两个坐标都必须落在格心上，而不是只对齐法线那一个轴。
        只对齐一个轴的话，A* 的第一个路径点（格心）在另一个轴上会和它差半格，
        于是「起点 → 第一个路径点」这一小段是斜的 —— 7px 的横向漂移摊在 14px 上
        就是 27°，肉眼一眼看得出折角。两个轴都对齐之后，从元素边缘到格心
        最多偏半格（7px），摊在至少 CLEAR+CELL≈34px 的引出段上只有 11°，看不出斜。

        🔴 **撞上别人的卡片就作废，不能绕过去继续往外找。**
        白板上卡片是紧挨着排的（同页主态与补态之间只隔 14px），所以「从卡片左边缘
        往左找空位」经常一出门就撞上左边的邻居。如果这时继续往外走，会在**那张卡片的
        另一侧**找到一个空位 —— 于是引出段从邻居身上横穿过去，画面上就是一条线
        糊在别人的页面上。这种线看起来"两端都对"，只有拿别人的卡片去求交才发现。
        作废之后由 route() 换一条边出去（改走右边或上下）。
        """
        c = self.cell
        # ⚠️ 本模块**只有一个矩形约定：矩形 = (x, y, w, h)**，和排版、和 element-map 一致。
        # 求交/命中判定（seg_rect_hit / _hits / _hits_any / place_label 的 obstacles）
        # 要的是角点 (x0, y0, x1, y1)，所以在**那几处的入口**转换。
        # 这里曾经直接写 `x0, y0, x1, y1 = card`，把宽度当成了右边缘：
        # 于是 base = w + pad，任何卡片探测出来的起始点都是同一个 x（≈273），
        # 引出段根本不在自己卡片旁边 —— 表现为线横穿隔壁卡片，
        # 而且**两端坐标看起来完全正常**，不拿别人的卡片去求交根本发现不了。
        x, y, w, h = card
        x0, y0, x1, y1 = x, y, x + w, y + h
        # 自己的卡片（含外扩）：在这块里走是允许的 —— 引出段本来就要穿过自己的卡
        own = (x0 - self.pad, y0 - self.pad, x1 + self.pad, y1 + self.pad)
        if side in ('r', 'l'):
            base = x1 + self.pad if side == 'r' else x0 - self.pad
            start = ((base // c) + 1) * c + c / 2.0 if side == 'r' \
                else (base // c) * c + c / 2.0
            step = c if side == 'r' else -c
            py = (anchor // c) * c + c / 2.0
            for k in range(int(MAX_STEP / c)):
                px = start + step * k
                if side == 'r' and px > box[2]:
                    break
                if side == 'l' and px < box[0]:
                    break
                if self.free(px, py):
                    return px, py
                if not (own[0] <= px <= own[2] and own[1] <= py <= own[3]):
                    return None                 # 撞上别人的卡片
        else:
            base = y1 + self.pad if side == 'b' else y0 - self.pad
            start = ((base // c) + 1) * c + c / 2.0 if side == 'b' \
                else (base // c) * c + c / 2.0
            step = c if side == 'b' else -c
            px = (anchor // c) * c + c / 2.0
            for k in range(int(MAX_STEP / c)):
                py = start + step * k
                if side == 'b' and py > box[3]:
                    break
                if side == 't' and py < box[1]:
                    break
                if self.free(px, py):
                    return px, py
                if not (own[0] <= px <= own[2] and own[1] <= py <= own[3]):
                    return None                 # 撞上别人的卡片
        return None

    # -------------------------------------------------------------- A*
    def _astar(self, g, ix0, iy0, w, h, s, t):
        c = self.cell
        N = w * h
        dist = [INF] * (2 * N)
        prev = [-1] * (2 * N)
        si = (s[0] - ix0) + (s[1] - iy0) * w
        ti = (t[0] - ix0) + (t[1] - iy0) * w
        if g[si] or g[ti]:
            return None
        # 起点同时以「横向进入」和「纵向进入」两种状态入队，代价都是 0 ——
        # 这样第一步往哪个方向走都不会被误判成一次转弯。
        for d in (0, 1):
            dist[d * N + si] = 0
        txi, tyi = ti % w, ti // w
        h0 = abs(si % w - txi) + abs(si // w - tyi)
        pq = [(h0, 0, 0, si), (h0, 0, 1, si)]
        goal = None
        while pq:
            _, cost, d, u = heapq.heappop(pq)
            if cost > dist[d * N + u]:
                continue
            if u == ti:
                goal = d * N + u
                break
            ui = u % w
            uj = u // w
            for nd in (0, 1):
                add = 1 + (TURN if nd != d else 0)
                for (dx, dy) in _dirs(nd):
                    vi = ui + dx
                    vj = uj + dy
                    if vi < 0 or vj < 0 or vi >= w or vj >= h:
                        continue
                    v = vj * w + vi
                    if g[v]:
                        continue
                    nc = cost + add
                    k = nd * N + v
                    if nc < dist[k]:
                        dist[k] = nc
                        prev[k] = d * N + u
                        # 曼哈顿距离可采纳：每格代价 ≥ 1，转弯只会加不会减
                        hh = abs(vi - txi) + abs(vj - tyi)
                        heapq.heappush(pq, (nc + hh, nc, nd, v))
        if goal is None:
            return None
        # 回溯
        cells = []
        cur = goal
        while cur >= 0:
            d = 0 if cur < N else 1
            u = cur % N
            cells.append((u % w + ix0, u // w + iy0))
            cur = prev[cur]
        cells.reverse()
        return [(ix * c + c / 2.0, iy * c + c / 2.0) for (ix, iy) in cells]

    # -------------------------------------------------------------- 对外接口
    def route(self, elements):
        """elements = [(rect, side, card)] 两个端点，先源后目标。

        返回 (points, stub_flags)：points 是折线顶点，stub_flags[i] 表示
        「points[i] → points[i+1] 这一段是引出段」，只有引出段允许落在卡片里。

        side 只是**首选**。首选那条边出不去的时候（最常见：一出门就撞上隔壁卡片，
        见 _probe），会换边重试 —— 否则一条本来走得通的线会因为"选边选错了"
        被报成找不到通道。候选排序保证首选永远第一个，其余按两端直线距离从近到远，
        所以正常情况下的画法完全不变。
        """
        (ra, side_a, card_a) = elements[0]
        (rb, side_b, card_b) = elements[1]
        primary = pick_side(card_a, card_b)

        cand = []
        for sa in 'rltb':
            pa = _edge_point(ra, sa)
            for sb in 'rltb':
                pb = _edge_point(rb, sb)
                d = abs(pa[0] - pb[0]) + abs(pa[1] - pb[1])
                cand.append((0 if (sa, sb) == primary else 1, d, sa, sb))
        cand.sort()

        for mg in (0, 1):
            for _, _, sa, sb in cand[:10]:
                pa = _edge_point(ra, sa)
                pb = _edge_point(rb, sb)
                m = MARGIN if mg == 0 else MARGIN_BIG
                box = (min(pa[0], pb[0]) - m, min(pa[1], pb[1]) - m,
                       max(pa[0], pb[0]) + m, max(pa[1], pb[1]) + m)
                s = self._probe(card_a, sa, pa[1] if sa in 'rl' else pa[0], box)
                if not s:
                    continue
                t = self._probe(card_b, sb, pb[1] if sb in 'rl' else pb[0], box)
                if not t:
                    continue
                g, ix0, iy0, w, h = self._raster(box)
                si = (int(s[0] // self.cell), int(s[1] // self.cell))
                ti = (int(t[0] // self.cell), int(t[1] // self.cell))
                mid = self._astar(g, ix0, iy0, w, h, si, ti)
                if not mid:
                    continue
                # 探测点本身就是格心（两个轴都对齐过），所以不需要替换 mid 的首尾 ——
                # 替换反而会在路径内部造出一个折角。
                pts = _dedupe([pa] + mid + [pb])
                flags = [i == 0 or i == len(pts) - 2 for i in range(len(pts) - 1)]
                return pts, flags
        return None


def _edge_point(rect, side):
    x, y, w, h = rect
    if side == 'r':
        return (x + w, y + h / 2.0)
    if side == 'l':
        return (x, y + h / 2.0)
    if side == 'b':
        return (x + w / 2.0, y + h)
    return (x + w / 2.0, y)


def _dedupe(pts):
    out = []
    for p in pts:
        if not out or abs(p[0] - out[-1][0]) > 0.01 or abs(p[1] - out[-1][1]) > 0.01:
            out.append(p)
    return out


def pick_side(src_card, dst_card):
    """按两端卡片的相对位置选引出/引入边。返回 (源边, 目标边)。

    只看主轴：横向距离更远就横着进出，纵向更远就竖着。这样两边天然相对，
    引出段最短，也就最不容易压到卡片里的其它内容。
    """
    sx, sy, sw, sh = src_card
    dx, dy, dw, dh = dst_card
    scx, scy = sx + sw / 2.0, sy + sh / 2.0
    dcx, dcy = dx + dw / 2.0, dy + dh / 2.0
    ddx, ddy = dcx - scx, dcy - scy
    if abs(ddx) >= abs(ddy):
        return ('r' if ddx >= 0 else 'l'), ('l' if ddx >= 0 else 'r')
    return ('b' if ddy >= 0 else 't'), ('t' if ddy >= 0 else 'b')


def l_connect(ra, rb, card=None, gap=26.0, bow=13.0):
    """同一张卡片内的两个元素：走一个肘，不绕障碍。

    🔴 两个元素**紧挨着**的时候不能走直肘。tab bar 上两个相邻 tab 的间隙是 0，
    输入框和它右边的按钮间隙可能只有 2px —— 这时肘形的两个拐点会落在同一点上，
    整条线退化成**一个点**（或 2px 的短线），画面上就是"什么都没有"。
    数据源里这条连线还在（计数对得上、清单里也有），只有眼睛看不到它。
    所以间隙小于 gap 时改成**绕一道**：从两个元素的上方/下方出去，横着连过去。

    bow 是绕出去的距离。方向选**空间大的那一侧**（拿卡片矩形比上下余量），
    这样绕出来的那一段落在留白里，不会压在别的控件上。
    """
    ax, ay, aw, ah = ra
    bx, by, bw, bh = rb
    acx, acy = ax + aw / 2.0, ay + ah / 2.0
    bcx, bcy = bx + bw / 2.0, by + bh / 2.0
    hsep = max(ax - (bx + bw), bx - (ax + aw))
    vsep = max(ay - (by + bh), by - (ay + ah))

    def horiz():
        sa = 'r' if bcx >= acx else 'l'
        sb = 'l' if bcx >= acx else 'r'
        p0, p1 = _edge_point(ra, sa), _edge_point(rb, sb)
        return [p0, (p1[0], p0[1]), p1]

    def vert():
        sa = 'b' if bcy >= acy else 't'
        sb = 't' if bcy >= acy else 'b'
        p0, p1 = _edge_point(ra, sa), _edge_point(rb, sb)
        return [p0, (p0[0], p1[1]), p1]

    def outward(axis):
        """绕一道。axis=1 横着绕（从上下出去），axis=0 竖着绕（从左右出去）。"""
        if axis == 1:
            side = _roomier_v(card, ay, ay + ah)
            p0, p1 = _edge_point(ra, side), _edge_point(rb, side)
            y = (ay - bow) if side == 't' else (ay + ah + bow)
            y2 = (by - bow) if side == 't' else (by + bh + bow)
            y = min(y, y2) if side == 't' else max(y, y2)
            return [p0, (p0[0], y), (p1[0], y), p1]
        side = _roomier_h(card, ax, ax + aw)
        p0, p1 = _edge_point(ra, side), _edge_point(rb, side)
        x = (ax - bow) if side == 'l' else (ax + aw + bow)
        x2 = (bx - bow) if side == 'l' else (bx + bw + bow)
        x = min(x, x2) if side == 'l' else max(x, x2)
        return [p0, (x, p0[1]), (x, p1[1]), p1]

    if hsep >= vsep:
        pts = horiz() if hsep >= gap else outward(1)
    else:
        pts = vert() if vsep >= gap else outward(0)
    pts = _dedupe(pts)
    return pts, [True] * max(0, len(pts) - 1)


def _roomier_v(card, y0, y1):
    """上下的余量哪边大。没有卡片信息时默认往下走（卡片顶部靠近标题栏，更容易撞到东西）。"""
    if not card:
        return 'b'
    cx, cy, cw, ch = card
    return 't' if (y0 - cy) > ((cy + ch) - y1) else 'b'


def _roomier_h(card, x0, x1):
    if not card:
        return 'r'
    cx, cy, cw, ch = card
    return 'l' if (x0 - cx) > ((cx + cw) - x1) else 'r'


# ------------------------------------------------------------------ 标签落位
def seg_len(p, q):
    return abs(p[0] - q[0]) + abs(p[1] - q[1])


def place_label(pts, flags, text_w, text_h, obstacles, taken, pad=5):
    """在长的「通道段」上放胶囊标签，压到卡片或别的标签就换下一段 / 换一个落点。

    为什么挑最长的段：短线（尤其是引出段）本来就短，标签放上去会把整条线盖住，
    就再也看不出线是从哪个元素出来的了。

    为什么一段上要试多个落点，而不是只试中点：通道是卡片之间那条缝，
    中点常常正好在某个拐角或卡片的延长线上（卡片是错位排的），
    于是"段够长"却"中点放不下"。只试中点会让一批本来放得下的标签被丢掉 ——
    表现是标签覆盖率没理由地偏低。按「越接近中点越优先」试一串位置，
    放下的标签仍然在视觉中段，但覆盖率高得多。

    注意 obstacles 必须是**角点** (x0, y0, x1, y1) —— 见模块头的矩形约定。
    """
    cand = []
    for i in range(len(pts) - 1):
        if flags[i]:
            continue
        cand.append((seg_len(pts[i], pts[i + 1]), i))
    cand.sort(reverse=True)
    fracs = (0.5, 0.4, 0.6, 0.32, 0.68, 0.25, 0.75, 0.18, 0.82, 0.08, 0.92, 0.0, 1.0)
    # 垂直于线错开一档：胶囊**贴着线**（一边压在线上），而不是只能骑在正中。
    # 为什么需要：同一行里相邻的两组控件，它们的肘线是**共线**的，
    # 于是两个标签抢同一块位置，后放的那个永远放不下。
    # 一上一下各贴一边，就互不打架了。h2 正好让胶囊的边压在线中心上。
    h2 = text_h / 2.0 + pad
    offs = (h2, -h2, 0.0)
    for _, i in cand:
        p, q = pts[i], pts[i + 1]
        horiz = abs(p[1] - q[1]) < 0.01
        for f in fracs:
            bx = p[0] + (q[0] - p[0]) * f
            by = p[1] + (q[1] - p[1]) * f
            for off in offs:
                mx, my = (bx, by + off) if horiz else (bx + off, by)
                box = (mx - text_w / 2.0 - pad, my - text_h / 2.0 - pad,
                       mx + text_w / 2.0 + pad, my + text_h / 2.0 + pad)
                if _hits(box, obstacles) or _hits_any(box, taken):
                    continue
                taken.append(box)
                return (mx, my), box
    return None, None


def _hits(box, rects):
    x0, y0, x1, y1 = box
    for (a0, b0, a1, b1) in rects:
        if x0 < a1 and x1 > a0 and y0 < b1 and y1 > b0:
            return True
    return False


def _hits_any(box, boxes):
    return _hits(box, boxes)


# ------------------------------------------------------------------ 压卡片检查
def seg_rect_hit(p, q, rect, tol=0.0):
    """线段与矩形是否相交（含内部）。用于「连线不能遮挡原型」的校验。"""
    x0, y0, x1, y1 = rect
    x0, y0, x1, y1 = x0 - tol, y0 - tol, x1 + tol, y1 + tol
    if abs(p[1] - q[1]) < 0.01:                      # 水平段
        ya = p[1]
        if not (y0 <= ya <= y1):
            return False
        lo, hi = sorted((p[0], q[0]))
        return lo < x1 and hi > x0
    if abs(p[0] - q[0]) < 0.01:                      # 垂直段
        xa = p[0]
        if not (x0 <= xa <= x1):
            return False
        lo, hi = sorted((p[1], q[1]))
        return lo < y1 and hi > y0
    # 引出段允许斜一点点（法线与格心之间的半格差），按包围盒判
    lo_x, hi_x = sorted((p[0], q[0]))
    lo_y, hi_y = sorted((p[1], q[1]))
    return lo_x < x1 and hi_x > x0 and lo_y < y1 and hi_y > y0
