# -*- coding: utf-8 -*-
"""把 Markdown 里的 GFM 表格拆出来，供「导入资料库文档」用。

为什么需要它：
    资料库的 `create_doc.py` **只接受 Markdown**，但只要正文里出现表格，
    一次性创建就很容易被网关 524 掉；而后续插入又**禁止 Markdown 表格语法**，
    必须写成 `<Table>` 组件。于是标准做法是「骨架法」：
        ① 把表格换成占位段 → 创建无表格的骨架
        ② 逐个 `insert_after` 插入 `<Table>` 组件，再删掉占位段

    这个脚本就负责第 ① 步的骨架，以及第 ② 步的组件片段。

用法：
    python md-tables-for-library.py <输入.md> --outdir <输出目录>
产出：
    <outdir>/skeleton.md        无表格正文（表格处替换为占位段）
    <outdir>/tbl-1.xml …        每张表的 <Table> 组件（可直接作为 insert 的 content）
    <outdir>/plan.json          占位符 → 表片段的对应关系

组件的写法约束（来自资料库文档）：
    - Table 的子只能是 TableRow；TableRow 的子只能是 TableCell
    - TableCell 里的文字必须包在 <Paragraph> 里；不能直接写 <TableCell>文字</TableCell>
    - insert 的 content 里禁止 <Mark ar>；样式属性（如 bold）可用
    - 一整张表 ≤ 约 3.6 KB / 12 行时可一次插入，本脚本会提示是否超限
"""

import argparse
import json
import pathlib
import re


def esc(s):
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def cell_inline(s):
    """把单元格里的行内 Markdown 转成组件能吃的形式。

    `code`        → 纯文本（去掉反引号）
    **bold**      → <Mark bold>…</Mark>
    {a,b}         → a / b     ← 正文里禁止 {...} 表达式，会被当成 content expression 拒收
    其余           → 原样，做 XML 转义
    """
    s = s.strip()
    s = re.sub(r'`([^`]+)`', r'\1', s)
    # 花括号是内容表达式的语法；正文里出现会被服务端拒绝
    s = re.sub(r'\{([^{}]*)\}', lambda m: m.group(1).replace(',', ' / '), s)
    s = s.replace('{', '（').replace('}', '）')
    parts = re.split(r'(\*\*[^*]+\*\*)', s)
    out = []
    for p in parts:
        if p.startswith('**') and p.endswith('**') and len(p) > 4:
            out.append('<Mark bold>%s</Mark>' % esc(p[2:-2]))
        else:
            out.append(esc(p))
    return ''.join(out)


def is_sep(line):
    return bool(re.match(r'^\s*\|[\s:|-]+\|\s*$', line))


def split_row(line):
    return [c.strip() for c in line.strip().strip('|').split('|')]


def to_table_xml(rows):
    """rows[0] 为表头行。"""
    L = ['<Table>']
    for ri, cells in enumerate(rows):
        L.append('    <TableRow>')
        for c in cells:
            L.append('        <TableCell>')
            L.append('            <Paragraph>%s</Paragraph>' % cell_inline(c))
            L.append('        </TableCell>')
        L.append('    </TableRow>')
    L.append('</Table>')
    return '\n'.join(L)


def main():
    ap = argparse.ArgumentParser(description='拆分 Markdown 表格，产出骨架与 <Table> 组件')
    ap.add_argument('src', help='输入 Markdown')
    ap.add_argument('--outdir', required=True, help='输出目录')
    a = ap.parse_args()

    src = pathlib.Path(a.src)
    out = pathlib.Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)

    lines = src.read_text(encoding='utf-8').split('\n')
    skel, tables, plan = [], [], []
    i = 0
    while i < len(lines):
        ln = lines[i]
        # 命中：本行是 | 开头，且下一行是分隔行
        if ln.strip().startswith('|') and i + 1 < len(lines) and is_sep(lines[i + 1]):
            rows = [split_row(ln)]
            i += 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append(split_row(lines[i]))
                i += 1
            idx = len(tables) + 1
            xml = to_table_xml(rows)
            fn = 'tbl-%d.xml' % idx
            (out / fn).write_text(xml, encoding='utf-8')
            kb = len(xml.encode('utf-8')) / 1024
            over = (len(rows) > 12) or (kb > 3.6)
            tables.append(fn)
            plan.append({'idx': idx, 'file': fn, 'rows': len(rows),
                         'kb': round(kb, 2), 'over_quota': over, 'fragment': xml})
            skel.append('〔TBL-%d〕' % idx)
            skel.append('')
            print('  表 %d：%d 行 / %.2f KB%s'
                  % (idx, len(rows), kb, '   ← 超配额，需分段插入' if over else ''))
            continue
        skel.append(ln)
        i += 1

    (out / 'skeleton.md').write_text('\n'.join(skel), encoding='utf-8')
    (out / 'plan.json').write_text(
        json.dumps({'tables': plan}, ensure_ascii=False, indent=1), encoding='utf-8')
    print()
    print('表格 %d 张 → %s' % (len(tables), out))
    print('骨架 %s（%.1f KB）'
          % (out / 'skeleton.md', len('\n'.join(skel).encode('utf-8')) / 1024))
    print('占位符：' + '、'.join('〔TBL-%d〕' % p['idx'] for p in plan))


if __name__ == '__main__':
    main()
