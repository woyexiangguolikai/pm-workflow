# 06 需求卡片画布（推荐形态）

> **06 是 05 的替代**：不要连线，用需求卡片表达「需求 ↔ 原型」的关系。
> 两者**二选一**，不要同时做。

**产出**：`requirement-cards.html` + `cards.json`（数据源）+ `card-canvas.json`（几何）

---

## 1. 形态（用户两次纠偏后的最终结果）

用户原话：
> 「我需要像之前一样在画布上展示所有的原型，你这样做开发没办法把原型关联起来」
> 「是画布放原型，需求卡片放侧边栏，用户点击卡片展开原型需求卡片看详细内容」

- **画布只放原型**，按端分**两条泳道**（小程序一行、后台一行）
- **需求卡片放右侧栏**，按**页面分组**
- **点卡片展开**（**手风琴**：开一张收其他）
- **点卡片 → 画布飞到它的落点框并高亮**
- 落点靠 `.an` 锚点框表达，**不画连线**

## 2. 🔴 两个视角都要有（重要设计原则）

| 视角 | 载体 | 粒度 | 回答的问题 |
|---|---|---|---|
| **需求视角** | 需求卡片 | 一条需求一张卡 | 这条需求要做什么 |
| **界面视角** | 页面级元素总表 | 一个元素一行 | 这个元素被谁管着 |

**少了界面视角，「某元素没写进任何需求」这类漏项就永远看不见。**

### 卡片内容（默认折叠，展开后全给）

折叠态 = **标题 + 计数微标**。展开态给 15 类信息：
涉及端与职责 · 字段展示/来源/限制 · 交互说明 · 动效 · 风险机制 · 触发机制 · 输入输出 ·
按钮与布局跳转 · 规则 · 关联字段 · 接口 …

### 页面级元素总表

放侧栏卡片流**末尾**（`<details>` 默认折叠），三列：`元素/类型` · `标签/位置` · `归属需求`。

未归属行整行**淡黄底** + 「未归属 · 骨架/内容」标签。
- 点**需求号** → 飞到落点框 + 侧栏展开对应卡片
- 点**元素行** → 飞到元素位置并闪一个**青色**定位框（`.an.flash-hi`，与蓝色落点框区分）

数据源：`cards.json` 的 `groups[].allElements[]`，字段：
`el` / `kind` / `kindCn` / `label` / `note` / `slotH` / `slotV` / `screen` / `unownedKind` / `coveredBy`。

---

## 3. 🔴 三个坑

### ① `elMap` 的 kind 有**四种**

```
Counter({'page': 20, 'var': 5, 'doc': 3, 'blab': 2})   # 共 30
```

`page` 主态 · `var` 补态 · `doc` 文档卡 · `blab` 泳道标签。

- **「原型画面数」= `page + var`**。只数 `kind='page'` 会得 20，与「内联截图 25」对不上。
- 落点框有 **12 处正落在补态卡（`var`）里**。判定「框在不在卡内」只收 `page` → **误报 12 个越界**。
- `manifest.pages = 25` 是**画面数**，侧栏分组是**页面数 20**。**拿 25 比 20 永远差 5。**

### ② 侧栏 id 必须加 `s-` 前缀

`sQ` / `sFEnd` / `sNShown` / `sExpandAll` / `sCollapseAll`

引擎 HUD 的 `#q` / `#fEnd` / `#fChg` / `#hitv` 与侧栏同名 → `bindSeg('fEnd')` 里 `box` 为 null →
**抛未捕获异常，中断整个内联脚本后续所有绑定**。

- 引擎侧：给 `bindClick` / `bindSeg` / `#q` / `#hitv` 加存在性守卫（纯增量，04/05 不受影响）
- 06 侧：改 `s-` 前缀消歧义
- 校验里加「侧栏 id 与引擎 HUD 无撞名」

### ③ `.pg` 的端要写在自己身上

