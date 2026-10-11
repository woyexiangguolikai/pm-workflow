# -*- coding: utf-8 -*-
"""design-spec.html 渲染复核

三件事：
1. 真渲染：用系统 Edge 无头打开页面并 dump DOM（不依赖任何浏览器自动化工具）
2. 结构计数：每个页签实际渲染出多少张卡 / 多少色块 / 多少表，防止「看起来生成了其实空着」
3. 双视图守卫：复用 02-prd 的官方守卫规则，业务视图不得残留技术标识

⚠️ --dump-dom 的输出会包含内联 <script> 源码本身，所以只对
   <!--VSTART--> 到 <!--VEND--> 之间的渲染结果做计数与检查。

用法：python check-design.py
"""

import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'design-spec.html')
TOK = os.path.join(HERE, 'tokens.json')
GUARD = os.path.join(HERE, '..', '02-prd', 'check-biz-lang.py')
EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'

if not os.path.exists(EDGE):
    EDGE = r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'

# --------------------------------------------------------- 载入官方守卫
spec = importlib.util.spec_from_file_location('guard', GUARD)
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
LEAKS = guard.LEAKS
strip_class = guard.strip_class

# --------------------------------------------------------- 注入全页签渲染
with open(SRC, 'r', encoding='utf-8') as f:
    html = f.read()

PROBE = '''
<!--VSTART-->
<script>
(function(){
  var names=['overview','color','primitive','component','page','a11y'];
  var fns=[vOverview,vColor,vPrimitive,vComponent,vPage,vA11y];
  var box=document.createElement('div');box.id='ALLTABS';
  var errs=[];
  for(var i=0;i<names.length;i++){
    var d=document.createElement('div');d.setAttribute('data-tab',names[i]);
    try{d.innerHTML=fns[i]();}catch(e){errs.push(names[i]+':'+(e&&e.message));}
    box.appendChild(d);
  }
  var e=document.createElement('div');e.id='ERRBOX';
  e.setAttribute('data-errs',errs.join(' || ')||'none');
  document.body.appendChild(box);document.body.appendChild(e);
  /* 组件与页面页签的卡片由独立函数填充，这里手动触发一次，否则只渲染出空壳 */
  try{renderComponents()}catch(x){errs.push('renderComponents:'+(x&&x.message))}
  try{renderPages()}catch(x){errs.push('renderPages:'+(x&&x.message))}
  try{renderLex()}catch(x){errs.push('renderLex:'+(x&&x.message))}
  e.setAttribute('data-errs',errs.join(' || ')||'none');
})();
</script>
<!--VEND-->
'''
html2 = html.replace('</body>', PROBE + '</body>')

tmp = os.path.join(tempfile.gettempdir(), 'ds_probe.html')
with open(tmp, 'w', encoding='utf-8') as f:
    f.write(html2)

url = 'file:///' + tmp.replace('\\', '/').replace(' ', '%20')
r = subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--no-sandbox',
                    '--virtual-time-budget=8000', '--dump-dom', url],
                   capture_output=True, text=True, encoding='utf-8', errors='replace')
dom = r.stdout or ''
if 'VSTART' not in dom:
    print('[失败] Edge 未渲染出内容，dump 长度 %d' % len(dom))
    print((r.stderr or '')[:600])
    sys.exit(1)

region = dom.split('<!--VSTART-->', 1)[1].split('<!--VEND-->', 1)[0] \
    if '<!--VSTART-->' in dom and '<!--VEND-->' in dom else dom

# 渲染期异常
merr = re.search(r'id="ERRBOX"[^>]*data-errs="([^"]*)"', dom)
render_errs = [] if not merr else ([] if merr.group(1) == 'none' else merr.group(1).split(' || '))

# 切出每个页签的渲染结果
tabs = {}
for m in re.finditer(r'<div data-tab="([a-z0-9]+)">([\s\S]*?)(?=<div data-tab="|<div id="ERRBOX")', region):
    tabs[m.group(1)] = m.group(2)
if not tabs:
    # 退化：整体切 6 段
    parts = region.split('<div data-tab="')
    for p in parts[1:]:
        name = p.split('"', 1)[0]
        tabs[name] = p

print('=' * 76)
print('design-spec.html 渲染复核')
print('=' * 76)
if render_errs:
    print()
    print('[0] 渲染期异常（%d 个页签）：' % len(render_errs))
    for e in render_errs:
        print('    !! ' + e)
else:
    print()
    print('[0] 渲染期异常：无（6 个页签全部渲染成功）')

# --------------------------------------------------------- 1. 结构计数
print()
print('[1] 结构计数（实际渲染出来的元素，不是源码文本）')
print('%-12s %8s %8s %8s %8s' % ('页签', '卡片', '色块', '表格', '行数'))
for k in ('overview', 'color', 'primitive', 'component', 'page', 'a11y'):
    seg = tabs.get(k, '')
    print('%-12s %8d %8d %8d %8d' % (
        k,
        seg.count('class="card"'),
        seg.count('class="sw-box'),
        seg.count('<table>'),
        seg.count('<tr>')))

allseg = ''.join(tabs.values())
lex_m = re.search(r'id="llist"[^>]*data-lex-rows="(\d+)"', dom) or \
        re.search(r'data-lex-rows="(\d+)"', dom)
