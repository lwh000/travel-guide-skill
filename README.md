# Travel Guide

**一份给 Codex 使用的旅游攻略 Skill。** 从目的地、日期、预算和同行情况出发，整理可执行的逐日行程；推荐地点与会变化的事实尽量附上可核对的来源和查询日期。需要时还能生成可点击、可打印的单文件 HTML 攻略。

## 能做什么

- **把行程排得能走通**：先确定交通、住宿片区和每日负荷，再安排景点、吃饭、休息与备选方案。
- **核对关键事实**：具名酒店、餐厅、景点，以及票价、开放时间、预约规则和交通信息按来源核实；查不到的数字不会凭空补齐。
- **按需求控制篇幅**：支持简要大纲、周末精简版、3–5 天完整攻略，以及多城市行程。
- **生成网页攻略**：默认采用杂志式封面、行程主线与逐日卡片；也可指定极简或打印优先。HTML 可本地双击打开，部分地图或图片资源需要联网。
- **按交通方式呈现路线**：境内自驾可使用路线图与导航链接；飞机、高铁、火车和市内步行/地铁行程以交通表与查询入口为主。分享版自驾网页使用不含私人地图凭据的 SVG 路线图。
- **按需处理天气**：有明确日期且天气影响安排时，尝试获取对应日期的数据；来源不可用时给出官方查询入口，不把近期参考写成出行日预报。

适用于旅行规划、周末出游、酒店或餐厅短名单、打包清单，以及可点击的 HTML 行程。Skill 不会替你登录账号、付款订票、代填签证或保证实时房价、余票和路况；境外行程不排自驾路线。

## 试着这样提问

```text
帮我做一份杭州 3 天攻略。两位成人，从上海坐高铁出发，
预算每人 2000 元，节奏轻松，想看西湖和博物馆。
给我逐日安排、真实住宿和餐厅、必订事项，并导出可点击 HTML。
```

```text
周末从广州自驾去清远，带一位长辈。
请安排不赶路的路线、停车和休息点，做一份可打印攻略。
```

```text
先给我一份东京 5 天行程大纲，重点是美术馆和街区散步。
签证或入境要求只给我需要核对的官方入口。
```

出发地、日期、人数、交通方式、预算、节奏、必去或避开的地点越明确，行程越贴近你的需要。也可以只给目的地和日期，让 Skill 先组织方案。

## 安装

克隆本仓库，或在 GitHub 的 Code 菜单下载 ZIP 并解压。将其中的 `travel-guide` 目录放入你的 Codex 技能目录，确保文件位置是：

```text
~/.codex/skills/travel-guide/SKILL.md
```

如果你的 Agent 使用另一处技能目录，以该程序实际扫描的路径为准；目录结构须保持不变。重新打开会话后，直接用上面的自然语言提问即可。

普通版不包含 API 密钥。生成一般攻略、来源链接和 SVG 路线图不要求先配置密钥。

### 手机端导入

手机端技能中心对包内 Markdown 的扫描比桌面端严格。v2.11.3 起，发布包中所有 Markdown 都带合法的 `name` / `description` frontmatter，且 ZIP 的第一个成员固定为 `SKILL.md`，可直接导入。

如果旧包仍报 `文件缺少合法的 frontmatter (name/description)`，不要改正文，换成 v2.11.3 或更新版本重新导入。只需要技能主文件时，可把仓库中的 `travel-guide/SKILL.md` 单独打包为只含一个文件的 ZIP；完整包则保留 `travel-guide/` 目录结构。

## 可选：天气和私人地图配置

复制 [`local-keys.example.json`](travel-guide/local-keys.example.json) 到包外的私人位置，填入自己申请的凭据，再设置 `TRAVEL_GUIDE_KEYS_FILE` 指向该 JSON 文件的绝对路径。未设置该变量时，脚本会尝试读取 Skill 根目录的 `local-keys.json`；请勿把这个文件提交到公开仓库。

| 字段 | 用途 |
| --- | --- |
| `qweather.key` | 和风天气 API Key |
| `qweather.host` | 和风控制台提供的专用 API Host；凭据 ID 不能代替 Host |
| `qweather.credentialId` | 可选的凭据标识，不作为请求地址 |
| `amap.jsKey` 与 `amap.securityJsCode` | 仅供私人本地境内自驾 HTML 加载高德地图 |

配置好后，在 `travel-guide/` 目录运行：

```bash
python scripts/live_data.py status
```

`status` 只报告字段是否已填，不输出密钥值。使用私人地图凭据生成的本地 HTML 可能把高德 JS 凭据暴露给打开网页的人；准备分享时请使用 SVG 路线图。天气查询依赖相应服务和网络连通性；失败时攻略会给出官方复核入口。

## 本地检查

辅助脚本使用 Python 3.10+。在 `travel-guide/` 目录运行：

```bash
python scripts/check_skill.py .
python scripts/live_data.py status
python scripts/selftest_validate.py
python scripts/selftest_live_data.py
python scripts/selftest_security_check.py
```

制作完 HTML 攻略后，再运行 `python scripts/validate_html.py 攻略.html`。这个校验器检查日期、链接、来源结构、地图数据等**离线结构问题**；它不替代对景点、票价和签证等事实的网页核查。

维护者发布前运行 `python scripts/release.py`；生成普通 ZIP 使用 `python scripts/release.py --zip`。发布脚本会复验、重算 [`MANIFEST.sha256`](travel-guide/MANIFEST.sha256)，并检查普通包中没有私人配置。不要直接压缩整个工作目录作为公开发行包。

## 目录

```text
travel-guide/
├─ SKILL.md                    Skill 入口与工作流
├─ agents/openai.yaml          展示名称与默认提问模板
├─ references/                 规划、检索、地区、地图、天气、HTML 等规则
├─ assets/guide-shell.html     HTML 攻略模板
├─ assets/icon.svg             图标
├─ scripts/                    实时数据、校验、回归与发布脚本
├─ local-keys.example.json     空白配置模板
├─ MANIFEST.sha256             普通发布文件的完整性清单
└─ CHANGELOG.md                版本记录
```

详细使用规则见 [`SKILL.md`](travel-guide/SKILL.md)；脚本说明见 [`scripts/README.md`](travel-guide/scripts/README.md)；版本变化见 [`CHANGELOG.md`](travel-guide/CHANGELOG.md)。
