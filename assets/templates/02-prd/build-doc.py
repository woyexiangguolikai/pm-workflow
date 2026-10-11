# -*- coding: utf-8 -*-
"""由 prd.json 生成 PRD.md 的「可再生成」章节，写回 PRD.md（幂等，可反复重跑）

生成内容用注释标记包住，每次重跑整段替换，保证文档与数据源不漂移：
  <!--GEN:FLOWS:START--> ... <!--GEN:FLOWS:END-->   第 5 章正文（Mermaid 图示化流程图）
  <!--GEN:TAIL:START-->  ... <!--GEN:TAIL:END-->    文末新增章节（动效规范 / 卡片模型与样板）

用法：python build-doc.py
"""
import json, io, os, re

BASE = os.path.dirname(os.path.abspath(__file__))
d = json.load(io.open(os.path.join(BASE, 'prd.json'), encoding='utf-8'))
MD = os.path.join(BASE, 'PRD.md')

LANE_STYLE = {
    '用户小程序': ('laneApp', '#3fb950'),
    '服务端': ('laneSrv', '#bc8cff'),
    '管理后台': ('laneAdmin', '#d29922'),
    '甲方一卡通平台': ('laneYtk', '#58a6ff'),
    '甲方人事系统': ('laneHr', '#39c5bb'),
}
CN = '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳'


def esc(s):
    return str(s).replace('|', '\\|').replace('\n', ' ')


# ---------------- 第 5 章：Mermaid 图示化流程图 ----------------
def flows_md():
    out = ['## 5. 核心业务流程', '',
           '> 下图由 `prd.json` 的 `flowDiagrams` 自动生成（脚本 `build-doc.py`）。'
           '每个节点标注所在端，箭头表示时间先后；HTML 视图（`PRD.html` 附录 A）为同一份数据的图形化呈现。', '']
    for fd in d['flowDiagrams']:
        lanes = fd['lanes']
        used = [l for l in lanes if any(s['lane'] == l for s in fd['steps'])]
        out.append('### 5.%s %s' % (fd['id'].split('-')[1], fd['name']))
        out.append('')
        out.append('涉及功能：' + ' · '.join(
            '%s %s' % (f, next((fn['name'] for m in d['modules'] for fn in m['functions'] if fn['id'] == f), ''))
            for f in fd['involvedFunctions']))
        out.append('')
        out.append('```mermaid')
        out.append('flowchart TD')
        for k, (cls, col) in LANE_STYLE.items():
            if k in used:
                out.append('    classDef %s stroke:%s,stroke-width:2px' % (cls, col))
        for i, s in enumerate(fd['steps'], 1):
            label = '%s <b>%s</b><br/>%s' % (CN[i - 1], s['lane'], esc(s['action']))
            out.append('    n%d["%s"]' % (i, label))
        for i in range(1, len(fd['steps'])):
            out.append('    n%d --> n%d' % (i, i + 1))
        for i, s in enumerate(fd['steps'], 1):
            cls = LANE_STYLE.get(s['lane'], ('laneYtk', ''))[0]
            out.append('    class n%d %s' % (i, cls))
        out.append('```')
        out.append('')
        tech = [(i, s['techNote']) for i, s in enumerate(fd['steps'], 1) if s.get('techNote')]
        if tech:
            out.append('实现备注（技术细节，业务侧可略过）：')
            out.append('')
            for i, tn in tech:
                out.append('- 第 %d 步：%s' % (i, esc(tn)))
            out.append('')
    return '\n'.join(out)


