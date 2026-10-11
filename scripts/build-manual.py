# -*- coding: utf-8 -*-
"""把 pm-workflow skill 打包成可入库的单文件手册（HTML + Markdown）。

为什么要有这个：
    skill 是**给 agent 读的**（分文件、按需加载、路径引用）。
    手册是**给人读的**（一份翻到底、能搜索、存知识库）。
    同一份知识，两种消费方式 → 从 skill 目录现渲染，**不手写第二份**（否则必然漂移）。

产出（默认落到 --out 指定的目录，缺省 ./_manual）：
    _manual/PM工作流手册.html     单文件，侧栏目录 + 内容区，可离线打开
    _manual/PM工作流手册.md       Markdown，给 IMA / 其他知识库
    _manual/分册/0X-*.md          阶段分册

用法：
    python build-manual.py                        # 输出到 ./_manual
    python build-manual.py --out D:/somewhere     # 指定输出目录
    python build-manual.py --skill <skill根目录>  # 指定 skill 目录（默认自动定位）

可移植：不依赖任何第三方库，不写死本机路径。放到 skill 的 scripts/ 下即可用。
"""

import argparse
import html
import os
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).resolve().parent


def locate_skill(explicit=None):
    """按 显式参数 → 环境变量 → 自身位置 → 常见默认位置 依次定位 skill 根目录。"""
    cands = []
    if explicit:
        cands.append(pathlib.Path(explicit))
    env = os.environ.get('PMWF_SKILL')
    if env:
        cands.append(pathlib.Path(env))
    cands.append(HERE)                  # 脚本就在 skill 根下
    cands.append(HERE.parent)           # 脚本在 skill/scripts/ 下
    cands.append(pathlib.Path.home() / '.workbuddy' / 'skills' / 'pm-workflow')
    for c in cands:
        if (c / 'SKILL.md').exists():
            return c.resolve()
    print('找不到 skill 根目录（需要含 SKILL.md）。试过：')
    for c in cands:
        print('  - %s' % c)
    sys.exit(1)


# (文件名, 标题, 分册序号)
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

STAGE_VOLUMES = {
    0: '00-总览与铁律',
    1: '01-盘点与需求',
    2: '02-PRD需求规格',
    3: '03-设计规范',
    4: '04-原型',
    5: '05-交互标注',
    6: '06-需求卡片画布',
    7: '07-校验与验证',
    8: '08-踩坑总表',
    9: '09-部署与迁移',
}

SKILL = None      # 由 main() 填入
OUT = None        # 由 main() 填入


# ---------------------------------------------------------------- 极简 Markdown
def _inline(s):
    """行内样式渲染。TOC 与正文共用，避免两处规则不一致。"""
    s = html.escape(s, quote=False)
    # 行内代码先抽成占位符。**不能**直接就地替换 —— 源里大量出现
    #    **`*.json`（喂脚本）+ `*.html`（给人看）**
    # 这种「加粗包着代码」，就地替换后 `*` 会和代码里的字符串起来，
    # 加粗规则就会啃错边界（实测渲染出半个裸 `**`）。抽走再放回最稳。
    slots = []

    def keep_code(m):
        slots.append(m.group(1))
        return '\x00%d\x00' % (len(slots) - 1)

    s = re.sub(r'`([^`]+)`', keep_code, s)
    # 加粗必须在斜体之前，否则 **x** 会先被斜体规则啃掉
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    s = re.sub(r'(?<!\*)\*([^*\n]+)\*(?!\*)', r'<i>\1</i>', s)
    s = re.sub(r'\x00(\d+)\x00',
               lambda m: '<code>%s</code>' % slots[int(m.group(1))], s)
    return s


