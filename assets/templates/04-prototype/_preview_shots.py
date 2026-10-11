# -*- coding: utf-8 -*-
"""白板形态预览图生成器 —— 出 4 张静态图，用于快速确认视觉方向。

为什么需要它：
    prototype-canvas.html 是交互式的，但「交互式」在汇报场景是缺点 —— 发给领导/客户
    看一眼的时候没人会去滚轮缩放。所以固定出 4 个视角的截图：
    全貌 / 放大看细节 / 技术视图带锚点框 / 点开单个页面的灯箱。

    这 4 张同时也是回归基线：改完画布跑一遍，肉眼一对比就知道布局有没有崩。

    ⚠️ 这 4 张是**预览**，不是交付物本体。交付物是 prototype-canvas.html。
    渲染出的图故意放在 preview/ 而不是 shots/ —— shots/ 是每页 1:1 的视觉稿，
    坐标清单（element-map.json）就是按那个目录的尺寸算的，混进去会让人分不清
    哪张图是「被标注的基准图」。
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
EDGE = r'C:/Program Files (x86)\Microsoft\Edge\Application\msedge.exe'
if not os.path.exists(EDGE):
    EDGE = r'C:/Program Files\Microsoft\Edge\Application\msedge.exe'

OUT = os.path.join(HERE, 'preview')
SRC = os.path.join(HERE, 'prototype-canvas.html')

# 聚焦到某一页并指定缩放：把该页中心对到画布中心
def focus(pid, z):
    return ("var el=document.querySelector('.el.page[data-id=\"%s\"]');"
            "var b=board.getBoundingClientRect();"
            "vs=Math.min(%s,maxZ());"
            "vx=b.width/2-(el.offsetLeft+el.offsetWidth/2)*vs;"
            "vy=b.height/2-(el.offsetTop+el.offsetHeight/2)*vs;apply();") % (pid, z)


def open_lb(pid):
    return "openLB(document.querySelector('.el.page[data-id=\"%s\"]'));" % pid


TO_TECH = ("document.body.classList.remove('biz');"
           "document.body.classList.add('tech','anno');"
           "document.getElementById('tView').innerHTML='视图：<b>技术</b>';"
           "document.getElementById('tAnno').classList.add('on');")

CASES = [
    ('1-全貌', ""),
    ('2-放大看细节', focus('PG-A4', '0.92')),
    ('3-技术视图-锚点框', TO_TECH + focus('PG-A4', '0.92')),
    ('4-点开单个页面', open_lb('PG-A4')),
    # 顶到清晰度上限（= 源图分辨率 1:1）。这张是「放大后不糊」的直接证据：
    # 到这个倍率图像仍与源图逐像素同级，右上角同时显示「已达上限」。
    ('5-顶到清晰上限', focus('PG-A4', '99')),
    # 后台端是 1440 宽的横屏，缩略卡天生比小程序窄卡小得多 ——
    # 单出一张放大的，用来确认后台页在画布上不是「只能看个框」。
    ('6-后台页放大', focus('PG-B6', '0.92')),
    ('7-后台页灯箱', open_lb('PG-B6')),
]


def main():
    if not os.path.isdir(OUT):
        os.makedirs(OUT)
    src = open(SRC, encoding='utf-8').read()
    for tag, js in CASES:
        hp = os.path.join(HERE, '_pv.html')
        with open(hp, 'w', encoding='utf-8') as f:
            f.write(src.replace('</body>', '<script>%s</script></body>' % js))
        pp = os.path.join(OUT, 'whiteboard-%s.png' % tag)
        subprocess.run([EDGE, '--headless=new', '--disable-gpu', '--no-sandbox',
                        '--hide-scrollbars', '--window-size=1720,1080',
                        '--force-device-scale-factor=1', '--virtual-time-budget=9000',
                        '--screenshot=' + pp.replace('\\', '/'),
                        'file:///' + hp.replace('\\', '/')],
                       capture_output=True, text=True)
        os.remove(hp)
        print('  %-18s %8.0f KB' % (tag, os.path.getsize(pp) / 1024.0))


if __name__ == '__main__':
    main()