`.lane` 是 `.pg` 的**兄弟不是祖先** → `pg.closest('.lane')` 永远返回 `null` → 端筛选「点后台一张都不剩」。

```html
<section class="pg" data-end="app">    <!-- ✓ -->
```

---

## 4. 🔴 落点框坐标怎么算

坐标来自 `element-map.json` 的 `screens[].anchors[]`，是**页面百分比**（分母是图尺寸）。

转世界坐标必须知道该屏缩略图位置：

```python
SHOT_GEO[(sid, vkey)] = (gx, row_y, w_, hh - HEAD_H - FOOT_H)

fx = e['x'] / img['w'] * card_w      # ⚠️ 分母是 img（图尺寸），不是 viewport
fy = e['y'] / img['h'] * ih
```

产出 `card-canvas.json` 的 `boxes`：`需求号 → [[x,y,w,h,页面id,状态key], ...]`

### 高亮按 `data-br` 在 DOM 里找

```js
document.querySelectorAll('.an[data-br="BR-601"]')
```

**不要按几何反算** → 世界层带 transform，反算易差一个 scale。

### 元素框坐标

`screens[].elements[]` 也有 `x/y/w/h`，**与锚点同一坐标系**（页面百分比）：

```python
def build_el_box_map(emap, el_map):
    out = {}
    for s in emap['screens']:
        img = s.get('img') or s['viewport']
        g = SHOT_GEO.get((s['id'], s['vkey']))
        if not g: continue
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
```

---

## 5. 🔴 CSS 变量必须定义在**共同祖先**上

```css
/* ✗ 只在 .card 上 → 元素总表不在 .card 里，var() 解析失败 */
.card { --cpad-x: 12px; }
/* ✓ 提到 .side 上，整条侧栏共用 */
.side { --cpad-x: 12px; }
```

**后果**：`padding: 4px var(--cpad-x)` 整条声明**作废** → `td` 拿到 `0px`，文字贴边。
**表头列宽是好的**（`th` 第一行定列宽），**只有数据行内边距塌了** —— 看图只是「有点挤」，不报错不崩。

**防复发**：校验里**实测 `computedStyle.paddingLeft >= 8`**，配变异（把变量挪出 `.side`）证明有判别力。

---

## 6. 侧栏窄（420px）时的表格排版

五列（元素/类型/标签/位置/归属）会把每列挤成**竖排换行**（图里出现「图 标」「入 口」）。

**改三列、每格两行**：`元素名+类型` · `标签+位置` · `归属`。
`table-layout:fixed` + `nth-child` 定宽（46 / 27 / 27%）。
元素名用**省略号截断不换行**（换行会把行高撑成两三倍，148 行扫读会散架），完整名字放 `title`。

```css
.el-el{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
```

---

## 7. 脚本

| 文件 | 作用 |
|---|---|
| `_build_cards.py` | 数据模型：从 `prd.json` + `element-map.json` 组卡片，含 `unownedKind` 分类与统计 |
| `build-card-canvas.py` | 画布 + 侧栏（`GROUPS` 等从 `build-canvas.py` 用 `importlib` 加载） |
| `check-card-view.py` | 八组结构检查 + 内联变异测试 |
| `_verify.js` | 真渲染断言（DOM 计数 / 交互 / 几何 / 计算样式） |
| `_shots.js` | 固定视角预览图 |
| `_card_css.css` / `_card_js.js` | 侧栏样式与交互（`body_extra` 注入） |

模板见 `assets/templates/06-anno-card/`。

### 🔴 分组定义单一来源

```python
import importlib.util
spec = importlib.util.spec_from_file_location('bc', HERE / 'build-canvas.py')
bc = importlib.util.module_from_spec(spec); spec.loader.exec_module(bc)
GROUPS = bc.GROUPS; CARD_W = bc.CARD_W; HEAD_H = bc.HEAD_H
```

