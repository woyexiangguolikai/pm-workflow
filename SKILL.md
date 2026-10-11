---
name: pm-workflow
description: 产品经理全流程工作流：盘点 → 需求 → PRD → 设计规范 → 组件库 → 原型 → 需求卡片画布。每阶段产出「JSON 数据源 + HTML 自包含视图」双格式，单一数据源驱动、脚本自校验 + 变异测试，每阶段末尾闭合质量反馈环路（rubric 自评 + 反例库 + 评审流水）。当用户要写 PRD、做需求规格、定设计规范、建组件库、画高保真原型、做需求卡片、把需求与原型关联、盘点存量系统、或提到「产品经理工作流」「PM 工作流」「需求卡片」「原型画布」时使用。
metadata:
  ai.workbuddy.version: 1.1.2
  ai.workbuddy.author: llllll
  ai.workbuddy.homepage: ""
---

# 产品经理工作流

一条从「盘清现状」到「交付可开发原型」的流水线。**七阶段串行**，每阶段独立可停可交付。

```
00 盘点 → 01 需求 → 02 PRD → 03 设计规范 → 03b 组件/素材库 → 04 原型 → 06 需求卡片画布
```

> **05 标注（连线）已取消** —— 用户 2026-10-11 决定：不做连线标注，只保留卡片形态。
> 06 需求卡片画布是**唯一的交付链末层**。原「05 / 06 二选一」的闸门随之作废。

> **03b 是唯一「横向」的阶段** —— 其余阶段每做一个项目产出一次；03b 是**持续往库里加条目**，
> 下次跑工作流时**先检索库**再决定自己做不做。库里没有的，做完可以回填进去（见 `library/README.md`）。

## 何时用哪个阶段

| 阶段 | 触发词 | 产出 |
|---|---|---|
| **00 盘点** | 「盘一下这个系统」「存量系统没有文档」「反向梳理」 | `audit.json` + `audit.html` |
| **01 需求** | 「理需求」「需求清单」「需求澄清」 | `requirement.json` + `requirements.html` |
| **02 PRD** | 「写 PRD」「需求规格说明书」 | `prd.json` + `PRD.md` + `PRD.html` |
| **03 设计规范** | 「设计规范」「设计 token」「视觉稿」 | `tokens.json` + `design-spec.md/.html` + `shots/` |
| **03b 组件/素材库** | 「组件库」「素材库」「设计系统」「看到好动效/组件想收集」 | **`library/` 里的条目**（`c-` 组件 / `m-` 动效 / `p-` 模式 + front matter）+ 脚本生成的 `library/index.json`。**跨项目累积，不是一次性的** |
| **04 原型** | 「做原型」「高保真」「可点击原型」 | `prototype-canvas.html` + `element-map.json` + `pages/` + `shots/` |
| **06 需求卡片画布** | 「需求卡片」「卡片画布」「需求与原型关联」 | `requirement-cards.html` + `cards.json` |

### 🔴 阶段闸门：哪些不能跳、怎么才算过

| 阶段 | 性质 | 过闸条件 |
|---|---|---|
| 00 盘点 | **条件必做**：第 0 问判为「存量改造 / 扩展」→ 必做；全新项目可免 | `audit.json` 存在，功能地图带新旧标注 |
| 01 需求（含澄清） | **必做** | 澄清 12 域无「没问到」、`clarify-log` 无未确认假设、每条需求 `source` 可追溯 |
| 02 PRD | **必做** | 每条需求六分区卡片齐全，check 全绿 |
| 03 设计规范 | **必做**（复用旧规范也要出 `tokens.json` + 一句复用声明） | `tokens.json` + design-spec 过 check |
| 03b 组件/素材库 | **条件必做**：有 >1 端或多页面复用 → 必做；单页一次性界面可免 | 注入的每条素材 front matter 齐全、可检索，且**许可在白名单内**（A4 是唯一「拦截」而非「上报」的判据 —— 漏记许可 = 与「不允许使用」等价） |
| 04 原型 | **必做** | `element-map.json` + 画面 PNG 过 check |
| 06 需求卡片画布 | **必做**（交付链末层） | `cards.json` 过 check，与上游一致 |

1. **上一阶段没过闸，不许开下一阶段的产**。发现没过 → 回去补，不是往下赶。
2. 用户想跳某阶段 → **先讲一句跳过的后果，拿到明确确认才可跳**，并在 `project.json` 里记
   `"skipped": {"stage": "03", "reason": "用户确认复用旧规范"}`。**用户的沉默不算确认。**
