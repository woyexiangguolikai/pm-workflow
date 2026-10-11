# -*- coding: utf-8 -*-
"""业务语言守卫：校验 PRD.html 的**业务视图**里没有技术标识泄漏

原理：用系统 Edge 无头渲染 PRD.html → 拿到真实 DOM（等价于浏览器打开时的样子）
      → 剔除所有 .tech-only 子树（业务视图下它们被 CSS 隐藏）
      → 在剩下的正文里搜索技术标识。搜到 = 业务侧会看到专业术语 = 不合格。

用法：python check-biz-lang.py
退出码：0 通过；1 有残留
"""
import json, io, os, re, subprocess, sys, tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
HTML = os.path.join(BASE, 'PRD.html')
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

TAG = re.compile(r'<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>')
VOID = ('br', 'img', 'input', 'hr', 'meta', 'link', 'source', 'path', 'circle',
        'rect', 'line', 'polyline', 'use', 'area', 'base', 'col', 'embed', 'track', 'wbr')

# 允许出现的技术词（在业务文案里属于正常表述）
ALLOW = re.compile(r'^(access_token|transRecId|accNum|cardAccNum|eWalletId|payType|'
                   r'queryType|optType|correctMon|durationId|deviceNum|consumeMgFee)$')


def dump_dom():
    out = os.path.join(tempfile.gettempdir(), 'prd_dom_check.html')
    url = 'file:///' + HTML.replace('\\', '/').replace(' ', '%20')
    subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--no-sandbox',
                    '--virtual-time-budget=6000', '--dump-dom', url],
                   stdout=io.open(out, 'w', encoding='utf-8', errors='replace'),
                   stderr=subprocess.DEVNULL, timeout=120)
    return io.open(out, encoding='utf-8', errors='replace').read()


def strip_class(src, cls):
    """按标签深度剔除带 cls 的整棵子树"""
    out, i, n, d = [], 0, len(src), 0
    while i < n:
        m = TAG.search(src, i)
        if not m:
            if d == 0:
                out.append(src[i:])
            break
        if d == 0:
            out.append(src[i:m.start()])
        closing, tag, selfc = m.group(1), m.group(2).lower(), m.group(3)
        void = tag in VOID
        if d == 0:
            if not closing and cls in m.group(0) and not void and not selfc:
                d = 1
            else:
                out.append(m.group(0))
        else:
            if not closing and not void and not selfc:
                d += 1
            elif closing:
                d -= 1
        i = m.end()
    return ''.join(out)


LEAKS = {
    '页面路径':     r'pages/[a-z0-9\-/]+',
    '数据表名':     r'jjjfood_[a-z_]+',
    '接口编号 SVC': r'\bSVC-\d{3}\b',
    '接口编号 API': r'\bAPI-\d{3}\b',
    '后台路径':     r'\badmin/[a-z\-]+',
    '原型锚点':     r'>\s*#[a-z][a-z0-9\-]*[a-z0-9]\s*<',
    '下划线字段名': r'\b[a-z][a-z0-9]*_[a-z0-9_]+\b',
    'SQL 类型':     r'\b(?:varchar|tinyint|decimal|bigint|datetime|text|int)\s*\(\s*\d',
    'Unix 时间戳':  r'\b1[6-9]\d{8}\b',
    '平台字段名(camelCase)': r'\b[a-z]{2,}[A-Z][a-zA-Z]{2,}\b',
}


def main():
    if not os.path.exists(HTML):
        print('找不到 PRD.html，请先运行 build-view.py'); return 1
    if not os.path.exists(EDGE):
        print('找不到 Edge，跳过渲染校验（仅做源码级粗查）'); return 2

    html = dump_dom()
    dom = re.sub(r'<script[\s\S]*?</script>', '', html)
    dom = re.sub(r'<style[\s\S]*?</style>', '', dom)
    biz = strip_class(dom, 'tech-only')

    print('业务视图正文（已剔除 .tech-only）：%d 字符' % len(biz))
    bad = 0
    for name, pat in LEAKS.items():
        hits = sorted({h for h in re.findall(pat, biz) if not ALLOW.match(h)})
        if hits:
            bad += 1
            print('  [残留] %-14s %s（共 %d）' % (name, hits[:10], len(hits)))
        else:
            print('  [通过] %s' % name)

    if bad == 0:
        print('\n✅ 业务视图无技术标识残留')
        return 0
    print('\n❌ 有 %d 类残留，请在 build-view.py 里包进 .tech-only' % bad)
    return 1


if __name__ == '__main__':
    sys.exit(main())
