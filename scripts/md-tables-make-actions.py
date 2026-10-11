# -*- coding: utf-8 -*-
"""生成「插入表格 + 删占位段」的 actions.json（配合 md-tables-for-library.py 用）。

`create_doc.py` 只收 Markdown，但正文带表格就容易被网关 524；而后续插入又禁止
Markdown 表格语法，必须用 `<Table>` 组件。于是走「骨架法」：

    ① md-tables-for-library.py  → skeleton.md（表格换成 〔TBL-N〕 占位段）+ tbl-N.xml
    ② 用 skeleton.md 创建文档
    ③ get_doc_reviews.py 读回，找出占位段的 block id，存成 {"1":"id1", ...}
    ④ 本脚本        → actions.json（每张表：insert_after 占位段 → delete 占位段）
    ⑤ submit_doc_edit.py --actions-file actions.json （先 --dry-run）
    ⑥ 再读回一次，确认表格在、占位段没了

用法：
    python md-tables-make-actions.py --plan <dir>/plan.json --ids <ids.json> --out <actions.json>

actions 的 schema（来自资料库文档）是**平铺**的：
    {"type":"insert_after","id":"<anchor>","content":"<Table>…</Table>"}
    {"type":"delete","id":"<anchor>"}
"""

import argparse
import json
import pathlib
import sys


def main():
    ap = argparse.ArgumentParser(description='生成资料库文档的表格插入 actions')
    ap.add_argument('--plan', required=True, help='md-tables-for-library.py 产出的 plan.json')
    ap.add_argument('--ids', required=True, help='占位段 block id：{"1":"id1", ...}')
    ap.add_argument('--out', required=True, help='输出 actions.json 路径')
    a = ap.parse_args()

    plan_path = pathlib.Path(a.plan).resolve()
    lib = plan_path.parent
    plan = json.loads(plan_path.read_text(encoding='utf-8'))['tables']
    ids = json.loads(pathlib.Path(a.ids).read_text(encoding='utf-8'))

    actions, missing = [], []
    for p in plan:
        ph = ids.get(str(p['idx']))
        if not ph:
            missing.append('TBL-%d' % p['idx'])
            continue
        frag = p.get('fragment')
        if not frag:
            frag = (lib / p['file']).read_text(encoding='utf-8')
        # 先插后删（安全顺序：万一提交被打断，占位段还在，看得到没做完）
        actions.append({'type': 'insert_after', 'id': ph, 'content': frag})
        actions.append({'type': 'delete', 'id': ph})

    if missing:
        print('缺占位段 block id：%s' % '、'.join(missing))
        sys.exit(1)

    out = pathlib.Path(a.out)
    out.write_text(json.dumps(actions, ensure_ascii=False, indent=1), encoding='utf-8')
    print('写 %s：%d 个 action（%d 张表）' % (out, len(actions), len(plan)))
    for p in plan:
        print('  TBL-%d  %d 行  %.2f KB%s'
              % (p['idx'], p['rows'], p['kb'], '  ← 超配额，需分段' if p.get('over_quota') else ''))


if __name__ == '__main__':
    main()
