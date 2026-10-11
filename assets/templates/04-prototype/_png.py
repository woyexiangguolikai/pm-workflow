# -*- coding: utf-8 -*-
"""PNG 字节级裁剪（不解码像素）。

为什么可以不解码：
    PNG 每行左边有一个 filter 字节，filter 只引用**本行左侧**的像素和**上一行**的像素
    （Sub / Up / Average / Paeth 都是这个方向）。所以：
      · 砍掉一行尾部的数据  → 保留的部分完全不受影响
      · 丢掉末尾若干行      → 保留下来的行引用的"上一行"仍在
    两条合起来说明：**只裁右下角**的裁剪可以纯靠字节操作完成，不需要还原任何像素。

    这很重要：本机没有 Pillow，而纯 Python 按字节还原 1500×2500 的图要十几秒一张。
    而我们要裁的恰好就是右下角 —— 截图 = 视口内容 + 右侧窗口余量 + 底部窗口余量。

    ⚠️ 这个前提只对「裁右下角」成立。要裁左上角或中间，就必须真的解码。
"""
import struct
import zlib


def ihdr(path):
    """读 IHDR：返回 (宽, 高, 位深, 颜色类型)。"""
    with open(path, 'rb') as f:
        b = f.read(33)
    if b[:8] != b'\x89PNG\r\n\x1a\n' or b[12:16] != b'IHDR':
        return None
    w, h, bd, ct = struct.unpack('>IIBB', b[16:26])
    return w, h, bd, ct


def _bpp(ct):
    return {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ct]


def truncate(src, dst, new_w, new_h):
    """把 src 的左上角 new_w×new_h 裁出来写到 dst。要求 new_w/new_h 不大于原尺寸。"""
    with open(src, 'rb') as f:
        data = f.read()
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
    new_w, new_h = min(new_w, w), min(new_h, h)
    bpp = _bpp(ct)
    stride = w * bpp
    keep = new_w * bpp
    raw = zlib.decompress(idat)
    out = bytearray()
    p = 0
    for y in range(new_h):
        out += raw[p:p + 1] + raw[p + 1:p + 1 + keep]   # filter 字节 + 该行前 keep 字节
        p += 1 + stride
    _write(dst, new_w, new_h, bd, ct, bytes(out))
    return new_w, new_h


def _write(path, w, h, bd, ct, raw):
    def chunk(t, d):
        c = t + d
        return struct.pack('>I', len(d)) + c + struct.pack('>I', zlib.crc32(c) & 0xffffffff)
    with open(path, 'wb') as f:
        f.write(b'\x89PNG\r\n\x1a\n')
        f.write(chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, bd, ct, 0, 0, 0)))
        f.write(chunk(b'IDAT', zlib.compress(raw, 9)))
        f.write(chunk(b'IEND', b''))
