---
name: pm-workflow-setup-and-migration
description: 把 PM 工作流搬到另一台电脑上使用（打包 / 放置 / 适配 / 验证）。
---

# 部署与迁移：拿到另一台电脑上怎么用

## 一句话

**整套工作流就是一个自包含的目录**（`pm-workflow/`，35 个文件 / 约 570KB）。
拷到另一台电脑的 `%USERPROFILE%\.workbuddy\skills\` 下就能用 —— **项目数据不用带**。

> 没有「一键同步到另一台设备」这回事，也不用去资料库/网盘传。就一次文件夹拷贝，加上两处路径适配。

---

## 0. 先分清：什么必须带，什么不用带

| 项 | 是否必须 | 位置 | 说明 |
|---|---|---|---|
| **skill 目录** | ✅ 必须 | `~/.workbuddy/skills/pm-workflow/` | 全部规则 + 25 个模板脚本 + 手册生成器 |
| WorkBuddy 本体 + 登录 | ✅ 必须 | — | skill 靠它加载；新机器装好登录一次即可 |
| Python / Node / Edge | ❌ 不用带 | — | Python、Node 由 WorkBuddy 自带 managed 运行时；Edge 用 Windows 自带的 |
| 项目数据 | ⭕ 可选 | `projects/<项目名>/` | 只在「接着做某个具体项目」时才需要 |
| 存量系统源码 | ⭕ 可选 | 如 `点餐连锁版v3_3.4/` | 只在要做反向盘点时才需要 |

**不要带**：`node_modules/`（新机器重装）、`_mut/`（Edge 临时 profile，实测能到 **54M**）、`shots/` 基准图（能重新生成，但很占地方 —— 要带就单独拷）。

---

## 1. 在本机打包

PowerShell 5.1 与 7 都能跑：

```powershell
$src = "$env:USERPROFILE\.workbuddy\skills\pm-workflow"
$dst = "$env:USERPROFILE\Desktop\pm-workflow-skill.zip"
if (Test-Path $dst) { Remove-Item $dst -Force }
Compress-Archive -Path $src -DestinationPath $dst -Force
[math]::Round((Get-Item $dst).Length / 1KB, 1)
```

期望输出约 **570** KB。

> ⚠️ 不要用 `tar --force-local` —— Windows 自带的是 bsdtar，不认这个参数（原生认盘符）。

---

## 2. 拷贝

U 盘 / 微信 / 网盘 / 邮件都行，一个 zip。

---

## 3. 放到新机器的 skill 目录

```powershell
# WorkBuddy 要先装好并登录过一次（登录后才会生成 ~/.workbuddy）
$dir = "$env:USERPROFILE\.workbuddy\skills"
New-Item -ItemType Directory -Path $dir -Force | Out-Null
Expand-Archive -Path "$env:USERPROFILE\Desktop\pm-workflow-skill.zip" `
               -DestinationPath $dir -Force

# 检查：解出来的目录名必须是 pm-workflow，且顶层有 SKILL.md
Get-ChildItem "$dir\pm-workflow" | Select-Object Name
```

要求的结构（**层级不能多也不能少**）：

```
~/.workbuddy/skills/pm-workflow/
├── SKILL.md                    ← 总控。有它才算 skill 根目录
├── references/                 8 份阶段文档 + 本文件
├── assets/templates/           25 个模板脚本 + README
└── scripts/build-manual.py     手册生成器
```

如果解压多套了一层（变成 `pm-workflow/pm-workflow/`），把里层移出来。

---

## 4. 新机器上只做三件事

### 4.1 路径：**不用改**（运行期自动推导）

自 v1.1 起，**没有任何文件写死本机路径** —— 原来唯一写死路径的
`assets/templates/06-anno-card/check-card-view.py` 已改为运行期推导：

```python
def _find_node():
    p = os.environ.get('WB_NODE')                       # ① 环境变量显式指定
    if p and os.path.exists(p):
        return p
    base = os.path.join(os.path.expanduser('~'), '.workbuddy', 'binaries', 'node', 'versions')
    ...                                                 # ② 扫版本目录取最新
NODE_MODULES = os.environ.get('WB_NODE_MODULES') or os.path.join(
    os.path.expanduser('~'), '.workbuddy', 'binaries', 'node', 'workspace', 'node_modules')
```

