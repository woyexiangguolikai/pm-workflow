# 04 原型 —— 白板式无限画布

**产出**：`prototype-canvas.html`（画布）+ `element-map.json`（元素坐标清单）+ `pages/`（单页 HTML）+ `shots/`（基准图）+ `preview/`（预览图）

---

## 1. 两个坐标系（别混）

| 坐标系 | 含义 | 谁算 |
|---|---|---|
| **世界坐标** world | 元素在画布上的位置 | `build-canvas.py` 算好**写进内联样式** |
| **屏幕坐标** screen | 世界经 `translate(vx,vy) scale(vs)` 后显示的位置 | 引擎的 `apply()` |

**两边不交叉。** 元素绝对定位，显示 = `translate(vx,vy) scale(vs)`；`#world{transform-origin:0 0}`。

### 以鼠标为中心缩放

```js
vx = cx - k*(cx - vx);   // k = 新scale/旧scale
vy = cy - k*(cy - vy);
```

改 `scale` 时**必须同步反解** `vx/vy`，否则画面往左上角跑。

### 点阵跟随缩放

```js
dots.style.backgroundSize = (24*vs) + 'px ' + (24*vs) + 'px';
dots.style.backgroundPosition = vx + 'px ' + vy + 'px';
```

### fit 的包围盒必须含组标签

```js
[].slice.call(document.querySelectorAll('.glab,.blab')).forEach(...)
```

漏掉的话 fit 之后标题会被挤出屏幕。

### 拖拽 4px 阈值

超过 4px 当**平移**，不触灯箱。否则轻微手抖就点开了灯箱。

### 卡宽按端取

小程序 **248px** / 后台 **460px**（后台界面本身宽）。

---

## 2. 🔴🔴 `#world` 上绝对不要写 `will-change: transform`

Chrome 会按**当时的缩放**把世界层光栅化成一张贴图，之后缩放只是放大这张贴图
—— 于是在 fit 视图（0.44）光栅化，放大到 2 倍就是放大 0.44 倍的图，**糊得肉眼可见**。

**实测：清晰度 1.75 → 去掉后 3.72（+113%）。**

**正确做法**：基础样式**不写**，**只在拖拽期间挂上**换来流畅度，松手就撤掉 —— 静止时一定是清晰的那一版。

**排除过的无效手段**（全部 +0.0%）：读几何 / 切不透明度 / 两步缩放。

### 缩放上限由像素预算现算，不是常数

```js
maxZ = min(8, max(1.2, naturalWidth / (clientWidth * dpr)))
```

卡片把一张图显示成 `clientWidth` 宽，放到 `z` 倍时设备上要占 `clientWidth*z*dpr` 像素；源图只有 `naturalWidth` 像素。

**写死 3.2 的后果**：150% 缩放（dpr=1.5）时源图只够撑到 2.77，超过就必然糊。
实测：`1032 / (248 × 2) = 2.08`。

**两条断言缺一不可**：`check-proto.py` 的「清晰度预算」+ `_verify_sharp.py`。

---

## 3. 引擎接口（`_canvas_html.py`）

```python
render(world_html, payload, stats, hud_left, hud_right, hud_br, hud_bl,
       extra_css='', extra_js='', bodycls='biz', title=..., 
       world_extra='', body_extra='')
```

**`render()` 已参数化**，05 / 06 直接复用，不要复制一份引擎。

### 引擎暴露给外部的视角控制口

```js
window.__setView__(k,x,y)   // 设视角，返回 {k,x,y}
window.__getView__()        // 读视角
window.__fit__(pad)         // 适配，返回新视角
window.__centerOn__(el,k)   // 居中到元素（⚠️ el 必须在世界层里）
```

**为什么必须由引擎暴露**：`vx/vy/vs` 是闭包变量。
在外部「猜」一个 transform 再写回 `style` 是**错的** —— 下次任何一次 `apply()`（缩放、拖拽、fit）都会覆盖掉。

⚠️ **`__centerOn__` 只能接世界层元素**。侧栏里的 `.card` 不在世界层，拿它算几何会把视角送到侧栏位置。

### 引擎自带的部件

| 部件 | 说明 |
|---|---|
| `.an` 锚点框 | `body.anno .an{display:block}`；`data-i` 显示序号 |
| `.t-only` | `body.biz .t-only{display:none!important}`（双视图开关） |
| 灯箱 `.lb` | `#lbT` `#lbV` `#lbImg` `#lbSide` `#lbPrev` `#lbNext` `#lbX` |
| 小地图 | `#mini` / `#miniL` / `#miniVP`；子项选择器 **`.mini i.KIND`**，kind 名必须与 el_map 的 `kind` 一致 |
| HUD | `.hud.tl/.tr/.br/.bl`；`.hud.tr{right:14px}`、`.hud.br{right:14px}` |

⚠️ **插侧栏后 HUD 必须一起让位**（`right` 要加上侧栏宽），否则被侧栏盖住。

⚠️ **引擎取件全部加存在性守卫** —— 见 `references/gotchas.md` §五。

---

## 4. 出图规格