def md_to_html(md):
    """够用的 Markdown 渲染：标题 / 表格 / 代码块 / 列表 / 引用 / 行内样式。

    刻意不引第三方库 —— 这份手册要能离线、能在任何机器上重跑。
    """
    inline = _inline
    lines = md.split('\n')
    out, i = [], 0
    in_code = False
    code_buf = []
    in_tbl = False
    in_ul = False

    def close_lists():
        nonlocal in_ul
        if in_ul:
            out.append('</ul>')
            in_ul = False

    while i < len(lines):
        ln = lines[i]

        # 代码块
        if ln.strip().startswith('```'):
            if in_code:
                out.append('<pre><code>%s</code></pre>'
                           % html.escape('\n'.join(code_buf), quote=False))
                code_buf = []
                in_code = False
            else:
                close_lists()
                in_code = True
            i += 1
            continue
        if in_code:
            code_buf.append(ln)
            i += 1
            continue

        # 表格
        if ln.strip().startswith('|') and i + 1 < len(lines) \
                and re.match(r'^\s*\|[\s:|-]+\|\s*$', lines[i + 1]):
            close_lists()
            head = [c.strip() for c in ln.strip().strip('|').split('|')]
            out.append('<table><thead><tr>%s</tr></thead><tbody>'
                       % ''.join('<th>%s</th>' % inline(c) for c in head))
            i += 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                cells = [c.strip() for c in lines[i].strip().strip('|').split('|')]
                out.append('<tr>%s</tr>' % ''.join('<td>%s</td>' % inline(c) for c in cells))
                i += 1
            out.append('</tbody></table>')
            continue

        # 标题
        m = re.match(r'^(#{1,6})\s+(.*)$', ln)
        if m:
            close_lists()
            lv = len(m.group(1))
            txt = m.group(2).strip()
            slug = re.sub(r'[^\w\u4e00-\u9fff]+', '-', txt).strip('-')[:60]
            out.append('<h%d id="%s">%s</h%d>' % (lv, slug, inline(txt), lv))
            i += 1
            continue

        # 分隔线
        if re.match(r'^\s*---+\s*$', ln):
            close_lists()
            out.append('<hr>')
            i += 1
            continue

        # 引用
        if ln.strip().startswith('>'):
            close_lists()
            buf = []
            while i < len(lines) and lines[i].strip().startswith('>'):
                buf.append(lines[i].strip().lstrip('>').strip())
                i += 1
            out.append('<blockquote>%s</blockquote>'
                       % '<br>'.join(inline(b) for b in buf if b))
            continue

        # 列表
        m = re.match(r'^(\s*)([-*]|\d+\.)\s+(.*)$', ln)
        if m:
            if not in_ul:
                out.append('<ul>')
                in_ul = True
            out.append('<li>%s</li>' % inline(m.group(3)))
            i += 1
            continue

        # 空行 / 正文
        if not ln.strip():
            close_lists()
            i += 1
            continue
        close_lists()
        out.append('<p>%s</p>' % inline(ln))
        i += 1

    if in_code and code_buf:
        out.append('<pre><code>%s</code></pre>'
                   % html.escape('\n'.join(code_buf), quote=False))
    return '\n'.join(out)


# ---------------------------------------------------------------- HTML 外壳
CSS = """
:root{--bg:#0b1016;--panel:#111820;--panel2:#0d1319;--bd:#222c37;--tx:#e6edf3;
  --mut:#8b98a6;--acc:#58a6ff;--ok:#3fb950;--wn:#d29922;--er:#f85149;--tl:#39c5bb}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font-size:14px;line-height:1.75;
  font-family:system-ui,-apple-system,"Segoe UI","Microsoft YaHei",sans-serif}
#wrap{display:flex;min-height:100vh}
#toc{position:sticky;top:0;align-self:flex-start;width:270px;height:100vh;overflow:auto;
  background:var(--panel);border-right:1px solid var(--bd);padding:20px 14px;flex:none}
#toc .brand{font-size:15px;font-weight:700;margin-bottom:4px}
#toc .sub{font-size:11.5px;color:var(--mut);margin-bottom:16px;line-height:1.6}
#toc a{display:block;color:var(--mut);text-decoration:none;font-size:13px;
  padding:5px 9px;border-radius:6px;border-left:2px solid transparent}
#toc a:hover{background:#161d26;color:var(--tx)}
#toc a.sec{color:var(--tx);font-weight:600;margin-top:9px}
#main{flex:1;min-width:0;padding:34px 46px 90px;max-width:1080px}
h1{font-size:27px;margin:52px 0 16px;padding-bottom:11px;border-bottom:2px solid var(--bd)}
h1:first-child{margin-top:0}
h2{font-size:20px;margin:36px 0 13px;padding-bottom:8px;border-bottom:1px solid var(--bd)}
h3{font-size:16.5px;margin:26px 0 10px;color:#cfd9e3}
h4{font-size:15px;margin:20px 0 8px;color:var(--mut)}
p{margin:11px 0}
code{background:#0b1016;border:1px solid #1e2833;border-radius:4px;padding:1px 5px;
  font-family:ui-monospace,Consolas,monospace;font-size:12.5px;color:#8fa3b5}
pre{background:var(--panel2);border:1px solid var(--bd);border-radius:9px;
  padding:14px 16px;overflow:auto;margin:14px 0}
pre code{background:0;border:0;padding:0;font-size:12.5px;color:#c3ccd6;line-height:1.65}
table{border-collapse:collapse;width:100%;margin:15px 0;font-size:13px}
th,td{border:1px solid var(--bd);padding:8px 11px;text-align:left;vertical-align:top}
th{background:#161d26;color:#cfd9e3;font-weight:600;white-space:nowrap}
tr:nth-child(even) td{background:rgba(255,255,255,.014)}
blockquote{margin:14px 0;padding:11px 16px;background:#161d26;border-left:3px solid var(--wn);
  border-radius:0 7px 7px 0;color:#d6dee6}
blockquote b{color:#fff}
ul{margin:11px 0;padding-left:22px}
li{margin:5px 0}
hr{border:0;border-top:1px solid var(--bd);margin:34px 0}
#main b{color:#fff}
#main h2 code,#main h3 code{font-size:.92em;background:0;border:0;color:var(--acc)}
@media print{#toc{display:none}#main{max-width:none;padding:0}
  body{background:#fff;color:#111}pre,table,blockquote{page-break-inside:avoid}}
"""