推导规则：**先读 `WB_NODE` / `WB_NODE_MODULES` 环境变量，没有再扫 `~/.workbuddy/binaries/node/`。**
所以换用户名、换机器、换 Node 版本都不用改代码。

只有一种情况需要手动指定 —— 你的 Node 装在**非默认位置**（比如自己装的、装在 D 盘的）：

```powershell
$env:WB_NODE         = 'D:\NodeJS\node.exe'
$env:WB_NODE_MODULES = 'D:\somewhere\node_modules'
```

**其余脚本也不用动**：
- Python 解释器用 `sys.executable`（谁跑脚本就用谁）
- Edge 路径是「先找 `Program Files (x86)`、没有再找 `Program Files`」的兜底写法
- 模板的其余部分不含本机绝对路径

### 4.1b 发布前自检（**改完任何文件都跑一次**）

```powershell
cd "$env:USERPROFILE\.workbuddy\skills\pm-workflow"
& "$env:USERPROFILE\.workbuddy\binaries\python\versions\<版本>\python.exe" scripts\check-publish-safe.py .
```

要求 **`0 BLOCK`**。它会扫三类东西：

| 级别 | 含义 | 例子 |
|---|---|---|
| 🔴 BLOCK | 绝对不能发布 | 私钥、API Key、`C:\Users\<真实用户名>`、`/home/<用户名>` |
| 🟡 WARN | 需人工确认 | 中国大陆手机号、像身份证的串、真实邮箱 |
| ℹ️ INFO | 提醒 | 注释里出现「示例」「测试」字样 |

**白名单只有一种写法**，且必须在输出里显式列出（不静默跳过）：
在文件（脚本、夹具、测试样本）**任意一行**加注释
`# wb-publish-scan: ignore-file`
—— 它的存在会在输出的 `exemptFiles` 段被打印出来，供发布者复核。
**不要**用「改路径绕过扫描」的方式让自检变绿，那等于把泄漏藏起来。

### 4.2 重新定标（**换机器必须做**）

```powershell
cd <项目目录>\04-prototype
& "$env:USERPROFILE\.workbuddy\binaries\python\versions\<版本>\python.exe" _viewpad.py
```

**为什么必须做**：截图尺寸 = **窗口**尺寸，不是视口；`视口 = 窗口 − (24, 92)`。
这个偏移**跟 Edge 版本、系统 DPI、窗口边框样式都有关** —— 在 12989 这台上是 (24, 92)，换机器不保证。

脚本会打印：

```
视口原点在截图里的位置 = (24, 92) 像素
→ build-proto 应写入 element-map 的 img 字段：
    {"padX": 24.0, "padY": 92.0, "w": ..., "h": ...}
```

把它给的 `padX / padY / w / h` 写进 `04-prototype/element-map.json` 的 `img` 字段。
`build-proto.py` 顶部的 `CHROME_W, CHROME_H = 24, 92` 与 `MIN_VIEW_W = 492` 也一并按实测值核对。

> 🔴 这一步漏掉的后果很隐蔽：**标注框会整体偏移几像素 —— 而且看起来是对的**。
> 差几个像素不报错、不崩，只是「差不多对」。这类错在本项目翻过车，别省。

### 4.3 确认运行时在位

```powershell
& "$env:USERPROFILE\.workbuddy\binaries\python\versions\<版本>\python.exe" -V
& "$env:USERPROFILE\.workbuddy\binaries\node\versions\<版本>\node.exe" -v
Test-Path "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
```

缺 Python/Node 的 managed 运行时 → 第一次用到时 WorkBuddy 会自动装，也可以直接让 agent 装。
Edge 是 Windows 自带的，`Test-Path` 返回 `True` 即可。

---

## 5. 验证装对了（**别只看「文件在不在」**）

「文件存在」与「skill 真能用」是两个世界，输出可能一模一样。所以要验到「能跑出结果」这一层：

| 检查 | 怎么做 | 期望看到 |
|---|---|---|
| skill 能被加载 | 新开会话说「按 PM 工作流做原型」 | agent 能讲出五条铁律，而不是瞎编 |
| 模板脚本语法 | 见下方命令 | 全过，无 FAIL |
| 手册能重生成 | 见下方命令 | 打印产物三行，且 `分册/` 有 **10** 份 |

