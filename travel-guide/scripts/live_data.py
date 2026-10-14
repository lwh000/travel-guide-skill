#!/usr/bin/env python3
"""查天气（和风 / 中央气象台）；飞机/高铁/火车给出检索表骨架。
Key 优先从 TRAVEL_GUIDE_KEYS_FILE 指向的文件读取；未设置时读取 skill 根目录 local-keys.json（私用包可自带）。

用法（在 skill 根目录或任意目录）：
    python scripts/live_data.py status
    python scripts/live_data.py weather --city 杭州 --start 2026-10-20 --days 3
    python scripts/live_data.py transit --from 上海虹桥 --to 杭州东

只把 JSON 打到 stdout。永远不要打印 key。HTML 片段里也不带 key。
高德 jsKey 只用于自驾 HTML 画地图，不要拿去调 restapi 查公交。
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import os
import re
import shutil
import ssl
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SKILL_ROOT = Path(__file__).resolve().parent.parent
KEYS_PATH = SKILL_ROOT / "local-keys.json"
CST = timezone(timedelta(hours=8))
TIMEOUT = 8
UA = "travel-guide-live-data/2.9.1"
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# 2026 起公共域名已停。只有控制台「设置」里的专用 API Host 才去调和风。
# Host 形如 xxx.xx.qweatherapi.com。凭据 ID 没有点，不是 Host。


def today() -> date:
    return datetime.now(CST).date()


def as_of() -> str:
    return today().isoformat()


def keys_path() -> Path:
    """Use the configured keys file, or the skill-root private config."""
    override = os.environ.get("TRAVEL_GUIDE_KEYS_FILE", "").strip()
    return Path(override).expanduser() if override else KEYS_PATH


def load_keys() -> dict:
    path = keys_path()
    if not path.is_file():
        return {"amap": {}, "qweather": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"amap": {}, "qweather": {}}
    if not isinstance(data, dict):
        return {"amap": {}, "qweather": {}}
    amap = data.get("amap") if isinstance(data.get("amap"), dict) else {}
    qw = data.get("qweather") if isinstance(data.get("qweather"), dict) else {}
    return {"amap": amap, "qweather": qw}


def _s(value: Any) -> str:
    return str(value or "").strip()


def secrets(keys: dict) -> list[str]:
    amap, qw = keys.get("amap") or {}, keys.get("qweather") or {}
    out = []
    for v in (amap.get("jsKey"), amap.get("securityJsCode"), amap.get("webKey"), qw.get("key")):
        t = _s(v)
        if len(t) >= 6:
            out.append(t)
    return out


def redact(text: str, keys: dict) -> str:
    out = str(text or "")
    for sec in sorted(secrets(keys), key=len, reverse=True):
        out = out.replace(sec, "***")
    return out


def dump(obj: dict, exit_code: int = 0) -> int:
    json.dump(obj, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return exit_code


def _decode_json(raw: str, keys: dict, code: int) -> tuple[int, Any]:
    try:
        return code, json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return code, {"error": "not_json", "text": redact(raw[:240], keys)}


def _decode_http_bytes(raw: bytes) -> str:
    """QWeather may gzip responses even when the client does not request it."""
    if raw.startswith(b"\x1f\x8b"):
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def http_json_curl(url: str, keys: dict, extra_headers: dict | None = None) -> tuple[int, Any]:
    """Windows 上 Python/OpenSSL 和风握手失败时，改走 curl（Schannel）。"""
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    exe = shutil.which("curl") or shutil.which("curl.exe")
    if not exe:
        return 0, {"error": "no_curl"}
    cmd = [
        exe, "-sS", "--compressed", "--max-time", str(TIMEOUT),
        "-w", "\n__TG_STATUS__:%{http_code}",
        "-A", (_s(headers.get("User-Agent")) or UA),
    ]
    for k, v in headers.items():
        if str(k).lower() == "user-agent":
            continue
        cmd += ["-H", f"{k}: {v}"]
    cmd.append(url)
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=TIMEOUT + 4)
    except Exception as exc:
        return 0, {"error": redact(str(exc), keys)}
    out = (proc.stdout or b"").decode("utf-8", "replace")
    err = (proc.stderr or b"").decode("utf-8", "replace")
    status = 0
    body = out
    if "__TG_STATUS__:" in out:
        body, _, tail = out.rpartition("__TG_STATUS__:")
        try:
            status = int(tail.strip().splitlines()[0].strip() or "0")
        except ValueError:
            status = 0
    if proc.returncode != 0 and not body.strip():
        return 0, {"error": redact(err.strip() or f"curl_{proc.returncode}", keys)}
    return _decode_json(body.strip(), keys, status)


def http_json(url: str, keys: dict, extra_headers: dict | None = None) -> tuple[int, Any]:
    headers = {"User-Agent": UA, "Accept": "application/json"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=ctx) as resp:
            raw = _decode_http_bytes(resp.read())
            code = resp.status
        return _decode_json(raw, keys, code)
    except urllib.error.HTTPError as exc:
        raw = _decode_http_bytes(exc.read()) if exc.fp else ""
        return _decode_json(raw, keys, exc.code)
    except Exception:
        return http_json_curl(url, keys, extra_headers)


def host_of(raw: str) -> str:
    h = _s(raw).replace("https://", "").replace("http://", "").strip().strip("/")
    return h.split("/")[0] if h else ""


def qw_api_host(raw: str) -> str:
    """只接受控制台专用 API Host。凭据 ID 无点，直接拒绝。公共域名不要再试。"""
    h = host_of(raw)
    if not h or "." not in h:
        return ""
    low = h.lower()
    if low in {"api.qweather.com", "devapi.qweather.com", "geoapi.qweather.com"}:
        return ""
    if low.endswith(".qweatherapi.com") or low == "qweatherapi.com":
        return h
    return ""


def is_jwt(key: str) -> bool:
    parts = key.split(".")
    return len(parts) == 3 and all(parts)


def qw_headers(key: str) -> dict:
    if is_jwt(key):
        return {"Authorization": f"Bearer {key}"}
    return {"X-QW-Api-Key": key}


def qw_get(path: str, key: str, hosts: list[str], keys: dict, expected: str = "geo") -> tuple[str, Any]:
    last: Any = {"error": "no_host"}
    for host in hosts:
        if not host:
            continue
        url = f"https://{host}{path}"
        code, body = http_json(url, keys, qw_headers(key))
        if code == 200 and isinstance(body, dict) and (
            (expected == "geo" and str(body.get("code") or "") == "200" and isinstance(body.get("location"), list))
            or (expected in {"days", "alerts"} and isinstance(body.get(expected), list))
        ):
            return host, body
        last = {"http": code, "body": body, "host": host}
    return "", last


def present(value: Any) -> str:
    return "已填" if _s(value) else "空"


def cmd_status(keys: dict) -> int:
    amap, qw = keys["amap"], keys["qweather"]
    host = qw_api_host(qw.get("host"))
    raw_host = host_of(qw.get("host"))
    if host:
        host_state = "已填"
    elif raw_host:
        host_state = "无效（凭据 ID 不是 API Host）"
    else:
        host_state = "空（公共域名已停，将走中央气象台）"
    return dump({
        "ok": True,
        "file": str(keys_path()),
        "amap": {
            "jsKey": present(amap.get("jsKey")),
            "securityJsCode": present(amap.get("securityJsCode")),
            "webKey": present(amap.get("webKey")),
            "canLoadMap": bool(_s(amap.get("jsKey")) and _s(amap.get("securityJsCode"))),
            "canQueryTransit": False,
        },
        "qweather": {
            "key": present(qw.get("key")),
            "host": host_state,
            "canQueryWeather": bool(_s(qw.get("key")) and host),
        },
        "note": "不要把 key 打进聊天或 HTML。jsKey / 安全密钥只用于自驾页画地图。飞机/高铁/火车检索 12306 或航司，不要用高德查市内公交。凭据 ID 不是 API Host。天气无 Host 时走中央气象台。",
    })


def parse_dates(start: str | None, days: int, dates: str | None) -> list[date]:
    if dates:
        out = []
        for part in dates.split(","):
            part = part.strip()
            if not part:
                continue
            out.append(date.fromisoformat(part))
        return out
    if not start:
        start = as_of()
    d0 = date.fromisoformat(start)
    n = max(1, int(days or 1))
    return [d0 + timedelta(days=i) for i in range(n)]


def temp_range(tmin: Any, tmax: Any) -> str:
    if tmin is not None and tmax is not None:
        return f"{tmin}–{tmax}°C"
    if tmax is not None:
        return f"{tmax}°C"
    if tmin is not None:
        return f"{tmin}°C"
    return ""


def wx_card(day: dict) -> str:
    d = day.get("date") or ""
    text = day.get("textDay") or day.get("text") or ""
    rng = temp_range(day.get("tempMin"), day.get("tempMax")) or "—"
    return (
        f'<div class="wx-card"><span class="wx-date">{esc(d)}</span>'
        f"<b>{esc(rng)}</b><span>{esc(text)}</span></div>"
    )


def esc(value: Any) -> str:
    return (
        str(value if value is not None else "")
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def pills_from(daily: list[dict]) -> dict:
    out = {}
    for day in daily:
        d = day.get("date")
        if not d:
            continue
        text = day.get("textDay") or ""
        rng = temp_range(day.get("tempMin"), day.get("tempMax"))
        out[d] = " · ".join(x for x in (rng, text) if x)
    return out


def qw_coordinates(location: dict) -> tuple[str, str] | None:
    """GeoAPI supplies lat/lon strings; v1 weather paths require lat before lon."""
    try:
        lat = float(location["lat"])
        lon = float(location["lon"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return f"{lat:.6f}".rstrip("0").rstrip("."), f"{lon:.6f}".rstrip("0").rstrip(".")


def qw_local_date(value: Any, location: dict) -> str:
    raw = _s(value)
    if not raw:
        return ""
    try:
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return ""
    if instant.tzinfo is not None:
        # With localTime=true, a non-UTC offset in the response is the
        # forecast date's own offset, including any DST transition.
        if instant.utcoffset() != timedelta(0):
            return instant.date().isoformat()
        tz_name = _s(location.get("tz"))
        if tz_name:
            try:
                return instant.astimezone(ZoneInfo(tz_name)).date().isoformat()
            except (ZoneInfoNotFoundError, ValueError):
                pass
        offset = _s(location.get("utcOffset"))
        match = re.fullmatch(r"([+-])(\d{2}):(\d{2})", offset)
        if match:
            hours, minutes = int(match.group(2)), int(match.group(3))
            if hours <= 14 and minutes < 60:
                delta = timedelta(hours=hours, minutes=minutes)
                if match.group(1) == "-":
                    delta = -delta
                return instant.astimezone(timezone(delta)).date().isoformat()
    return instant.date().isoformat()


def qw_temperature(value: Any) -> int | float | None:
    if not isinstance(value, dict):
        return None
    n = to_num(value.get("value"))
    if n is None:
        return None
    unit = _s(value.get("unit")).lower()
    if unit in {"°f", "f", "fahrenheit"}:
        n = round((n - 32) * 5 / 9, 1)
    elif unit not in {"°c", "c", "celsius"}:
        return None
    return to_num(n)


def qw_attributions(*blocks: dict) -> list[str]:
    out = []
    for block in blocks:
        metadata = block.get("metadata") if isinstance(block.get("metadata"), dict) else {}
        for item in metadata.get("attributions") or []:
            text = _s(item)
            if text and text not in out:
                out.append(text)
    return out


def daily_from_qweather(block: dict, location: dict | None = None) -> list[dict]:
    location = location or {}
    out = []
    for row in block.get("days") or []:
        if not isinstance(row, dict):
            continue
        d = qw_local_date(row.get("forecastStartTime"), location)
        tmin = qw_temperature(row.get("temperatureMin"))
        tmax = qw_temperature(row.get("temperatureMax"))
        if not d or (tmin is None and tmax is None):
            continue
        daytime = row.get("daytime") if isinstance(row.get("daytime"), dict) else {}
        nighttime = row.get("nighttime") if isinstance(row.get("nighttime"), dict) else {}
        day_condition = daytime.get("weatherCondition") if isinstance(daytime.get("weatherCondition"), dict) else {}
        night_condition = nighttime.get("weatherCondition") if isinstance(nighttime.get("weatherCondition"), dict) else {}
        wind = daytime.get("wind") if isinstance(daytime.get("wind"), dict) else {}
        direction = wind.get("direction") if isinstance(wind.get("direction"), dict) else {}
        speed = wind.get("speed") if isinstance(wind.get("speed"), dict) else {}
        wind_text = " ".join(part for part in (_s(direction.get("compass")),
                                               " ".join(part for part in (_s(speed.get("value")), _s(speed.get("unit"))) if part)) if part)
        humidity = to_num(daytime.get("humidity"))
        if humidity is not None and 0 <= humidity <= 1:
            humidity = to_num(round(humidity * 100, 1))
        else:
            humidity = None
        uv = row.get("uvIndexMax") if isinstance(row.get("uvIndexMax"), dict) else {}
        out.append({
            "date": d,
            "tempMin": tmin,
            "tempMax": tmax,
            "textDay": _s(day_condition.get("text")),
            "textNight": _s(night_condition.get("text")),
            "wind": wind_text,
            "precip": None,
            "humidity": humidity,
            "uvIndex": to_num(uv.get("value")),
        })
    return out


def to_num(value: Any):
    if value in (None, "", [], {}):
        return None
    try:
        n = float(str(value))
        if not math.isfinite(n):
            return None
        return int(n) if n.is_integer() else n
    except (TypeError, ValueError):
        return None


def weather_html(mode: str, note: str, daily: list[dict], warnings: list[str], asof: str, place: str,
                 attributions: list[str] | None = None) -> str:
    bits = [f'<p class="muted">{esc(place)} · 查询 {esc(asof)}。{esc(note)}</p>']
    if warnings:
        bits.append('<div class="wx-warn">' + "<br>".join(esc(w) for w in warnings) + "</div>")
    if daily:
        bits.append('<div class="wx-grid">' + "".join(wx_card(d) for d in daily) + "</div>")
    if mode == "climate_plus_recent":
        bits.append('<div class="callout">以上是所列日期的近期预报参考，并非出行日预报或气候统计；出发前再查询。</div>')
    if attributions:
        bits.append('<p class="muted">数据声明：' + "；".join(esc(item) for item in attributions) + "</p>")
    return "\n".join(bits)

def nmc_temp(value: Any):
    n = to_num(value)
    if n is None or n >= 99 or n <= -90:
        return None
    return int(round(n))


def nmc_text(value: Any) -> str:
    t = _s(value)
    if t in {"", "999", "-", "--", "暂无"}:
        return ""
    return t


def valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def norm_city(name: str) -> str:
    s = _s(name)
    for suf in ("特别行政区", "维吾尔自治区", "壮族自治区", "回族自治区", "自治区", "地区", "盟"):
        if s.endswith(suf) and len(s) > len(suf):
            s = s[: -len(suf)]
            break
    for suf in ("市", "县"):
        if s.endswith(suf) and len(s) > len(suf):
            s = s[: -len(suf)]
            break
    return s


# stationid, 省码, 页面拼音。中央气象台优先走 HTTPS。
NMC_STATIONS: dict[str, tuple[str, str, str]] = {
    "北京": ("54511", "ABJ", "beijing"),
    "上海": ("58362", "ASH", "shanghai"),
    "天津": ("54527", "ATJ", "tianjin"),
    "重庆": ("57516", "ACQ", "chongqing"),
    "杭州": ("58457", "AZJ", "hangzhou"),
    "宁波": ("58562", "AZJ", "ningbo"),
    "温州": ("58659", "AZJ", "wenzhou"),
    "绍兴": ("58453", "AZJ", "shaoxing"),
    "嘉兴": ("58452", "AZJ", "jiaxing"),
    "湖州": ("58450", "AZJ", "huzhou"),
    "金华": ("58549", "AZJ", "jinhua"),
    "舟山": ("58477", "AZJ", "zhoushan"),
    "南京": ("58238", "AJS", "nanjing"),
    "苏州": ("58349", "AJS", "suzhou"),
    "无锡": ("58354", "AJS", "wuxi"),
    "扬州": ("58245", "AJS", "yangzhou"),
    "广州": ("59287", "AGD", "guangzhou"),
    "深圳": ("59493", "AGD", "shenzhen"),
    "珠海": ("59488", "AGD", "zhuhai"),
    "成都": ("56294", "ASC", "chengdu"),
    "西安": ("57036", "ASN", "xian"),
    "武汉": ("57494", "AHB", "wuhan"),
    "长沙": ("57687", "AHN", "changsha"),
    "厦门": ("59134", "AFJ", "xiamen"),
    "福州": ("58847", "AFJ", "fuzhou"),
    "青岛": ("54857", "ASD", "qingdao"),
    "济南": ("54823", "ASD", "jinan"),
    "大连": ("54662", "ALN", "dalian"),
    "沈阳": ("54342", "ALN", "shenyang"),
    "哈尔滨": ("50953", "AHL", "haerbin"),
    "长春": ("54161", "AJL", "changchun"),
    "昆明": ("56778", "AYN", "kunming"),
    "丽江": ("56651", "AYN", "lijiang"),
    "桂林": ("57957", "AGX", "guilin"),
    "南宁": ("59431", "AGX", "nanning"),
    "三亚": ("59948", "AHI", "sanya"),
    "海口": ("59758", "AHI", "haikou"),
    "拉萨": ("55591", "AXZ", "lasa"),
    "乌鲁木齐": ("51463", "AXJ", "wulumuqi"),
    "兰州": ("52889", "AGS", "lanzhou"),
    "西宁": ("52866", "AQH", "xining"),
    "银川": ("53614", "ANX", "yinchuan"),
    "呼和浩特": ("53463", "ANM", "huhehaote"),
    "郑州": ("57083", "AHA", "zhengzhou"),
    "合肥": ("58321", "AAH", "hefei"),
    "南昌": ("58606", "AJX", "nanchang"),
    "太原": ("53772", "ASX", "taiyuan"),
    "石家庄": ("53698", "AHE", "shijiazhuang"),
    "贵阳": ("57816", "AGZ", "guiyang"),
    "香港": ("45005", "AXG", "hongkong"),
    "澳门": ("45011", "AAM", "macao"),
}


def nmc_city_info(city: str) -> tuple[str, str, str] | None:
    raw = _s(city)
    key = norm_city(raw)
    for name in (raw, key):
        if name in NMC_STATIONS:
            return NMC_STATIONS[name]
    return None


def nmc_page_urls(city: str) -> list[str]:
    info = nmc_city_info(city)
    out = []
    if info:
        _sid, prov, pinyin = info
        out.append(f"https://www.nmc.cn/publish/forecast/{prov}/{pinyin}.html")
        out.append(f"http://www.nmc.cn/publish/forecast/{prov}/{pinyin}.html")
    out.append("https://www.nmc.cn/publish/forecast.html")
    out.append("http://www.nmc.cn/publish/forecast.html")
    return list(dict.fromkeys(out))


def http_json_nmc(url: str, keys: dict) -> tuple[int, Any, str]:
    """Try NMC HTTPS first; use HTTP only after transport failure or 5xx."""
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.nmc.cn/",
    }
    if url.lower().startswith("http://"):
        secure_url = "https://" + url[7:]
    elif url.lower().startswith("https://"):
        secure_url = url
    else:
        raise ValueError("NMC URL must use HTTP or HTTPS")
    candidates = [secure_url, "http://" + secure_url[8:]]
    last: tuple[int, Any] = (0, {"error": "no_attempt"})
    for cand in candidates:
        req = urllib.request.Request(cand, headers=headers)
        try:
            kw: dict[str, Any] = {"timeout": TIMEOUT}
            if cand.lower().startswith("https://"):
                kw["context"] = ssl.create_default_context()
            with urllib.request.urlopen(req, **kw) as resp:
                raw = resp.read().decode("utf-8", "replace")
                code, body = _decode_json(raw, keys, getattr(resp, "status", 200) or 200)
                return code, body, cand
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace") if exc.fp else ""
            last = _decode_json(raw, keys, exc.code)
            if exc.code < 500:
                return last[0], last[1], cand
        except Exception as exc:
            last = (0, {"error": redact(str(exc), keys)})
        # One curl attempt can recover a local TLS-stack failure. No unbounded retries.
        code2, body2 = http_json_curl(cand, keys, headers)
        if code2 == 200:
            return code2, body2, cand
        last = (code2, body2)
        if 400 <= code2 < 500:
            return last[0], last[1], cand
    return last[0], last[1], candidates[-1]



def iso_date(raw: str) -> str:
    s = _s(raw).replace("/", "-")
    m = re.match(r"^(\d{4}-\d{2}-\d{2})", s)
    if m:
        return m.group(1)
    m = re.match(r"^(\d{1,2})-(\d{1,2})$", s)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        current = today()
        candidates = []
        for year in (current.year - 1, current.year, current.year + 1):
            try:
                candidates.append(date(year, month, day))
            except ValueError:
                continue
        if candidates:
            return min(candidates, key=lambda d: abs((d - current).days)).isoformat()
    return ""


def daily_from_nmc(payload: Any) -> tuple[str, list[dict]]:
    obj = payload if isinstance(payload, dict) else {}
    data = obj.get("data") if isinstance(obj.get("data"), dict) else obj
    predict = data.get("predict") if isinstance(data.get("predict"), dict) else {}
    detail = predict.get("detail")
    if not isinstance(detail, list):
        return "", []
    station = data.get("station") if isinstance(data.get("station"), dict) else {}
    if not station:
        real = data.get("real") if isinstance(data.get("real"), dict) else {}
        station = real.get("station") if isinstance(real.get("station"), dict) else {}
    place = _s(station.get("city") or station.get("name"))
    out = []
    for row in detail:
        if not isinstance(row, dict):
            continue
        d = iso_date(_s(row.get("date")))
        day = row.get("day") if isinstance(row.get("day"), dict) else {}
        night = row.get("night") if isinstance(row.get("night"), dict) else {}
        dw = day.get("weather") if isinstance(day.get("weather"), dict) else {}
        nw = night.get("weather") if isinstance(night.get("weather"), dict) else {}
        tmax = nmc_temp(dw.get("temperature"))
        tmin = nmc_temp(nw.get("temperature"))
        text_day = nmc_text(dw.get("info")) or nmc_text(nw.get("info"))
        if not d or (tmax is None and tmin is None):
            continue
        out.append({
            "date": d,
            "tempMin": tmin,
            "tempMax": tmax,
            "textDay": text_day,
            "textNight": nmc_text(nw.get("info")),
        })
    return place, out


def nmc_lookup_station(city: str, keys: dict) -> tuple[str, str, str] | None:
    known = nmc_city_info(city)
    if known:
        return known
    q = urllib.parse.quote(norm_city(city) or city)
    for url in (
        f"https://www.nmc.cn/rest/find?q={q}",
        f"https://www.nmc.cn/f/rest/autocomplete?q={q}",
    ):
        code, body, _used_url = http_json_nmc(url, keys)
        rows = None
        if isinstance(body, list):
            rows = body
        elif isinstance(body, dict):
            for k in ("data", "list", "station", "result"):
                if isinstance(body.get(k), list):
                    rows = body.get(k)
                    break
        if not rows:
            continue
        want = norm_city(city)
        for row in rows:
            if not isinstance(row, dict):
                continue
            name = _s(row.get("city") or row.get("name") or row.get("stationName"))
            sid = _s(row.get("code") or row.get("stationid") or row.get("id"))
            url_path = _s(row.get("url"))
            prov, pinyin = "", ""
            m = re.search(r"/forecast/([A-Z]{2,4})/([a-z0-9_-]+)", url_path)
            if m:
                prov, pinyin = m.group(1), m.group(2)
            if sid and (not want or want in norm_city(name) or norm_city(name) in want or not name):
                return sid, prov, pinyin
    return None


def select_daily(daily_all: list[dict], dates: list[date], horizon_days: int) -> tuple[list[dict], str, str]:
    trip_iso = [d.isoformat() for d in dates]
    by_date = {d.get("date"): d for d in daily_all if d.get("date")}
    matched = [by_date[d] for d in trip_iso if d in by_date]
    missing = [d for d in trip_iso if d not in by_date]
    if matched:
        if missing:
            note = f"仅 {len(matched)}/{len(trip_iso)} 个出行日有对应日期的预报；未覆盖：{'、'.join(missing)}。缺失日不推断气温。出发前再核预警。"
        else:
            note = "所列出行日均有对应日期的预报。出发前再核预警。"
        return matched, "forecast", note
    # A near-term date with no matching record is a data failure, not a forecast.
    if min(dates) <= today() + timedelta(days=horizon_days):
        return [], "forecast", "出行日没有对应日期的预报；请查询其他官方来源。"
    recent = [d for d in daily_all if date.fromisoformat(d["date"]) >= today() - timedelta(days=1)]
    if not recent:
        return [], "climate_plus_recent", "近期参考数据已过期；请查询其他官方来源。"
    reference_dates = [d["date"] for d in recent]
    note = (
        "出行日尚无对应日期的预报。以下仅是 "
        f"{' 至 '.join((min(reference_dates), max(reference_dates)))} 的近期预报参考，"
        "并非出行日预测或气候统计。出发前再查。"
    ) if reference_dates else "出行日尚无对应日期的预报。"
    return recent, "climate_plus_recent", note


def pack_weather(provider: str, place: str, daily: list[dict], dates: list[date], asof: str, extra_note: str, warnings: list[str] | None = None, extra: dict | None = None) -> dict | None:
    usable = [d for d in daily if valid_iso_date(d.get("date")) and temp_range(d.get("tempMin"), d.get("tempMax"))]
    if not usable:
        return None
    horizon = 7 if provider == "nmc" else 10
    picked, mode, note = select_daily(usable, dates, horizon)
    if not picked:
        return None
    if extra_note:
        note = extra_note + note
    attributions = extra.get("attributions") if isinstance(extra, dict) and isinstance(extra.get("attributions"), list) else []
    html = weather_html(mode, note, picked, warnings or [], asof, place, attributions)
    if "wx-card" not in html:
        return None
    picked_dates = {row["date"] for row in picked}
    trip_dates = [d.isoformat() for d in dates]
    payload = {
        "ok": True,
        "asOf": asof,
        "provider": provider,
        "place": {"name": place},
        "mode": mode,
        "note": note,
        "dates": trip_dates,
        "warnings": warnings or [],
        "daily": picked,
        "pills": pills_from(picked),
        "html": html,
        "coverage": {
            "matchedDates": [d for d in trip_dates if d in picked_dates] if mode == "forecast" else [],
            "missingDates": [d for d in trip_dates if d not in picked_dates] if mode == "forecast" else trip_dates,
            "referenceDates": [row.get("date") for row in picked] if mode == "climate_plus_recent" else [],
        },
    }
    if mode == "climate_plus_recent":
        payload["referenceKind"] = "recent_forecast"
    if extra:
        payload.update(extra)
    return payload


def try_qweather(city: str, dates: list[date], asof: str, keys: dict) -> dict | None:
    qw = keys["qweather"]
    key = _s(qw.get("key"))
    host = qw_api_host(qw.get("host"))
    if not key or not host:
        return None
    loc = urllib.parse.quote(city)
    geo_host, geo = qw_get(f"/geo/v2/city/lookup?location={loc}&lang=zh", key, [host], keys)
    if not geo_host:
        return None
    loc_row = (geo.get("location") or [{}])[0] if isinstance(geo.get("location"), list) else {}
    coords = qw_coordinates(loc_row)
    if not coords:
        return None
    lat, lon = coords
    loc_id = _s(loc_row.get("id")) or city
    place_name = _s(loc_row.get("name")) or city
    adm = " ".join(x for x in (_s(loc_row.get("adm1")), _s(loc_row.get("adm2"))) if x)
    block = None
    daily_all = []
    used_host = ""
    used_days = 0
    for days in (10, 7, 3):
        candidate_host, candidate = qw_get(
            f"/weather/v1/daily/{lat}/{lon}?days={days}&localTime=true&lang=zh",
            key, [host], keys, expected="days",
        )
        if not candidate_host:
            continue
        candidate_daily = daily_from_qweather(candidate, loc_row)
        if candidate_daily:
            block, daily_all, used_host, used_days = candidate, candidate_daily, candidate_host, days
            break
    if not block or not daily_all:
        return None
    warnings = []
    warn_host, warn_body = qw_get(
        f"/weatheralert/v1/current/{lat}/{lon}?localTime=true&lang=zh",
        key, [host], keys, expected="alerts",
    )
    if warn_host:
        for w in warn_body.get("alerts") or []:
            if not isinstance(w, dict):
                continue
            title = " ".join(x for x in (w.get("title"), w.get("description")) if x)
            if title:
                warnings.append(title[:180])
    place = f"{place_name} {adm}".strip()
    packed = pack_weather("qweather", place, daily_all, dates, asof, "数据来源：和风天气。", warnings, {
        "hostUsed": used_host,
        "forecastDaysRequested": used_days,
        "place": {"name": place_name, "id": loc_id, "adm": adm},
        "attributions": qw_attributions(block, warn_body) if warn_host else qw_attributions(block),
    })
    return packed


def try_nmc(city: str, dates: list[date], asof: str, keys: dict) -> dict | None:
    info = nmc_lookup_station(city, keys) or nmc_city_info(city)
    if not info:
        return None
    sid, prov, pinyin = info
    urls = [f"https://www.nmc.cn/rest/weather?stationid={urllib.parse.quote(sid)}"]
    if sid:
        urls.append(f"https://nmc.cn/rest/weather?stationid={urllib.parse.quote(sid)}")
    for url in urls:
        code, body, used_url = http_json_nmc(url, keys)
        if code != 200 or not isinstance(body, dict):
            continue
        place, daily = daily_from_nmc(body)
        packed = pack_weather(
            "nmc",
            place or norm_city(city) or city,
            daily,
            dates,
            asof,
            "数据来源：中央气象台。",
            extra={
                "stationid": sid,
                "url": nmc_page_urls(city)[0] if nmc_page_urls(city) else url,
                "apiTransport": urllib.parse.urlsplit(used_url).scheme,
            },
        )
        if packed:
            return packed
    return None


def weather_search_fail(city: str, dates: list[date], asof: str, error: str) -> dict:
    return {
        "ok": False,
        "asOf": asof,
        "error": error,
        "city": city,
        "dates": [d.isoformat() for d in dates],
        "mustSearch": True,
        "html": "",
        "open": nmc_page_urls(city),
        "search": [
            f"{city} 天气预报 中央气象台",
            f"{city} 天气 site:nmc.cn",
            f"{city} 天气预报 中国天气网",
        ],
        "note": "脚本没拿到出行日气温。请按指定日期查询中央气象台 / 中国天气网；仍无对应日期预报时，注明待查并附官方查询链接，不填无来源的气温或天气。",
    }


def cmd_weather(args: argparse.Namespace, keys: dict) -> int:
    city = _s(args.city)
    asof = as_of()
    if not city:
        return dump(weather_search_fail("目的地", [today()], asof, "missing_city"), 2)
    try:
        dates = parse_dates(args.start, args.days, args.dates)
    except ValueError as exc:
        return dump(weather_search_fail(city, [today()], asof, f"bad_dates:{exc}"), 3)
    if not dates:
        return dump(weather_search_fail(city, [today()], asof, "bad_dates"), 3)

    packed = try_qweather(city, dates, asof, keys)
    if packed:
        return dump(packed)
    packed = try_nmc(city, dates, asof, keys)
    if packed:
        return dump(packed)
    return dump(weather_search_fail(city, dates, asof, "weather_unavailable"), 1)


def cmd_transit(args: argparse.Namespace, keys: dict) -> int:
    origin_s, dest_s = _s(args.start_from), _s(args.to)
    city, cityd = _s(args.city), _s(args.cityd)
    asof = as_of()
    label_from = origin_s or "出发"
    label_to = dest_s or "到达"
    html = (
        f'<p class="muted">查询 {esc(asof)}。高铁以 12306 为准，机票以航司 / 官方渠道为准；'
        "下表先占位，检索后填入参考价，不是余票。不要用地图，也不要调高德公交。</p>"
        '<div class="table-wrap"><table>'
        "<thead><tr><th>路段</th><th>方式</th><th>参考价</th><th>来源</th></tr></thead>"
        "<tbody>"
        f"<tr><td>{esc(label_from)} → {esc(label_to)}</td><td>高铁</td><td>待核</td><td>12306</td></tr>"
        f"<tr><td>{esc(label_from)} → {esc(label_to)}</td><td>飞机</td><td>待核</td><td>航司官网</td></tr>"
        "</tbody></table></div>"
    )
    payload = {
        "ok": False,
        "asOf": asof,
        "from": origin_s,
        "to": dest_s,
        "error": "need_official_fares",
        "note": "高德只用于自驾地图，不查市内公交。飞机 / 高铁 / 火车请检索 12306 或航司官网，把参考价填进表。",
        "search": [
            f"12306 {origin_s} {dest_s} 高铁 票价",
            f"{origin_s} 到 {dest_s} 机票 官方 票价",
            f"{origin_s} 到 {dest_s} 火车 票价",
        ],
        "html": html,
    }
    if city or cityd:
        payload["city"] = city
        payload["cityd"] = cityd
    if not origin_s or not dest_s:
        payload["error"] = "missing_place"
        return dump(payload, 3)
    return dump(payload, 0)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="travel-guide 实时天气 / 城际票价检索表（key 不入库、不进 HTML）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="只显示哪些 key 已填，不打印 key")
    w = sub.add_parser("weather", help="和风 / 中央气象台；失败则给出要打开的页面")
    w.add_argument("--city", required=True)
    w.add_argument("--start", default=None, help="出行开始日 YYYY-MM-DD")
    w.add_argument("--days", type=int, default=3)
    w.add_argument("--dates", default=None, help="逗号分隔的日期，优先于 --start/--days")
    t = sub.add_parser("transit", help="飞机/高铁/火车票价表骨架（不走高德）")
    t.add_argument("--from", dest="start_from", required=True)
    t.add_argument("--to", required=True)
    t.add_argument("--city", default="")
    t.add_argument("--cityd", default="")
    return p


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    keys = load_keys()
    args = build_parser().parse_args()
    if args.cmd == "status":
        return cmd_status(keys)
    if args.cmd == "weather":
        return cmd_weather(args, keys)
    if args.cmd == "transit":
        return cmd_transit(args, keys)
    return 3


if __name__ == "__main__":
    sys.exit(main())
