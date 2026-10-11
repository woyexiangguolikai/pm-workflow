# PM Workflow · 产品经理全流程工作流

> 一条从「盘清现状」到「交付可开发原型」的 AI Agent 流水线。
> 每个阶段产出 **JSON 数据源 + HTML 自包含视图** 双格式；
> 脚本自校验、检查器带变异测试、**每阶段末尾闭合质量反馈环路**。

**它和「写个 prompt 让它生成一份 PRD」的区别**：这条流水线的重点是**可验证** ——
每个阶段的产物都配一组可执行的判据（rubric + checker），
而判据本身还要用**变异测试**证明它「在被验证的东西坏掉时真的会变红」。

```
00 盘点 → 01 需求 → 02 PRD → 03 设计规范 → 03b 组件/素材库 → 04 原型 → 06 需求卡片画布
```

> 05 标注（连线）已取消，06 需求卡片画布是唯一的交付链末层。

---

## 一、它解决什么问题

产品经理的重复劳动里，真正难的不是「写出来」，而是**每次都写对、且前后不打架**。
三个具体痛点，以及本工作流的对应做法：

| 痛点 | 做法 |
|---|---|
| **产出不稳定** —— 同一份需求，不同时候做出来质量差很多 | 每阶段有 `feedback/rubric/<阶段>.md` 质量标尺（A 类可脚本化 + B 类需人判）；**A 类必须自动判**，不推给人 |
| **改了上游、下游不跟着变** —— PRD 改了字段，原型还是旧的 | **单一数据源**：`*.json` 喂脚本，`*.html` 由脚本生成。改数据源 → 重新生成视图，两者禁止漂移 |
| **同样的错反复犯** —— 每次都要人肉提醒 | **反馈层**：把踩过的坑写成判据，下轮自动注入。**存产出不会让它变好，存判据才会** |

---

## 二、安装

这是一个 WorkBuddy / Claude 风格的 Skill，**放进 skills 目录即可用**。

**Windows（PowerShell 7）**

```powershell
git clone https://github.com/woyexiangguolikai/pm-workflow.git "$env:USERPROFILE\.workbuddy\skills\pm-workflow"
```

**macOS / Linux**

```bash
git clone https://github.com/woyexiangguolikai/pm-workflow.git ~/.workbuddy/skills/pm-workflow
```

**没有 git**：在 <https://github.com/woyexiangguolikai/pm-workflow> 点 `Code → Download ZIP`，
解压后把整个文件夹放到 `~/.workbuddy/skills/pm-workflow/`
（注意别多套一层，变成 `pm-workflow/pm-workflow/`）。

**路径不用改** —— 脚本的运行期依赖（Python / Node / Edge）全部在运行期推导，
只有装在非默认位置时才需要通过 `WB_NODE` / `WB_NODE_MODULES` 环境变量指定。
细节见 [`references/setup-and-migration.md`](references/setup-and-migration.md)。

---

## 三、快速开始

在 WorkBuddy 里直接说话，Skill 会按触发词自动选择阶段：

```
帮我盘一下这个存量系统          → 00 盘点
理一份需求清单                  → 01 需求
写一份 PRD                      → 02 PRD
定设计规范和 token              → 03 设计规范
（看到好组件，收进库）          → 03b 组件/素材库
做个高保真可点击原型            → 04 原型
把这些页面的需求做成卡片画布    → 06 需求卡片画布
```

**第一次跑建议走完整条链**（01 → 06）：只有跑完，才能看到反馈层是怎么在每一环
把上一环的教训捡起来的。

---

## 四、七个阶段，各产出什么

| 阶段 | 产出 | 过闸条件 |
|---|---|---|
| **00 盘点** | `audit.json` + `audit.html` | 功能地图带新旧标注（**条件必做**：存量改造必做，全新项目可免） |
| **01 需求** | `requirement.json` + `requirements.html` | 澄清 12 域无「没问到」、每条需求 `source` 可追溯 |
| **02 PRD** | `prd.json` + `PRD.md` + `PRD.html` | 每条需求六分区卡片齐全，check 全绿 |
| **03 设计规范** | `tokens.json` + `design-spec.md/.html` + `shots/` | tokens + design-spec 过 check（复用旧规范也要出一份 `tokens.json`） |
| **03b 组件/素材库** | `library/` 条目 + `library/index.json` | front matter 齐全、可检索、**许可在白名单内** |
| **04 原型** | `prototype-canvas.html` + `element-map.json` + `pages/` + `shots/` | element-map + 画面 PNG 过 check |
| **06 需求卡片画布** | `requirement-cards.html` + `cards.json` | cards.json 过 check，且与上游一致 |

