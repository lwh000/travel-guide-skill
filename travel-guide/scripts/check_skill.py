# -*- coding: utf-8 -*-
"""skill 自查：frontmatter、命名、断链、SKILL.md 里的残留占位符。

不依赖 pyyaml（系统没装也能跑）。skill-creator 自带的 quick_validate.py 需要 pyyaml，
本机 python 没有该模块时用这个代替：

    python scripts/check_skill.py <skill 目录>

退出码 0 = 通过。
"""
import pathlib, re, sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

root = pathlib.Path(sys.argv[1]).resolve()
text = (root / "SKILL.md").read_text(encoding="utf-8")
problems = []

if not text.startswith("---\n"):
    problems.append("缺少 YAML frontmatter")
m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
if not m:
    problems.append("frontmatter 格式不对")
else:
    fm = m.group(1)
    name = re.search(r"^name:\s*(.+)$", fm, re.M)
    desc = re.search(r"^description:\s*(.+)$", fm, re.M)
    if not name:
        problems.append("缺 name")
    else:
        n = name.group(1).strip().strip('"\'')
        if not re.fullmatch(r"[a-z0-9-]+", n):
            problems.append(f"name 不是 hyphen-case：{n}")
        if n != root.name:
            problems.append(f"name({n}) 与目录名({root.name}) 不一致")
    if not desc:
        problems.append("缺 description")
    else:
        d = desc.group(1).strip().strip('"\'')
        if len(d) > 1024:
            problems.append(f"description 超长：{len(d)}")
        if "<" in d or ">" in d:
            problems.append("description 里有尖括号")
        if "[TODO:" in d:
            problems.append("description 里有 TODO")
    allowed = {"name", "description", "license", "allowed-tools", "metadata",
               "short-description", "version", "last-reviewed"}
    extra = set(re.findall(r"^([A-Za-z_-]+):", fm, re.M)) - allowed
    if extra:
        problems.append("frontmatter 有未预期字段：" + ", ".join(sorted(extra)))

for ph in re.findall(r"\{\{\s*[A-Z_]+\s*\}\}", text):
    problems.append(f"SKILL.md 残留占位符 {ph}")

for p in sorted(root.rglob("*")):
    if p.is_file() and p.suffix in (".md", ".html", ".py", ".ps1"):
        t = p.read_text(encoding="utf-8", errors="replace")
        for link in re.findall(r"\]\((?!/?https?:)([^)#\s]+?\.(?:md|html|py|ps1))\)", t):
            if not (p.parent / link).resolve().exists():
                problems.append(f"{p.relative_to(root)} 断链 -> {link}")

if problems:
    print("发现问题：")
    for x in problems:
        print("  -", x)
    sys.exit(1)
print(f"{root.name}: frontmatter / 命名 / 引用检查通过")
