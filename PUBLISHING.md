# 发布标准（PUBLISHING）

> 让这套工作流成为**别人 clone 下来就能用**的标准版。
> 本文覆盖：仓库布局、发布前自检、白名单规则、版本与发布流程。

---

## 0. 一句话结论

```powershell
# 改完任何东西 → 提交/发布前跑这一条，要求 0 BLOCK
python scripts/check-publish-safe.py .
```

**不是 0 BLOCK 就不要发。** 其余都是细节。

---

## 1. 仓库布局：仓库根 = skill 根

**决定：仓库根目录就是 `pm-workflow/` 本身**，不再多套一层。理由：

- Skill 的安装位置固定是 `<skills_dir>/pm-workflow/`，
  **额外套一层会让 `git clone` 的目标目录与 skill 目录名不一致**，用户必须手动改名。
- `clone` 出来直接就是可用形态：

```powershell
git clone https://github.com/woyexiangguolikai/pm-workflow.git "$env:USERPROFILE\.workbuddy\skills\pm-workflow"
```

```
pm-workflow/              ← 仓库根 = skill 根
├── SKILL.md              ← front matter 是 Skill 的入口契约，必须在根
├── README.md LICENSE CHANGELOG.md CONTRIBUTING.md PUBLISHING.md
├── .gitignore
├── references/  feedback/  library/  assets/  scripts/
```

> ⚠️ `SKILL.md` 的 front matter **必须**是文件的第一个东西，且**只能有一份**。
> 曾经因为「追加而不是替换」出现过两份 front matter，加载器读到的是**旧的那一份**
> （描述里没有 03b 组件库和反馈层）—— 表面文件能打开，实际注册信息全是过期的。
> 改 `SKILL.md` 后确认一下：`name:` 只出现一次。

---

## 2. 发布前自检

```powershell
cd "$env:USERPROFILE\.workbuddy\skills\pm-workflow"
python scripts\check-publish-safe.py .
```

退出码：`0` 可发布 · `1` 有 BLOCK（或 `--strict` 下有 WARN）· `2` 运行错误。

**同一套判据自带变异测试**，改扫描器前先确认它有判别力：

```powershell
python scripts\check-publish-safe.py --selftest
# 好样本 期望可发布   : 通过
# 坏样本 期望有 BLOCK : 通过
```

### 为什么必须是「可复跑的脚本」而不是一份手工清单

发布前的泄露风险是**动态的**：

- 每跑完一次工作流，`<项目>/feedback-review/` 就多一份**含具体项目内容**的记录；
- 每往 `library/` 加一条素材，就可能多一条**来源不明**的条目。

**手工清单一定会过期。** 所以这条判据必须能一键重跑。

---

## 3. 三级分类（不要混）

| 级别 | 含义 | 例子 |
|---|---|---|
| 🔴 **BLOCK** | 绝对不能发布 | 私钥块、`AKIA…`、长串 API Key、`Authorization: "<16+ 字符>"`、数据库连接串、**`C:\Users\<真实用户名>`**、`/home/<用户名>/` |
| 🟡 **WARN** | 逐个人工确认 | 中国大陆手机号、身份证号形态、真实邮箱（`@example.com` / `@test.` / `@xxx` 不算） |
| ℹ️ **INFO** | 仅列出 | 已忽略文件里的命中（例如 `<项目>/feedback-review/` 里的手机号 —— 它不会发出去，只登记） |

**为什么本机绝对路径是 BLOCK 而不是 WARN**：它不只是「暴露作者机器」，
更是**换机器必错** —— 别人 clone 下来会直接因为一路径跑不起来。
所以它同时是**隐私问题**和**可用性问题**，必须挡在发布前。

> **现状**：仓库里已无任何写死的本机路径（自 v1.1）。
> 运行期依赖（Python / Node / Edge）全部自动推导，必要时用
> `WB_NODE` / `WB_NODE_MODULES` 覆盖。见 `references/setup-and-migration.md` §4.1。

---

## 3b. 项目词黑名单（常规规则**抓不到**的那一类）

上面 §3 的三级分类**全是「技术性」泄露** —— 密钥、PII、路径。
但还有一类更严重的，常规规则**一个都抓不到**：