**闸门规则**：上一阶段没过闸，不许开下一阶段的工。用户想跳阶段时，
必须先讲清跳过的后果、拿到**明确**确认（沉默不算确认）。

---

## 五、四条核心概念

### 1. 单一数据源

每阶段都是 `*.json`（喂脚本）+ `*.html`（给人看）。
**HTML 一律由脚本生成**，禁止手写 HTML 里的业务内容。

> 改数据源 → 重新生成视图。**两者不漂移，是这套工作流的根。**

### 2. 校验必须证明判别力

写完任何检查，**必须做一次变异测试**：把被验证的东西弄坏，同一套探针**必须变红**。

```bash
python feedback/checks/check-prototype.py --selftest
# 好样本全绿 + 坏样本全红 = 有判别力
# 只有好样本全绿      = 等于没测
```

⚠️ 检查器里散落着大量**「踩过一次」**的注释，记的都是真实踩过的坑
（比如「给元素加 `hidden` 不算真破坏 —— 元素还在 DOM 里，选择器照样数得到」）。
**改检查器之前，先把它们读完。**

### 3. 03b 组件/素材库是跨项目累积的

其余阶段每做一个项目产出一次；03b 是持续往库里加条目：

```
library/
├── index.json       # 索引，脚本生成，禁止手改
├── components/      # c-0001-xxx.md
├── motions/         # m-0001-xxx.md
├── patterns/        # p-0001-xxx.md
└── local/           # 私有区，不进 git
```

**看到好的组件 / 动效 / 交互就往里加**；下次跑工作流时**先检索库，再决定自己做**。

许可纪律是硬门槛。白名单：

```
original   public-domain   cc0-1.0   mit   apache-2.0   isc   0bsd
bsd-2-clause   bsd-3-clause   cc-by-4.0   cc-by-3.0
```

GPL 系、`cc-by-nc`、`cc-by-nd`、`proprietary`、**以及没写许可的（`unknown`）**一律拦下 ——
**「忘了记许可」和「许可不允许商用」在数据上等价**，所以按同一标准处理。

怎么加一条 → [`library/README.md`](library/README.md)。

### 4. 反馈层

```
阶段产出 → 按 rubric 自评 → 人评（只看打问号的项）→ 提炼 → 写回 feedback/
```

| 路径 | 内容 | 加载方式 |
|---|---|---|
| `feedback/rubric/<阶段>.md` | 质量标尺（A 类可脚本化 + B 类需人判） | **常驻注入**，每阶段 ≤10 条 |
| `feedback/anti-patterns.md` | 反例库（**只收录实际发生过的**问题） | **常驻注入** |
| `feedback/checks/*.py` | A 类判据检查器（每个都带 `--selftest`） | 运行时执行 |
| `<项目>/feedback-review/review-log.jsonl` | 评审流水 | 失效判定依据 |

**四条纪律**

1. **A 类判据必须自动判，不许推给人。** 能脚本化的推给人工 = 浪费唯一的稀缺资源。
2. **人评只看自评打问号的项。** 否则人要从头看一遍产出，兜底就变成瓶颈。
3. **存产出不会让它变好，存判据才会。** 提炼物才进库，原始产物留在项目目录。
4. **限长 + 可失效。** 长期不命中、或业务已变的判据要删 ——
   **没有失效机制的知识库会从资产退化成负债**。

机制详解 → [`feedback/README.md`](feedback/README.md)。

---

## 六、目录结构

