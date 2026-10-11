---
id: c-0001
type: component
name: 加载按钮（原地变 Spinner + 宽度锁定）
tags: [button, loading, 防重复提交, feedback]
summary: 提交类按钮点击后原地变为 Spinner 并锁定原宽度，避免布局跳动与重复点击
license: original
sourceUrl: _original_
capturedAt: 2026-10-11
support: Chrome 80+ / Safari 14+ / Firefox 78+
status: active
usedBy: []
---

## 一句话

提交类按钮点击后，**不换位置、不换尺寸**，把文字换成 Spinner；宽度用 `min-width` 锁死。

## 什么时候用

- 任何**会发请求**的按钮：提交订单、发起支付、保存配置、导出报表。
- 表单较长、用户可能反复点的地方。

## 什么时候别用

- 纯前端即时响应的操作（开关、Tab 切换）—— 加 loading 反而显得慢。
- 耗时超过 10 秒且无进度的场景 —— 该换进度条，Spinner 会让人以为卡死。
- **列表内的小按钮**（如每行一个「删除」）—— 逐行 Spinner 会让整张表闪。

## 实现要点

1. **宽度锁定**：按钮外层 `min-width` 取「文字态」实测宽度，或直接固定尺寸。
   否则文字→图标会缩窄，右侧内容左移（这是最常见的低级跳动）。
2. **状态切换而非替换节点**：切换 `data-loading` 属性，不要 `innerHTML` 重建 ——
   重建会丢焦点，键盘用户会被踢出。
3. **同时禁用**：`disabled` 与 `aria-busy="true"` 一起加。
   ⚠️ 只用 `pointer-events:none` 是不够的 —— 键盘回车仍能触发。
4. **超时兜底**：超过 15 秒需回到可点状态并提示，否则用户会刷新页面
   （刷新对幂等接口无害，对非幂等接口是灾难）。
5. **成功后的去向要在点击前就确定**：不要「成功后再决定跳哪」—— 那会在 loading 态卡住。

## 无障碍

- `aria-busy="true"` + 文字替换为 `loading` 文案（对读屏用户，Spinner 是不可见的）。
- 最小触控目标 44×44 CSS px。
- **不要**用颜色单独表达「正在加载」。

## 依赖

- 无 JS 框架依赖；CSS 变量建议：`--brand-500`（Spinner 前景）、`--radius-r2`。
- 动画时长：旋转 0.8s linear infinite；**必须响应 `prefers-reduced-motion`**。

## 反面参照

- 反例一：按钮变成全屏遮罩 —— 用户失去所有上下文，且无法取消。
- 反例二：`alert('提交中')` —— 阻塞式，多端环境里尤其糟。
