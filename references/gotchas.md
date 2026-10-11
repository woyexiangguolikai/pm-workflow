# 踩坑总表

> 按「症状 → 根因 → 修法」写。**看症状能查到根因**是这个文件的价值。

---

## 一、环境（本机 Windows）

### 🔴 Node 的 `spawnSync` / `execSync` 恒报 `EBUSY`

`errno -4082`。连 spawn 自己 `process.execPath` 都失败；**异步 `spawn` 完全正常**。

```js
// ✗ 恒失败
const r = require('child_process').execSync('node -v');
// ✓ 用 spawn + Promise
const r = await new Promise(res => {
  let o = '';
  spawn(NODE, args, { stdio: ['ignore','pipe','pipe'] })
    .on('close', c => res({ code: c, out: o }))
    .stdout.on('data', d => o += d);
});
```

排查过：不是沙箱、不是路径斜杠、不是 System32 重定向。Bash 工具与 PowerShell 工具里都一样。

### Shell

- **Windows 上以 PowerShell 7 为准。** 本文档所有命令按 **PowerShell 7** 写
  （`&&`、`||`、`?:`、`??` 都可以用）；macOS / Linux 换成对应的 bash 命令。
- ⚠️ **不要为了兼容旧版本而降级语法。** 曾把「命令要 5.1 也能跑」当成硬约束写进文档，
  结果是把**一台机器上的工具限制**变成了**对所有使用者的要求**。
  **版本下限只该由工作流真正依赖的东西决定。**
- **没有 Git Bash**。唯一可用的 bash 是 PortableGit：`%USERPROFILE%\.workbuddy\binaries\PortableGit\versions\<ver>\bin\bash.exe`。
  ⚠️ **不要写死用户名** —— 脚本里用 `os.path.expanduser('~')` 或 `$env:USERPROFILE` 推导。
- 工具里**禁止 `cmd.exe`**（会被安全策略挡掉），要用原生 cmdlet。

### POSIX → PowerShell 对照

| 想要 | PowerShell 里怎么写 |
|---|---|
| `openssl rand -hex 32` | `$b=New-Object byte[] 32;[Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($b);-join($b\|ForEach-Object{$_.ToString('x2')})` |
| `tar --force-local ...` | `tar ...` —— **去掉 `--force-local`**（Windows 自带 bsdtar 原生认盘符，加了报错） |
| `... \| grep x` | `... \| Select-String x` |
| `which X` | `Get-Command X` |

⚠️ 续行符是反引号，**反引号后不能有空格** → 尽量把命令写成一整行。

### 路径

- Edge 无头**必须绝对路径**，空格用 `%20`。
- Python/Node 都用 managed 版本（见 SKILL.md §环境）。

---

## 二、坐标与截图

### 🔴 截图尺寸 = **窗口**尺寸，不是视口

- **视口 = 窗口 − (24, 92)**；Windows 对窗口宽有下限钳制 → 视口最小 **492**。
- 视口原点就在截图原点 **(0,0)** → 「图上像素 = 视口坐标 × dpr」。

### 🔴🔴 按百分比定位必须用**图尺寸**当分母

用视口当分母会让所有框**整体偏移**，**而且看起来是对的**——最难发现的一类 bug。

```python
# ✓ 分母是 img.w / img.h（截图尺寸）
fx = e['x'] / img['w'] * card_w
# ✗ 用 viewport 当分母 → 整体偏移且看起来正常
```

### 出图时帧必须贴视口左上角

构建期断言 `|x|, |y| ≤ 0.6`。偏移 1px 在 3 倍图上就是 3px 的错位。

### 换机器 / 换 Edge 版本先跑定标

`_viewpad.py` 实测视口原点在截图里的像素位置。**不要写死**。

### PNG 字节级裁剪只能裁右下角

PNG 每行 filter 只引用**本行左侧**和**上一行** → 砍行尾不影响保留部分。
**裁左上或中间必须真解码。**

---

## 三、CSS

### 🔴🔴 CSS 变量必须定义在**共同祖先**上

**案例**：`--cpad-x:12px` 只写在 `.card` 上，而元素总表在 `.side-f` 里、**不是 `.card` 的后代**：

```css
.card { --cpad-x: 12px; }        /* ✗ 只管 .card 自己这一支 */
.side-f td { padding: 4px var(--cpad-x); }   /* var() 解析失败 */
```

→ **整条 padding 声明作废** → `td` 拿到 `0px`，文字贴边。

**为什么隐蔽**：表头列宽是好的（`th` 的第一行决定 fixed 布局列宽），**只有数据行的内边距塌了** —— 看图只是「有点挤」，不报错、不崩。

- 修法：变量提到 `.side` 上（整条侧栏共用）。
- **防复发**：校验里加**实测 `computedStyle.paddingLeft >= 8`**，并配变异（把变量挪出去）证明有判别力。

