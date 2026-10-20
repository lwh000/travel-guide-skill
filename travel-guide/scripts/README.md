---
name: travel-guide-scripts-readme
description: travel-guide 脚本内部说明，不单独作为技能导入。
---

# scripts

改完 skill 后在 skill 根目录跑：

    python scripts/release.py

私人钥匙可由 `TRAVEL_GUIDE_KEYS_FILE` 指向包外文件；未设置时读取根目录 `local-keys.json`。普通发布包不含密钥；明确选择 `--private` 时，自用包会将当前配置放进根目录 `local-keys.json`。

## live_data.py

查天气（和风 / 中央气象台），失败则返回官方查询入口；只把出行日期精确匹配的记录标为预报，部分覆盖见 `coverage.matchedDates` / `coverage.missingDates`。远期的 `climate_plus_recent` 是带 `referenceKind=recent_forecast` 的近期参考，不是出行日预报或历史气候。另给飞机 / 高铁 / 火车检索表骨架。高德 jsKey 只用于私人本地自驾 HTML 画地图，不用于公交或 Web 服务。

    python scripts/live_data.py status
    python scripts/live_data.py weather --city 杭州 --start 2026-10-20 --days 3
    python scripts/live_data.py transit --from 上海虹桥 --to 杭州东

`status` 只显示选用的配置路径及字段已填/空，不会把 key 打出来。聊天和 HTML 都不要出现和风 key。准备分享自驾页时使用 SVG 路线图，不嵌个人地图凭据。

返回 JSON 里的 `html` 只有在地点、日期和来源一致时才用于 `{{WEATHER}}`。缺数据就写官方入口和复核时间，不造气温卡。交通骨架填实际查到的 12306 / 航司票价；查不到时保留官方查询入口。

## validate_html.py

交付前机械校验单份 HTML 攻略。**只做离线结构 / 格式检查，不重验旅游事实**：`#trip-geo`、点位引用、地图模式、驾车 URI 参数、日期与星期、来源结构、占位符、图片 alt、BOM、不安全链接与脚本，以及存在天气节时的日期/来源/气温或诚实的无数据状态。只有写交通时才需要交通表，未知票价给官方查询入口。

杂志版可给视觉与时段提醒；`<body data-guide-style="minimal">` 或 `print` 会跳过装饰类提醒。WARN 不阻塞交付。

    python scripts/validate_html.py 杭州3日.html
    python scripts/validate_html.py --quiet 杭州3日.html

- 退出码非 0 = 有 FAIL，必须改完再交付。
- WARN 不阻塞交付，但要在对话里说明。
- 纯标准库，不联网。

## selftest_validate.py

`validate_html.py` 的自查用例，覆盖天气日期与来源、星期、链接与脚本、驾车 URI 和版式条件。动过校验逻辑或壳子就跑一次：

    python scripts/selftest_validate.py

天气日期选择和跨年处理的离线回归：

    python scripts/selftest_live_data.py

## 正式包怎么生成

**正式 ZIP 只通过 `release.py --zip` 生成。** 普通包采用显式白名单，排除 `.playwright-cli` 快照、单次行程生成器、私人配置、缓存和备份。用户要求私用包时加 `--private`，只额外加入当前配置作为 `travel-guide/local-keys.json`；其他临时文件仍不入包。

## security_check.py

钥匙门禁扫描所有可解码的发布文本（含 `.py` / `.yml`）及压缩包成员。普通包不含真实 key；私用包只允许指定的 `local-keys.json` 成员携带当前配置。既有 `.playwright-cli` 本地调试文件不发布。报错只写字段名和路径，不打印密钥。

    python scripts/security_check.py
    python scripts/security_check.py --zip travel-guide-v2.11.0.zip

`release.py` 会在自查后和打包后再跑。不要将整个工作目录另行压缩发布。

门禁同时比对包外配置与根目录旧配置中的已填 key；显式设置 `TRAVEL_GUIDE_KEYS_FILE` 后，文件缺失、JSON 损坏或结构无效会直接中止。`local-keys.example.json` 只接受空值或明确占位值，避免把新钥匙误填进示例后发布。对应的离线合成值回归：

    python scripts/selftest_security_check.py

## check_skill.py

本 skill 自身的自查（frontmatter、name 与目录名一致、描述长度、`SKILL.md` 残留占位符、文档内部链接是否断链）。不依赖 pyyaml。

    python scripts/check_skill.py .
    python scripts/check_skill.py ~/.agents/skills/travel-guide

## release.py

发版一条命令。按顺序做：钥匙状态 → skill 自查 → 钥匙门禁 → HTML/天气/安全门禁回归 → 壳子 JS 语法 → 重算 `MANIFEST.sha256`（普通发布文件）。
带 `--zip` 时再写临时压缩包、核对成员 / CRC / SHA256、扫描密钥位置并解压复验；全通过才替换正式 ZIP。`--private` 仅在 `--zip` 时可用，私用包默认放桌面，不要放在 skill 根目录内。任何一步失败就中止。

    python scripts/release.py                  # 复验 + 重算清单
    python scripts/release.py --zip            # 再打个包，默认放桌面
    python scripts/release.py --zip --private  # 自用包，包含当前密钥配置
    python scripts/release.py --zip --out OUTPUT_DIR

`MANIFEST.sha256` 是逐文件 SHA256 完整性清单。改动任何文件后清单即失效 —— 不用手改，跑一次 `release.py` 重算即可。

## 安装位置

脚本以 `SKILL.md` 所在目录定位资源，不依赖固定用户目录或盘符。保持一份实际工作副本，避免修改了旧目录却发布了另一个目录。
