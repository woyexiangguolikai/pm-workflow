# -*- coding: utf-8 -*-
"""
build-view.py —— 由 audit.json 生成 audit.html（00 盘点阶段视图）

用法:
    python build-view.py [audit.json] [-o audit.html]

铁律
----
1. **所有数字现算**。本脚本不写死任何计数 —— 改了 audit.json 就重跑，
   数字必须跟着变。写死字面量的视图是**骗人的**：它看起来自洽，实际在撒谎。
2. **端名/ 模块名一律从数据源取**。本脚本不认识任何具体项目的模块名。
3. 视图不引入新信息：这里出现的每一条都能在 audit.json 里找到。

改了 audit.json 一定要重跑本脚本 —— 双格式的意义就在这一条。
"""
from __future__ import annotations

import argparse
import html
import json
import os
import sys

STATUS_STYLE = {
    # status -> (底色, 字色, 说明)
    "新增": ("#e6f4ea", "#137333", "本次要做的新功能"),
    "改造": ("#fef7e0", "#b06000", "在现网基础上改"),
    "保留": ("#f1f3f4", "#5f6368", "现网已有，本次不动"),
    "待定": ("#fce8e6", "#c5221f", "还没确认，需要澄清"),
}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def render(data: dict) -> str:
    modules = data.get("modules") or []
    feats = [f for m in modules for f in (m.get("features") or [])]
    total = len(feats)
    nature = data.get("nature") or "未声明"

    # —— 统计一律现算
    dist = {s: sum(1 for f in feats if f.get("status") == s) for s in STATUS_STYLE}

    rows = []
    for m in modules:
        fs = m.get("features") or []
        rows.append(
            '<tr class="modhead"><td colspan="4">%s <span class="code">%s</span>'
            '<span class="cnt">%d 项</span></td></tr>'
            % (esc(m.get("name")), esc(m.get("code")), len(fs))
        )
        for f in fs:
            st = f.get("status") or ""
            bg, fg, tip = STATUS_STYLE.get(st, ("#f1f3f4", "#5f6368", ""))
            note = ('<div class="note">%s</div>' % esc(f["note"])) if f.get("note") else ""
            rows.append(
                '<tr><td class="id">%s</td><td>%s%s</td>'
                '<td><span class="badge" style="background:%s;color:%s" title="%s">%s</span></td>'
                '<td class="tail"></td></tr>'
                % (esc(f.get("id")), esc(f.get("name")), note, bg, fg, esc(tip), esc(st))
            )

    dist_html = "".join(
        '<span class="stat"><b>%d</b> %s</span>' % (dist[s], s) for s in STATUS_STYLE
    )

    warn = ""
    if nature in ("存量改造", "存量扩展") and dist["改造"] + dist["保留"] == 0:
        warn = ('<div class="warn">声明为「%s」，但没有任何「改造 / 保留」条目 —— '
                '存量功能地图大概没盘。这不是失败，但请回去确认。</div>' % esc(nature))
    if nature == "全新项目":
        warn = ('<div class="info">全新项目：00 盘点可免，功能地图为空是正常的。'
                '本表只记录你额外写下的部分。</div>')

    # 用 replace 而不是 % 格式化 —— CSS 里有大量 `%`（width:100% 等），
    # %-格式化会把它当格式符，直接抛 ValueError。
    # 模板不实测就一定会踩这个坑，所以这里写死这个做法。
    html_out = _TEMPLATE
    for key, val in (("{{WARN}}", warn), ("{{NATURE}}", esc(nature)),
                     ("{{STATS}}", dist_html), ("{{NMOD}}", str(len(modules))),
                     ("{{NTOTAL}}", str(total)), ("{{ROWS}}", "\n".join(rows))):
        html_out = html_out.replace(key, val)
    return html_out


_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{项目名}} · 00 盘点</title>
<style>
:root{--fg:#202124;--mut:#5f6368;--line:#e0e0e0;--bg:#fff;--sub:#f8f9fa}
*{box-sizing:border-box}
body{margin:0;padding:28px;font:14px/1.7 -apple-system,"Segoe UI","Microsoft YaHei",sans-serif;
color:var(--fg);background:var(--bg)}
h1{font-size:20px;margin:0 0 4px}
.sub{color:var(--mut);font-size:13px;margin-bottom:18px}
.card{border:1px solid var(--line);border-radius:8px;padding:14px 16px;margin-bottom:16px;background:var(--sub)}
.k{color:var(--mut)}
.stats{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px}
.stat{font-size:12px;color:var(--mut)}
.stat b{font-size:17px;color:var(--fg);margin-right:3px}
table{width:100%;border-collapse:collapse;margin-top:6px}
td{padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
td.id{font-family:Consolas,monospace;color:var(--mut);white-space:nowrap;width:96px}
tr.modhead td{background:#eef1f5;font-weight:600;padding:9px 8px}
tr.modhead .code{font-family:Consolas,monospace;color:var(--mut);font-weight:400;margin-left:6px}
tr.modhead .cnt{float:right;color:var(--mut);font-weight:400;font-size:12px}
td.tail{width:90px}
.badge{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;white-space:nowrap}
.note{color:var(--mut);font-size:12px;margin-top:3px;white-space:pre-wrap}
.warn{border-left:3px solid #c5221f;background:#fce8e6;padding:10px 12px;border-radius:0 6px 6px 0;margin-bottom:14px}
.info{border-left:3px solid #1a73e8;background:#e8f0fe;padding:10px 12px;border-radius:0 6px 6px 0;margin-bottom:14px}
.foot{color:var(--mut);font-size:12px;margin-top:18px;padding-top:10px;border-top:1px solid var(--line)}
</style></head><body>
<h1>{{项目名}} · 00 存量盘点</h1>
<div class="sub">{{项目名}} · 00 盘点 · {{日期}} · 全部数字由 audit.json 现算</div>

{{WARN}}

<div class="card">
  <div><span class="k">项目性质</span> <b>{{NATURE}}</b></div>
  <div class="stats">{{STATS}}</div>
  <div class="k" style="margin-top:8px">模块 {{NMOD}} 个 / 盘点 {{NTOTAL}} 项</div>
</div>

<table>
{{ROWS}}
</table>

<div class="foot">
  字段口径：<b>新增</b>=本次要做；<b>改造</b>=现网基础上改（PRD 只写差异）；
  <b>保留</b>=现网已有本次不动；<b>待定</b>=未确认，需要澄清。<br>
  改数据源请改 audit.json 后重跑 build-view.py —— 本文件不手写任何计数。
</div>
</body></html>"""


def main() -> int:
    ap = argparse.ArgumentParser(description="生成 audit.html")
    ap.add_argument("source", nargs="?", default="audit.json")
    ap.add_argument("-o", "--out", default=None)
    args = ap.parse_args()

    if not os.path.exists(args.source):
        print("数据源不存在: %s" % args.source, file=sys.stderr)
        return 2
    with open(args.source, encoding="utf-8") as f:
        data = json.load(f)

    out = args.out or os.path.join(
        os.path.dirname(os.path.abspath(args.source)), "audit.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(data))
    print("已写出: %s" % out)
    print("提醒: 改了 audit.json 必须重跑本脚本，否则视图与数据源不一致。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())