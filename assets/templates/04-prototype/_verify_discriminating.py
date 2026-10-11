# -*- coding: utf-8 -*-
"""变异测试：证明「业务视图技术信息清零」这条检查真的有判别力。

动机：
    上一版这条检查拿 `.t-only` 的全集当样本，而画布上 30 个 `.t-only` 恰好全是
    锚点框 —— 锚点框另有 `.an{display:none}` 管着，所以哪怕 `body.biz .t-only`
    这条规则整条不存在，检查照样全绿。这就是典型的假绿灯：在「规则生效」和
    「规则根本没写」这两个世界状态下，输出一模一样。

    修法是改样本（只认非锚点框的 .t-only）。但改完必须**证明**新的检查能抓错，
    否则只是换了一个没验证过的绿灯。

做法：
    把产物里的那条规则删掉（变异），跑同一套探针。期望：
        变异前 bizHidden == bizProbed（全隐藏）
        变异后 bizHidden <  bizProbed（露出来了）
    如果变异后仍然相等，说明这条检查依旧没有判别力，得回去重写。
"""
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RULE = 'body.biz .t-only{display:none!important}'


def load_checker():
    spec = importlib.util.spec_from_file_location(
        'proto_check', os.path.join(HERE, 'check-proto.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    m = load_checker()
    src = open(m.CANVAS, encoding='utf-8').read()
    if RULE not in src:
        print('[变异测试] 产物里找不到规则 %s —— 变异无效，先确认规则已写入' % RULE)
        return 1

    emap = json.load(open(m.EMAP, encoding='utf-8'))
    tok = json.load(open(m.TOKENS, encoding='utf-8'))

    print('[变异测试] 基线（规则在位）')
    base = m.render_check()
    print('  bizHidden=%s / bizProbed=%s / techShown=%s'
          % (base['bizHidden'], base['bizProbed'], base['techShown']))

    mut_path = os.path.join(HERE, '_mut-canvas.html')
    with open(mut_path, 'w', encoding='utf-8') as f:
        f.write(src.replace(RULE, ''))
    m.CANVAS = mut_path
    print('[变异测试] 变异（删掉规则）')
    mut = m.render_check()
    os.remove(mut_path)
    print('  bizHidden=%s / bizProbed=%s' % (mut['bizHidden'], mut['bizProbed']))

    ok_base = base['bizProbed'] > 0 and base['bizHidden'] == base['bizProbed']
    ok_mut = mut['bizHidden'] < mut['bizProbed']
    print()
    if ok_base and ok_mut:
        print('[变异测试通过] 检查有判别力：删掉规则 → 业务视图立刻露出 %d 处技术信息'
              % (mut['bizProbed'] - mut['bizHidden']))
        return 0
    if not ok_base:
        print('[变异测试失败] 规则在位时就没能全隐藏，检查本身有问题')
    if not ok_mut:
        print('[变异测试失败] 删掉规则检查仍然全绿 —— 这条检查没有判别力，'
              '说明样本又被锚点框带偏了')
    return 1


if __name__ == '__main__':
    sys.exit(main())
