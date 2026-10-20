#!/usr/bin/env python3
"""发版：重算完整性清单 → 全套复验 → 打包到桌面。

用法（在 skill 根目录）：
    python scripts/release.py                 # 复验 + 重算清单，不打包
    python scripts/release.py --zip           # 复验 + 重算清单 + 打包到桌面
    python scripts/release.py --zip --private # 私用包：额外纳入当前选用的本地钥匙配置
    python scripts/release.py --zip --out D:/some/dir

做的事，按顺序：
  1. 跑 live_data.py status       —— 只显示钥匙已填/空，不打印 key
  2. 跑 check_skill.py            —— frontmatter / 命名 / 断链
  3. 跑 security_check.py         —— 钥匙硬门禁（不打印密钥）
  4. 跑 HTML、实时数据与钥匙门禁离线回归用例
  5. 校验壳子里的 JS 能否解析      —— 需要 node，没有就跳过
  6. 按发布白名单重算 MANIFEST.sha256（不含 local-keys.json）
  7. 打包时：写临时 zip → CRC/成员白名单/SHA256 → 钥匙门禁 → 解压实跑 → 替换正式包
     普通包不含钥匙；--private 仅额外允许 travel-guide/local-keys.json
     两种包均排除快照、缓存、开发日志和临时测试文件
     正式 ZIP 只通过本脚本生成，禁止直接压整个工作目录

任何一步失败就中止，不会交出半成品压缩包。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

MANIFEST = "MANIFEST.sha256"
PRIVATE_REL = pathlib.Path("local-keys.json")
# 发版文件只从这里取。新增通用资源时先审查并显式加入；临时行程、
# .playwright-cli、local-keys.json、_user_meta.json、备份和缓存不属于发版内容。
PUBLISH_ROOT_FILES = frozenset({
    "SKILL.md", "CHANGELOG.md", "local-keys.example.json", MANIFEST,
})
PUBLISH_DIR_FILES = {
    "agents": frozenset({"openai.yaml"}),
    "assets": frozenset({"guide-shell.html", "icon.svg"}),
    "references": frozenset({
        "china.md", "eval.md", "html-guide.md", "international.md",
        "live-data.md", "maps.md", "media.md", "modes.md",
        "output-template.md", "packing.md", "planning.md",
        "research-playbook.md",
    }),
    "scripts": frozenset({
        "README.md", "check_skill.py", "live_data.py", "release.py",
        "security_check.py", "selftest_live_data.py", "selftest_security_check.py",
        "selftest_validate.py",
        "validate_html.py",
    }),
}


def find_root() -> pathlib.Path:
    here = pathlib.Path(__file__).resolve().parent
    root = here.parent
    if not (root / "SKILL.md").is_file():
        raise SystemExit(f"找不到 SKILL.md，scripts/ 的上级不是 skill 根目录：{root}")
    return root


def iter_files(root: pathlib.Path):
    # 手机端导入器可能只取压缩包里的第一个 Markdown；SKILL.md 必须排第一。
    root_names = sorted(PUBLISH_ROOT_FILES - {"SKILL.md"})
    paths = [pathlib.Path("SKILL.md")] + [pathlib.Path(name) for name in root_names]
    paths.extend(
        pathlib.Path(directory, name)
        for directory, names in PUBLISH_DIR_FILES.items()
        for name in names
    )
    for rel in sorted(paths, key=lambda p: (p.as_posix() != "SKILL.md", p.as_posix())):
        p = root / rel
        if (not p.resolve().is_relative_to(root.resolve())
                or any((root / pathlib.Path(*rel.parts[:i])).is_symlink()
                       for i in range(1, len(rel.parts) + 1))
                or not p.is_file()):
            raise SystemExit(f"发版文件缺失或不是普通文件：{rel.as_posix()}")
        yield p, rel


def run(cmd: list[str], label: str, cwd: pathlib.Path | None = None, echo: bool = False) -> bool:
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=cwd)
    ok = r.returncode == 0
    print(f"  {'OK  ' if ok else 'FAIL'}  {label}")
    if echo and (r.stdout or "").strip():
        for line in r.stdout.strip().splitlines():
            print("        " + line)
    elif not ok:
        out = (r.stdout or "") + (r.stderr or "")
        for line in out.strip().splitlines()[-12:]:
            print("        " + line)
    return ok


def check_shell_js(root: pathlib.Path) -> bool:
    """壳子里的 <script> 语法检查（需要 node）。"""
    node = shutil.which("node")
    shell = root / "assets" / "guide-shell.html"
    if not shell.is_file():
        print("  FAIL  找不到 assets/guide-shell.html")
        return False
    if not node:
        print("  SKIP  没装 node，跳过壳子 JS 语法检查")
        return True
    js_blocks = re.findall(
        r"<script(?![^>]*type=[\"']application/json)[^>]*>(.*?)</script>",
        shell.read_text(encoding="utf-8"), re.S,
    )
    with tempfile.TemporaryDirectory() as tmp:
        for i, js in enumerate(js_blocks):
            if not js.strip():
                continue
            f = pathlib.Path(tmp) / f"chunk{i}.js"
            f.write_text(js, encoding="utf-8")
            r = subprocess.run([node, "--check", str(f)], capture_output=True, text=True)
            if r.returncode != 0:
                print(f"  FAIL  壳子 JS 第 {i} 段语法错误")
                print(r.stderr[:800])
                return False
    print(f"  OK    壳子 JS {len(js_blocks)} 段语法通过")
    return True


def rebuild_manifest(root: pathlib.Path, version: str) -> int:
    lines = []
    for p, rel in iter_files(root):
        if rel.as_posix() == MANIFEST:
            continue
        lines.append(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {rel.as_posix()}")
    header = (
        f"# travel-guide {version} 完整性清单\n"
        "# 复核：python scripts/release.py（会重算并复验）\n"
        "# 手查：sha256sum -c MANIFEST.sha256\n"
        "# local-keys.json 不进本清单；仅 --private 私用包另行纳入并单独校验\n"
    )
    (root / MANIFEST).write_text(header + "\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"  OK    重算 {MANIFEST}，{len(lines)} 个文件")
    return len(lines)


def verify_manifest(root: pathlib.Path) -> bool:
    man = root / MANIFEST
    if not man.is_file():
        print("  FAIL  没有 MANIFEST.sha256")
        return False
    bad = 0
    expected = {rel.as_posix(): p for p, rel in iter_files(root) if rel.as_posix() != MANIFEST}
    listed: set[str] = set()
    for line in man.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            digest, rel = line.split("  ", 1)
        except ValueError:
            print("  FAIL  清单行格式错误")
            bad += 1
            continue
        if rel in listed or rel not in expected:
            print(f"  FAIL  清单含重复或非发布文件：{rel}")
            bad += 1
            continue
        listed.add(rel)
        if hashlib.sha256(expected[rel].read_bytes()).hexdigest() != digest:
            bad += 1
            print(f"  FAIL  清单不一致：{rel}")
    for rel in sorted(expected.keys() - listed):
        print(f"  FAIL  清单缺少发布文件：{rel}")
        bad += 1
    if not bad:
        print("  OK    清单与实际文件一致")
    return bad == 0


def selected_private_config(root: pathlib.Path) -> pathlib.Path:
    """与 live_data.py 的选址语义一致，缺配置时终止私用包制作。"""
    override = os.environ.get("TRAVEL_GUIDE_KEYS_FILE")
    if override is None:
        path = root / PRIVATE_REL
    elif override.strip():
        path = pathlib.Path(override.strip()).expanduser()
    else:
        raise SystemExit("TRAVEL_GUIDE_KEYS_FILE 已设置但为空，私用包已中止")
    if not path.is_file():
        raise SystemExit("当前选用的本地钥匙配置缺失，私用包已中止")
    return path


def check_private_output(root: pathlib.Path, out_dir: pathlib.Path) -> None:
    if out_dir.resolve().is_relative_to(root.resolve()):
        raise SystemExit("私用包输出目录必须位于 skill 根目录之外")


def make_zip(root: pathlib.Path, version: str, out_dir: pathlib.Path,
             private: bool = False) -> pathlib.Path:
    if private:
        check_private_output(root, out_dir)
    out = out_dir / f"travel-guide-v{version}{'-private' if private else ''}.zip"
    files = [(p, rel) for p, rel in iter_files(root)]
    if private:
        files.append((selected_private_config(root), PRIVATE_REL))
    expected = {"travel-guide/" + rel.as_posix() for _, rel in files}
    with tempfile.NamedTemporaryFile(prefix="tg-release-", suffix=".zip", dir=out_dir, delete=False) as tmp:
        staging = pathlib.Path(tmp.name)
    try:
        with zipfile.ZipFile(staging, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
            for p, rel in files:
                z.write(p, arcname="travel-guide/" + rel.as_posix())
        print(f"  OK    打包 {out.name}（{len(files)} 个文件，{staging.stat().st_size / 1024:.1f} KB）")

        # CRC、成员白名单、重复成员和逐文件 SHA256。
        problems = 0
        with zipfile.ZipFile(staging) as z:
            broken = z.testzip()
            if broken:
                print(f"  FAIL  压缩包损坏：{broken}")
                problems += 1
            else:
                print("  OK    CRC 校验通过")
            names = [info.filename for info in z.infolist()]
            if not names or names[0] != "travel-guide/SKILL.md":
                print("  FAIL  压缩包第一个成员必须是 SKILL.md（手机端可能只解析首个 Markdown）")
                problems += 1
            if len(names) != len(expected) or set(names) != expected:
                print("  FAIL  压缩包成员与发布白名单不一致")
                problems += 1
            if len(names) != len(set(names)):
                print("  FAIL  压缩包含重复成员")
                problems += 1
            if not problems:
                for p, rel in files:
                    arc = "travel-guide/" + rel.as_posix()
                    with z.open(arc) as fh:
                        if hashlib.sha256(fh.read()).hexdigest() != hashlib.sha256(p.read_bytes()).hexdigest():
                            print(f"  FAIL  压缩包内容不一致：{arc}")
                            problems += 1
        print("  OK    成员和逐文件比对一致" if not problems else f"  FAIL  {problems} 处问题")
        if problems:
            raise SystemExit("压缩包内容校验失败，已中止")

        security_cmd = [sys.executable, str(root / "scripts" / "security_check.py"), "--zip", str(staging)]
        if private:
            security_cmd.append("--private")
        if not run(security_cmd,
                   "压缩包钥匙门禁", cwd=root):
            raise SystemExit("压缩包钥匙门禁失败，已中止")

        # 解压实跑，全部通过后才替换正式文件。
        with tempfile.TemporaryDirectory(prefix="tg-release-") as tmp:
            with zipfile.ZipFile(staging) as z:
                z.extractall(tmp)
            ex = pathlib.Path(tmp) / "travel-guide"
            ok = run([sys.executable, str(ex / "scripts" / "check_skill.py"), str(ex)],
                     "解压后 check_skill.py", cwd=ex)
            ok = run([sys.executable, str(ex / "scripts" / "selftest_validate.py")],
                     "解压后 selftest_validate.py", cwd=ex) and ok
            ok = run([sys.executable, str(ex / "scripts" / "selftest_live_data.py")],
                     "解压后 selftest_live_data.py", cwd=ex) and ok
            ok = run([sys.executable, str(ex / "scripts" / "selftest_security_check.py")],
                     "解压后 selftest_security_check.py", cwd=ex) and ok
            ok = run([sys.executable, str(ex / "scripts" / "security_check.py"), "--root", str(ex)],
                     "解压后 security_check.py", cwd=ex) and ok
            if not ok:
                raise SystemExit("压缩包解压后复验失败，已中止")
        staging.replace(out)
    finally:
        staging.unlink(missing_ok=True)
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="travel-guide 发版：复验 + 重算清单 (+ 打包)")
    ap.add_argument("--zip", action="store_true", help="同时打包到桌面")
    ap.add_argument("--private", action="store_true", help="制作包含当前本地钥匙配置的私用 ZIP，须与 --zip 同用")
    ap.add_argument("--out", default=None, help="压缩包输出目录（默认桌面）")
    args = ap.parse_args()
    if args.private and not args.zip:
        ap.error("--private 必须与 --zip 一起使用")

    root = find_root()
    skill_md = (root / "SKILL.md").read_text(encoding="utf-8")
    m = re.search(r'^\s*version:\s*"([^"]+)"', skill_md, re.M)
    version = m.group(1) if m else "0.0.0"
    print(f"travel-guide {version}  @ {root}")
    print()

    print("[1/7] 钥匙状态（只显示已填/空）")
    if not run([sys.executable, str(root / "scripts" / "live_data.py"), "status"],
               "live_data.py status", cwd=root, echo=True):
        return 1

    print("[2/7] skill 自查")
    if not run([sys.executable, str(root / "scripts" / "check_skill.py"), str(root)], "check_skill.py", cwd=root):
        return 1

    print("[3/7] 钥匙门禁")
    if not run([sys.executable, str(root / "scripts" / "security_check.py")], "security_check.py", cwd=root):
        return 1

    print("[4/7] HTML、实时数据与安全门禁回归用例")
    if not run([sys.executable, str(root / "scripts" / "selftest_validate.py")], "selftest_validate.py", cwd=root):
        return 1
    if not run([sys.executable, str(root / "scripts" / "selftest_live_data.py")], "selftest_live_data.py", cwd=root):
        return 1
    if not run([sys.executable, str(root / "scripts" / "selftest_security_check.py")], "selftest_security_check.py", cwd=root):
        return 1

    print("[5/7] 壳子 JS 语法")
    if not check_shell_js(root):
        return 1

    print("[6/7] 重算完整性清单")
    count = rebuild_manifest(root, version)
    if not verify_manifest(root):
        return 1

    if not args.zip:
        print()
        print(f"复验完成（{count} 个文件）。要打包加 --zip。")
        return 0

    print("[7/7] 打包")
    out_dir = pathlib.Path(args.out).expanduser() if args.out else pathlib.Path.home() / "Desktop"
    if args.private:
        check_private_output(root, out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = make_zip(root, version, out_dir, private=args.private)

    print()
    print("发版完成：")
    print(f"  {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
