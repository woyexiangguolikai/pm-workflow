# 03 设计

**产出**：`tokens.json`（设计 token）+ `design-spec.md` / `design-spec.html`（双视图）+ `shots/`（视觉稿）

---

## 1. 设计 Token 集中管理

**所有颜色/字号/间距/圆角/阴影都进 `tokens.json`**，页面不许写死。

```json
{
  "color": {
    "brand":  { "value": "#2563eb", "desc": "主色" },
    "n0".."n900": { "value": "...", "desc": "中性色阶" },
    "ok": {...}, "wn": {...}, "er": {...}, "nt": {...}, "dc": {...}
  },
  "space":  { "s1": 4, "s2": 8, "s3": 12, "s4": 16, "s6": 24 },
  "radius": { "r1": 4, "r2": 6, "r3": 10, "rFull": 999 },
  "type":   { "h1": {...}, "body": {...}, "caption": {...} }
}
```

**校验**：扫描页面定义，断言所有颜色值都能在 token 里找到 → 找不到就是硬编码。

> 这条是**产品化前提**：token 集中了，换主题/换客户只改一个文件。

---

## 2. 🔴 后台端视觉与商家品牌主题**不同源**

后台是**独立视觉**（`#2563eb` + n0~n900 中性色阶，设计基准宽 1440），
**不跟随商家品牌主题** —— 后台是内部工具，稳定比花哨重要。

### 语义色 vs 涨跌色

🔴 **两者不同源**：
- 对账差异用**语义状态色**（`ok` / `wn` / `er`）
- **不要用涨跌红绿** —— 中国股市红涨绿跌，但财务对账的「差异」不是涨跌

折扣让利用 `dc` + 「**−**」符号。

### 布局

左导航 **216** + 顶栏 **52** + 内容区。

### 组件清单

`.card` / `.callout` / `.tag` / `.pill` / `.btn` / `.fi` / `.sw` / `.opt` /
`table.tb` / `.kpi` / `.chip` / `.seg` / `.plist` / `.calc`

---

## 3. 🔴 后台端三个坑

### ① `nav()` 必须整块包在 `.adm-nav` 里

`.adm` 是 flex，**漏掉包裹层会让导航与正文并排挤一行**
（导航被拉成 1000+px、正文只剩 400+）—— 表现像「内容太多」，**很迷惑**。

### ② 「无默认值的必选项」未选状态**不要用错误色填充背景**

会被读成「**已选中**」—— **恰恰相反**。

正确做法：**错误色边框 + 文字 + `必选` 标签**，不要填背景。

### ③ 页面定义用 `P(**kw)` 收集，`platform` 在 `P()` 里统一打上

不要在每处手写 `platform` —— 漏一个就是一次 bug。

---

## 4. 锚点（阶段衔接）

03 产出 **`data-anchor`（需求落点）** —— 一块区域，**一条需求一处**。

```html
<div data-anchor="BR-101" class="...">  ...  </div>
```

04 原型的页面定义继承这些锚点，05/06 直接读。

**校验**：每个锚点的需求号在 PRD 里存在（跨阶段闭环）。

---

## 5. 视觉稿（`shots/`）

产物（双视图各一套）：

```
shots/
├── overview.png  color.png  component.png  primitive.png  page.png  a11y.png
└── tech-overview.png  tech-color.png  tech-component.png  tech-page.png  tech-primitive.png
```

另有 `zoom-*.png` 局部放大图（`ladder` / `anchor` / `component` / `lexicon` / `page`）。

**出图手法**同 04：Edge 无头 + 绝对路径。

---

## 6. 脚本

| 文件 | 作用 |
|---|---|
| `_color_lib.py` | 色阶生成（n0~n900） |
| `_lexicon.py` | 文案词表（统一用语） |
| `_extract_tokens.py` | 从页面定义反向抽取实际用到的值 → 与 `tokens.json` 比对 |
| `build-tokens.py` | token → CSS |
| `build-view.py` | `tokens.json` → `design-spec.html`（双视图） |
| `build-doc.py` | → `design-spec.md` |
| `_dv_page*.py` / `_dv_component.py` / `_dv_primitive.py` | 视觉稿页面定义 |
| `check-design.py` | 校验 |

---

## 7. 校验要点

| 查什么 | 怎么查 |
|---|---|
| 无硬编码颜色 | 扫描页面定义，颜色值必须都在 token 里 |
| 对比度 | 关键文字/背景组合算对比度 ≥ 4.5:1（正文） |
| 双视图不漂移 | `design-spec.html` 与 `tokens.json` 逐字比对 |
| 锚点闭环 | 每个 `data-anchor` 的需求号在 PRD 里存在 |
| 视觉稿齐全 | 两类视图各 5 张，且尺寸符合预期 |

⚠️ **对比度检查样本为 0 判失败**（没有文字对就说「通过」是假检查）。