lex_rows = int(lex_m.group(1)) if lex_m else 0
# 锚点总数从 tokens.json 现算，不写死。写死的话在 _dv_page_*.py 里补一个锚点
# 就得改两个地方（数据源 + 校验脚本），迟早漏一处 —— 校验就退化成假检查了。
with open(TOK, encoding='utf-8') as f:
    _TOK = json.load(f)
ANCHOR_TOTAL = sum(len(p['anchors']) for p in _TOK['pages'])
PAGE_TOTAL = len(_TOK['pages'])

checks = [
    ('页面规格卡', tabs.get('page', '').count('class="p-head"'), PAGE_TOTAL),
    ('组件卡', tabs.get('component', '').count('class="card"'), 16),
    ('主题色卡（7 套）', tabs.get('color', '').count('class="th-head"'), 7),
    ('锚点落位行', tabs.get('page', '').count('data-anchor="1"'), ANCHOR_TOTAL),
    ('对比度断言行', len(re.findall(r'<span class="badge (?:p|e)">(?:通过|豁免)</span>',
                                tabs.get('a11y', ''))), 76),
    ('业务语义词典条目', lex_rows, 168),
]
print()
for name, got, want in checks:
    flag = 'OK ' if got == want else '!! '
    print('    %s%s：渲染 %d，期望 %d' % (flag, name, got, want))

# --------------------------------------------------------- 2. 双视图守卫
print()
print('[2] 双视图守卫（复用 02-prd 的 10 类规则）')
biz = strip_class(allseg, 'tech-only')
tech = strip_class(allseg, 'biz-only')

print()
print('  业务视图（剔除技术标识子树）正文 %d 字符' % len(biz))
biz_bad = 0
if os.environ.get('CTX'):
    plain = re.sub(r'<[^>]+>', ' ', biz)
    plain = re.sub(r'\s+', ' ', plain)


def show_ctx(word, plain):
    for mm in re.finditer(re.escape(word), plain):
        a = max(0, mm.start() - 45)
        print('        … %s …' % plain[a:mm.start() + len(word) + 45])
        break


for name, pat in LEAKS.items():
    hits = sorted(set(re.findall(pat, biz)))
    if hits:
        biz_bad += 1
        print('    [残留] %s %s（共 %d）' % (name, hits[:8], len(hits)))
        if os.environ.get('CTX'):
            for hh in (hits if os.environ.get('CTX') == 'all' else hits[:6]):
                show_ctx(hh, plain)
if not biz_bad:
    print('    10 类检查全部通过：业务视图无技术标识残留')

print()
print('  技术视图（剔除业务名子树）正文 %d 字符' % len(tech))
tech_must = [
    ('页面路径', r'pages/[a-z0-9\-/]+', 12),
    ('后台路径', r'\badmin/[a-z\-]+', 11),
    ('十六进制色值', r'#[0-9a-fA-F]{6}', 60),
    ('主题语义键', r'\b(?:font_color_readable|discount_font|downgrade_notice|yikatong_brand)\b', 4),
    ('锚点 id', r'>[a-z][a-z0-9]*-[a-z0-9\-]*<', 20),
]
tech_bad = 0
for name, pat, least in tech_must:
    hits = sorted(set(re.findall(pat, tech)))
    ok = len(hits) >= least
    if not ok:
        tech_bad += 1
    print('    %s%-12s 命中 %d 个（下限 %d）' % ('OK  ' if ok else '!!  ', name, len(hits), least))
if not tech_bad:
    print('    技术视图信息完整：双轨不丢信息')

# --------------------------------------------------------- 3. 取值列回归
print()
print('[3] 取值列回归（业务视图不留空占位、不留英文技术词）')
import json

TOK = json.load(open(os.path.join(HERE, 'tokens.json'), encoding='utf-8'))
LEXI = TOK.get('lexicon', {})
ALLBIZ = {v['biz'] for v in LEXI.values() if v.get('biz')}
biz_hits = {b for b in ALLBIZ if b in biz}
stub = biz.count('见技术视图')
lex_bad = 0
if stub:
    lex_bad += 1
    print('    [残留] 「见技术视图」占位 %d 处（期望 0）' % stub)
got = len(biz_hits)
ok = got >= 100
if not ok:
    lex_bad += 1
print('    %s词典业务说法在业务视图出现 %d / %d 种（下限 100）'
      % ('OK  ' if ok else '!!  ', got, len(ALLBIZ)))
resid = sorted(set(re.findall(r'\b(?:padding|cursor|transform|aria-disabled|tabular-nums|min-width|variants|hover)\b', biz)))
if resid:
    lex_bad += 1
    print('    [残留] 英文技术词 %s（共 %d 类）' % (resid[:8], len(resid)))
else:
    print('    OK  英文技术词 0 类（padding / cursor / transform 等已转中文）')
if not lex_bad:
    print('    业务视图每一处取值都有中文说法，没有空白列')

# --------------------------------------------------------- 3. 结论
print()
print('=' * 76)
if render_errs or biz_bad or tech_bad or lex_bad or any(g != w for _, g, w in checks):
    print('[复核未通过] 见上方 !! 标记')
    sys.exit(1)
print('[复核通过] 结构计数全部命中，业务视图技术标识为零，技术视图信息完整，取值列无空占位')