3. **禁止「用户一句话就开工做原型」**—— 那是需求漂移的起点，做出来的东西不一定适用。
4. 用户已有现成 PRD 时：02 仍不可免，但工作从「写」变「灌」—— 把现稿内容灌进 `prd.json`
   （下游 04/06 全靠它喂数据），缺失分区照常追问。**不许拿着 Word PRD 直接跳到 04。**

澄清怎么做才不偏移 → `references/00-audit-and-01-requirements.md` §澄清协议（第 0 问 + 12 域 + 追问节奏 + 过闸判据）。
卡片画布怎么做 → `references/06-anno-card.md`。

---

## 🔴 五条铁律（所有阶段通用，违反必出问题）

### 1. 单一数据源：先改数据源，再重新生成视图

每阶段都是 **`*.json`（喂脚本）+ `*.html`（给人看）** 双格式。**HTML 一律由脚本生成**，禁止手写 HTML 里的业务内容。

> **改数据源 → 重新生成视图。** 两者不漂移是这套工作流的根。

校验里必须有一条**逐字比对**：HTML 里的关键数据与 JSON 完全一致（见 `references/verification.md` §视图不漂移）。

**为什么双格式**（用户原话）：「纯 JSON 可读性不高」「需求澄清内容多时记忆负担太重」。

### 2. 校验期望值一律**从数据源现算**，不写死数字

```python
# ✗ 错：写死 42，改了数据源就假绿
assert len(cards) == 42

# ✓ 对：从数据源现算
assert len(cards) == len(json.load(open('cards.json'))['cards'])
```

写死数字的检查在数据源变更后**照样全绿**，等于没有检查。

### 3. 两种计数不能混用

**去重落位数**（`elementsPlaced`）≠ **各画面累计出现次数**（`elementRecords`）。
同一个元素在 3 个补态里出现 → 去重算 1、累计算 3。**报数时必须标明是哪种**，否则校验永远对不上。

### 4. 不证明判别力的检查等于没有检查

写完任何检查，**必须做一次变异测试**：把被验证的东西删掉，同一套探针**必须变红**。

⚠️ **「真破坏」才算数**（踩过三次）：
- ✗ 给元素加 `hidden` 属性 —— 元素还在 DOM 里，选择器照样数得到
- ✗ 给 `data-x` 前面插个属性 —— `data-x` 还在
- ✗ 只改 `bindClick` 没改 `bindClickCtx` —— 另一个同名实现顶着
- ✓ **删标签 / 删属性 / 同名实现全量替换**，并断言被验证的量**真的变了**（`anchors 53→0`、`errs` 非空）

**样本为 0 时判失败**，不是「无事通过」。详见 `references/verification.md`。

### 5. 感知类结论必须给**可量化替代指标**

不许说「应该没压」。要算「**最小间距 20.9px**」。
要看图时，给画布**描上判定用的红框**再截图，把「有没有压」变成一眼可判。

---

## 🔴 反馈层 —— 工作流自我改进（每阶段末尾必须闭合）

**为什么需要它**：五条铁律 + 全部 check 保证的是「**不崩**」，不是「**好**」。
一份平庸但格式完整的产出能全绿通过。**测量什么就得到什么；没被测量的质量等于没有质量。**

```
阶段产出 → 按 rubric 自评 → 人评（只看打问号的项）→ 提炼 → 写回 feedback/
```

**🔴 本体与产出必须分开**：`feedback/` 只放**判据本体**（跨项目复用）；
**单次评审的产出**（报告、流水、锚定结论）写到**项目目录** `<项目>/feedback-review/`。

| 路径 | 内容 | 加载方式 | 进仓库？ |
|---|---|---|---|
| `feedback/rubric/<阶段>.md` | 质量标尺（A 类可脚本化 + B 类需人判） | **常驻注入**，每阶段 ≤10 条 | ✅ |
| `feedback/anti-patterns.md` | 反例库（只收录**实际发生过**的问题） | **常驻注入** | ✅ |
| `feedback/checks/*.py` | A 类判据检查器 | 运行时执行 | ✅ |
| `feedback/ANCHORING.md` | 不一致锚定规则 + B→A 升级路线 | 遇到冲突时读 | ✅ |
| `<项目>/feedback-review/*.report.md` | 单次评价报告 | 留档 | ❌ 产出 |
| `<项目>/feedback-review/review-log.jsonl` | 评审流水 | 失效判定依据 | ❌ 产出 |

**为什么必须分开**：产出里含**真实业务参数**（阈值、比例、通道、内部文件清单）——
那是项目的资产，不是工作流的资产。**把产出留在本体目录，等于违反自己的规矩。**