| 类型 | 例子 | 为什么严重 |
|---|---|---|
| **业务参数** | 真实阈值、分成比例、账期、金额上限 | 直接暴露商业模型 |
| **合作方** | 付款通道、供应商、云厂商 | 暴露商业关系 |
| **内部文档名** | 《XX 说明书》《XX 规格书》 | 对别人无意义，却暴露交付物结构 |
| **人名** | 客户、对接人、负责人 | 隐私 + 关系 |

### 这不是假想，是真实发生过的

一次自检报了 `0 BLOCK`，看起来干净 —— 但一份 **224 行的项目复盘**
（含真实阈值 `10min / 500元 / 23:30 / 180天`、分成比例、付款通道、内部文件清单）
**就在待发布目录里，自检一句没提**。

> ### **「通过」只证明被检查过的那几类没问题，不证明没问题。**

### 怎么用

```powershell
# 1) 复制模板
Copy-Item scripts\publish-denylist.example.txt scripts\publish-denylist.txt
# 2) 按你的项目填词（一行一个，# 注释）
# 3) 自检会把它当作 BLOCK 级
python scripts\check-publish-safe.py .
```

**设计上的两个要点**：

1. **真名单不进版本库**（`.gitignore` 已排除）—— 它列的就是敏感词，
   放出去等于把要防的东西自己发一遍。仓库里只有 `.example.txt` 模板。
2. **「没有黑名单」必须被报出来**，不能表现为「没有命中」。自检会打印
   `项目词黑名单: 未配置 → ⚠️ 项目词这一类**未扫描**`。
   **否则又是一个假绿** —— 没配名单看起来和配了名单但没命中一模一样。

> **填什么**：区分「行业常识」与「项目独有口径」。
> 「银行家舍入」是常识（不用填）；「我方与某通道谈定的分成比例」是项目独有（必须填）。

---

## 4. 白名单：唯一被认可的豁免写法

有些文件**结构上必须**包含「像密钥 / 像本机路径」的字符串 —— 典型是**扫描器自己的测试样本**。

**唯一认可的写法**：在文件**任意一行**加注释

```
wb-publish-scan: ignore-file
```

三个硬性要求：

1. **必须显式**，不能用「把字符串拼起来绕过正则」或「改路径」的方式让自检变绿 ——
   那等于**把泄漏藏起来**，比不检查更糟。
2. **必须在输出里被打印**。扫描器会把豁免文件列在 `已豁免 N 个文件` 段落下，
   发布者**逐个复核**。静默跳过 = AP-06 那种「假绿」。
3. **新增豁免必须在下面的登记表里写理由。** 没登记 = 不该存在。

### 豁免登记表

| 文件 | 理由 | 加于 |
|---|---|---|
| `scripts/check-publish-safe.py` | 它是**检测器**，`GOOD_DIR` / `BAD_DIR` 测试样本里必然含「Windows 用户目录形态的假路径」与「手机号形态的假号码」；无豁免则自检永远红，判据会被无视而失效 | v1.0 |

> 📌 **上表刻意不贴那些样本的真实字面量。** 规则文档**不该**嵌入「像密钥 / 像本机路径」的字符串 ——
> 那样它自己就会成为一处待豁免的地方，而**豁免一旦变多，扫描就形同虚设**。
> 描述**类别**就够了，不要贴**样本**。
>
> 写这份文档时就踩了一次：初稿把两个测试样本原样贴进上表，自检立刻报
> `BLOCK 1 · WARN 1`（都指向这一行）。**修法是改文案，不是加豁免** ——
> 给 `PUBLISHING.md` 加豁免会把整份文档（包括将来可能被误粘进去的真凭据）一起放过，
> 那是把洞开在文档里。

---

## 5. `.gitignore` 里每条排除的理由

**「不该发出去」和「不该进版本库」是两回事。** 前者是泄露，后者是噪音。