**不要复制一份。** 并且 `build-canvas.py` 结尾必须有 `if __name__ == "__main__":`，
否则 `exec_module` 会把整个构建跑一遍。

### 🔴 侧栏卡片视角要用 `data-boxes` 现算

不能对侧栏的 `.card` 用 `__centerOn__`（它不在世界层）。
按 `data-boxes` 的世界坐标算包围盒：

```js
var boxes = JSON.parse(c.dataset.boxes || '[]');
var x0 = Math.min.apply(null, boxes.map(b => b[0])), x1 = Math.max.apply(null, boxes.map(b => b[0]+b[2]));
// ... __setView__(kk, board.clientWidth/2 - (x0+x1)/2*kk, ...)
```

---

## 8. 校验清单（八组 + 变异）

| 组 | 查什么 |
|---|---|
| ① 数据源自洽 | `manifest.els == elMap` 数；`manifest.cards == cards.json` 卡片数；`anchorBoxes == boxes` 展开总数；boxes 的键全部命中需求号；所有元素在世界内 |
| ② 画布结构 | 原型画面数 == 内联截图数；落点框数 == boxes 数；`data-br` 全部能对回需求号 |
| ③ 侧栏结构 | 容器存在；泳道 2 条；**分组数 == 页面数（不是画面数）**；全部 `.pg` 带 `data-end`；卡片数；**id 与引擎 HUD 无撞名** |
| ④ 卡片内容 | 卡片 id 双向对账；分区数现算；空分区说明 |
| ⑤ 视图不漂移 | 每个需求号的 `data-boxes` 与 JSON **逐字一致** |
| ⑥ 版式规范 | 折叠态 `.ch` 与展开态 `.cb` **共用 `--cpad-x`**；侧栏让位（`#board` 与右上/右下 HUD 一起让位） |
| ⑦ 落点闭环 | 原型卡几何数 == `page + var`；**全部落点框落在对应卡内（范围含 `var`）**；页面 id 全部有效 |
| ⑧ 元素总表 | 容器存在；行数 == `allElements`；未归属行数 == 现算；页面分组数；归属标签数 == 现算覆盖关系 |

### 变异测试（7 条，每条都要真破坏）

| # | 变异 | 断言变红 |
|---|---|---|
| M1 | 删掉落点框（`replace_all`） | `anchors 53 → 0` |
| M2 | 拆掉异常守卫（两处同名实现都改） | `errs` 非空 |
| M3 | 侧栏容器移除 | `geom.side` 变 `null` |
| M4 | 真删 `.pg` 的 `data-end` | `adminVisible` 归零 |
| M5 | 拆掉手风琴 | 同时展开多张 |
| M6 | 元素总表不输出 | 探针数到 0 行 |
| M7 | 把 `--cpad-x` 挪出 `.side` | 总表 `td` padding 掉到 0px |

### `_verify.js` 断言组

`errs` / `counts` / `accordion` / `fly` / `clickAnchor` / `search` / `filter` /
`expandAll` / `geom` / `layout` / `elTable` / `elTablePad` / `elTableFly` / `elTableEl`

---

## 9. 复跑

```bash
cd 06-anno-card && python build-card-canvas.py && python check-card-view.py && node _verify.js && node _shots.js
```

⚠️ **改了原型元素先回 04 跑 `build-proto.py`** 刷新 `element-map.json`。

### 实测基线

世界 **5536×2087** · 元素 **30**（画面 25 = 主态 20 + 补态 5 · 文档 3）· 页面 **20** ·
卡片 **42** · 落点框 **53 处 / 42 个需求号** · 元素总表 **148 行 / 74 未归属 / 20 分组** ·
`check-card-view.py` **36 项 + 7/7 变异全绿** · `_verify.js` **13 组断言 + `errs:[]`** · 文件 **10.2 MB**

另：`_mut/` 里会残留 Edge 临时 profile（实测 **54M**），跑完清掉。
