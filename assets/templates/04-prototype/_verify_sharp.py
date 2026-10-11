# -*- coding: utf-8 -*-
"""验证「放大缩小都一样清晰」：把画布渲染出来的图，跟同一张源图按理想方式缩放的
结果逐区域比对清晰度。

为什么非要跟参照系比：
    「清晰度 3.72」这种绝对值说明不了问题 —— 换个内容、换个字号它就变了。
    有意义的问法是：**画布渲染出来的，和「直接拿源图缩到同样大小」相差多少？**
    后者就是理想上限。比值接近 1 说明画布没有额外损失；掉到 0.6 就是肉眼可见的糊。

覆盖四个缩放档：
    fit（约 0.44，缩得很小）/ 1.0（原尺寸）/ 2.0 / max（一路顶到源图分辨力上限）
要求每一档的比值都不低于 0.85 —— 这正是用户要的「放大缩小都一样清晰」。

同时它也是守卫：
    把 will-change:transform 加回世界层，或者把缩放上限改回写死的 3.2，
    这个比值会掉下来。check-proto 的预算断言只算「够不够像素」，算不出光栅化被贴图放大。
"""
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _viewpad import read_png          # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
EDGE = r'C:/Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if not os.path.exists(EDGE):
    EDGE = r'C:/Program Files\Microsoft\Edge\Application\msedge.exe'
OUT = os.path.join(HERE, '_diag')
WIN_W, WIN_H = 1400, 1000
PID = 'PG-A4'
FLOOR = 0.85


def sharp(rows, bpp, x0, y0, x1, y1):
    """水平+垂直亮度梯度均值。越大越清晰。rows 是每行 bytes。"""
    tot, n = 0, 0
    for y in range(max(1, y0), y1):
        r, p = rows[y], rows[y - 1]
        for x in range(max(1, x0), x1):
            i = x * bpp
            l = (r[i] * 299 + r[i + 1] * 587 + r[i + 2] * 114) // 1000
            lu = (p[i] * 299 + p[i + 1] * 587 + p[i + 2] * 114) // 1000
            j = (x - 1) * bpp
            ll = (r[j] * 299 + r[j + 1] * 587 + r[j + 2] * 114) // 1000
            tot += abs(l - ll) + abs(l - lu)
            n += 2
    return tot / float(n) if n else 0.0


def ref_rows(nw, nh, bpp, rows, u0, v0, u1, v1, ow, oh):
    """把源图的 [u0,u1]×[v0,v1] 归一化区域，按面积加权缩到 ow×oh。"""
    out = []
    for oy in range(oh):
        sy0 = (v0 + (v1 - v0) * oy / oh) * nh
        sy1 = (v0 + (v1 - v0) * (oy + 1) / oh) * nh
        line = bytearray(ow * 3)
        for ox in range(ow):
            sx0 = (u0 + (u1 - u0) * ox / ow) * nw
            sx1 = (u0 + (u1 - u0) * (ox + 1) / ow) * nw
            acc = [0.0, 0.0, 0.0]
            wsum = 0.0
            for sy in range(int(sy0), max(int(sy0) + 1, min(nh, int(sy1) + 1))):
                wy = min(sy + 1.0, sy1) - max(float(sy), sy0)
                if wy <= 0:
                    continue
                r = rows[sy]
                for sx in range(int(sx0), max(int(sx0) + 1, min(nw, int(sx1) + 1))):
                    wx = min(sx + 1.0, sx1) - max(float(sx), sx0)
                    if wx <= 0:
                        continue
                    w = wx * wy
                    i = sx * bpp
                    acc[0] += r[i] * w
                    acc[1] += r[i + 1] * w
                    acc[2] += r[i + 2] * w
                    wsum += w
            if wsum:
                line[ox * 3] = int(acc[0] / wsum)
                line[ox * 3 + 1] = int(acc[1] / wsum)
                line[ox * 3 + 2] = int(acc[2] / wsum)
        out.append(bytes(line))
    return out


def probe(setup, mutate=False):
    """在目标缩放下截一张图，并回报卡片图区在页面上的矩形。

    setup 是一段 JS：要么调用 fit(56)，要么自己设 vs/vx/vy。
    不能写成 `vs=<表达式>` 再让 fit 走这条路 —— fit() 返回 undefined，
    赋给 vs 会让整个画布崩成 NaN，而且报错信息是 KeyError，很难往回追。

    mutate=True 时把 will-change:transform 注入回去，用来做变异测试：
    见 main() 末尾 —— 证明这套清晰度验证真的抓得住「世界层被当贴图放大」。
    """
    src = open(os.path.join(HERE, 'prototype-canvas.html'), encoding='utf-8').read()
    if mutate:
        src = src.replace('</head>', '<style>#world{will-change:transform}</style></head>')
    js = ("var el=document.querySelector('.el.page[data-id=\"" + PID + "\"]');"
          "var b=board.getBoundingClientRect();"
          + setup +
          "var im=el.querySelector('.el-img img');var t=el.querySelector('.el-img');"
          "var r=t.getBoundingClientRect();"
          "document.title='R:'+JSON.stringify({x:r.left,y:r.top,w:r.width,h:r.height,"
          "nw:im.naturalWidth,nh:im.naturalHeight,vs:vs});")
    hp = os.path.join(HERE, '_vsharp.html')
    with open(hp, 'w', encoding='utf-8') as f:
        f.write(src.replace('</body>', '<script>%s</script></body>' % js))
    pp = os.path.join(OUT, '_vsharp.png')
    r = subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--no-sandbox',
                        '--hide-scrollbars', '--window-size=%d,%d' % (WIN_W, WIN_H),
                        '--force-device-scale-factor=1', '--virtual-time-budget=9000',
                        '--screenshot=' + pp.replace('\\', '/'), '--dump-dom',
                        'file:///' + hp.replace('\\', '/')],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    os.remove(hp)
    m = re.search(r'<title>R:(.*?)</title>', r.stdout or '', re.S)
    return (json.loads(m.group(1).replace('&quot;', '"')) if m else None), pp