**四条纪律**

1. **A 类判据必须自动判，不许推给人。** 能脚本化的推给人工 = 浪费唯一的稀缺资源。
2. **人评只看自评打问号的项。** 否则人要从头看一遍产出，兜底就变成瓶颈。
3. **存产出不会让它变好，存判据才会。** 提炼物才进 `feedback/`，原始产物留项目目录。
4. **限长 + 可失效。** rubric 每阶段 ≤10 条；长期不命中或业务已变的判据要删 ——
   旧判据会把新产出带偏。**没有失效机制的知识库会从资产退化成负债。**
   **「待确认」是判据的尸体** —— 能机械化的 B 类必须升级为 A 类（见 `feedback/ANCHORING.md`）。

机制详解与已跑通记录见 `feedback/README.md`。

---

## 标准动作：每阶段怎么跑

### 第 1 步：确认效果再动手（用户明确要求）

> **先讨论确认效果，再动手实现。**

追问规则：**每轮 3–5 题，每题给推荐选项**（用 `AskUserQuestion`）。不要一次抛 10 个问题，也不要自己拍脑袋替用户决定。

### 第 2 步：建目录、写数据源

```
projects/<项目名>/
├── project.json                 # 单一数据源：项目元信息 + 各阶段索引
├── 00-audit/{audit.json, audit.html}
├── 01-requirements/{requirement.json, requirements.html}
├── 02-prd/{prd.json, PRD.md, PRD.html, build-view.py, build-doc.py, check-biz-lang.py}
├── 03-design/{tokens.json, design-spec.md, design-spec.html, shots/, build-*.py, check-design.py}
├── 04-prototype/{prototype-canvas.html, element-map.json, pages/, shots/, preview/, build-*.py}
└── 06-anno-card/{requirement-cards.html, cards.json, card-canvas.json, build-*.py, check-*.py}
```

⚠️ **03b 不在这棵树里** —— 组件/素材库是 **skill 级、跨项目累积**的资产，放在
`<skill>/library/`，不随项目建目录、不随项目归档：

```
<skill>/library/
├── README.md          # 怎么加一条（三步）
├── index.json         # 索引，脚本生成，禁止手改
├── components/        # c-0001-xxx.md
├── motions/           # m-0001-xxx.md
├── patterns/          # p-0001-xxx.md
└── local/             # 私有区，不进 git（见 .gitignore）
```

**怎么用**：跑 03/04 之前先 `library/index.json` 按 tag 检索一遍 —— **先看库里有没有，再决定自己做**。
项目里只记「用了库里的哪几条」（front matter 的 `usedBy`），不复制库内容。

脚本从 `assets/templates/<阶段>/` 拷过去改。**脚本与数据源同目录**（相对路径可用）。

### 第 3 步：写构建脚本 → 生成视图

### 第 4 步：写校验脚本 + 变异测试，跑绿

### 第 5 步：出预览图，目视核对

### 第 6 步：**追加记忆**（`.workbuddy/memory/` 当日日志）

### 第 7 步：**闭合质量环路**（每阶段末尾，不可跳过）

1. 跑该阶段的 A 类检查器：`feedback/checks/check-*.py`，先 `--selftest` 证明判别力，再跑真实产出。
2. 对照 `feedback/rubric/<阶段>.md` 逐条自评，**逐条给证据，不许写「已满足」三个字**。
3. 把打问号的项交给用户 —— **人评只看问号项**。
4. **提炼**：新判据写回 `rubric/`，新反例写回 `anti-patterns.md`，追加一行 `review-log.jsonl`（在项目目录）。
5. 出评价报告 `<项目>/feedback-review/<阶段>-<对象>.report.md`。

> **判据出现假阳性时必须改判据，不能靠人工忽略。** 判据被无视一次，它就永久失效了。
> 首轮实测即因此把 A6 从二元判定改为覆盖率制。

---

## 端枚举（固定，全流程统一）

```
用户小程序 / 管理后台 / 收银端 / 商家端 / 服务端
```

**逐端写职责，禁止「系统自动处理」**。纯服务端步骤（定时任务、对账）执行方写「服务端」。

---

## 编号体系（全流程闭环的骨架）

| 编号 | 含义 | 谁产生 | 谁消费 |
|---|---|---|---|
| `BR-xxx` | 业务规则 / 需求条款号 | 02 PRD | 04 原型锚点、06 卡片 |
| `PG-xx` | 页面 id | 04 `element-map.json` | 06 卡片 |
| `SVC-xxx` | 接口编号 | 02 PRD | 技术视图 |
| `data-anchor` | **需求落点**（一块区域） | 03 设计 | 04 原型 |
| `data-el` | **交互点**（一个具体元素） | 04 原型 | 06 卡片 |
| `c-/m-/p-xxxx` | **素材条目 id**（组件 / 动效 / 模式） | 03b 组件库 | 03 设计、04 原型 |