### 🔴 `#world` 上绝对不要写 `will-change: transform`

Chrome 会按**当时的缩放**把世界层光栅化成一张贴图，之后缩放只是放大这张贴图。

实测清晰度 **1.75 → 去掉后 3.72（+113%）**。

**正确做法**：基础样式不写，**只在拖拽期间挂上**。
排除过的无效手段：读几何 / 切不透明度 / 两步缩放（全部 **+0.0%**）。

### 窄容器（<450px）里别放四列以上的表

五列会把每列挤成竖排换行（图里出现「图 标」「入 口」）。
**改三列、每格两行** + `table-layout:fixed` + `nth-child` 定宽。
长文本用**省略号截断不换行**（换行会把行高撑成两三倍，几百行扫读会散架），完整值放 `title`。

---

## 四、矩形约定（最大坑，同类错误犯过三次）

| 写法 | 谁用 |
|---|---|
| `(x, y, w, h)` | 排版、`element-map`、`_probe` 的 card、`_edge_point`、`l_connect`、`Router.__init__` 入参 |
| `(x0,y0,x1,y1)` 角点 | `Router` 内部 `obstacles/inflated/free`、`seg_rect_hit`、`_hits`、`_hits_any`、`place_label` 的 obstacles |

**混用不报错**，只让框悄悄变矮变窄（`240` 是宽、也是「x 到 240」），于是「不压卡片」全绿而其实在压。

- **转换只允许在函数入口做。**
- **防复发断言**：「每个元素矩形都落在自己卡片的矩形里」——元素坐标由百分比现算、卡片坐标来自排版，两个量独立，**约定搞反立刻炸**。

---

## 五、DOM / 引擎

### 🔴 引擎取件必须全部加存在性守卫

消费方（如 06）可能**不挂全套 HUD 控件**。原写法 `document.getElementById('tView').onclick=...` 在控件不存在时抛未捕获异常，
**中断整个内联脚本后续所有绑定**（灯箱、键盘、锚点全部失效），而表面只看到「有几个功能不好使」。

```js
function bindClick(id, fn){ var e = document.getElementById(id); if (e) e.onclick = fn; }
function bindClickCtx(id, fn){ var e = document.getElementById(id); if (e) e.onclick = function(){ fn.call(this); }; }
function bindSeg(id, cb){ var box = document.getElementById(id); if (!box) return; /* ... */ }
var hv = document.getElementById('hitv'); if (hv) hv.textContent = shown;
var qEl = document.getElementById('q');    if (qEl) qEl.oninput = function(){...};
```

### 🔴 两个组件共用一份 HUD id 会互相污染

侧栏的 `#q`/`#fEnd`/`#nShown` 与引擎 HUD 同名 → 两套筛选互相打架。
**修法：侧栏 id 全部加 `s-` 前缀**（`sQ`/`sFEnd`/`sNShown`/`sExpandAll`/`sCollapseAll`）。
校验里加一条「侧栏 id 与引擎 HUD 无撞名」。

### 🔴 元素自己的属性 vs 元素之间的关系，分开放

- **内联在元素上**：`data-kind` / `data-label` / `data-note`（元素**自身**属性）
- **放关系表**：「点了去哪」（元素**之间**的关系）

写在页面里会让每一页都知道别的页，改一处要动一片。

### 🔴 `.closest()` 找祖先，找不到兄弟

`.pg`（页面）要读自己的端标记，**必须写在 `.pg` 自己身上**（`data-end`）。
`.lane` 是 `.pg` 的**兄弟不是祖先** → `pg.closest('.lane')` 永远返回 `null` → 端筛选「点后台一张都不剩」。

### 🔴 世界层元素不能用 `__centerOn__` 定位侧栏里的元素

侧栏的 `.card` **不在世界层**，拿它算几何会把视角送到侧栏位置（实测 `x:379` 但画布宽 1156，图里显示的是文档说明区）。
**修法**：按 `data-boxes` 的世界坐标现算包围盒。

### 🔴 同卡连线两元素贴在一起时，直肘会退化成一点

间隙 0~2.5px 时两拐点重合 → 整条线**退化成一个点**（画面上什么都没有，**数据源里它还在**）。
`l_connect` 在 `hsep/vsep < 26` 时**绕一道**。

---

## 六、数据 / 校验

### 🔴 同一个字段名在不同分区形状不同

实测 `cards.json` 各分区 `body`：

```
ends      {end, resp}                                  ← 裸列表！未包在 {'rows':...} 里
fields    {rows:{where,name,field,fmt,mask,empty,note}} 41 张
          {rows:{item,source,tech,mode,fallback}}        1 张   ← 变体
trigger   {rows:{k,v}} 41 张 / {rows:{scene,handling}} 1 张  ← 变体
buttons   {buttons,exits,entry,action,pageTotal,...}
```

