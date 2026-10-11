# 模板脚本

**把需要的拷到项目目录再改，不要直接引用这里的路径。**

```bash
# 例：新项目要用 04 的画布
mkdir -p projects/<新项目>/04-prototype
cp <skill>/assets/templates/04-prototype/*.py projects/<新项目>/04-prototype/
cp <skill>/assets/templates/04-prototype/_canvas_html.py projects/<新项目>/04-prototype/
```

---

## 🔴 模板必须是中性的 —— 不许带任何项目的痕迹

模板是要被**拷贝进下一个项目**的。里面只要留着上一个项目的名字、业务实体、泳道角色
或写死的数字，拷贝的人就会把它们当成"本来就该这样"，继承一整套错的东西。

真实发生过：这批模板一度直接写着某个项目的标题、它的支付渠道、它的甲方系统名，
甚至写着 `42 条需求` 这种字面量 —— **模板自己违反了工作流铁律 2（期望值从数据源现算）**。

**约定**

| 类别 | 写法 |
|---|---|
| 项目名 / 版本 / 日期 | `{{项目名}}` `{{版本}}` `{{日期}}` —— **故意做成显眼**，没替换时会留在产物里 |
| 业务实体 | 用中性概念（`外部渠道` / `外部系统`），不要用某个项目的具体产品名 |
| 参与方 / 泳道 | 只能用 SKILL.md 的**端枚举**（用户小程序 / 管理后台 / 收银端 / 商家端 / 服务端），端枚举之外的一律归 `外部系统` |
| 数量 / 统计 | **从数据源现算**，不许写字面量 |

**守卫**（改完模板跑一次，要求 `BLOCK 0`）：

```bash
python scripts/check-templates-clean.py .        # 扫项目词 / 写死标题 / 已下线阶段 / 泳道端枚举
python scripts/check-templates-clean.py --selftest
```

---

---

## 哪些是「直接可用」，哪些是「要改」

| 类别 | 文件 | 说明 |
|---|---|---|
| **直接可用**（跨项目不变） | `_canvas_html.py` `_png.py` `_viewpad.py` `_verify_discriminating.py` `_card_css.css` `_card_js.js` `_route.py` | 通用引擎与工具，拷过去就用 |
| **要改路径/常量** | `check-*.py` `_verify.js` `_shots.js` `build-*.py` | 顶部的 `HERE` / `NODE` / `EDGE` / 项目常量 |
| **要改数据模型** | `_build_cards.py` `build-view.py` `build-doc.py` | 与本项目的 `*.json` 字段强耦合 |
| **只作参考** | `_verify_sharp.py` `_preview_shots.py` `_interact.py` | 视角/连线清单是项目特有的 |

---

## 每个模板里必改的地方

**路径一律不要写死。** 用下面两种写法之一 —— 写死用户名（`C:/Users/<你的名字>/...`）
在换机器时会静默失效，而且没法发布给别人用。

```python
# ① 运行时推导（推荐）
import os
HOME = os.path.expanduser('~')
NODE = os.environ.get('WB_NODE') or os.path.join(
    HOME, '.workbuddy', 'binaries', 'node', 'versions', '<ver>', 'node.exe')
# ② 模板已内置自动定位（如 check-card-view.py 的 _find_node()），直接用 NODE / NODE_MODULES

PY   = sys.executable                      # 永远用这个，不要写路径
EDGE = r'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
```

```js
// _verify.js / _shots.js
const EDGE = 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe';
const PORT = 9333 + (process.pid % 500);   // 端口要跟 pid 走，防撞车
```

```powershell
# 跑 Node 脚本时（PowerShell 7）
$env:NODE_PATH = "$env:USERPROFILE\.workbuddy\binaries\node\workspace\node_modules"
```

> 🔴 **发布前跑一次** `python scripts/check-publish-safe.py .`
> —— 它会扫出所有写死用户名的路径与形似凭据的串。

---

## 🔴 跑完必须清

- `_mut/`（变异测试的 Edge 临时 profile，实测 **54M**）
- 一次性探针 `_diag*.js` / `_probe.js`

---

## 常用命令速查

```bash
# 04 原型
cd 04-prototype && python _viewpad.py && python build-proto.py && python build-canvas.py && python check-proto.py && python _preview_shots.py

# 06 卡片画布（交付链末层，**05 标注已下线，不要再用**）
cd 06-anno-card && python build-card-canvas.py && python check-card-view.py && node _verify.js && node _shots.js

# 02 PRD
cd 02-prd && python build-view.py && python build-doc.py && python check-biz-lang.py
```

---

## ⚠️ 已知缺口：00 / 01 还没有脚本模板

`00-audit/` 与 `01-requirements/` 目前**只有数据模型**（见
`references/00-audit-and-01-requirements.md`），没有可拷贝的构建脚本 ——
`check-templates-clean.py` 会一直报 `T5` 的 WARN，**这是真的没做，不是误报**。

在补上之前，这两个阶段的 `*.html` 视图需要按该文档的数据模型自写脚本，
约束与 02 一样：**HTML 由脚本生成、期望值从 JSON 现算**。

> 不要把 00 / 01 加进 `NO_TEMPLATE_STAGES` 来消掉这条 WARN ——
> 它们**结构上需要脚本**（要产出 HTML 视图），登记成"不需要"就是把缺口藏起来。
> 只有 03b 那种"结构上不随项目建目录"的阶段才可以登记。