def focus(z):
    return ("vs=Math.min(%s,maxZ());" % z +
            "vx=b.width/2-(el.offsetLeft+el.offsetWidth/2)*vs;"
            "vy=b.height/2-(el.offsetTop+el.offsetHeight/2)*vs;apply();")


def measure(name, setup, snw, snh, sbpp, srows, mutate=False, quiet=False):
    """返回 (比值, 描述行)。比值 = 画布清晰度 / 理想缩放清晰度。"""
    info, pp = probe(setup, mutate)
    if not info:
        if not quiet:
            print('  %-10s 探针无输出' % name)
        return None, '探针无输出'
    w, h, bpp, rows = read_png(pp)
    # 图区可能超出窗口（高倍放大时），只比可见部分
    x0 = max(0, int(info['x'])); y0 = max(0, int(info['y']))
    x1 = min(w, int(info['x'] + info['w'])); y1 = min(h, int(info['y'] + info['h']))
    ins = 6
    x0, y0, x1, y1 = x0 + ins, y0 + ins, x1 - ins, y1 - ins
    if x1 - x0 < 40 or y1 - y0 < 40:
        if not quiet:
            print('  %-10s 可见区域太小（%dx%d），跳过' % (name, x1 - x0, y1 - y0))
        return None, '可见区域太小'
    u0 = (x0 - info['x']) / info['w']
    v0 = (y0 - info['y']) / info['h']
    u1 = (x1 - info['x']) / info['w']
    v1 = (y1 - info['y']) / info['h']
    ref = ref_rows(snw, snh, sbpp, srows, u0, v0, u1, v1, x1 - x0, y1 - y0)
    a = sharp(rows, bpp, x0, y0, x1, y1)
    b = sharp(ref, 3, 0, 0, x1 - x0, y1 - y0)
    ratio = a / b if b else 0
    if not quiet:
        flag = 'OK' if ratio >= FLOOR else '偏低'
        print('  %-10s 缩放 %5.2fx ｜ 比可见 %4dx%-4d ｜ 画布 %6.2f ｜ 理想 %6.2f ｜ '
              '比值 %.2f  %s' % (name, info['vs'], x1 - x0, y1 - y0, a, b, ratio, flag))
    return ratio, '缩放 %.2fx' % info['vs']


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    shot = os.path.join(HERE, 'shots', '%s-main.png' % PID.lower())
    snw, snh, sbpp, srows = read_png(shot)
    args = (snw, snh, sbpp, srows)

    PAN = ("board.dispatchEvent(new MouseEvent('mousedown',{clientX:600,clientY:500,"
           "button:0,bubbles:true}));"
           "window.dispatchEvent(new MouseEvent('mousemove',{clientX:660,clientY:540,"
           "bubbles:true}));"
           "window.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));")
    cases = [('全貌 fit', 'fit(56);'), ('100%', focus('1')), ('200%', focus('2')),
             ('顶到上限', focus('maxZ()*99')),
             # 拖拽期间会临时挂上 will-change，松手必须撤掉并按新缩放重新光栅化。
             # 如果撤了但不重新光栅化，用户拖一下就永久变糊 —— 这条专门守它。
             ('拖拽之后', PAN + focus('2'))]
    bad = []
    print('[清晰度验证] %s ｜ 源图 %d×%d ｜ 参照 = 源图按理想方式缩到同样大小' %
          (PID, snw, snh))
    for name, setup in cases:
        ratio, _ = measure(name, setup, *args)
        if ratio is None:
            bad.append(name)
        elif ratio < FLOOR:
            bad.append('%s（比值 %.2f）' % (name, ratio))

    # 变异测试：把 will-change:transform 加回去。这套验证必须因此变红，
    # 否则它证明不了「去掉 will-change」这件事有用 —— 那就又是一条假绿灯。
    print()
    print('[变异测试] 把 will-change:transform 注入回世界层，清晰度必须掉下来')
    mut_bad = []
    for name, setup in cases[2:]:
        base, _ = measure(name, setup, *args, quiet=True)
        mut, _ = measure(name, setup, *args, mutate=True, quiet=True)
        if base is None or mut is None:
            print('  %-10s 取样失败，跳过' % name)
            continue
        drop = (1 - mut / base) * 100 if base else 0
        print('  %-10s 正常 %.2f → 变异 %.2f ｜ 掉 %.0f%%  %s'
              % (name, base, mut, drop, 'OK' if drop > 20 else '没掉下来'))
        if drop <= 20:
            mut_bad.append(name)

    print()
    if bad:
        print('[清晰度验证失败] 以下档位比理想缩放明显更糊：%s' % '、'.join(bad))
        return 1
    print('[清晰度验证通过] 四个缩放档的清晰度都达到理想缩放的 %.0f%% 以上'
          % (FLOOR * 100))
    if mut_bad:
        print('[变异测试失败] 注入 will-change 后 %s 的清晰度没掉下来 —— '
              '说明这套验证抓不住「世界层被当贴图放大」，结论不可信' % '、'.join(mut_bad))
        return 1
    print('[变异测试通过] 注入 will-change 后清晰度明显下降 —— 这套验证有判别力')
    return 0


if __name__ == '__main__':
    sys.exit(main())
