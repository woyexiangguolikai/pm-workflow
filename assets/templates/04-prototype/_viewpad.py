# -*- coding: utf-8 -*-
"""实测「视口原点在截图里的像素位置」。

为什么要实测而不是照着推测写死：
    标注的全部价值建立在「坐标能落到图上的正确位置」这一点上。之前标定的是
    「视口 = 窗口 − (24, 92)」，但那只说明探针读到的 window.innerWidth 少了 24/92，
    不等于**截图里边框占多少、占在哪一侧**。差几像素不会报错，只会让标注框整体
    偏一点 —— 这种错最危险，因为看起来是对的。

方法：
    在 position:fixed 的 (0,0) 放一个纯红方块（视口原点），截图，
    再用纯 Python 解 PNG 找红色像素的最小 x/y。那就是视口原点的图上像素。

PNG 解码只用标准库 zlib（本机没有 Pillow，也不为这个装一个）。
Edge 输出的是 8bit RGBA、非隔行、逐行 filter，按 PNG 规范还原即可。
"""

import json
import os
import struct
import subprocess
import sys
import tempfile
import zlib

EDGE = r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if not os.path.exists(EDGE):
    EDGE = r'C:\Program Files\Microsoft\Edge\Application\msedge.exe'

HERE = os.path.dirname(os.path.abspath(__file__))

WIN_W, WIN_H = 516, 949          # 与 build-proto 用的窗口尺寸一致
DSF = 2
MARK = 24                        # 方块边长（CSS px）