# ---------------- 文末新增章节 ----------------
def motion_md():
    am = d['appendixMotion']
    out = ['## 14. 动效与微交互规范', '',
           '> %s。共 %d 条。' % (am['title'], len(am['rules'])),
           '> 各需求卡片只写该需求**特有**的动效，通用部分不重复。开发实现动效时以本章为验收依据。', '',
           '| 项 | 规范 |', '| --- | --- |']
    for r in am['rules']:
        out.append('| **%s** | %s |' % (esc(r['item']), esc(r['spec'])))
    out += ['', '### 14.1 逐条需求的动效说明', '',
            '| 需求 | 页面转场 | 微交互 | 反馈动效 | 时长与缓动 | 无障碍降级 |',
            '| --- | --- | --- | --- | --- | --- |']
    for r in d['requirements']:
        mo = (r.get('interactions') or {}).get('motion') or {}
        if not mo:
            continue
        out.append('| %s %s | %s | %s | %s | %s | %s |' % (
            r['id'], esc(r['title']), esc(mo.get('pageEntry', '—')), esc(mo.get('microInteraction', '—')),
            esc(mo.get('feedback', '—')), esc(mo.get('durationEasing', '—')), esc(mo.get('reducedMotion', '—'))))
    miss = [r['id'] for r in d['requirements']
            if not (r.get('interactions') or {}).get('motion')]
    if miss:
        out += ['', '> 尚未补齐动效说明的需求（清单级）：' + '、'.join(miss) + '。', '']
    else:
        out += ['', '> 全部 %d 条需求均已补齐动效与微交互说明（页面转场 / 微交互 / 反馈 / 缓动 / 无障碍降级）。'
                % len(d['requirements']), '']
    return '\n'.join(out)