def build_html():
    parts = []
    toc = ['<div class="brand">产品经理工作流 · 手册</div>',
           '<div class="sub">00 盘点 → 01 需求 → 02 PRD → 03 设计 → 04 原型 → 05 标注 / 06 需求卡片</div>']
    for fname, title, vol in SECTIONS:
        p = SKILL / fname
        if not p.exists():
            print('  ⚠ 缺文件：%s' % fname)
            continue
        md = p.read_text(encoding='utf-8')
        # 去掉 YAML front-matter
        md = re.sub(r'^---\n.*?\n---\n', '', md, count=1, flags=re.S)
        body = md_to_html(md)
        anchor = 'sec-%d' % vol
        parts.append('<section id="%s">%s</section>' % (anchor, body))
        toc.append('<a class="sec" href="#%s">%s</a>' % (anchor, title))
        # 二级标题进目录（TOC 文本也要走 inline，否则出现裸 ** 与裸反引号）
        for m in re.finditer(r'^#{2,2}\s+(.*)$', md, re.M):
            t = m.group(1).strip()
            slug = re.sub(r'[^\w\u4e00-\u9fff]+', '-', t).strip('-')[:60]
            toc.append('<a href="#%s">· %s</a>' % (slug, _inline(t)))

    doc = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>产品经理工作流 · 手册</title>
<style>%s</style></head><body>
<div id="wrap">
<nav id="toc">%s</nav>
<main id="main">%s</main>
</div></body></html>""" % (CSS, '\n'.join(toc), '\n'.join(parts))
    (OUT / 'PM工作流手册.html').write_text(doc, encoding='utf-8')
    # 报字节数（中文 UTF-8 一字 3 字节，报字符数会与 stat 对不上）
    return len(doc.encode('utf-8'))


def build_md():
    """单文件 Markdown（给知识库）。"""
    buf = ['# 产品经理工作流 · 手册', '',
           '> 00 盘点 → 01 需求 → 02 PRD → 03 设计 → 04 原型 → 05 标注 / 06 需求卡片画布',
           '> 每阶段产出「JSON 数据源 + HTML 自包含视图」双格式，脚本自校验 + 变异测试。', '',
           '## 目录', '']
    bodies = []
    for fname, title, vol in SECTIONS:
        p = SKILL / fname
        if not p.exists():
            continue
        md = re.sub(r'^---\n.*?\n---\n', '', p.read_text(encoding='utf-8'),
                    count=1, flags=re.S)
        md = md.replace('\n# ', '\n## ')          # 降一级，避免多个 H1
        if md.startswith('# '):
            md = '#' + md
        else:
            md = '## ' + title + '\n' + md
        buf.append('- [%s](#%s)' % (title, title.replace(' ', '-')))
        bodies.append('\n---\n\n<a id="%s"></a>\n\n%s\n' % (title, md))
    text = '\n'.join(buf) + '\n' + '\n'.join(bodies)
    (OUT / 'PM工作流手册.md').write_text(text, encoding='utf-8')
    return text


def build_volumes():
    d = OUT / '分册'
    d.mkdir(exist_ok=True)
    n = 0
    for fname, title, vol in SECTIONS:
        p = SKILL / fname
        if not p.exists():
            continue
        md = re.sub(r'^---\n.*?\n---\n', '', p.read_text(encoding='utf-8'),
                    count=1, flags=re.S)
        if not md.lstrip().startswith('# '):
            md = '# %s\n\n%s' % (title, md)
        nm = STAGE_VOLUMES.get(vol, '%02d-%s' % (vol, title))
        (d / ('%s.md' % nm)).write_text(md, encoding='utf-8')
        n += 1
    return n


def main():
    global SKILL, OUT
    ap = argparse.ArgumentParser(description='把 pm-workflow skill 渲染成手册')
    ap.add_argument('--skill', help='skill 根目录（含 SKILL.md），默认自动定位')
    ap.add_argument('--out', help='输出目录，默认 ./_manual')
    a = ap.parse_args()

    SKILL = locate_skill(a.skill)
    OUT = pathlib.Path(a.out).resolve() if a.out else (pathlib.Path.cwd() / '_manual')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / '分册').mkdir(exist_ok=True)

    n_html = build_html()
    md = build_md()
    n_vol = build_volumes()
    print('[PM 工作流手册]')
    print('  单文件 HTML : %s（%.1f KB）' % (OUT / 'PM工作流手册.html', n_html / 1024))
    print('  单文件 MD   : %s（%.1f KB）' % (OUT / 'PM工作流手册.md', len(md.encode('utf-8')) / 1024))
    print('  阶段分册    : %d 份 → %s' % (n_vol, OUT / '分册'))
    print('  来源        : %s' % SKILL)


if __name__ == '__main__':
    main()
