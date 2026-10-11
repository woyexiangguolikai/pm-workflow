# 校验与验证（写检查前必读）

> 这套工作流的价值有一半在校验上。**没有判别力的检查比没有检查更糟**——它把「没生效」当成「生效」。

## 1. 判别力：一个真实的反例

校验输出「业务视图隐藏 30/30 处技术信息」，全绿。真相是：

```css
/* body.biz .t-only{display:none}  ← 这条规则压根没写 */
```

画布上那 30 个 `.t-only` 恰好**全是 `.an` 锚点框**，被另一条 `.an{display:none}` 管着。

→ **「规则生效」与「规则不存在」两个世界，检查输出一模一样。**

### 四条判据

1. **样本要挑对了能判别的**。上面只认「非 `.an` 的 `.t-only`」才能区分。
2. **样本为 0 时判失败**，不是「无事通过」。
3. **写完检查做一次变异测试**：删掉被验证的东西，同一套探针必须变红。
4. **感知类指标跟参照系比**（参照系 = 同一份源数据按最朴素方式渲染一遍，比值 ≥ 0.85）。

### 顺序铁律

```
先跑变异测试确认有判别力  →  再信它的结论
```

**教训**：检查全绿其实是矩形约定搞反导致框变小；是「变异测试没变红」暴露的。
**动手改校验之前，先证明校验自己是对的。**

---

## 2. 变异测试必须「真破坏」

**案例**：5 条变异全绿（不变红），查出来是**变异本身没破坏目标**：

| 错误改法 | 为什么没破坏 |
|---|---|
| 给锚点框加 `hidden` 属性 | 元素还在 DOM，`querySelectorAll` 照样数到 53 个 |
| 给 `data-end` 前面插个属性 | `data-end` 还在，逻辑没变 |
| 只改 `bindClick` 没改 `bindClickCtx` | 另一个同实现顶着 |

**正确改法**：

```python
# 删标签（而且是全部删）
variant('M1 删掉落点框', '<i class="an t-only"', '<x-an-removed t-only',
        n_expect=53, replace_all=True)
# 删属性（改成不存在的属性名，而不是插一个）
variant('M4 删掉端标记', 'class="pg" data-end=', 'class="pg" data-xend=')
# 同名实现全量替换
variant('M2 拆异常守卫', 'if(e) e.onclick=fn;', 'e.onclick=fn;',
        n_expect=2, replace_all=True)
```

**并且必须断言被验证的量真的变了**：

```python
assert mut_result['counts']['anchors'] == 0, '变异没生效，这条检查没有判别力'
assert mut_result['errs'], '变异没生效'
```

### 变异探针的写法

```python
def variant(name, old, new, n_expect=1, replace_all=False):
    n = src.count(old)
    if n < n_expect:
        bad('%s 变异点找不到（%d < %d）' % (name, n, n_expect)); return None
    out = src.replace(old, new) if replace_all else src.replace(old, new, 1)
    if out == src:
        bad('%s 变异后内容没变' % name); return None
    ... 写临时文件 → 跑探针 → 断言变红 → 删临时文件
```

---

## 3. 视图不漂移：逐字比对

HTML 由脚本生成，校验要证明「HTML 里的数据 == JSON 里的数据」。

```python
# 从 HTML 里抠出每个需求号的 data-boxes，与 JSON 逐字比
for br, boxes in card_canvas['boxes'].items():
    m = re.search(r'data-cid="%s"[^>]*data-boxes=\'([^\']*)\'' % br, html)
    assert m, '%s 的 data-boxes 在 HTML 里找不到' % br
    assert json.loads(m.group(1)) == boxes, '%s 的视图漂移了' % br
```

⚠️ **正则要提防内联脚本里的字符串模板**。踩过：`_card_js.js` 内联在页面里，
里面有 `querySelectorAll('.an[data-br="'+br+'"]')` → 正则把 `"br"` 抓成假锚点，报「有 1 个 data-br 在需求号里不存在」。

```python
# ✗ 会抓到内联源码里的模板
re.findall(r'data-br="([^"]+)"', html)
# ✓ 只匹配真实元素标签
re.findall(r'<i class="an t-only"[^>]*data-br="([^"]+)"', html)
```

---

## 4. 结构检查 vs 真渲染检查

**能静态查的别开浏览器**（快、稳）。只有这几种情况必须真渲染：

