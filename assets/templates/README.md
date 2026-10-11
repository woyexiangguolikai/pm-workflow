# 模板脚本

**把需要的拷到项目目录再改，不要直接引用这里的路径。**

```bash
# 例：新项目要用 04 的画布
mkdir -p projects/<新项目>/04-prototype
cp <skill>/assets/templates/04-prototype/*.py projects/<新项目>/04-prototype/
cp <skill>/assets/templates/04-prototype/_canvas_html.py projects/<新项目>/04-prototype/
```

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
# 跑 Node 脚本时（PowerShell 5.1 / 7 都能跑）
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

# 05 标注
cd 05-annotation && python build-anno.py && python check-anno.py && python _preview_shots.py

# 06 卡片画布（推荐形态）
cd 06-anno-card && python build-card-canvas.py && python check-card-view.py && node _verify.js && node _shots.js

# 02 PRD
cd 02-prd && python build-view.py && python build-doc.py && python check-biz-lang.py
```