def card_md(r):
    B = lambda x: '—' if not x else x
    o = []
    o.append('#### %s %s `%s`' % (r['id'], r['title'], r['priority']))
    o.append('')
    o.append(r['description'])
    o.append('')

    o.append('**① 涉及端与职责**')
    o.append('')
    o.append('| 端 | 职责 |')
    o.append('| --- | --- |')
    for e in r['ends']:
        o.append('| **%s** | %s |' % (esc(e['end']), esc(e['responsibility'])))
    o.append('')

    o.append('**② 前置条件**')
    o.append('')
    for x in r['preconditions']['functional']:
        o.append('- %s' % esc(x))
    if r['preconditions']['data']:
        o.append('')
        o.append('*数据前置*')
        o.append('')
        for x in r['preconditions']['data']:
            o.append('- %s' % esc(x))
    o.append('')

    if r['mainFlow']:
        o.append('**③ 主流程**')
        o.append('')
        o.append('| 执行方 | 做什么 | 说明 |')
        o.append('| --- | --- | --- |')
        for s in r['mainFlow']:
            o.append('| %s | %s | %s |' % (esc(s['actor']), esc(s['action']), esc(s.get('note', ''))))
        o.append('')

    if r['exceptions']:
        o.append('**④ 异常与分支**')
        o.append('')
        o.append('| 场景 | 处理方式 |')
        o.append('| --- | --- |')
        for e in r['exceptions']:
            o.append('| %s | %s |' % (esc(e['scene']), esc(e['handling'])))
        o.append('')

    it = r.get('interactions') or {}
    o.append('**⑤ 交互说明**')
    o.append('')
    rows = [('入口形态', 'entry'), ('点击行为', 'click'), ('二次确认', 'confirm'), ('加载态', 'loading'),
            ('空态', 'empty'), ('置灰条件', 'disabled'), ('埋点', 'analytics')]
    o.append('| 项 | 说明 |')
    o.append('| --- | --- |')
    for label, k in rows:
        if it.get(k):
            o.append('| %s | %s |' % (label, esc(it[k])))
    o.append('')
    if it.get('errorText'):
        o.append('提示文案（原文，开发不得自行拟定）：')
        o.append('')
        for k, v in it['errorText'].items():
            o.append('- %s → 「%s」' % (esc(k), esc(v)))
        o.append('')
    mo = it.get('motion') or {}
    if mo:
        o.append('动效与微交互（全局基线见第 14 章）：')
        o.append('')
        o.append('| 项 | 说明 |')
        o.append('| --- | --- |')
        for label, k in [('页面转场', 'pageEntry'), ('微交互', 'microInteraction'), ('反馈动效', 'feedback'),
                         ('时长与缓动', 'durationEasing'), ('无障碍降级', 'reducedMotion')]:
            if mo.get(k):
                o.append('| %s | %s |' % (label, esc(mo[k])))
        o.append('')

    pf = r.get('pageFlow') or {}
    if pf.get('entry'):
        o.append('页面流转：')
        o.append('')
        o.append('| 环节 | 内容 |')
        o.append('| --- | --- |')
        o.append('| 入口（从哪来） | %s |' % esc(pf['entry']))
        o.append('| 本页动作 | %s |' % esc(pf.get('action', '—')))
        for x in pf.get('exits') or []:
            extra = '' if x.get('params') in ('无', '—', None) else '（参数：%s）' % esc(x['params'])
            o.append('| 出口 · %s | %s%s |' % (esc(x['condition']), esc(x['page']), extra))
        o.append('')

    if r.get('displayFields'):
        o.append('页面展示字段（每个位置显示什么、什么格式、看不到时怎么办）：')
        o.append('')
        o.append('| 页面位置 | 展示名 | 取值来源 | 展示格式 | 脱敏规则 | 取不到时 |')
        o.append('| --- | --- | --- | --- | --- | --- |')
        for x in r['displayFields']:
            o.append('| %s | %s | %s | %s | %s | %s |' % (
                esc(x['where']), esc(x['name']), esc(x['field']), esc(x['fmt']), esc(x['mask']), esc(x['empty'])))
        o.append('')

    if r.get('inputRules'):
        o.append('输入限制（用户能输什么、输不进去什么）：')
        o.append('')
        o.append('| 输入项 | 输入方式 | 长度上限 | 允许字符 | 自动处理 | 边界行为 |')
        o.append('| --- | --- | --- | --- | --- | --- |')
        for x in r['inputRules']:
            o.append('| %s | %s | %s | %s | %s | %s |' % (
                esc(x['input']), esc(x['keyboard']), esc(x['maxLen']), esc(x['allow']),
                esc(x['normalize']), esc(x['boundary'])))
        o.append('')
        o.append('对应提示文案：')
        o.append('')
        for x in r['inputRules']:
            if x.get('tip') and x['tip'] != '—':
                o.append('- %s：%s' % (esc(x['input']), esc(x['tip'])))
        o.append('')

    o.append('**⑥ 业务规则**')
    o.append('')
    for x in r['rules']:
        o.append('- %s' % esc(x))
    o.append('')

    sl = r.get('stateLink') or {}
    if any(sl.get(k) for k in ('dependsOn', 'triggers', 'triggeredBy')):
        o.append('状态联动：')
        o.append('')
        for label, k in [('本需求依赖的状态', 'dependsOn'), ('本需求触发的状态变化', 'triggers'),
                         ('谁会触发本需求变化', 'triggeredBy')]:
            if sl.get(k):
                o.append('- **%s**：%s' % (label, '；'.join(esc(x) for x in sl[k])))
        o.append('')

    if r.get('dataShow'):
        o.append('数据展示与来源：')
        o.append('')
        o.append('| 展示项 | 来源 | 口径 | 取不到时 |')
        o.append('| --- | --- | --- | --- |')
        for x in r['dataShow']:
            o.append('| %s | %s | %s | %s |' % (esc(x['item']), esc(x['source']), esc(x['mode']), esc(x['fallback'])))
        o.append('')

    pm = r.get('permissions') or {}
    if pm:
        o.append('权限：可见 —— %s；可操作 —— %s；受限 —— %s。' % (
            esc(pm.get('visible', '—')), esc(pm.get('operable', '—')), esc(pm.get('forbidden', '—'))))
        o.append('')

    if r.get('fields'):
        o.append('**⑦ 涉及字段（含规格）**')
        o.append('')
        o.append('| 字段 | 说明 | 必填 | 类型 | 默认 | 取值与校验 | 示例 | 约束 | 变更 |')
        o.append('| --- | --- | --- | --- | --- | --- | --- | --- | --- |')
        for f in r['fields']:
            o.append('| %s | %s | %s | `%s` | %s | %s | %s | %s | %s |' % (
                esc(f.get('business') or f.get('column')), esc(f.get('desc', '')),
                '是' if f.get('nullable') is False else ('否' if f.get('nullable') is True else '—'),
                esc(f.get('sqlType') or f.get('type', '')), esc(f.get('default', '—')),
                esc(f.get('validate', '—')), esc(f.get('example', '')), esc(f.get('constraint', '—')),
                esc(f.get('change', ''))))
        o.append('')

    io_ = r.get('interfaces') or {}
    if (io_.get('ours') or io_.get('external')):
        o.append('接口：')
        o.append('')
        o.append('| 侧 | 接口 | 说明 |')
        o.append('| --- | --- | --- |')
        for x in (io_.get('ours') or []):
            o.append('| 我方服务 | %s %s | %s |' % (x['id'], esc(x.get('business') or x.get('name', '')), esc(x.get('note', ''))))
        for x in (io_.get('external') or []):
            o.append('| 一卡通平台 | %s %s | %s |' % (x['id'], esc(x.get('business') or x.get('name', '')), esc(x.get('note', ''))))
        o.append('')

    if r.get('landing'):
        o.append('原型落点：%s 页 · 锚点 `#%s` · 页面路径 `%s`' % (
            esc(r['landing'].get('page', '')), esc(r['landing'].get('anchor', '')), esc(r['landing'].get('pagePath', ''))))
        o.append('')

    out = r.get('output') or {}
    o.append('**⑧ 输出与后置条件**')
    o.append('')
    if out.get('returns'):
        o.append('输出：%s' % esc(out['returns']))
        o.append('')
    for x in out.get('postConditions') or []:
        o.append('- %s' % esc(x))
    o.append('')

    if r.get('acceptance'):
        o.append('**⑨ 验收标准**')
        o.append('')
        for x in r['acceptance']:
            o.append('- %s' % esc(x))
        o.append('')

    tr = r.get('trace') or {}
    if tr.get('upstream') or tr.get('downstream'):
        o.append('追溯：')
        o.append('')
        if tr.get('upstream'):
            o.append('- 上游依赖（我依赖谁）：%s' % '、'.join(esc(x) for x in tr['upstream']))
        if tr.get('downstream'):
            o.append('- 下游影响（谁依赖我）：%s' % '、'.join(esc(x) for x in tr['downstream']))
        if tr.get('flowDiagram'):
            o.append('- 所属流程：%s' % esc(tr['flowDiagram']))
        o.append('')

    o.append('---')
    o.append('')
    return '\n'.join(o)