- 交互行为（手风琴、筛选、飞视角）
- 运行时异常（`errs`）
- 计算样式（`getComputedStyle` 拿到的 padding / 列宽）
- 清晰度（光栅化质量）

两者都要有。静态查「结构对不对」，渲染查「跑起来对不对」。

### 真渲染探针的骨架（Node + CDP）

见 `assets/templates/06-anno-card/_verify.js`（可直接改 PROJECT/HTML 常量复用）。要点：

```js
// 1) 用 spawn 起 Edge（本机 spawnSync 恒 EBUSY）
const ch = spawn(EDGE, [
  '--headless=new', '--disable-gpu', '--no-sandbox',
  '--remote-debugging-port=' + PORT,
  '--user-data-dir=' + PROFILE,
  '--no-first-run', '--no-default-browser-check',
  '--disable-features=msEdgeIdentitySignIn,msSyncPromo,msEdgeSyncPromo',
  '--disable-sync', '--disable-background-networking',
  fileUrl
]);

// 2) Runtime.exceptionThrown 必须收，且要打印 stackTrace
if (m.method === 'Runtime.exceptionThrown') {
  const ed = m.params.exceptionDetails || {};
  const desc = (ed.exception && (ed.exception.description || ed.exception.value)) || '';
  const st = (ed.stackTrace && ed.stackTrace.callFrames || [])
    .slice(0, 4).map(f => `${f.functionName||'(anon)'}@${f.lineNumber+1}:${f.columnNumber+1}`).join(' <- ');
  logs.push('EXC:' + (ed.text||'') + (desc ? ' | '+String(desc).split('\n')[0] : '') + (st ? ' | '+st : ''));
}

// 3) 收尾必须杀整棵进程树
spawn('taskkill', ['/PID', String(ch.pid), '/T', '/F'])
```

### 🔴🔴 必须杀整棵进程树（否则变异测试假绿）

`ch.kill()` **只打死 launcher**，渲染/GPU/网络子进程会留下，**占着调试端口与 user-data-dir**。

后果：**下一次探针连到上一个实例，读到的是上一份 HTML 的结果** → 变异测试假绿。
（实测攒了 **30 个 `msedge` 僵尸**，最早的挂了 3 小时。同一份文件跑两次结果不同，就是这么来的。）

```python
def run_probe(html_path, out_json, label):
    time.sleep(1.2)          # 两次探针之间必须留冷却：进程树退出需要时间
    r = subprocess.run([NODE, ...], capture_output=True, text=True,
                       env=env, cwd=HERE, timeout=180)   # 超时也要给
```

排查：`Get-Process msedge | Stop-Process -Force`

---

## 5. Edge 无头命令速查

```bash
"/c/Program Files (x86)/Microsoft/Edge/Application/msedge.exe" --headless=new --disable-gpu --no-sandbox \
  --virtual-time-budget=4000 --dump-dom "file:///<绝对路径，空格用%20>"
```

⚠️ 三个坑：
1. `--dump-dom` 输出**包含内联 `<script>` 源码本身** → 做「渲染元素计数」校验前先 `textContent=''` 排除。
2. `--screenshot` 与滚动**不兼容**（永远截文档顶部）→ 要截中段先把其他兄弟区块 `display:none`。
3. **相对路径失败，必须绝对路径**（空格用 `%20`）。

**校验双视图是否泄漏技术标识**：不靠截图，用字符串搜索（剔除 `.tech-only` 子树后按 10 类正则查）。

---

## 6. 断言交互时不要只断「变了」

符号写反**也会变**。要拆 matrix 比**方向**和**位移量**：

```js
// ✗ 只证明「变了」
if (after.x !== before.x) pass();
// ✓ 证明「往对的方向、走了对的距离」
if (after.x < before.x && Math.abs(after.x - before.x) > 100) pass();
```

**同一个数有两处含义时拆开报**（如「元素数」既是去重又是累计）。

---

## 7. 目视核对的做法

**先用可量化替代指标回答**（「最小间距 20.9px」而不是看图说「应该没压」）。

确实要看图时，**给画布描上判定用的框再截图**：

```python
# 给每张卡片描红框，把「连线有没有压到卡片」变成一眼可判
extra_css = '.card-outline{outline:2px solid #ff4444;outline-offset:0}'
```

**改完校验要做的最后一件事**：跑一遍全部变异，确认每一条都还变红。