**写完数据源要 dump 一遍真实形状再写消费代码**，不要按想象写。

### 🔴 `sections` 是**列表**不是字典

```python
# ✗ AttributeError: 'list' object has no attribute 'values'
for k, v in card['sections'].items(): ...
# ✓
def _n_sections(card): return len(card.get('sections') or [])
```

### 🔴 页面 id 的真实来源

**`prd.pages.app[]` / `prd.pages.admin[]` 里没有 `id` 字段**（只有 `path`/`name`/`requirements`）。
页面 id（`PG-A1`…）**只在 `04-prototype/element-map.json` 的 `screens[].id`** 里。

→ **id 从 emap 取，其余属性从 prd 按 `name` 对上。**

### 🔴 校验器口径错 vs 产物错，先分清

踩过三次，全是**校验器口径错**：

| 报错 | 真相 |
|---|---|
| 「原型元素 20 ≠ 内联截图 25」 | 「画面数」= `page + var`，只数 `page` 得 20 |
| 「侧栏分组 20 ≠ 页面数 25」 | `manifest.pages=25` 是**画面数**，页面数是 **20** |
| 「12 个落点框不在任何卡内」 | 那些框落在 `kind='var'` 的**补态卡**里，范围要加 `var` |

**先怀疑校验，再怀疑产物**（但前提是变异测试已证明校验有判别力）。

### 🔴 `elMap` 的 kind 有四种

```
Counter({'page': 20, 'var': 5, 'doc': 3, 'blab': 2})   # 共 30
```

`page` 主态 · `var` 补态 · `doc` 文档卡 · `blab` 泳道标签。
**「原型画面数」= `page + var` = 25。**

---

## 七、流程

### 🔴 散文里不能手写接口编号

`note` / `preconditions` 里写「见 SVC-009」会**泄漏到业务视图**。
有专门的守卫脚本做 10 类正则检查。

### 🔴 `_expand_lib.recompute` 不回写功能节点状态

必须用 `_finalize.py` 补。

### 🔴 手写静态章节决策落定后要手动对齐

`PRD.md` 第 4 章是手写静态文本 → 决策改了不改它，会出现**互相打架的条款**。

### 🔴 生成脚本必须有 `if __name__ == "__main__":`

否则 `importlib` 加载它取常量时会**把整个构建跑一遍**。

### 🔴 分组定义单一来源

`build-card-canvas.py` 的 `GROUPS` / `END_LABEL` / `CARD_W` 等从 `build-canvas.py` 用 `importlib.util` 加载，**不要复制一份**。

```python
import importlib.util
spec = importlib.util.spec_from_file_location('bc', HERE / 'build-canvas.py')
bc = importlib.util.module_from_spec(spec); spec.loader.exec_module(bc)
GROUPS = bc.GROUPS
```

---

## 八、文件与目录卫生

### 🔴 Edge 临时 profile 会残留在项目里

`_mut/` 目录里塞满 Edge profile（实测 **54M**）。**跑完变异测试要清掉。**

### 一次性探针用完就删

`_diag.js` / `_diag2.js` / `_diag3.js` 这类排查工具，定位完问题就删。留着的代价是下次读目录时要逐一判断「这个还有没有用」。

### 预览图命名即视角

`01-全貌.png` / `06-卡片-BR601-落点.png`。**不要留两套命名**（旧形态残留会让目录越来越糊）。

## 六、流程（agent 行为）

### 🔴🔴 写了「允许跳阶段」又没有闸门 = agent 会自由发挥

**事故**：新机器、新项目。用户一句「帮我做 XX」，agent 直接跳过 00 盘点和 01 需求澄清，
没有做任何苏格拉底式追问就开工 —— 做出来的东西不一定适用。
**根因有两个，都在 SKILL.md 自己身上**：
① 明文写着「**允许跳阶段**：已有 PRD 时直接进 04」—— agent 把「允许」读成了「默认可以跳」；
② 只说了产出物，**没定义「过闸条件」**，跳了也没有任何东西报错。
**修法**（已落实）：
1. 「允许跳阶段」改为**阶段闸门表**：00 条件必做（由第 0 问的项目性质决定）、01/02/03/04 必做、05/06 二选一必做；
2. 跳过必须**显式确认**（用户沉默不算），并记进 `project.json` 的 `skipped`；
3. 澄清协议化：**第 0 问（项目性质）+ 12 个问题域（每个域标了答案的消费方）+ 追问节奏 + 过闸三条**，
   落盘 `01-requirements/clarify-log.md`，见 `references/00-audit-and-01-requirements.md`。
**教训**：给 agent 的规则里，「没有禁止」不等于「禁止」；**每个允许跳过的口子，必须配一个可判定的闸门**，
否则「规则生效」与「规则不存在」两个世界没有区别 —— 又是判别力红线在流程层的翻版。