**闭环**：`BR-xxx` 串起 PRD ↔ 原型 ↔ 卡片。校验必须断言「锚点上的需求号在 PRD 里存在」。

⚠️ **05 连线已下线**，编号体系里不再有「连线起点 / 连线终点」这类概念 —— 交互点由 06 卡片承载。
⚠️ **业务文案里不出现**：表名、字段名、页面路径、接口编号、原型锚点。有专门的守卫脚本（见 `references/02-prd.md`）。

---

## 参考资料（按需读，不要一次全读）

| 文件 | 什么时候读 |
|---|---|
| `references/00-audit-and-01-requirements.md` | 盘点存量系统 / 理需求清单 |
| `references/02-prd.md` | 写 PRD（含卡片六分区模型、双视图、业务语言守卫） |
| `references/03-design.md` | 设计规范 / token |
| `references/03b-components.md` | 组件/素材库：**怎么加一条、许可纪律、工作流怎么吃这个库** |
| `references/04-prototype.md` | 高保真原型、无限画布、出图规格 |
| `references/06-anno-card.md` | 需求卡片画布（交付链末层） |
| `references/verification.md` | **写校验前必读**：判别力、变异测试、Edge 无头 |
| `references/gotchas.md` | **踩坑总表**：环境、坐标、CSS、进程 |
| `references/setup-and-migration.md` | **换机器 / 给别人用 / 重新生成手册** |
| `feedback/rubric/<阶段>.md` | **每阶段开头必读**：质量标尺（常驻注入） |
| `feedback/anti-patterns.md` | **每阶段开头必读**：反例库（常驻注入） |
| `feedback/README.md` | 反馈层机制说明；加新阶段 / 新判据时怎么接 |
| `library/README.md` | **建 / 加素材前必读**：三步加一条、front matter 字段、私有区 |
| `PUBLISHING.md` | **要发布 / 改完代码准备提交时读**：发布前自检、白名单写法 |
| `CONTRIBUTING.md` | 改这套工作流本身时读：改哪一层、判据怎么加、为什么不许静默跳过 |

> `references/05-annotation.md` **已下线**，文件保留仅作历史存档，不要读、不要引。

脚本模板：`assets/templates/<阶段>/`。**拷贝后按项目改名**，别直接引用 skill 目录里的路径。

---

## 打包成手册 / 搬到另一台电脑

**手册**（给人读、存知识库）由脚本**从 `references/` 现渲染**，不手写第二份：

```bash
python <skill>/scripts/build-manual.py --out ./_manual
# → _manual/PM工作流手册.html（侧栏目录，可离线打开）
#    _manual/PM工作流手册.md  （给 IMA / 知识库）
#    _manual/分册/00…09-*.md
```

**🔴 改了 `references/` 里任何一份，都要重跑一次生成器** —— 否则手册与 skill 漂移。

**换机器**：整个 skill 目录是自包含的，拷到目标机的 `~/.workbuddy/skills/` 即可；
**路径不用改**（运行期推导，可用 `WB_NODE` / `WB_NODE_MODULES` 覆盖）；
但**必须重新定标**（`_viewpad.py` 实测视口偏移，它跟 Edge 版本与系统 DPI 有关）。
逐步清单见 `references/setup-and-migration.md`。

**发布 / 分享给别人** → 见 `PUBLISHING.md`（发布前必须跑 `scripts/check-publish-safe.py .` 到 `0 BLOCK`）。

---

## 环境（Windows）

**路径全部运行期推导，没有写死的本机路径**（自 v1.1 起，`scripts/check-publish-safe.py` 守卫）。

- Python：managed 运行时，用 `sys.executable` 取，不要写死
- Node：先读 `$env:WB_NODE`，再扫 `~/.workbuddy/binaries/node/versions/` 取最新；`NODE_PATH` 指向 `.../node/workspace/node_modules`（可用 `$env:WB_NODE_MODULES` 覆盖）
- Edge：`C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe`（没有则试 `C:\Program Files\...`）
- ⚠️ **Node 的 `spawnSync`/`execSync` 恒报 `EBUSY`** → 一律用 `spawn` + Promise
- ⚠️ 没有 Git Bash；PowerShell 5.1 不支持 `&&`
- 详见 `references/gotchas.md`