```
pm-workflow/
├── SKILL.md                  # Skill 入口（front matter + 铁律 + 闸门）
├── README.md  LICENSE  CHANGELOG.md  CONTRIBUTING.md  PUBLISHING.md
├── .gitignore  .gitattributes
├── references/               # 各阶段详细方法（按需读，不要一次全读）
│   ├── 00-audit-and-01-requirements.md
│   ├── 02-prd.md
│   ├── 03-design.md
│   ├── 03b-components.md
│   ├── 04-prototype.md
│   ├── 05-annotation.md      # ⛔ 已下线，仅存档
│   ├── 06-anno-card.md
│   ├── verification.md       # 写校验前必读
│   ├── setup-and-migration.md
│   └── gotchas.md            # 踩坑总表
├── feedback/                 # 反馈层 —— 只放「判据本体」，不放产出
│   ├── rubric/               # 6 份质量标尺（每阶段 ≤10 条）
│   ├── checks/               # 8 个检查器（每个都带 --selftest）
│   ├── anti-patterns.md      # 反例库：AP-01 …
│   ├── ANCHORING.md          # 不一致锚定规则 + B→A 升级路线
│   └── README.md             # 机制说明 + 本体/产出的分界线
├── library/                  # 03b 组件/素材库（跨项目累积）
│   ├── components/  motions/  patterns/
│   ├── index.json            # 索引，脚本生成，禁止手改
│   └── local/                # 私有区（不进版本库）
├── assets/templates/         # 各阶段可拷贝的脚本模板
└── scripts/
    ├── build-manual.py               # 从 references/ 现渲染手册
    ├── check-manual.py               # 手册与 references/ 的漂移检查
    ├── check-publish-safe.py         # 发布前自检：密钥 / PII / 本机路径 / 项目词
    ├── md-tables-for-library.py      # 素材库表格渲染
    └── publish-denylist.example.txt  # 项目词黑名单模板（真名单不进库）
```

> **`feedback/` 里只有判据，没有产出。**
> 单次评审报告、评审流水、锚定结论全部写在**项目目录**（`<项目>/feedback-review/`）——
> 因为产出含真实业务参数，那是**项目的**资产，不是工作流的资产。
> 详见 [`feedback/README.md`](feedback/README.md)。

---

## 七、运行环境

| 依赖 | 要求 | 说明 |
|---|---|---|
| **Python** | 3.13+ | 脚本用 `sys.executable` 取解释器，不写死路径 |
| **Node** | 22+ | 卡片渲染用；`NODE_PATH` 指向 `node_modules` |
| **Microsoft Edge** | 近期版本 | 无头截图；先找 `Program Files (x86)`，再找 `Program Files` |
| **Shell** | Windows：PowerShell 7 · macOS / Linux：bash | 本文档的命令按 PowerShell 7 写 |

配套的坑位清单（坐标偏移、CSS 泄漏、`spawnSync` 恒报 `EBUSY`、Babel 中文转义……）
→ [`references/gotchas.md`](references/gotchas.md)。

---

## 八、发布前自检

改完东西准备提交或发布时，**先跑自检**：

```powershell
python scripts/check-publish-safe.py .
```

要求 **`0 BLOCK`**。它扫两类东西，**第二类是重点**：

| 类别 | 扫什么 | 能自动判吗 |
|---|---|---|
| **常规** | 私钥、API Key、数据库连接串、`C:\Users\<用户名>` 形态的本机路径、手机号 / 身份证 / 真实邮箱 | ✅ 内置规则 |
| **项目词** | **商业 know-how** —— 真实阈值、分成比例、付款通道、合作方名称、内部文档名、客户人名 | ⚠️ **要你自己维护名单** |

**为什么第二类必须单独做**：常规规则**一个都抓不到**它。

> **「通过」只证明被检查过的那几类没问题，不证明没问题。**

配置方式：把 `scripts/publish-denylist.example.txt` 复制为 `scripts/publish-denylist.txt`，
按你的项目填词。**真名单本身不进版本库**（它列的就是敏感词）。

白名单（文件级豁免）只有一种写法，且**必须在输出里逐条显式列出**：
在文件任意一行加注释 `# wb-publish-scan: ignore-file`。

> **不要用「改路径绕过扫描」的方式让自检变绿** —— 那等于把泄漏藏起来。
> **豁免名额是稀缺的**：只能给「结构上必须含这类字符串」的文件
> （比如检测器自己的测试样本），不能给「写文档图省事」。

完整规范 → [`PUBLISHING.md`](PUBLISHING.md)。

---

## 九、许可

[MIT](LICENSE) —— 随便用、随便改、随便商用，保留版权声明即可。

> ⚠️ `library/` 里**你自己加进去的素材**不自动继承 MIT。
> 每条素材的 `license` front matter 才是它的真实许可，
> 加入时必须是白名单内的许可（见 §5.3）。

---

## 十、参与贡献

改判据、加反例、贡献素材都可以。
**动手之前先读** [`CONTRIBUTING.md`](CONTRIBUTING.md) ——
里面写了提交纪律（改 `checks/` 或 `rubric/` 必须先跑 `--selftest`；
改 `references/` 必须重渲染手册，否则手册与正文漂移）。
