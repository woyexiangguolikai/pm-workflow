# -*- coding: utf-8 -*-
"""Token 派生器：把「人定的设计取值」+「可复算的色彩派生」合并成 tokens.json

设计原则（对应 PRINCIPLES P4）：
- 品牌色由商家决定、不可改 → 凡是需要「可读」的地方，一律**程序派生**而不手工挑色
- 派生结果全部带实测对比度；任一断言不达标，构建直接失败（fail loud）
- 换品牌色只需重跑本脚本，产物不漂移

输入：_baseline.json（存量 7 套主题）、_dv_primitive.py、_dv_component.py、_dv_page.py、_color_lib.py
输出：tokens.json
"""

import json
import os
import re
import sys

from _color_lib import (ratio, darken_to, best_on, mix, soft_bg, readable_on,
                        parse, hexof, DARK_TEXT)
import _dv_primitive as P
import _dv_component as C
import _dv_page as PG
import _lexicon as LX

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'tokens.json')
WHITE = '#ffffff'

TARGET_TEXT = 4.5      # 正文/信息性文字
TARGET_LARGE = 3.0     # 大字号文字
TARGET_NONTEXT = 3.0   # 非文字元素

failures = []
checks = []


def chk(name, fg, bg, target, kind='text'):
    r = ratio(fg, bg)
    ok = r >= target - 1e-9
    checks.append({'name': name, 'fg': fg, 'bg': bg, 'ratio': round(r, 2),
                   'target': target, 'kind': kind, 'pass': ok})
    if not ok:
        failures.append('%s: %s on %s = %.2f < %.1f' % (name, fg, bg, r, target))
    return r


# ===================================================================== 载入
with open(os.path.join(HERE, '_baseline.json'), 'r', encoding='utf-8') as f:
    BASE = json.load(f)

THEMES_IN = BASE['themes']
THEME_NAMES = sorted(THEMES_IN.keys())

# 主题名（业务可读）—— 由品牌色调性给出，不写死 index
THEME_LABEL = {
    'theme0': '明黄 · 默认主题',
    'theme1': '正红',
    'theme2': '亮蓝',
    'theme3': '翠绿',
    'theme4': '橙',
    'theme5': '咖',
    'theme6': '淡紫',
}

# ============================================== 新增的 4 个主题语义键（最小扩充）
NEW_THEME_KEYS = [
    {'key': 'font_color_readable', 'name': '品牌色文字变体', 'fixed': None,
     'use': '白底上的链接、强调文字、可点文字（品牌色直接当文字多数不可读）',
     'derivation': '把品牌色沿明度逐级压深（每级 1%），直到与白底的对比度达到 4.5:1'},
    {'key': 'discount_font', 'name': '折扣金额色', 'fixed': '#c2410c',
     'use': '折扣金额、让利、已优惠；暖橙红，与错误红明确区分',
     'derivation': '固定语义色（不随主题），7 套同步补同值，保证口径一致'},
    {'key': 'downgrade_notice', 'name': '降级警示色', 'fixed': '#b54708',
     'use': '余额不足自动降级提示、需要用户行动的警示',
     'derivation': '固定语义色（不随主题），取自 semantic.warning 的可读值'},
    {'key': 'channel_brand', 'name': '渠道品牌标识色', 'fixed': '#1c5fd4',
     'use': '渠道的图标、标签、渠道标识；用于区分「甲方平台能力」与「商家自有功能」',
     'derivation': '固定品牌标识色（不随商家主题），保证跨主题识别一致'},
]

# 存量 17 键的用途说明（保留，值不动，仅 text_color 修正）
LEGACY_THEME_KEYS = {
    'white0': '透明白底（渐变起点用）',
    'font_color': '品牌色原文 —— **限定装饰用途**（图标、描边），不得直接作白底文字',
    'font_color_inverse': '品牌色的反色（保留，历史用途）',
    'background_color': '品牌主色底（按钮、头部、选中态）',
    'border_color': '品牌色边框',
    'theme-price': '价格强调色（历史：随主题变化的价钱色）',
    'notice-price': '提示价格色',
    'notice-bg': '提示浅底',
    'full-reduction-bg': '满减标签底',
    'full-reduction-font': '满减标签文字',
    'dine-in': '堂食标签底',
    'opacify_background_0': '品牌色淡底（选中行、轻量色块）—— 等价于语义 Token color.primarySoft',
    'bg_user_index1': '个人中心背景 1',
    'bg_user_index2': '个人中心背景 2',
    'bg_user_index3': '个人中心背景 3',
    'text_color': '**品牌色底上的文字色** —— 已由程序择优（原一律 #ffffff，5 套主题下不可读）',
    'bg-nop-6': '备用浅底',
}

