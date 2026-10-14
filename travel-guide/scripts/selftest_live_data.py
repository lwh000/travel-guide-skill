#!/usr/bin/env python3
"""Offline regression checks for weather dates, transport, and key-file routing."""
from __future__ import annotations

import argparse
import contextlib
import json
import gzip
import io
import os
import tempfile
import unittest
import urllib.error
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import live_data


FROZEN = date(2026, 10, 13)


def weather_day(offset: int) -> dict:
    return {
        "date": (FROZEN + timedelta(days=offset)).isoformat(),
        "tempMin": 12,
        "tempMax": 21,
        "textDay": "晴",
    }


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return b"{}"


class LiveDataTests(unittest.TestCase):
    def test_qweather_tls_failure_downgrades_without_false_forecast(self):
        key = "FAKE_KEY_FOR_TEST"
        config = {"qweather": {"key": key, "host": "fixture.qweatherapi.com"}, "amap": {}}
        args = argparse.Namespace(city="杭州", start=FROZEN.isoformat(), days=1, dates=None)
        output = io.StringIO()
        with patch.object(live_data, "http_json", return_value=(0, {"error": "TLS reset"})), \
                patch.object(live_data, "try_nmc", return_value=None) as nmc, \
                patch.object(live_data, "today", return_value=FROZEN), \
                contextlib.redirect_stdout(output):
            exit_code = live_data.cmd_weather(args, config)
        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["mustSearch"])
        self.assertEqual(payload["html"], "")
        self.assertNotIn(key, output.getvalue())
        nmc.assert_called_once()

    def test_qweather_v1_daily_fields_and_local_date(self):
        block = {"days": [{
            "forecastStartTime": "2026-10-13T16:00:00Z",
            "temperatureMin": {"value": 12, "unit": "°C"},
            "temperatureMax": {"value": 23, "unit": "°C"},
            "daytime": {
                "weatherCondition": {"text": "多云"},
                "humidity": 0.5,
                "wind": {"direction": {"compass": "NE"}, "speed": {"value": 3, "unit": "m/s"}},
            },
            "nighttime": {"weatherCondition": {"text": "晴"}},
            "uvIndexMax": {"value": 5},
        }]}
        rows = live_data.daily_from_qweather(block, {"tz": "Asia/Shanghai", "utcOffset": "+08:00"})
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["date"], "2026-10-14")
        self.assertEqual((rows[0]["tempMin"], rows[0]["tempMax"]), (12, 23))
        self.assertEqual((rows[0]["textDay"], rows[0]["textNight"]), ("多云", "晴"))
        self.assertEqual(rows[0]["humidity"], 50)
        self.assertEqual(rows[0]["uvIndex"], 5)
        self.assertEqual(rows[0]["wind"], "NE 3 m/s")
        self.assertEqual(live_data.qw_temperature({"value": 68, "unit": "°F"}), 20)
        self.assertEqual(
            live_data.qw_local_date("2026-03-15T00:00:00-04:00", {"utcOffset": "-05:00"}),
            "2026-03-15",
        )

    def test_qweather_coordinates_validate_bounds_and_order(self):
        self.assertEqual(live_data.qw_coordinates({"lat": "30.28000", "lon": "120.15000"}), ("30.28", "120.15"))
        self.assertIsNone(live_data.qw_coordinates({"lat": "NaN", "lon": "120.15"}))
        self.assertIsNone(live_data.qw_coordinates({"lat": "91", "lon": "120.15"}))

    def test_qweather_v1_falls_back_10_7_3_and_uses_header_only(self):
        calls = []
        key = "FAKE_KEY_FOR_TEST"
        geo = {"code": "200", "location": [{
            "id": "101210101", "name": "杭州", "adm1": "浙江", "adm2": "杭州",
            "lat": "30.28", "lon": "120.15", "tz": "Asia/Shanghai", "utcOffset": "+08:00",
        }]}
        daily = {"metadata": {"attributions": ["QWeather", "Data disclaimer"]}, "days": [{
            "forecastStartTime": "2026-10-13T16:00:00Z",
            "temperatureMin": {"value": 14, "unit": "°C"},
            "temperatureMax": {"value": 24, "unit": "°C"},
            "daytime": {"weatherCondition": {"text": "阴"}},
            "nighttime": {"weatherCondition": {"text": "多云"}},
        }]}
        alerts = {"metadata": {"attributions": ["Alert authority"]}, "alerts": [
            {"title": "大风黄色预警", "description": "局地阵风较强"},
        ]}

        def fake_http(url, _keys, headers):
            calls.append((url, headers))
            if "/geo/v2/city/lookup" in url:
                return 200, geo
            if "days=10" in url or "days=7" in url:
                return 403, {"error": "plan"}
            if "days=3" in url:
                return 200, daily
            if "/weatheralert/v1/current/" in url:
                return 200, alerts
            self.fail(f"Unexpected URL: {url}")

        config = {"qweather": {"key": key, "host": "fixture.qweatherapi.com"}, "amap": {}}
        with patch.object(live_data, "http_json", side_effect=fake_http), patch.object(live_data, "today", return_value=FROZEN):
            packed = live_data.try_qweather("杭州", [FROZEN + timedelta(days=1)], FROZEN.isoformat(), config)

        self.assertIsNotNone(packed)
        self.assertEqual(packed["forecastDaysRequested"], 3)
        self.assertEqual(packed["daily"][0]["date"], "2026-10-14")
        self.assertEqual(packed["daily"][0]["textDay"], "阴")
        self.assertIn("大风黄色预警", packed["warnings"][0])
        self.assertEqual(packed["attributions"], ["QWeather", "Data disclaimer", "Alert authority"])
        self.assertIn("数据声明：QWeather；Data disclaimer；Alert authority", packed["html"])
        self.assertEqual([url.split("?", 1)[0] for url, _ in calls[1:4]],
                         ["https://fixture.qweatherapi.com/weather/v1/daily/30.28/120.15"] * 3)
        self.assertEqual(["days=10", "days=7", "days=3"],
                         [url.split("?", 1)[1].split("&", 1)[0] for url, _ in calls[1:4]])
        self.assertIn("/weatheralert/v1/current/30.28/120.15", calls[4][0])
        self.assertTrue(all("key=" not in url.lower() and headers == {"X-QW-Api-Key": key} for url, headers in calls))

    def test_qweather_accepts_empty_alert_list_and_gzip(self):
        body = {"metadata": {"attributions": ["QWeather"]}, "alerts": []}
        def fake_http(_url, _keys, _headers):
            return 200, body
        with patch.object(live_data, "http_json", side_effect=fake_http):
            host, parsed = live_data.qw_get("/weatheralert/v1/current/30.28/120.15", "FAKE_KEY_FOR_TEST",
                                            ["fixture.qweatherapi.com"], {}, expected="alerts")
        self.assertEqual(host, "fixture.qweatherapi.com")
        self.assertEqual(parsed["alerts"], [])
        compressed = gzip.compress(b'{"days":[]}')
        self.assertEqual(live_data._decode_http_bytes(compressed), '{"days":[]}')

    def test_missing_near_term_date_is_not_replaced_by_other_forecast(self):
        with patch.object(live_data, "today", return_value=FROZEN):
            packed = live_data.pack_weather(
                "nmc", "杭州", [weather_day(0), weather_day(1)],
                [FROZEN + timedelta(days=3)], FROZEN.isoformat(), "",
            )
        self.assertIsNone(packed)

    def test_partial_coverage_contains_exact_trip_dates_only(self):
        trip = [FROZEN + timedelta(days=i) for i in (1, 2, 3)]
        with patch.object(live_data, "today", return_value=FROZEN):
            packed = live_data.pack_weather(
                "nmc", "杭州", [weather_day(0), weather_day(1), weather_day(3)],
                trip, FROZEN.isoformat(), "",
            )
        self.assertIsNotNone(packed)
        self.assertEqual(packed["mode"], "forecast")
        self.assertEqual([row["date"] for row in packed["daily"]], [trip[0].isoformat(), trip[2].isoformat()])
        self.assertEqual(packed["coverage"]["missingDates"], [trip[1].isoformat()])
        self.assertNotIn(weather_day(0)["date"], packed["pills"])
        self.assertIn("缺失日不推断气温", packed["note"])

    def test_far_future_reference_has_its_real_dates_and_clear_label(self):
        trip = [FROZEN + timedelta(days=30)]
        with patch.object(live_data, "today", return_value=FROZEN):
            packed = live_data.pack_weather(
                "qweather", "杭州", [weather_day(0), weather_day(1)],
                trip, FROZEN.isoformat(), "",
            )
        self.assertIsNotNone(packed)
        self.assertEqual(packed["mode"], "climate_plus_recent")
        self.assertEqual(packed["referenceKind"], "recent_forecast")
        self.assertEqual(packed["coverage"]["matchedDates"], [])
        self.assertEqual(packed["coverage"]["missingDates"], [trip[0].isoformat()])
        self.assertEqual(packed["coverage"]["referenceDates"], [weather_day(0)["date"], weather_day(1)["date"]])
        self.assertIn("并非出行日预测或气候统计", packed["note"])

    def test_stale_or_invalid_reference_is_rejected(self):
        trip = [FROZEN + timedelta(days=30)]
        with patch.object(live_data, "today", return_value=FROZEN):
            stale = live_data.pack_weather("qweather", "杭州", [weather_day(-9)], trip, FROZEN.isoformat(), "")
            invalid = live_data.pack_weather("qweather", "杭州", [{**weather_day(0), "date": "2026-02-30"}], trip, FROZEN.isoformat(), "")
        self.assertIsNone(stale)
        self.assertIsNone(invalid)

    def test_nmc_month_day_rolls_over_new_year(self):
        with patch.object(live_data, "today", return_value=date(2026, 12, 30)):
            self.assertEqual(live_data.iso_date("01-02"), "2027-01-02")
        with patch.object(live_data, "today", return_value=date(2027, 1, 2)):
            self.assertEqual(live_data.iso_date("12-31"), "2026-12-31")

    def test_nmc_https_first_even_for_http_input(self):
        called = []

        def open_url(req, **_kwargs):
            called.append(req.full_url)
            return FakeResponse()

        with patch.object(live_data.urllib.request, "urlopen", side_effect=open_url), patch.object(live_data, "http_json_curl") as curl:
            code, body, used = live_data.http_json_nmc("http://www.nmc.cn/rest/weather?stationid=58457", {})
        self.assertEqual((code, body), (200, {}))
        self.assertEqual(called, ["https://www.nmc.cn/rest/weather?stationid=58457"])
        self.assertEqual(used, called[0])
        curl.assert_not_called()

    def test_nmc_http_fallback_only_after_https_failure(self):
        called = []

        def open_url(req, **_kwargs):
            called.append(req.full_url)
            if req.full_url.startswith("https:"):
                raise urllib.error.URLError("TLS failure")
            return FakeResponse()

        with patch.object(live_data.urllib.request, "urlopen", side_effect=open_url), patch.object(live_data, "http_json_curl", return_value=(0, {"error": "curl_failed"})) as curl:
            code, body, used = live_data.http_json_nmc("https://www.nmc.cn/rest/weather?stationid=58457", {})
        self.assertEqual((code, body), (200, {}))
        self.assertEqual([u.split(":", 1)[0] for u in called], ["https", "http"])
        self.assertEqual(used.split(":", 1)[0], "http")
        self.assertEqual(curl.call_count, 1)

    def test_nmc_4xx_does_not_downgrade(self):
        def open_url(req, **_kwargs):
            raise urllib.error.HTTPError(req.full_url, 403, "Forbidden", {}, None)

        with patch.object(live_data.urllib.request, "urlopen", side_effect=open_url), patch.object(live_data, "http_json_curl") as curl:
            code, _body, used = live_data.http_json_nmc("https://www.nmc.cn/rest/weather?stationid=58457", {})
        self.assertEqual(code, 403)
        self.assertTrue(used.startswith("https://"))
        curl.assert_not_called()

    def test_external_keys_file_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "keys.json"
            path.write_text(json.dumps({"qweather": {"host": "example.qweatherapi.com", "key": "fixture-secret"}}), encoding="utf-8")
            with patch.dict(os.environ, {"TRAVEL_GUIDE_KEYS_FILE": str(path)}):
                loaded = live_data.load_keys()
                selected_path = live_data.keys_path()
        self.assertEqual(selected_path, path)
        self.assertEqual(loaded["qweather"]["host"], "example.qweatherapi.com")


if __name__ == "__main__":
    unittest.main()
