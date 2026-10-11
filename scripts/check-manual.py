# -*- coding: utf-8 -*-
"""手册产物完整性自检（判别力版）。

验到「内容和源一致」这一层 —— 不是只数文件大小、不只看文件在不在。
校验点：
  1. section 数与 SECTIONS 一致
  2. **每份源文件的一级标题原文都出现在 HTML 里**（证明正文真渲染了，不是空壳）
  3. 分册份数一致
  4. 代码块之外无裸 `**`
  5. 目录无断锚点
  6. 报字节数（与 stat 对得上）

用法：
    python check-manual.py                    # 校验 ./_manual
    python check-manual.py --out D:/x/_manual --skill <skill根目录>
"""

import argparse
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent

SECTIONS = [
    ('SKILL.md', '总览与铁律', 0),
    ('references/00-audit-and-01-requirements.md', '盘点与需求', 1),
    ('references/02-prd.md', 'PRD 需求规格', 2),
    ('references/03-design.md', '设计规范', 3),
    ('references/04-prototype.md', '04 原型', 4),
    ('references/05-annotation.md', '05 交互标注', 5),
    ('references/06-anno-card.md', '06 需求卡片画布', 6),
    ('references/verification.md', '校验与验证', 7),
    ('references/gotchas.md', '踩坑总表', 8),
    ('references/setup-and-migration.md', '部署与迁移', 9),
]


def locate_skill(explicit=None):
    import os
    cands = []
    if explicit:
        cands.append(pathlib.Path(explicit))
    env = os.environ.get('PMWF_SKILL')
    if env:
        cands.append(pathlib.Path(env))
    cands.append(HERE)                                   # 脚本在 skill 根下
    cands.append(HERE.parent)                            # 脚本在 skill/scripts/ 下
    cands.append(pathlib.Path.home() / '.workbuddy' / 'skills' / 'pm-workflow')
    for c in cands:
        if (c / 'SKILL.md').exists():
            return c.resolve()
    print('找不到 skill 根目录（需要含 SKILL.md）')
    sys.exit(1)


OUT = None
SK = None


def main():
    global OUT, SK
    ap = argparse.ArgumentParser(description='校验手册产物')
    ap.add_argument('--out', help='手册输出目录，默认 ./_manual')
    ap.add_argument('--skill', help='skill 根目录，默认自动定位')
    a = ap.parse_args()
    OUT = pathlib.Path(a.out).resolve() if a.out else (pathlib.Path.cwd() / '_manual')
    SK = locate_skill(a.skill)

    hp = OUT / 'PM工作流手册.html'
    mp = OUT / 'PM工作流手册.md'
    for p in (hp, mp):
        if not p.exists():
            print('缺产物：%s' % p)
            sys.exit(1)

    h = hp.read_text(encoding='utf-8')
    md = mp.read_text(encoding='utf-8')
    fails = []

    # 1. section 齐
    secs = re.findall(r'<section id="sec-(\d+)"', h)
    print('section 数 = %d（应 %d）' % (len(secs), len(SECTIONS)))
    if len(secs) != len(SECTIONS):
        fails.append('section 数不符')

    # 2. 每份源的首标题必须出现在 HTML 里（真渲染，不是空壳）
    for fname, title, vol in SECTIONS:
        p = SK / fname
        if not p.exists():
            fails.append('源缺失 ' + fname)
            continue
        src = re.sub(r'^---\n.*?\n---\n', '', p.read_text(encoding='utf-8'),
                     count=1, flags=re.S)
        m = re.search(r'^#\s+(.+)$', src, re.M)
        head = m.group(1).strip() if m else title
        plain = re.sub(r'[`*]', '', head)
        ok = plain in h
        print('  [%s] %-46s 首标题「%s」' % ('OK' if ok else 'FAIL', fname, plain[:26]))
        if not ok:
            fails.append('首标题缺失 ' + fname)

    # 3. 分册数
    vols = sorted((OUT / '分册').glob('*.md'))
    print('分册数 = %d（应 %d）' % (len(vols), len(SECTIONS)))
    if len(vols) != len(SECTIONS):
        fails.append('分册数不符')

    # 4. 代码块外无裸 **
    body = re.sub(r'<pre>.*?</pre>', '', h, flags=re.S)
    body = re.sub(r'<code>.*?</code>', '', body, flags=re.S)
    nb = body.count('**')
    print('裸 ** 出现 = %d（应 0）' % nb)
    if nb:
        fails.append('裸 **')

    # 5. 断锚点
    ids = set(re.findall(r'id="([^"]+)"', h))
    hrefs = re.findall(r'href="#([^"]+)"', h)
    dead = [x for x in hrefs if x not in ids]
    print('目录链接 %d 条 · 断锚点 %d（应 0）' % (len(hrefs), len(dead)))
    if dead:
        fails.append('断锚点 %d' % len(dead))

    # 6. 字节数（与 stat 对得上）
    print('HTML %.1f KB · MD %.1f KB（字节）'
          % (len(h.encode('utf-8')) / 1024, len(md.encode('utf-8')) / 1024))

    print()
    print('结果：' + ('全部通过' if not fails else '失败 → ' + '; '.join(fails)))
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())