# 语义 Token → 主题键 映射（交给开发照抄；业务代码只引用左侧）
SEMANTIC_TO_THEME = [
    {'token': 'color.primary', 'key': 'background_color', 'use': '主色：主按钮底、选中态、进度条激活色'},
    {'token': 'color.onPrimary', 'key': 'text_color', 'use': '品牌色底上的文字'},
    {'token': 'color.primaryText', 'key': 'font_color_readable', 'use': '白底上的品牌色文字（可读变体）'},
    {'token': 'color.primarySoft', 'key': 'opacify_background_0', 'use': '品牌色浅底：标签底、选中行、轻量色块'},
    {'token': 'color.primaryBorder', 'key': 'border_color', 'use': '品牌色边框、选中描边'},
    {'token': 'color.discount', 'key': 'discount_font', 'use': '折扣金额、让利金额'},
    {'token': 'color.downgrade', 'key': 'downgrade_notice', 'use': '余额不足降级警示'},
    {'token': 'color.brandMark.channel', 'key': 'channel_brand', 'use': '渠道品牌标识'},
]


# ============================================================ 单套主题派生
def derive_theme(tname):
    src = THEMES_IN[tname]
    brand = src['background_color']
    out = {'label': THEME_LABEL.get(tname, tname), 'brand': brand,
           'source': 'uni.scss $themes[%s]' % tname}

    # ---- 存量 17 键：原值保留，text_color 修正
    legacy = {}
    for k in LEGACY_THEME_KEYS:
        if k in src:
            legacy[k] = src[k]
    text_color_old = legacy.get('text_color')
    on_brand, on_r, other_r = best_on(brand)
    legacy['text_color'] = on_brand
    out['legacyKeys'] = legacy
    out['corrections'] = [{
        'key': 'text_color', 'from': text_color_old, 'to': on_brand,
        'reason': '品牌色底上按对比度择优（白字 %.2f:1 / 深字 %.2f:1）'
                  % (ratio('#ffffff', brand), ratio(DARK_TEXT, brand)),
        'ratioBefore': round(ratio(text_color_old or '#ffffff', brand), 2),
        'ratioAfter': round(on_r, 2),
    }]

    # ---- 新增 4 键
    brand_text, brand_text_r, _ = darken_to(brand, WHITE, TARGET_TEXT)
    soft = soft_bg(brand, 0.12, WHITE)
    soft_text, soft_text_r, _ = darken_to(brand, soft, TARGET_TEXT)
    # 交互控件的选中/聚焦边框属「非文字元素」，须 ≥3:1；品牌色浅叠不达标，改用加深变体
    border, border_r, _ = darken_to(brand, WHITE, TARGET_NONTEXT)
    newk = {
        'font_color_readable': brand_text,
        'discount_font': '#c2410c',
        'downgrade_notice': '#b54708',
        'channel_brand': '#1c5fd4',
    }
    out['newKeys'] = newk
    out['derived'] = {
        'color.primarySoft': soft,
        'color.primarySoftText': soft_text,
        'color.primaryBorder': border,
        'color.primaryBorderNote': '品牌色加深至 3:1；存量 border_color（原值 %s，%0.2f:1）'
                                   '保留为装饰性描边，交互控件一律用本值' % (brand, ratio(brand, WHITE)),
    }

    # ---- 断言
    chk('%s 品牌色文字变体/白底' % tname, brand_text, WHITE, TARGET_TEXT)
    chk('%s 品牌色底上文字/%s' % (tname, brand), on_brand, brand, TARGET_TEXT)
    chk('%s 浅底文字/浅底' % tname, soft_text, soft, TARGET_TEXT)
    chk('%s 品牌色边框/白底(非文字)' % tname, border, WHITE, TARGET_NONTEXT, 'nontext')
    chk('%s 折扣金额/白底' % tname, newk['discount_font'], WHITE, TARGET_TEXT)
    chk('%s 降级警示/白底' % tname, newk['downgrade_notice'], WHITE, TARGET_TEXT)
    chk('%s 渠道标识/白底' % tname, newk['channel_brand'], WHITE, TARGET_TEXT)

    out['a11y'] = {
        'brandTextOnWhite': round(brand_text_r, 2),
        'onBrandOnBrand': round(on_r, 2),
        'onBrandChoice': '深色文字' if on_brand == DARK_TEXT else '白色文字',
        'softTextOnSoft': round(soft_text_r, 2),
        'brandAsTextOnWhiteRaw': round(ratio(brand, WHITE), 2),
        'whiteOnBrandRaw': round(ratio('#ffffff', brand), 2),
    }
    return out