| 被排除 | 理由 |
|---|---|
| `feedback/review/` | **防御性**：产出**按约定应写到项目目录**（`<项目>/feedback-review/`），不该出现在这里。留这条是防止有人在 skill 目录里就地生成了评审报告 —— 那会**含具体项目内容**。且反馈层的纪律就是「**存判据不存产出**」 |
| `feedback/review-log.jsonl` | 同上，防御性 |
| `library/local/` | 素材库私有区：没把握许可的、内部的、未整理的草稿。**放进来的东西永不发布** |
| `scripts/publish-denylist.txt` | **项目词黑名单本体** —— 它列的就是敏感词，放出去等于把要防的东西自己发一遍。仓库里只放 `.example.txt` 模板 |
| `projects/` | 跑工作流时产生的项目目录（数据源 + 视图都是逐项目产出） |
| `_manual/` | 手册生成物，由 `scripts/build-manual.py` 从 `references/` 现渲染 |
| `__pycache__/` `*.pyc` | Python 缓存 |
| `.DS_Store` `Thumbs.db` `desktop.ini` `~$*` | 系统 / Office 临时文件 |

> **自检脚本会主动核对**这张表：如果某个应忽略的路径**存在但没被 `.gitignore` 覆盖**，
> 它会在输出里报 `🟡 这些路径存在但没被 .gitignore 排除`。
> 所以加新目录时别忘了同步 `.gitignore`。
>
> ⚠️ **`feedback/` 下的一切都要逐条问一句「这是判据还是产出？」**
> 判据（rubric / checks / anti-patterns / ANCHORING）进库；产出（报告 / 流水 / 锚定结论 / 现状页）不进。
> 混进来的后果不是「多一个文件」，而是**把项目的商业参数一起发出去了**。

---

## 5b. 行尾统一（`.gitattributes`）

```
* text=auto eol=lf
```

**这不是洁癖，是发布给别人用的必需品。**

没有它，本机若设置了 `core.autocrlf=true`（Windows 上很常见），
别人 clone 到 macOS / Linux 会遇到：

- 提交时刷出满屏 `LF will be replaced by CRLF` 警告
- `.sh` 脚本报 `bad interpreter: No such file or directory`
- diff 因行尾差异**虚增**，review 时看不出真实改动

**验证方式**：`git ls-files --eol <文件>` 应显示 `i/lf w/lf`（索引与工作区都是 LF）。

### 5b-1. 仓库内必须关掉 `core.autocrlf`（会和 `.gitattributes` 打架）

`.gitattributes` 一旦接管行尾，`core.autocrlf=true` 就成了**第二套互相矛盾的政策**。
两者同时存在时会进入一个很费时间的迷惑状态：

| 现象 | 说明 |
| --- | --- |
| `git status` 说十几个文件被改了 | 看上去像有未提交改动 |
| `git diff` **完全是空的** | 同一个文件，两个命令结论相反 |
| `git update-index --refresh` 报 `needs update` | 刷不掉，越刷越可疑 |
| `git ls-files --eol` 一堆 `w/crlf` | 这才是真正的线索 |

**一条命令解决**（只动本仓库，不碰你的全局偏好）：

```powershell
git -C "$env:USERPROFILE\.workbuddy\skills\pm-workflow" config --local core.autocrlf false
git -C "$env:USERPROFILE\.workbuddy\skills\pm-workflow" add --renormalize .
```

**为什么只改 `--local`**：`core.autocrlf` 是用户级偏好，别的仓库还要用；
本仓库的行尾政策已经写在 `.gitattributes` 里，由它单独负责就够了。

`add --renormalize` 会重写索引。执行前先记下 tree，执行后必须一模一样：

```powershell
git rev-parse HEAD^{tree}     # 刷新前
git add --renormalize .
git write-tree                # 刷新后，必须与前一行相同
```

tree 不变 ⇒ 这次重写是纯粹的 stat 缓存刷新，没有任何内容变化，**远端不需要重推**。
tree 变了 ⇒ 说明真的动了内容，要停下来查清楚，不能直接推。

---

## 6. 素材库的许可约束（**贡献者最容易踩的**）

`library/` 里的素材**不自动继承本仓库的 MIT 许可**。
每条素材的 `license` front matter 才是它的真实许可。

**白名单**（检查器 A4 是唯一「拦截」而非「上报」的判据）：

```
original · public-domain · cc0-1.0 · mit · apache-2.0 · isc · 0bsd
bsd-2-clause · bsd-3-clause · cc-by-4.0 · cc-by-3.0
```

**拦截**（带原因，不允许进库）：

| 许可 | 拦截原因 |
|---|---|
| `gpl*` `agpl*` `lgpl` | 传染性许可，会污染整个仓库的许可 |
| `cc-by-nc*` | 禁止商用（NC）—— 本仓库允许商用 |
| `cc-by-nd` | 禁止演绎（ND）—— 本仓库允许修改 |
| `bsd-4-clause` | 含广告条款，与商用场景冲突 |
| `proprietary` | 专有许可 |
| `unknown` | **许可未标注 —— 与「不允许使用」等价处理** |