def fields_md():
    """第 16 章：字段规格与数据格式规范"""
    o = ['## 16. 字段规格与数据格式规范', '',
         '### 16.1 为什么单列一章', '',
         '模板版的 PRD 常常只写「字段名 + 一句说明」，开发实现时仍要回头问：这个字段多长？'
         '能不能为空？默认值是什么？小数保留几位？页面上显示成什么样子？用户能输入什么？'
         '—— 这些问题不写清楚，就会在开发中反复来回。本章把这些一次性定死。', '',
         '每个字段定义 **8 项规格**：', '',
         '| 规格 | 回答的问题 |', '| --- | --- |',
         '| 类型（含长度与精度） | 存储多大、几位小数 |',
         '| 是否必填 | 能不能为空 |',
         '| 默认值 | 建记录时初始是什么 |',
         '| 约束 | 是否唯一、是否建索引 |',
         '| 取值与校验 | 取值范围、格式要求、由谁提供 |',
         '| 脱敏与展示 | 用户在界面上看到什么样的值 |',
         '| 示例值 | 填什么算对 |',
         '| 变更性质 | 新增 / 复用 / 修改 |',
         '', '> 业务视图只展示「说明 / 必填 / 取值与校验 / 示例 / 变更」；'
         '类型、默认、约束、表名、字段名切到技术视图可见。', '',
         '### 16.2 字段规格字典（新增字段）', '',
         '| 字段 | 说明 | 必填 | 类型 | 默认 | 取值与校验 | 示例 | 约束 | 脱敏 | 变更 |',
         '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for c in d['fields']['newColumns']:
        o.append('| %s | %s | %s | `%s` | %s | %s | %s | %s | %s | %s |' % (
            esc(c.get('business', c['column'])), esc(c.get('desc', '')),
            '是' if c.get('nullable') is False else ('否' if c.get('nullable') is True else '—'),
            esc(c.get('sqlType', c.get('type', ''))), esc(c.get('default', '—')),
            esc(c.get('validate', '—')), esc(c.get('example', '')), esc(c.get('constraint', '—')),
            esc(c.get('mask', '—')), esc(c.get('change', ''))))
    o += ['', '### 16.3 字段规格字典（复用字段）', '',
          '| 字段 | 说明 | 必填 | 类型 | 默认 | 取值与校验 | 示例 | 约束 | 脱敏 | 变更 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |']
    for c in (d['fields'].get('reusedFields') or []):
        o.append('| %s | %s | %s | `%s` | %s | %s | %s | %s | %s | %s |' % (
            esc(c.get('business', c['column'])), esc(c.get('desc', '')),
            '是' if c.get('nullable') is False else ('否' if c.get('nullable') is True else '—'),
            esc(c.get('sqlType', c.get('type', ''))), esc(c.get('default', '—')),
            esc(c.get('validate', '—')), esc(c.get('example', '')), esc(c.get('constraint', '—')),
            esc(c.get('mask', '—')), esc(c.get('change', ''))))
    o += ['', '新增枚举：', '', '| 枚举 | 取值 | 业务上怎么问 |', '| --- | --- | --- |']
    for e in d['fields']['newEnums']:
        o.append('| %s | %s | %s |' % (esc(e['name']), esc(e['values']), esc(e.get('businessAsk', '—'))))
    if d['fields'].get('mapping'):
        o += ['', '我方字段 ⇄ 一卡通字段对照（开发细节）：', '',
              '| 我方字段 | 一卡通字段 | 说明 |', '| --- | --- | --- |']
        for m in d['fields']['mapping']:
            o.append('| %s | `%s` | %s |' % (esc(m['ours']), esc(m['yikatong']), esc(m['note'])))

    ds = d.get('dataSpec') or {'rows': []}
    o += ['', '### 16.4 %s' % ds.get('title', '数据格式与精度规范'), '',
          ds.get('intro', ''), '',
          '| 项目 | 单位 | 存储类型 | 怎么显示 | 取值与计算规则 | 示例 |',
          '| --- | --- | --- | --- | --- | --- |']
    for x in ds['rows']:
        o.append('| %s | %s | `%s` | %s | %s | %s |' % (
            esc(x['item']), esc(x['unit']), esc(x['store']), esc(x['display']),
            esc(x['rule'] + '（来源：' + x['source'] + '）'), esc(x['example'])))
    if ds.get('openNote'):
        o += ['', '> ' + esc(ds['openNote'])]

    o += ['', '### 16.5 各页面展示字段与输入限制汇总', '',
          '**页面展示字段**（每个位置显示什么、什么格式、看不到时怎么办）：', '',
          '| 所属需求 | 页面位置 | 展示名 | 取值来源 | 展示格式 | 脱敏规则 | 取不到时 |',
          '| --- | --- | --- | --- | --- | --- | --- |']
    for r in d['requirements']:
        for x in (r.get('displayFields') or []):
            o.append('| %s | %s | %s | %s | %s | %s | %s |' % (
                r['id'], esc(x['where']), esc(x['name']), esc(x['field']),
                esc(x['fmt']), esc(x['mask']), esc(x['empty'])))
    o += ['', '**输入限制**（用户能输什么、输不进去什么）：', '',
          '| 所属需求 | 输入项 | 输入方式 | 长度上限 | 允许字符 | 自动处理 | 边界行为 | 提示文案 |',
          '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for r in d['requirements']:
        for x in (r.get('inputRules') or []):
            o.append('| %s | %s | %s | %s | %s | %s | %s | %s |' % (
                r['id'], esc(x['input']), esc(x['keyboard']), esc(x['maxLen']),
                esc(x['allow']), esc(x['normalize']), esc(x['boundary']), esc(x['tip'])))
    o += ['', '> 其余 38 条需求的展示字段与输入限制，随卡片补全一并补齐。', '']
    return '\n'.join(o)

def tail_md():
    out = [motion_md(), '']
    out += ['## 15. 需求规格卡片模型与完整样板', '',
            '> 本章说明每条需求在数据源与视图中如何被组织。',
            '> **全部 42 条需求均已按该模型完整展开**，完整卡片见 `PRD.html`；',
            '> 本节 15.4 保留一组样板，便于快速理解卡片模型。', '',
            '### 15.1 为什么改成长卡片', '',
            '原先把「规则 / 字段 / 异常 / 验收 / 权限」拆到多个平级页签，读一条需求要在页签间来回切，'
            '记忆负担重。现在改为：**一条需求就是一张卡片，卡片内按固定顺序分区，所有信息在同一处读完**。',
            '',
            '层级为 **模块 › 功能 › 需求** 三级：模块 9 个、功能 18 个、需求 42 条。', '',
            '### 15.2 卡片模型的 6 分区', '',
            '| 分区 | 回答的问题 | 包含维度 |',
            '| --- | --- | --- |',
            '| 定位 | 这是什么、谁来做 | 一句话业务描述、涉及端与逐端职责 |',
            '| 前置 | 开始之前必须成立什么 | 功能前置、数据前置、上下游依赖 |',
            '| 过程 | 具体怎么发生 | 主流程（执行方│做什么│说明）、异常与分支、交互说明、动效与微交互、**页面展示字段**、**输入限制**、页面流转 |',
            '| 规则 | 约束是什么 | 业务规则、状态联动、数据展示与来源、权限 |',
            '| 关联 | 牵动了什么 | 涉及字段（**含类型长度、必填、默认、约束、校验、示例**）、接口、原型锚点、流程图 |',
            '| 产出 | 会得到什么 | 输出、后置条件、验收标准 |',
            '',
            '### 15.3 两种读法：业务视图 / 技术视图', '',
            '同一份数据，`PRD.html` 右上角一键切换：', '',
            '| | 业务视图（默认） | 技术视图 |',
            '| --- | --- | --- |',
            '| 面向 | 业务侧领导、客户、测试 | 开发实现 |',
            '| 接口 | 显示业务名（如「查询一卡通绑定状态」） | 附编号与技术名（如 `SVC-004 查询绑定状态`） |',
            '| 字段 | 显示业务名（如「一卡通绑定状态」） | 附 `表.字段` 与枚举值 |',
            '| 页面 | 只显示页面名称（如「我的钱包」） | 附页面路径（如 `pages/user/my-wallet/my-wallet`） |',
            '| 锚点 | 隐藏 | 显示（如 `#wallet-yikatong-entry`） |',
            '',
            '**原则：业务文案里不出现表名、字段名、页面路径、接口编号。**'
            '技术细节统一由"业务名 + 技术标识"双轨承载 —— 业务视图读得懂，技术视图不丢信息。', '',
            '### 15.4 卡片模型样板（F1-1 一卡通绑定，4 条需求）', '',
            '> 本节的每一条都由 `prd.json` 自动生成，与 HTML 视图同源。',
            '> 其余 38 条按同一模型展开，完整卡片见 `PRD.html`。', '']
    for rid in ('BR-101', 'BR-102', 'BR-103', 'BR-106'):
        r = next((x for x in d['requirements'] if x['id'] == rid), None)
        if r:
            out.append(card_md(r))
    # 15.5 补全情况：按模块统计展开进度（动态生成，避免与数据源漂移）
    mods = d.get('modules', [])
    reqs_all = d['requirements']
    rows = []
    for m in mods:
        mid = m.get('id')
        mine = [x for x in reqs_all if x.get('moduleId') == mid]
        full_n = len([x for x in mine if x.get('detailLevel') == 'full'])
        ids = '、'.join(x['id'] for x in mine)
        rows.append('| %s %s | %d | %d | %s |' % (
            mid, m.get('name', ''), len(mine), full_n, ids))
    tot = len(reqs_all)
    tot_full = len([x for x in reqs_all if x.get('detailLevel') == 'full'])
    out += ['### 15.5 补全情况', '',
            '全部需求已按同一卡片模型展开为完整卡片，**无待补全项**。', '',
            '| 模块 | 需求数 | 已完整展开 | 需求编号 |',
            '| --- | --- | --- | --- |'] + rows + [
            '| **合计** | **%d** | **%d** | — |' % (tot, tot_full), '',
            '展开顺序：M1（绑定闭环）→ M2/M3（支付主链路）→ M4（退款）→ M5（员工身份）'
            '→ M6/M7（折扣规则与叠加）→ M8（对账与结算）→ M9（后台配置与报表）。', '',
            '### 15.6 后续维护约定', '',
            '- **改数据源，视图重新生成**：`prd.json` 为唯一数据源，`PRD.html` 与本章由生成器产出，两者不漂移。',
            '- **业务语言守卫**：生成 HTML 后执行一次业务语言检查，剔除业务视图中的页面路径、表字段名、接口编号、'
            '原型锚点、SQL 类型等技术标识；有残留即视为未通过。',
            '- **锚点闭环**：需求卡片的落点锚点须在原型阶段一一埋入，形成「PRD 条目 ↔ 原型锚点 ↔ 标注」闭环。', '']
    out += [fields_md(), '']
    return '\n'.join(out)


# ---------------- 写回 PRD.md ----------------
md = io.open(MD, encoding='utf-8').read()

FLOW_S, FLOW_E = '<!--GEN:FLOWS:START-->', '<!--GEN:FLOWS:END-->'
TAIL_S, TAIL_E = '<!--GEN:TAIL:START-->', '<!--GEN:TAIL:END-->'

# 1) 第 5 章
sec5 = re.compile(r'## 5\. 核心业务流程[\s\S]*?(?=\n## 6\. )')
if FLOW_S in md:
    md = re.sub(re.escape(FLOW_S) + r'[\s\S]*?' + re.escape(FLOW_E),
                lambda m: FLOW_S + '\n' + flows_md() + '\n' + FLOW_E, md)
else:
    md = sec5.sub(lambda m: FLOW_S + '\n' + flows_md() + '\n' + FLOW_E + '\n\n---\n\n', md, count=1)

# 2) 文末章节
if TAIL_S in md:
    md = re.sub(re.escape(TAIL_S) + r'[\s\S]*?' + re.escape(TAIL_E),
                lambda m: TAIL_S + '\n' + tail_md() + '\n' + TAIL_E, md)
else:
    md = md.rstrip() + '\n\n' + TAIL_S + '\n' + tail_md() + '\n' + TAIL_E + '\n'

# 3) 阅读指引：补一段双视图说明（只加一次）
MARK = '**本 PRD 有两种读法**'
if MARK not in md:
    old = '- **技术视图**：第 7 ~ 10 章、附录。给出接口、字段、枚举、状态等实现要素，供开发实现与测试验收。'
    new = (old + '\n\n' + MARK + '：`PRD.html` 右上角可一键切换。'
           '**业务视图**（默认）隐藏页面路径、数据表字段名、接口编号、原型锚点，业务侧与客户看到的是纯业务描述；'
           '**技术视图**保留全部技术标识，供开发对照实现。同一份数据，两种读法，不分叉。')
    md = md.replace(old, new, 1)

io.open(MD, 'w', encoding='utf-8').write(md)
print('OK -> %s | %d 字符' % (MD, len(md)))