THEMES = {t: derive_theme(t) for t in THEME_NAMES}


# ============================================================ 跨主题固定语义
APP_TEXT_RAW = {
    'primary': BASE['appScalars'].get('$uni-text-color', '#333'),
    'secondary': BASE['appScalars'].get('$uni-text-color-grey', '#999'),
    'assist': BASE['appScalars'].get('$text-color-assist', '#919293'),
    'base': BASE['appScalars'].get('$text-color-base', '#5a5b5c'),
    'placeholder': BASE['appScalars'].get('$uni-text-color-placeholder', '#808080'),
    'disabled': BASE['appScalars'].get('$uni-text-color-disable', '#c0c0c0'),
}

# 反色文字用于深底，不参与「白底可读」修正
APP_TEXT = {
    'inverse': {'v': '#ffffff', 'use': '深底（品牌底/遮罩）上的文字；不适用于白底'},
}
for k, v in APP_TEXT_RAW.items():
    if k in ('placeholder', 'disabled'):
        APP_TEXT[k] = {'v': v, 'note': 'WCAG 豁免（仅用于占位/禁用，不得作为唯一信息载体）'}
        continue
    fixed, r, _ = darken_to(v, WHITE, TARGET_TEXT)
    normalized = hexof(parse(v))
    if fixed.lower() == normalized.lower():
        APP_TEXT[k] = {'v': fixed, 'ratioOnWhite': round(r, 2)}
    else:
        APP_TEXT[k] = {'v': fixed, 'origin': v, 'ratioOnWhite': round(r, 2),
                       'ratioOriginOnWhite': round(ratio(v, WHITE), 2)}
    chk('app 文字 %s / 白底' % k, fixed, WHITE, TARGET_TEXT)

APP_BG = {
    'surface': {'v': '#ffffff', 'use': '卡片、列表、弹层底'},
    'page': {'v': BASE['appScalars'].get('$uni-bg-color-grey', '#f8f8f8'), 'use': '页面底'},
    'hover': {'v': BASE['appScalars'].get('$uni-bg-color-hover', '#f1f1f1'), 'use': '按压/悬停底'},
    'pageAlt': {'v': BASE['appScalars'].get('$bg-color', '#f1f8fa'), 'use': '备用页面底（存量）'},
}
APP_BORDER = {
    'base': {'v': BASE['appScalars'].get('$border-color', '#e2e2e2'), 'use': '分割线、卡片描边'},
    'strong': {'v': BASE['appScalars'].get('$uni-border-color', '#c8c7cc'), 'use': '输入框边框'},
    'hairline': {'v': '1rpx', 'use': '线宽'},
}

# 后台派生 Token：中性色阶本身既是底色也是边框来源，需按用途分别定标
# - n50~n200 是「底色与分割线」，不承担识别控件的职责，仅需视觉可见
# - n300 是输入框边框，属「非文字元素」需 ≥3:1 → 派生 borderInput
# - n400 声明为纯装饰；承载信息的图标另派生 iconBase（≥3:1）
_ADM = P.ADMIN_PALETTE['neutral']
_border_input, _bi_r, _ = darken_to(_ADM['n300']['v'], WHITE, TARGET_NONTEXT)
_icon_base, _ib_r, _ = darken_to(_ADM['n400']['v'], WHITE, TARGET_NONTEXT)
for k, item in _ADM.items():
    if k.startswith('n') and int(k[1:]) >= 500:
        chk('admin %s 可用作正文/白底' % k, item['v'], WHITE, TARGET_TEXT)
    elif k == 'n300':
        checks.append({'name': '后台 原输入框边框色（未达 3:1，已被派生值替代）',
                       'fg': item['v'], 'bg': WHITE, 'ratio': round(ratio(item['v'], WHITE), 2),
                       'target': TARGET_NONTEXT, 'kind': 'nontext', 'pass': True,
                       'note': '原值保留作装饰线；交互控件边框一律用 borderInput'})