> ⚠️ **最后一条是关键**：`unknown` 不是「待补充」，是**拦截**。
> 因为「**忘了记许可**」和「**许可不允许商用**」在数据上完全一样 ——
> 你无法在事后区分它们，所以必须按同一个标准处理。
> 没把握的素材放 `library/local/`（永不发布），整理清楚了再移出来。

发布自检会顺带扫 `library/` 里的许可字段，`local/` 目录整体豁免（并**列出**豁免条数）。

---

## 7. 版本与发布

### 版本号写在哪

**唯一事实源**：`SKILL.md` 的 front matter

```yaml
metadata:
  ai.workbuddy.version: <x.y.z>   # 与 CHANGELOG 段头、git tag 三处一致
```

**同步动作**（改版本号时三处一起动）：

1. `SKILL.md` front matter 的 `ai.workbuddy.version`
2. `CHANGELOG.md` 加一段
3. `git tag v<版本>`

### 发布流程

```powershell
cd "$env:USERPROFILE\.workbuddy\skills\pm-workflow"

# 1) 自检 —— 必须 0 BLOCK
python scripts\check-publish-safe.py .

# 2) 确认 references/ 改过就重渲染手册（否则手册与 skill 漂移）
python scripts\build-manual.py --out .\_manual

# 3) 看一眼到底会提交什么（.gitignore 有没有生效）
git status --short
git check-ignore -v <项目>/feedback-review/ library/local/   # 应打印出匹配的规则

# 4) 提交
git add -A
git commit -m "feat(03b): 素材库改为跨项目累积形态"

# 5) 打标签并推送
git tag v<版本>          # 与 SKILL.md、CHANGELOG 一致
git push origin main --tags
```

### 首次建仓

```powershell
cd "$env:USERPROFILE\.workbuddy\skills\pm-workflow"

git init -b main
git add -A
git commit -m "chore: 初始提交 —— PM 工作流 v<版本>"

# 在 GitHub / Gitee 建好空仓库后：
git remote add origin https://github.com/woyexiangguolikai/pm-workflow.git
git push -u origin main
git push origin --tags
```

> ⚠️ **`git init` 之前先确认 `.gitignore` 已存在**。否则第一次 `git add -A`
> 会把 `feedback/review/`、`library/local/` 一起加进索引 ——
> 之后**即使补上 `.gitignore`，已进索引的文件仍会继续被跟踪**（需要 `git rm --cached`）。

### 7-1. 兜底路径：`git push` 不通时走 API

有些网络环境会**只放通 `api.github.com`、挡掉 `github.com:443`**
（典型症状：`curl https://github.com` 报 `502 CONNECT tunnel failed`，
而 `https://api.github.com/user` 返回 200）。此时 `git push` 用不了，
只能走 Git Data API。四条硬规则：

| 步骤 | 要点 |
| --- | --- |
| 建仓 | 空仓库上**建不了对象**（API 报 `409 Git Repository is empty`）。先用 Contents API `PUT /contents/.seed-placeholder` 塞一个占位文件 |
| 造 blob | 🔴 **字节取自 `git cat-file blob <sha>`，不要打开工作区文件读**。工作区可能是 CRLF，读出来会污染整个远端（见 §8） |
| 造 tree | `POST /git/trees`，`base_tree` 传上一次的 tree，就只需提交**变化的条目**；`path` 可以直接写带 `/` 的完整路径，会自动建子树 |
| 挪 ref | 默认分支**删不掉**（`422 Cannot delete the default branch`），只能 `PATCH /git/refs/heads/main` 带 `force: true` |

**唯一的验收方式：比 tree sha。**

```powershell
# 本地
git rev-parse HEAD^{tree}

# 远端（本机 api.github.com 通、github.com 不通，所以用 curl 而不是 git）
curl.exe -s https://api.github.com/repos/woyexiangguolikai/pm-workflow/git/commits/main
# 输出里的 "tree":{"sha":"..."} 就是远端 tree
```

两个 sha 相同 ⇒ 全部路径 + 全部内容 + 全部文件模式**逐字节一致**，这才是"推成功了"。
文件数量相同、网页上看着对，都**不算**证据。