| | 小程序端 | 后台端 |
|---|---|---|
| 帧选择器 / 设计宽 | `.phone` / 375（出图时 scale 填满视口） | `.adm` / 1440（即视口，不缩放） |
| 窗口宽 / 截图倍率 | 492 + 24 / 3 | 1440 + 24 / 2 |
| 出图样式 | `body` 透明 + `.stage` 去 padding + `.phone` scale + 去阴影 | `.adm{min-height:0}` 让帧贴合内容 |
| PNG 颜色类型 | 6（RGBA） | 2（RGB） |

- 窗口高两端都自适应。**后台若保留 `min-height:100vh`，帧高被撑到整个视口** → 出图变成「一大片空白 + 内容挤在上面」。
- 实测裁剪量：小程序 `1548→1476`（切 72 = 24×3）；后台 `2928→2880`（切 48 = 24×2）。

### 坐标关系（本机实测）

- 截图尺寸 = **窗口**尺寸，**不是**视口；**视口 = 窗口 − (24, 92)**；Windows 窗口宽有下限钳制 → 视口最小 **492**。
- 视口原点就在截图原点 **(0,0)** → 「图上像素 = 视口坐标 × dpr」。
- **图比视口大** → 按百分比定位**必须用图尺寸当分母**（用视口当分母会让所有框整体偏移，**而且看起来是对的**，最难发现）。
- 一次调用**同时**给 `--screenshot` 与 `--dump-dom`，坐标与图同源。
- **样式必须在探针之前注入**；**帧必须贴视口左上角**（构建期断言 `|x|,|y| ≤ 0.6`）。

### 换机器 / 换 Edge 版本先跑定标

`_viewpad.py` 实测视口原点在截图里的像素位置。**不要写死。**

### 「灰蓝色卡片框」的来历与修法

那张框**不是卡片，是舞台底色被截图带进来了**。

1. 出图时把设备框**缩放填满视口** + **透明背景**（`--default-background-color=00000000`）→ 圆角外 alpha = 0。
2. 出图后沿**右下角字节级截断**。`_png.py` 能不解码像素的原因：PNG 每行 filter 只引用本行左侧和上一行 → **砍行尾不影响保留部分**。**裁左上或中间必须真解码。**
3. 三条断言：清单 `crop` 与 `img` 一致；右侧切掉宽度 ≈ (窗口宽−视口宽)×倍率；**裁剪后 `img.w` 必须等于 `frame.w`**。

---

## 5. 锚点模型：两套锚点

| 属性 | 含义 | 粒度 | 谁产生 |
|---|---|---|---|
| `data-anchor` | **需求落点** | 一块区域 | 03 设计（一条需求一处） |
| `data-el` | **交互点** | 一个具体元素 | 04 原型 |

- `data-el` 附 `data-kind`（button/entry/tab/tabbar/field/switch/link/modal/step/chip/row/icon/form）+ `data-label` + `data-note`。
- 🔴 **kind/label 内联在元素上、「点了去哪」放关系表** —— 前者是元素**自身**属性，后者是元素**之间**的关系（写在页面里会让每页都知道别的页）。
- 一条需求多个落点：`landing.anchor` 写主落点，同页第二处用可选键 `extra`（**必须写理由**，防它变成绕过校验的后门）。
- **计数分开报**：`elementRecords`（累计）与 `elementsPlaced`（去重）。
- 元素 id **同屏唯一**、跨状态可重复；取首次出现的画面为 `home`。

---

## 6. 脚本

| 文件 | 作用 |
|---|---|
| `_viewpad.py` | **定标**：实测视口原点在截图里的像素位置 |
| `_png.py` | PNG 字节级右下角裁剪（不解码像素） |
| `build-proto.py` | 页面定义 → 页面 HTML + PNG + `element-map.json` |
| `build-canvas.py` | 页面定义 → 白板画布 |
| `check-proto.py` | 四层校验（产物一致 / 坐标有效 / 锚点闭环 / 真渲染+白板+双视图+清晰度预算） |
| `_preview_shots.py` | 固定视角预览图 |
| `_verify_sharp.py` | **清晰度验证**：画布渲染 vs「源图理想缩放」比梯度均值，含变异测试 |
| `_verify_discriminating.py` | 变异测试：删掉被验证的规则跑同一套探针，必须变红 |
| `_verify_anno.py` | 锚点对齐目视验证图；**倍率逐屏读 `s['dpr']`**，不要写死 |

模板见 `assets/templates/04-prototype/`。

---

## 7. 目录约定

- `shots/` = 被标注的**基准图**（05/06 从这里读）
- `preview/` = 给人看的预览图
- **改了原型元素必须先回 04 跑 `build-proto.py` 刷新 `element-map.json`**，再去跑 05/06

---

## 8. 校验要点

| 查什么 | 怎么查 |
|---|---|
| 产物一致 | 页面 HTML 数 == PNG 数 == `element-map.screens` 数 |
| 坐标有效 | 所有元素在世界矩形内；锚点框落在页面图内 |
| 锚点闭环 | 每个 `data-anchor` 的需求号在 PRD 里存在 |
| 帧贴角 | `|x|,|y| ≤ 0.6` |
| 清晰度预算 | `maxZ` 现算，与 `_verify_sharp.py` 双保险 |
| 双视图不泄漏 | 业务视图里无非锚点的 `.t-only` 可见（**样本为 0 判失败**） |
| 计数不混用 | 去重数与累计数**分开报** |