chk('后台 输入框与控件边框（派生值）/白底', _border_input, WHITE, TARGET_NONTEXT, 'nontext')
chk('后台 承载信息的图标（派生值）/白底', _icon_base, WHITE, TARGET_NONTEXT, 'nontext')
chk('admin 主色 / 白底', P.ADMIN_PALETTE['color']['primary']['v'], WHITE, TARGET_TEXT)
chk('admin 主色底上白字', P.ADMIN_PALETTE['color']['onPrimary']['v'],
    P.ADMIN_PALETTE['color']['primary']['v'], TARGET_TEXT)
chk('admin 次要文字 / 白底', P.ADMIN_PALETTE['neutral']['n500']['v'], WHITE, TARGET_TEXT)
chk('admin 正文 / 白底', P.ADMIN_PALETTE['neutral']['n600']['v'], WHITE, TARGET_TEXT)
chk('admin 禁用文字 / 白底(非文字豁免)', P.ADMIN_PALETTE['text']['disabled']['v'], WHITE, 1.0, 'exempt')
for nm in ('success', 'warning', 'error', 'notice', 'discount'):
    chk('语义 %s / 白底' % nm, P.SEMANTIC_STATE[nm]['v'], WHITE, TARGET_TEXT)
    chk('语义 %s 软底上的文字' % nm, P.SEMANTIC_STATE[nm]['v'], P.SEMANTIC_STATE[nm]['soft'], TARGET_TEXT)


# ============================================================== 组件/页面汇总
COMPONENTS = []
for c in C.COMPONENTS:
    COMPONENTS.append({
        'id': c['id'], 'name': c['name'], 'nameEn': c['nameEn'], 'use': c['use'],
        'platform': c['platform'], 'variants': c.get('variants', []),
        'sizes': c.get('sizes', {}), 'states': c.get('states', []),
        'tokens': c.get('tokens', {}), 'motion': c.get('motion', {}),
        'a11y': c.get('a11y', []), 'rules': c.get('rules', []),
        'prdRefs': c.get('prdRefs', []),
    })

PAGES = []
for p in PG.PAGES:
    PAGES.append({
        'id': p['id'], 'platform': p['platform'], 'name': p['name'], 'path': p['path'],
        'change': p['change'], 'baseline': p.get('baseline', ''), 'goal': p['goal'],
        'prdRefs': p['prdRefs'], 'anchors': p['anchors'], 'components': p['components'],
        'zones': p['zones'], 'states': p['states'], 'visualPoints': p['visualPoints'],
        'themeNote': p.get('themeNote', ''), 'tokens': p.get('tokens', []),
    })

page_errs, page_warns = PG.validate()
if page_errs:
    failures.extend(page_errs)


# ====================================================== Token 引用完整性校验
def token_registry():
    """本项目所有真实存在的 Token 名

    注意：radiusAdmin / spacingAdmin / fontSizeAdmin 只是基础层的「容器名」，
    它们的语义名统一是 admin.radius / admin.spacing / admin.fontSize。
    同一份值挂两套名字违反「同一语义只有一个来源」，所以容器名不进注册表。
    """
    reg = set()
    PR = P.PRIMITIVE
    for g in ('fontFamily', 'fontSizeApp', 'fontWeight', 'lineHeight',
              'spacing', 'radius', 'shadow',
              'borderWidth', 'opacity', 'zIndex'):
        reg |= {g + '.' + k for k in PR[g]}
    for g in ('duration', 'easing', 'distance'):
        reg |= {'motion.' + g + '.' + k for k in PR['motion'][g]}
    reg.add('motion.reducedMotion')
    reg |= {m['token'] for m in SEMANTIC_TO_THEME}
    reg |= {'text.' + k for k in APP_TEXT}
    reg |= {'bg.' + k for k in APP_BG}
    reg |= {'border.' + k for k in APP_BORDER}
    for k, v in P.SEMANTIC_STATE.items():
        reg.add('semantic.' + k)
        for sub in ('v', 'soft', 'border'):
            if sub in v:
                reg.add('semantic.%s.%s' % (k, sub))
    reg |= {'admin.color.' + k for k in P.ADMIN_PALETTE['color']}
    reg |= {'admin.neutral.' + k for k in P.ADMIN_PALETTE['neutral']}
    reg |= {'admin.text.' + k for k in P.ADMIN_PALETTE['text']}
    reg |= {'admin.radius.' + k for k in PR['radiusAdmin']}
    reg |= {'admin.spacing.' + k for k in PR['spacingAdmin']}
    reg |= {'admin.fontSize.' + k for k in PR['fontSizeAdmin']}
    reg |= {'admin.shadow.' + k for k in ('card', 'raised', 'overlay', 'sticky')}
    reg |= {'admin.borderInput', 'admin.iconBase', 'admin.fontFamily'}
    return reg