> 📌 **本次真实踩到**：远端 tree 与本地不一致，第一反应是"GitHub 存了 CP1252"——
> 错的。真正原因是推送脚本读了工作区字节，工作区那 13 个文件是 CRLF、git 里是 LF。
> **先量，别先猜**：`git ls-files --eol` 一跑就现形。

> 📌 **让两边提交 sha 也一致的做法**：远端提交对象的内容（identity / 时间戳 / 消息）
> 与本地不同，sha 就对不上。可以 `POST /git/commits` 时**显式传** `author` / `committer`
> （含 `date`，用 `+08:00` 形式）与**完整消息**，GitHub 会复现出与本地**完全相同**的 sha。
> 注意消息**不要 `.strip()`** —— 尾换行少一个字节，整个对象就不同了。

---

## 8. 不要做什么（反模式）

| ✗ 不要 | 为什么 |
|---|---|
| 用「改路径 / 字符串拼接」让自检变绿 | 把泄漏藏起来，比不检查更糟 |
| 静默跳过豁免文件（不打印） | 就是 AP-06 的「静默假绿」——报告通过，实际什么都没查 |
| **不配项目词黑名单就直接发** | 常规规则**抓不到**商业 know-how。没配名单时自检会明确报「未扫描」——**别把那条提示当噪音** |
| **把逐项目的产出（报告 / 流水 / 锚定结论）留在 skill 目录里** | 那里面是项目的商业参数。**要发布的是工作流的内容，不是工作流产出的内容** |
| 把 `<项目>/feedback-review/` 里的真实项目记录当「示例」提交 | 含客户数据；且反馈层的纪律是存判据不存产出 |
| 在 README 里给 `~/.workbuddy/skills/pm-workflow` 之外**再套一层目录** | 用户 clone 后必须手动改名，装不上 |
| 手工维护一份「发布前检查清单」 | 风险是动态的，清单一定会过期。**必须可复跑** |
| 新增豁免不登记 | 豁免会变成后门。没写在登记表里的豁免**不该存在** |
| 改 `references/` 后忘记重渲染手册 | 手册与 skill 漂移，别人按手册做会和实际不符 |
| 漏掉 `.gitattributes` | 别人 clone 到 macOS / Linux 会拿到 CRLF，`.sh` 直接跑不起来 |
| **走 API 推送时读「工作区字节」** | 工作区可能是 CRLF（或任何未 norm 的形态），git 里存的才是标准形态。**后果是远端每个文件都多一个 `\r`，而你只看 GitHub 网页完全看不出来**。必须取 `git cat-file blob <sha>` 的字节 |
| **推完只对比「文件数量」就宣布成功** | 数量对不代表字节对。要比 **tree sha**（见 §7 的核对方式）——它是对全部路径 + 全部内容 + 全部模式的密码学摘要 |

---

## 9. 提交前自检清单（一屏）

```
[ ] python scripts/check-publish-safe.py .          → 0 BLOCK
[ ] python scripts/check-publish-safe.py --selftest → 判别力成立（4 个场景）
[ ] 输出里「项目词黑名单」不是「未配置」          → 否则商业 know-how 这一类没扫
[ ] feedback/ 下每个文件都问过「这是判据还是产出？」 → 产出不该在这
[ ] git check-ignore -v feedback/review/ library/local/ scripts/publish-denylist.txt  → 命中
[ ] git ls-files --eol <抽一个文件>                  → i/lf w/lf（行尾统一）
[ ] 仓库内 core.autocrlf 已置 false                  → 否则 status / diff 会互相矛盾（§5b-1）
[ ] git status --short 为空                          → 若报 M 但 git diff 为空，见 §5b-1
[ ] 推完比过 tree sha（本地 HEAD^{tree} == 远端 tree.sha）→ 数量相同不算证据
[ ] SKILL.md 里 name: 只出现一次
[ ] SKILL.md 版本号 / CHANGELOG / 即将打的 tag 三者一致
[ ] references/ 改过 → 已重渲染手册
[ ] 新增豁免已在 PUBLISHING.md 登记表里写了理由
[ ] library/ 新增素材的 license 在白名单内（unknown 也算拦截）
[ ] git status --short 里没有出现不该提交的目录
```