```powershell
# ① 模板脚本语法
$tpl = "$env:USERPROFILE\.workbuddy\skills\pm-workflow\assets\templates"
Get-ChildItem -Recurse -Filter *.py $tpl | ForEach-Object {
  & "$env:USERPROFILE\.workbuddy\binaries\python\versions\<版本>\python.exe" -m py_compile $_.FullName
  if ($LASTEXITCODE -ne 0) { Write-Host "FAIL $($_.Name)" }
}
Get-ChildItem -Recurse -Filter *.js $tpl | ForEach-Object {
  & "$env:USERPROFILE\.workbuddy\binaries\node\versions\<版本>\node.exe" --check $_.FullName
  if ($LASTEXITCODE -ne 0) { Write-Host "FAIL $($_.Name)" }
}
Write-Host "语法检查完成"

# ② 手册能重生成（这同时证明 references 齐全、脚本可跑）
$sk = "$env:USERPROFILE\.workbuddy\skills\pm-workflow"
& "$env:USERPROFILE\.workbuddy\binaries\python\versions\<版本>\python.exe" "$sk\scripts\build-manual.py" --out "$env:USERPROFILE\Desktop\pm-manual"
Get-ChildItem "$env:USERPROFILE\Desktop\pm-manual\分册" | Measure-Object
```

第 ② 步期望：HTML 约 100KB、MD 约 70KB、分册 **10** 份（多了「09-部署与迁移」）。
跑通了就说明 skill 完整 —— 因为它把 `references/` 全读了一遍才渲染得出来。

---

## 6. 开始用

新会话里直接说人话即可：

- 「用 PM 工作流给『XX』做一个新项目」→ 从 00 盘点开始
- 「按 PM 工作流做需求卡片画布」→ 直接进 06
- 「重新生成 PM 工作流手册」→ 跑 `scripts/build-manual.py`
- 「盘点这份源码」→ 进 00 反向盘点

---

## 7. 常见问题

| 现象 | 原因 | 处理 |
|---|---|---|
| agent 说没有这个 skill | 目录名不对，或层级多套了一层 | 必须是 `...\skills\pm-workflow\SKILL.md` |
| 只有总纲、六阶段文档找不到 | zip 解压丢了层级 | 重解压，确认 `references/` 下有 9 个 md |
| 标注框整体偏移几像素 | 没跑 `_viewpad.py` 重新定标 | 回到 §4.2 |
| Node 脚本报 `EBUSY` | 用了 `spawnSync` / `execSync` | 改成 `spawn` + Promise（该机行为） |
| 探针读到上一次的结果 | Edge 进程树没杀干净 | `taskkill /PID <pid> /T /F`；两次探针间 `sleep(1.2)` |
| 截图里出现「灰蓝色卡片框」 | 舞台底色被截进来了 | 见 `REFERENCE.md` 出图规格（工作区内） |
| `node --check` 报错 | 新机器的 Node 版本过老 | 换 managed 的 22.x |

---

## 8. 🔴 不要做的事

- ❌ **不要把 skill 目录上传到资料库/网盘，就当迁移完成了。** 那是**备份**，不是迁移 —— 新机器上仍然得把文件放进 `~/.workbuddy/skills/` 才会生效。
- ❌ 不要带 `node_modules/`。新机器上按需重装，版本还能更合适。
- ❌ 不要带 `_mut/` 与 `_diag*/`。前者是 Edge 临时 profile（实测 54M），后者是一次性探针。
- ❌ 不要改 `SKILL.md` 的 `name:` 字段。它必须是 `pm-workflow`，否则目录名与标识不符会加载不到。
- ❌ 不要把 `references/` 里某份文档单独拷出来用。它们是互相引用的（`SKILL.md` 指向各份，`gotchas.md` 被多份引用），拆开一定断链。

---

## 9. 长期维护：两份东西，一个源头

| 产物 | 给谁 | 怎么生成 |
|---|---|---|
| `references/*.md` | **agent 读** | 手写、是唯一源头 |
| `_manual/PM工作流手册.{html,md}` + `分册/` | **人读**、存知识库 | `scripts/build-manual.py` **从 references 现渲染** |

🔴 **改了 `references/` 里任何一份，都要重跑一次生成器** —— 否则手册和 skill 就漂移了（手册会留在旧版本，而看手册的人不知道）。

```powershell
& "$env:USERPROFILE\.workbuddy\binaries\python\versions\<版本>\python.exe" `
  "$env:USERPROFILE\.workbuddy\skills\pm-workflow\scripts\build-manual.py" --out .\_manual
```