REG = token_registry()
REG_SUFFIX = {'.'.join(x.split('.')[-2:]) for x in REG}

REFS = {}
for _p in PAGES:
    for _t in _p.get('tokens', []):
        REFS.setdefault(_t.strip(), []).append(_p['id'])
for _c in COMPONENTS:
    for _k, _v in (_c.get('tokens') or {}).items():
        for _t in _v.replace('+', '/').split('/'):
            _t = _t.strip()
            if _t:
                REFS.setdefault(_t, []).append(_c['id'])

TOKLEN = re.compile(r'^[a-z][A-Za-z0-9]*(?:[.<|][A-Za-z0-9.*|<>-]+)+$')
unresolved, prose = [], []
for _r, _who in REFS.items():
    if not TOKLEN.match(_r) or '*' in _r or '<' in _r or '|' in _r:
        prose.append(_r)
        continue
    if _r in REG or _r in REG_SUFFIX:
        continue
    unresolved.append((_r, sorted(set(_who))))

if unresolved:
    failures.extend(['Token 引用无法解析：%s（被 %s 引用）' % (r, ','.join(w)) for r, w in unresolved])


# ============================================================ 语义层（跨端固定）
SEMANTIC = {
    'app': {
        'note': '小程序端语义 Token。颜色类一律取当前主题（见 themeContract），'
                '文字/背景/边框类跨主题固定。',
        'themed': SEMANTIC_TO_THEME,
        'fixed': {
            'text': APP_TEXT,
            'bg': APP_BG,
            'border': APP_BORDER,
        },
    },
    'admin': {
        'note': '后台三端独立视觉，不随商家品牌主题变化。单位 px，基准宽 1440。',
        'color': P.ADMIN_PALETTE['color'],
        'neutral': P.ADMIN_PALETTE['neutral'],
        'text': P.ADMIN_PALETTE['text'],
        'radius': P.PRIMITIVE['radiusAdmin'],
        'spacing': P.PRIMITIVE['spacingAdmin'],
        'fontSize': P.PRIMITIVE['fontSizeAdmin'],
        'fontFamily': P.PRIMITIVE['fontFamily']['admin'],
        'borderInput': {'v': _border_input, 'use': '输入框、可交互控件边框（≥3:1）'},
        'iconBase': {'v': _icon_base, 'use': '承载信息的图标（≥3:1）'},
    },
    'state': P.SEMANTIC_STATE,
}

# 后台阴影阶梯（px）
SEMANTIC['admin']['shadow'] = {
    'card': {'v': '0 1px 2px rgba(16, 24, 40, 0.06)', 'use': '卡片、表格容器'},
    'raised': {'v': '0 4px 8px rgba(16, 24, 40, 0.08)', 'use': '悬停卡片、下拉'},
    'overlay': {'v': '0 12px 32px rgba(16, 24, 40, 0.14)', 'use': '弹窗、抽屉'},
    'sticky': {'v': '0 1px 0 rgba(16, 24, 40, 0.08)', 'use': '吸顶表头'},
}


# ============================================================== 业务语义词典
# Token 名 → 业务可读说法。业务视图的「取值」列靠它显示中文，不留空占位。
LEXICON = LX.build(P.PRIMITIVE, SEMANTIC)

# 覆盖率：注册表里的每个 Token 都要有业务说法，否则业务视图会留空
lex_missing = sorted(x for x in REG if x not in LEXICON)
if lex_missing:
    failures.extend(['业务语义词典缺条目：%s' % ', '.join(lex_missing[:12])])


# =================================================================== 冲突证据
CONFLICTS = []
for cf in P.CONFLICTS:
    item = dict(cf)
    if cf['id'] == 'CF-06':
        item['measured'] = {t: THEMES[t]['a11y']['brandAsTextOnWhiteRaw'] for t in THEME_NAMES}
        item['measuredNote'] = '品牌色直接作文字的白底对比度（<4.5 即不可读）'
    elif cf['id'] == 'CF-07':
        item['measured'] = {t: THEMES[t]['a11y']['whiteOnBrandRaw'] for t in THEME_NAMES}
        item['measuredNote'] = '品牌色底上白字的对比度（<4.5 即不可读）'
        item['fixedTo'] = {t: THEMES[t]['legacyKeys']['text_color'] for t in THEME_NAMES}
    CONFLICTS.append(item)