def read_png(path):
    """返回 (w, h, 每行 bytes 的像素数据 list)。只处理 8bit RGBA、非隔行。"""
    with open(path, 'rb') as f:
        data = f.read()
    assert data[:8] == b'\x89PNG\r\n\x1a\n', '不是 PNG'
    pos, idat, w, h, bd, ct = 8, b'', 0, 0, 0, 0
    while pos < len(data):
        ln = struct.unpack('>I', data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        if typ == b'IHDR':
            w, h, bd, ct = struct.unpack('>IIBB', body[:10])
        elif typ == b'IDAT':
            idat += body
        elif typ == b'IEND':
            break
        pos += 12 + ln
    assert bd == 8 and ct in (2, 6), '只支持 8bit RGB/RGBA，实际 bitdepth=%s colortype=%s' % (bd, ct)
    raw = zlib.decompress(idat)
    bpp = 3 if ct == 2 else 4          # Edge 不需要 alpha 时输出 rgb24，省 1/4 体积
    stride = w * bpp
    out, prev = [], bytearray(stride)
    p = 0
    for _ in range(h):
        ft = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride
        if ft == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif ft == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 255
        elif ft == 3:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 255
        elif ft == 4:
            for i in range(stride):
                a = line[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        out.append(bytes(line))
        prev = line
    return w, h, bpp, out


def find_mark(w, h, rows, bpp):
    """返回红色区域的 (min_x, min_y, max_x, max_y)"""
    xs, ys = [], []
    for y in range(h):
        r = rows[y]
        for x in range(0, w * bpp, bpp):
            if r[x] > 200 and r[x + 1] < 60 and r[x + 2] < 60:
                xs.append(x // bpp)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


def probe_page():
    """决定性实验：在**真实页面**里把红块摆到手机帧左上角，看它落在图的哪个像素。

    红块位置是拿 `.phone` 的 getBoundingClientRect() 算的（就是探针写进
    element-map 的 frame.x/frame.y），所以：
        · 红块图上位置 == frame × dsf  →  图就是视口内容，坐标可直接当图上坐标
        · 差一个固定量                  →  那个差就是窗口装饰带来的偏移
    """
    hp = os.path.join(HERE, 'pages', 'pg-a1-main.html')
    with open(hp, encoding='utf-8') as f:
        html = f.read()
    inject = """
<script>
(function(){
  var p=document.querySelector('.phone'), r=p.getBoundingClientRect();
  var d=document.createElement('div');
  d.style.cssText='position:fixed;left:'+r.left+'px;top:'+r.top+'px;width:20px;height:20px;'
    +'background:#ff0000;z-index:2147483647';
  document.body.appendChild(d);
  document.title='F:'+JSON.stringify({fx:r.left,fy:r.top,fw:r.width,fh:r.height,
    iw:window.innerWidth,ih:window.innerHeight,dpr:window.devicePixelRatio});
})();
</script>
"""
    tmp = os.path.join(HERE, 'pages', '_pad-probe.html')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(html.replace('</body>', inject + '</body>'))
    pp = os.path.join(HERE, 'shots', '_pad-probe.png')
    url = 'file:///' + tmp.replace('\\', '/').replace(' ', '%20')
    r = subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--no-sandbox',
                        '--hide-scrollbars', '--window-size=%d,%d' % (WIN_W, WIN_H),
                        '--force-device-scale-factor=%d' % DSF, '--virtual-time-budget=5000',
                        '--screenshot=' + pp.replace('\\', '/'), '--dump-dom', url],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    os.remove(tmp)
    import re
    m = re.search(r'<title>F:(.*?)</title>', r.stdout or '', re.S)
    info = json.loads(m.group(1).replace('&quot;', '"')) if m else None
    w, h, bpp, rows = read_png(pp)
    box = find_mark(w, h, rows, bpp)
    os.remove(pp)
    print()
    print('[真实页面定标] pg-a1-main')
    if not info:
        print('  探针没输出'); return
    print('  帧相对视口：x=%.1f y=%.1f w=%.0f h=%.0f ｜ 视口 %dx%d dpr=%d'
          % (info['fx'], info['fy'], info['fw'], info['fh'],
             info['iw'], info['ih'], info['dpr']))
    if not box:
        print('  图上没找到红块'); return
    x0, y0, x1, y1 = box
    print('  红块图上像素：左上 (%d, %d)' % (x0, y0))
    print('  按「图上像素 = 帧坐标 × dpr」应为：(%d, %d)'
          % (round(info['fx'] * DSF), round(info['fy'] * DSF)))
    print('  偏差：dx=%d dy=%d' % (x0 - round(info['fx'] * DSF),
                                  y0 - round(info['fy'] * DSF)))
    print('  截图 %dx%d 像素 = %.0fx%.0f CSS px（窗口 %dx%d）'
          % (w, h, w / DSF, h / DSF, WIN_W, WIN_H))
    print()
    print('  → element-map 的 s.img 应写：')
    print('      {"w": %.0f, "h": %.0f, "padX": %.1f, "padY": %.1f}'
          % (w / DSF, h / DSF, (x0 - round(info['fx'] * DSF)) / DSF,
             (y0 - round(info['fy'] * DSF)) / DSF))


def main():
    if '--page' in sys.argv:
        probe_page()
        return
    html = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>html,body{margin:0;padding:0;background:#ffffff}
#mk{position:fixed;left:0;top:0;width:%dpx;height:%dpx;background:#ff0000}
#rb{position:fixed;right:0;bottom:0;width:%dpx;height:%dpx;background:#0000ff}
</style></head><body>
<div id="mk"></div><div id="rb"></div>
<script>
(function(){
  var m=document.getElementById('mk').getBoundingClientRect();
  document.title='V:'+JSON.stringify({iw:window.innerWidth,ih:window.innerHeight,
    ow:window.outerWidth,oh:window.outerHeight,dpr:window.devicePixelRatio,
    mx:m.left,my:m.top});
})();
</script></body></html>""" % (MARK, MARK, MARK, MARK)

    tmpd = tempfile.mkdtemp()
    hp = os.path.join(tmpd, 'pad.html')
    pp = os.path.join(tmpd, 'pad.png')
    with open(hp, 'w', encoding='utf-8') as f:
        f.write(html)
    url = 'file:///' + hp.replace('\\', '/')
    r = subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--no-sandbox',
                        '--hide-scrollbars', '--window-size=%d,%d' % (WIN_W, WIN_H),
                        '--force-device-scale-factor=%d' % DSF,
                        '--virtual-time-budget=4000',
                        '--screenshot=' + pp.replace('\\', '/'), '--dump-dom', url],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    import re
    m = re.search(r'<title>V:(.*?)</title>', r.stdout or '', re.S)
    print('窗口 %dx%d · dsf=%d' % (WIN_W, WIN_H, DSF))
    print('页内探针：%s' % (m.group(1).replace('&quot;', '"') if m else '（读不到）'))

    w, h, bpp, rows = read_png(pp)
    print('截图实际 %dx%d 像素 · 每像素 %d 字节 → %.0fx%.0f CSS px'
          % (w, h, bpp, w / DSF, h / DSF))
    box = find_mark(w, h, rows, bpp)
    if not box:
        print('没找到红色标记，无法定标'); sys.exit(1)
    x0, y0, x1, y1 = box
    print()
    print('红色方块（视口原点）在图上：x %d~%d, y %d~%d' % (x0, x1, y0, y1))
    print('  尺寸 %dx%d 像素（应为 %d×%d）' % (x1 - x0 + 1, y1 - y0 + 1, MARK * DSF, MARK * DSF))
    print()
    print('视口原点在截图里的位置 = (%d, %d) 像素 = (%.1f, %.1f) CSS px'
          % (x0, y0, x0 / DSF, y0 / DSF))
    print('截图 CSS 尺寸 %.0f x %.0f' % (w / DSF, h / DSF))
    print('  左右留白合计 %.0f px（每边 %.1f）· 上下留白合计 %.0f px'
          % (w / DSF - WIN_W + 24, (w / DSF - (WIN_W - 24)) / 2, h / DSF - WIN_H + 92))
    print()
    print('→ build-proto 应写入 element-map 的 img 字段：')
    print('    {"padX": %.1f, "padY": %.1f, "w": %.0f, "h": %.0f}'
          % (x0 / DSF, y0 / DSF, w / DSF, h / DSF))


if __name__ == '__main__':
    main()
