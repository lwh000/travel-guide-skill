#!/usr/bin/env python3
"""钥匙硬门禁。

可通过 TRAVEL_GUIDE_KEYS_FILE 指向外部钥匙文件；门禁同时扫描外部与根目录旧配置的钥匙。
显式外部配置缺失/无效时中止。local-keys.example.json 仅允许空值或明确占位值。
所有可解码的工作区文本、压缩包、
git 跟踪文件里不能出现真实 key，也不能把 local-keys.json 打进包。

报错只写字段名和路径，永远不要打印密钥。

用法：
    python scripts/security_check.py
    python scripts/security_check.py --zip travel-guide-v2.11.1.zip
    python scripts/security_check.py --zip travel-guide-v2.11.1-private.zip --private
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
PRIVATE_NAME = "local-keys.json"
PRIVATE_MEMBER = "travel-guide/local-keys.json"
EXAMPLE_NAME = "local-keys.example.json"
SKIP_DIRS = {"__pycache__", ".git", ".idea", ".vscode", ".pytest_cache", ".playwright-cli", "logs"}
SKIP_NAMES = {".DS_Store", "Thumbs.db", "desktop.ini"}
MIN_SECRET_LEN = 8
MIN_QUERY_KEY_LEN = 12
PLACEHOLDER_VALUES = {
    "js_key", "jskey", "your_key", "yourkey", "changeme", "placeholder",
    "安全密钥", "用户的安全密钥", "用户的js_key", "your-key", "xxx", "todo",
}
EXAMPLE_FIELDS = {
    "amap": frozenset({"jsKey", "securityJsCode", "webKey"}),
    "qweather": frozenset({"key", "host", "credentialId"}),
}
EXAMPLE_PLACEHOLDERS = PLACEHOLDER_VALUES | {
    "your_js_key", "your_security_js_code", "your_web_key",
    "your_qweather_key", "your_qweather_host", "your_qweather_credential_id",
    "example.qweatherapi.com",
}
FIELD_PATHS = (
    ("amap.jsKey", ("amap", "jsKey")),
    ("amap.securityJsCode", ("amap", "securityJsCode")),
    ("amap.webKey", ("amap", "webKey")),
    ("qweather.key", ("qweather", "key")),
    ("qweather.credentialId", ("qweather", "credentialId")),
)
QUERY_PATTERNS = (
    (re.compile(r"(?:devapi|api|geoapi)\.qweather\.com[^\"\s<>]*[?&]key=([^&\s\"'<>]+)", re.I), "qweather.key"),
    (re.compile(r"qweatherapi\.com[^\"\s<>]*[?&]key=([^&\s\"'<>]+)", re.I), "qweather.key"),
    (re.compile(r"restapi\.amap\.com[^\"\s<>]*[?&]key=([^&\s\"'<>]+)", re.I), "amap.webKey"),
    (re.compile(r"webapi\.amap\.com/maps[^\"\s<>]*[?&]key=([^&\s\"'<>]+)", re.I), "amap.jsKey"),
)


class Report:
    def __init__(self) -> None:
        self.fails: list[str] = []

    def fail(self, msg: str) -> None:
        self.fails.append(msg)
        print(f"  FAIL  {msg}")


class KeyConfigError(ValueError):
    """配置无法安全用于泄漏扫描；错误消息不能包含密钥内容。"""


def _s(value: object) -> str:
    return str(value or "").strip()


def nested_get(data: dict, path: tuple[str, ...]) -> object:
    cur: object = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def selected_keys_path(root: Path) -> Path:
    """环境变量优先；空的显式设置应阻断发布。"""
    override = os.environ.get("TRAVEL_GUIDE_KEYS_FILE")
    if override is None:
        return root / PRIVATE_NAME
    if not override.strip():
        raise KeyConfigError("TRAVEL_GUIDE_KEYS_FILE 已设置但为空")
    return Path(override.strip()).expanduser()


def validate_key_config_data(data: object, label: str) -> dict:
    if not isinstance(data, dict) or not any(section in data for section in EXAMPLE_FIELDS):
        raise KeyConfigError(f"{label}不是有效的钥匙配置对象")
    for section in EXAMPLE_FIELDS:
        value = data.get(section)
        if value is not None and not isinstance(value, dict):
            raise KeyConfigError(f"{label}的 {section} 结构无效")
    for field, keys in FIELD_PATHS:
        value = nested_get(data, keys)
        if value is not None and not isinstance(value, str):
            raise KeyConfigError(f"{label}的 {field} 类型无效")
    host = nested_get(data, ("qweather", "host"))
    if host is not None and not isinstance(host, str):
        raise KeyConfigError(f"{label}的 qweather.host 类型无效")
    return data


def _read_key_config(path: Path, label: str, required: bool) -> dict | None:
    if not path.is_file():
        if required:
            raise KeyConfigError(f"{label}缺失或不是普通文件")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise KeyConfigError(f"{label}无法读取或不是有效 JSON") from exc
    return validate_key_config_data(data, label)


def secret_fields_from_data(data: dict, min_length: int = MIN_SECRET_LEN) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for field, keys in FIELD_PATHS:
        val = _s(nested_get(data, keys))
        if len(val) < min_length or val.lower() in PLACEHOLDER_VALUES:
            continue
        out.append((field, val))
    return out


def load_secret_fields(root: Path) -> list[tuple[str, str]]:
    selected = selected_keys_path(root)
    legacy = root / PRIVATE_NAME
    explicit_override = os.environ.get("TRAVEL_GUIDE_KEYS_FILE") is not None
    configs = []
    for path, label, required in (
        (legacy, "根目录旧配置", False),
        (selected, "外置钥匙配置" if selected != legacy else "根目录旧配置", explicit_override),
    ):
        if any(path.resolve() == seen.resolve() for seen, _ in configs):
            continue
        data = _read_key_config(path, label, required)
        if data is not None:
            configs.append((path, data))
    out: list[tuple[str, str]] = []
    for _, data in configs:
        for item in secret_fields_from_data(data):
            if item not in out:
                out.append(item)
    out.sort(key=lambda item: len(item[1]), reverse=True)
    return out


def check_example_json(raw: bytes, where: str, rep: Report) -> None:
    """示例配置只准包含约定字段和空值/显式占位，绝不回显值。"""
    decoded = decode_text(raw)
    if decoded is None:
        rep.fail(f"{where} 不是可解码的 JSON 文本")
        return
    try:
        data = json.loads(decoded)
    except json.JSONDecodeError:
        rep.fail(f"{where} 不是有效 JSON")
        return
    if not isinstance(data, dict) or set(data) != set(EXAMPLE_FIELDS):
        rep.fail(f"{where} 的顶层字段与示例模板不一致")
        return
    for section, names in EXAMPLE_FIELDS.items():
        values = data[section]
        if not isinstance(values, dict):
            rep.fail(f"{where} 的 {section} 字段与示例模板不一致")
            continue
        fields = set(values)
        missing = names - fields
        extra = fields - names
        # 2.11.1 以前的示例没有 credentialId；允许检查已有历史 ZIP。
        if extra or missing - ({"credentialId"} if section == "qweather" else set()):
            rep.fail(f"{where} 的 {section} 字段与示例模板不一致")
            continue
        for name in fields:
            value = values[name]
            if value is None:
                continue
            if not isinstance(value, str) or (value.strip() and value.strip().lower() not in EXAMPLE_PLACEHOLDERS):
                rep.fail(f"{where} 的 {section}.{name} 不是空值或明确占位值")


def private_fields_from_bytes(raw: bytes, where: str, rep: Report) -> list[tuple[str, str]]:
    """私用包内的唯一钥匙文件必须可解析；值仅留在内存中参与比对。"""
    decoded = decode_text(raw)
    if decoded is None:
        rep.fail(f"{where} 不是可解码的 JSON 配置")
        return []
    try:
        data = validate_key_config_data(json.loads(decoded), "私用包钥匙配置")
    except (json.JSONDecodeError, KeyConfigError):
        rep.fail(f"{where} 不是有效的钥匙配置")
        return []
    if set(data) - set(EXAMPLE_FIELDS):
        rep.fail(f"{where} 含未约定的顶层配置字段")
        return []
    for section, names in EXAMPLE_FIELDS.items():
        values = data.get(section) or {}
        if set(values) - names:
            rep.fail(f"{where} 的 {section} 含未约定的配置字段")
            return []
    fields = secret_fields_from_data(data, min_length=1)
    if not fields:
        rep.fail(f"{where} 没有已填的有效钥匙字段")
    return fields


def is_placeholder_query(value: str) -> bool:
    v = value.strip()
    if len(v) < MIN_QUERY_KEY_LEN:
        return True
    return v.lower() in PLACEHOLDER_VALUES


def decode_text(raw: bytes) -> str | None:
    """只扫描能可靠解码的文本，不因扩展名遗漏 Python/YAML 等文件。"""
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return raw.decode("utf-16")
        except UnicodeError:
            return None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeError:
        return None
    # 非 BOM 的 NUL 或大量控制字节通常表示二进制文件。
    if "\x00" in text:
        return None
    controls = sum(ch < " " and ch not in "\t\n\r\f" for ch in text)
    if controls > max(2, len(text) // 100):
        return None
    return text


def scan_text(text: str, where: str, secrets: list[tuple[str, str]], rep: Report) -> None:
    for field, value in secrets:
        if value and value in text:
            rep.fail(f"{where} 出现真实钥匙字段 {field}")
            return
    for cre, field in QUERY_PATTERNS:
        for hit in cre.findall(text):
            token = hit if isinstance(hit, str) else str(hit)
            if is_placeholder_query(token):
                continue
            rep.fail(f"{where} 出现疑似 key 查询参数（字段 {field}）")
            return


def scan_bytes(raw: bytes, where: str, secrets: list[tuple[str, str]], rep: Report) -> None:
    decoded = decode_text(raw)
    if decoded is not None:
        scan_text(decoded, where, secrets, rep)
        return
    # 对不能可靠解码的成员，仍匹配 UTF-8/UTF-16 原始字节中的已知钥匙。
    for field, value in secrets:
        if any(value.encode(codec) in raw for codec in ("utf-8", "utf-16-le", "utf-16-be")):
            rep.fail(f"{where} 出现真实钥匙字段 {field}")
            return


def iter_root_files(root: Path):
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        if p.name in SKIP_NAMES or p.suffix.lower() in {".pyc", ".pyo"}:
            continue
        yield p, rel


def scan_root(root: Path, secrets: list[tuple[str, str]], rep: Report) -> None:
    for path, rel in iter_root_files(root):
        posix = rel.as_posix()
        if path.name == PRIVATE_NAME:
            continue
        if path.suffix.lower() == ".zip":
            scan_zip(path, secrets, rep, label=posix)
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if path.name == EXAMPLE_NAME:
            check_example_json(raw, posix, rep)
        scan_bytes(raw, posix, secrets, rep)


def scan_zip(zpath: Path, secrets: list[tuple[str, str]], rep: Report,
             label: str | None = None, allow_private_config: bool = False) -> None:
    where = label or zpath.name
    try:
        zf = zipfile.ZipFile(zpath)
    except zipfile.BadZipFile:
        rep.fail(f"{where} 不是合法 zip")
        return
    with zf:
        infos = zf.infolist()
        private_infos = [info for info in infos if info.filename == PRIVATE_MEMBER]
        scan_secrets = list(secrets)
        if allow_private_config:
            if len(private_infos) != 1:
                rep.fail(f"{where} 应恰有一个 {PRIVATE_MEMBER}，实际 {len(private_infos)} 个")
            else:
                try:
                    private_raw = zf.read(private_infos[0])
                except (OSError, RuntimeError, zipfile.BadZipFile):
                    rep.fail(f"{where} 中的 {PRIVATE_MEMBER} 无法读取")
                else:
                    for item in private_fields_from_bytes(private_raw, f"{where}:{PRIVATE_MEMBER}", rep):
                        if item not in scan_secrets:
                            scan_secrets.append(item)
        for info in infos:
            name = info.filename.replace("\\", "/")
            if name.endswith("/"):
                continue
            base = Path(name).name
            if base == PRIVATE_NAME:
                if allow_private_config and info.filename == PRIVATE_MEMBER:
                    continue
                rep.fail(f"{where} 含非指定的 {PRIVATE_NAME}：{name}")
                continue
            try:
                raw = zf.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile):
                rep.fail(f"{where} 中的文件无法读取：{name}")
                continue
            if base == EXAMPLE_NAME:
                check_example_json(raw, f"{where}:{name}", rep)
            loc = f"{where}:{name}"
            scan_bytes(raw, loc, scan_secrets, rep)


def git_tracked(root: Path) -> list[str] | None:
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, encoding="utf-8",
        )
    except OSError:
        return None
    if r.returncode != 0 or (r.stdout or "").strip() != "true":
        return None
    listed = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"],
        capture_output=True,
    )
    if listed.returncode != 0:
        return None
    # Keep NUL-delimited paths as bytes until decoding. Git emits UTF-8 paths, but
    # test doubles may supply text, so accept both subprocess output shapes.
    output = listed.stdout or b""
    if isinstance(output, bytes):
        output = output.decode("utf-8", errors="surrogateescape")
    return [name for name in output.split("\0") if name]


def scan_git(root: Path, secrets: list[tuple[str, str]], rep: Report) -> None:
    files = git_tracked(root)
    if files is None:
        print("  info  不是 git 仓库，跳过跟踪检查")
        return
    for rel in files:
        posix = rel.replace("\\", "/")
        base = Path(posix).name
        if base == PRIVATE_NAME:
            rep.fail(f"git 跟踪了 {PRIVATE_NAME}：{posix}")
            continue
        path = root / posix
        if not path.is_file():
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        scan_bytes(raw, f"git:{posix}", secrets, rep)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="travel-guide 钥匙硬门禁（不打印密钥）")
    ap.add_argument("--zip", dest="zip_path", default=None, help="检查压缩包")
    ap.add_argument("--private", action="store_true", help="只允许 ZIP 内 travel-guide/local-keys.json 含配置钥匙")
    ap.add_argument("--root", default=None, help="skill 根目录，默认本脚本的上级")
    args = ap.parse_args()
    if args.private and not args.zip_path:
        ap.error("--private 必须与 --zip 一起使用")

    root = Path(args.root).expanduser().resolve() if args.root else SKILL_ROOT
    if not (root / "SKILL.md").is_file():
        print(f"找不到 SKILL.md：{root}")
        return 1

    rep = Report()
    print(f"security_check  @ {root}")
    try:
        secrets = load_secret_fields(root)
    except KeyConfigError as exc:
        rep.fail(str(exc))
        print("\n钥匙配置无效，发布门禁已中止（不打印密钥）")
        return 1

    if args.zip_path:
        zpath = Path(args.zip_path).expanduser().resolve()
        if not zpath.is_file():
            print(f"找不到压缩包：{zpath}")
            return 1
        scan_zip(zpath, secrets, rep, allow_private_config=args.private)
    else:
        scan_root(root, secrets, rep)
        scan_git(root, secrets, rep)

    print()
    if rep.fails:
        print(f"{len(rep.fails)} FAIL（只报字段名和路径，不打印密钥）")
        return 1
    print("钥匙门禁通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