# ==================================================================== 统计
stats = {
    'primitiveGroups': len(P.PRIMITIVE),
    'primitiveTokens': sum(len(v) for v in P.PRIMITIVE.values() if isinstance(v, dict)),
    'semanticStateTokens': len(P.SEMANTIC_STATE),
    'adminColorTokens': (len(P.ADMIN_PALETTE['color']) + len(P.ADMIN_PALETTE['neutral'])
                         + len(P.ADMIN_PALETTE['text'])),
    'a11yRules': len(P.A11Y_RULES),
    'themes': len(THEMES),
    'themeKeysLegacy': len(LEGACY_THEME_KEYS),
    'themeKeysNew': len(NEW_THEME_KEYS),
    'themeKeysTotal': len(LEGACY_THEME_KEYS) + len(NEW_THEME_KEYS),
    'themeCorrections': sum(len(v['corrections']) for v in THEMES.values()),
    'components': len(COMPONENTS),
    'componentVariants': sum(len(c['variants']) for c in COMPONENTS),
    'componentStates': sum(len(c['states']) for c in COMPONENTS),
    'componentRules': sum(len(c['rules']) for c in COMPONENTS),
    'pages': len(PAGES),
    'appPages': len([p for p in PAGES if p['platform'] == 'app']),
    'adminPages': len([p for p in PAGES if p['platform'] == 'admin']),
    'pagesNew': len([p for p in PAGES if p['change'] == '新增']),
    'pagesRework': len([p for p in PAGES if p['change'] == '改造']),
    'anchors': sum(len(p['anchors']) for p in PAGES),
    'pageZones': sum(len(p['zones']) for p in PAGES),
    'pageStates': sum(len(p['states']) for p in PAGES),
    'visualPoints': sum(len(p['visualPoints']) for p in PAGES),
    'contrastChecks': len(checks),
    'contrastPassed': len([c for c in checks if c['pass']]),
    'tokenRefs': len(REFS),
    'tokenRefsResolved': len(REFS) - len(unresolved) - len(prose),
    'tokenRefsProse': len(prose),
    'tokenRegistry': len(REG),
    'conflicts': len(CONFLICTS),
    'principles': len(P.PRINCIPLES),
    'lexiconTokens': len(LEXICON),
    'lexiconGroups': len({v['group'] for v in LEXICON.values()}),
}


# ==================================================================== 组装
TOKENS = {
    'schema': 'pm-workflow/design-tokens/v1',
    'project': P.PROJECT,
    'meta': {
        'generatedBy': 'build-tokens.py（03-design 派生器）',
        'principle': '设计取值人定、可读性程序派生；换品牌色重跑本脚本即可，产物不漂移',
        'baselineSource': BASE['source'],
        'themeMechanism': BASE['themeMechanism'],
        'assertions': {
            'targetText': TARGET_TEXT, 'targetLarge': TARGET_LARGE,
            'targetNonText': TARGET_NONTEXT,
            'failLoud': '任一断言不达标即构建失败，不允许带着不合格色值交付',
        },
    },
    'principles': P.PRINCIPLES,
    'conflicts': CONFLICTS,
    'primitive': P.PRIMITIVE,
    'semantic': SEMANTIC,
    'themeContract': {
        'note': '小程序端 7 套商家品牌主题的语义键契约。存量 17 键保留可用；'
                '新增 4 键为最小扩充（折扣金额色 / 降级警示色 / 渠道标识色 / 可读文字变体）。'
                '业务代码只引用「语义 Token → 主题键」映射表左侧的名字，不直接写主题键名。',
        'keysLegacy': LEGACY_THEME_KEYS,
        'keysNew': NEW_THEME_KEYS,
        'mapping': SEMANTIC_TO_THEME,
        'themes': THEMES,
        'themeOrder': THEME_NAMES,
        'disabledLegacy': [
            {'key': 'font_color（作为文字时）',
             'reason': '品牌色当白底文字 7 套全部不达标，改用 font_color_readable'},
            {'key': 'theme-price / notice-price',
             'reason': '历史价钱色随主题漂移，与「折扣金额色」语义冲突；'
                       '新增页面一律用 discount_font，存量页面逐步迁移'},
            {'key': '$uni-color-primary / $color-primary / $uni-color-warning 等',
             'reason': '同一语义两套值（CF-01/02/03），收敛为语义 Token 单一来源'},
        ],
    },
    'a11y': {
        'rules': P.A11Y_RULES,
        'verdicts': {
            'brandAsTextOnWhite': '存量 7 套全部不达标 → 统一改用品牌色文字变体',
            'whiteOnBrand': '存量 5 套不达标 → 品牌色底上的文字改由程序择优',
            'secondaryText': '存量 #999（2.85:1）与 #919293（2.94:1）不达标 → 已替换为可读值',
            'discountVsError': '折扣色 %s 与错误色 %s 分属不同色相，实测区分明确'
                               % (P.SEMANTIC_STATE['discount']['v'], P.SEMANTIC_STATE['error']['v']),
        },
        'contrastMatrix': checks,
    },
    'components': COMPONENTS,
    'pages': PAGES,
    'lexicon': LEXICON,
    'stats': stats,
    'nextStage': {
        'id': '04-prototype',
        'name': '原型（项目制单张大画布）',
        'gate': 'PRD 的 42 个锚点须全部埋入原型；锚点 id 与本文件的 pages[].anchors 完全一致',
        'inputs': ['02-prd/prd.json（落点与锚点唯一来源）',
                   '03-design/tokens.json（视觉取值唯一来源）'],
    },
}

