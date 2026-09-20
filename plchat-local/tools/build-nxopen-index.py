"""从本机 NX 安装的 NXOpen.xml 抽出所有 API 名称,建立离线索引。
XML 形如 <member name="M:NXOpen.Session.UndoToMark(NXOpen.Session.UndoMarkId,System.String)">。
前缀 T/M/P/F/E = 类型/方法/属性/字段/事件;方法名去掉参数签名后再入索引。
用途:提交 journal 脚本前校验 NXOpen.* 名称是否真实存在(精确对应本机这个版本)。
路径必须纯 ASCII。
"""
import os
import re
import sys
import time

src_dir = sys.argv[1]
out_path = sys.argv[2]
name_re = re.compile(rb'<member name="[A-Za-z]:([^"]{3,300})"')

found = set()
t0 = time.time()
files = 0
for fn in sorted(os.listdir(src_dir)):
    if not fn.lower().endswith(".xml"):
        continue
    files += 1
    with open(os.path.join(src_dir, fn), "rb") as fh:
        data = fh.read()
    for m in name_re.finditer(data):
        raw = m.group(1).decode("utf-8", "replace").strip()
        found.add(raw.split("(")[0])

parent = os.path.dirname(out_path)
if parent and not os.path.isdir(parent):
    os.makedirs(parent)
with open(out_path, "w", encoding="utf-8") as fh:
    for n in sorted(found):
        fh.write(n + "\n")

print("xml files: %d" % files)
print("names: %d" % len(found))
print("seconds: %.1f" % (time.time() - t0))
print("out: %s (%.1f KB)" % (out_path, os.path.getsize(out_path) / 1024.0))