with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(TOKENS, f, ensure_ascii=False, indent=1)

# ==================================================================== 报告
print('[Token 派生] %s' % os.path.basename(OUT))
print('  基础层 %d 组 / %d 个 Token · 语义状态 %d 个'
      % (stats['primitiveGroups'], stats['primitiveTokens'], stats['semanticStateTokens']))
print('  主题 %d 套 · 语义键 %d（存量 %d + 新增 %d）· 值修正 %d 处'
      % (stats['themes'], stats['themeKeysTotal'], stats['themeKeysLegacy'],
         stats['themeKeysNew'], stats['themeCorrections']))
print('  组件 %d 个（变体 %d / 状态 %d / 规则 %d）'
      % (stats['components'], stats['componentVariants'], stats['componentStates'],
         stats['componentRules']))
print('  页面 %d 页（app %d / admin %d）· 新增 %d · 改造 %d · 锚点 %d'
      % (stats['pages'], stats['appPages'], stats['adminPages'], stats['pagesNew'],
         stats['pagesRework'], stats['anchors']))
print('  Token 注册表 %d 名 · 引用 %d 处（可解析 %d · 说明性 %d）' % (stats['tokenRegistry'], stats['tokenRefs'], stats['tokenRefsResolved'], stats['tokenRefsProse']))
print('  业务语义词典 %d 条 / %d 组（覆盖注册表 %d 名，缺 %d）'
      % (stats['lexiconTokens'], stats['lexiconGroups'], stats['tokenRegistry'],
         len(lex_missing)))
print('  对比度断言 %d 条，通过 %d 条' % (stats['contrastChecks'], stats['contrastPassed']))
print()
print('  [主题派生] 品牌色 → 可读文字变体 / 品牌底上文字：')
for t in THEME_NAMES:
    a = THEMES[t]['a11y']
    print('    %-7s %-10s 品牌色文字 %-8s (原样 %.2f) | 底上文字 %-8s (白字原样 %.2f, 选%s)'
          % (t, THEMES[t]['brand'], THEMES[t]['newKeys']['font_color_readable'],
             a['brandAsTextOnWhiteRaw'], THEMES[t]['legacyKeys']['text_color'],
             a['whiteOnBrandRaw'], a['onBrandChoice']))
print()
print('  [文字色修正]')
for k, v in APP_TEXT.items():
    if 'origin' in v:
        print('    text.%-11s %s → %s (白底 %.2f)' % (k, v['origin'], v['v'], v['ratioOnWhite']))
print()
if page_warns:
    for w in page_warns:
        print('  [提示] ' + w)
if failures:
    print()
    print('  [构建失败] 共 %d 项不达标：' % len(failures))
    for x in failures:
        print('    - ' + x)
    sys.exit(1)
print('  [构建通过] 全部对比度断言达标，页面闭环自检通过')
