---
name: travel-guide
description: 做可核对来源的旅游攻略与逐日行程，含真实酒店、餐厅、景点、票价、交通和打包。用户提到旅游攻略、行程、旅行计划、周末去哪、酒店短名单、门票、自驾路线，要可点击 HTML 攻略或打印版，或只给了目的地和日期时使用。不要用于订票账号登录、代填签证、退改签、纯机票比价，或没有行程的城市百科。
metadata:
  short-description: 可核对的行程攻略
  version: "2.11.3"
  last-reviewed: "2026-10-20"
---

# 旅游攻略

产出能照着走的行程：店名、票价、路线都要能核对，不要写成宣传册。不要编店名。

语言跟用户走。先看当前会话实际有哪些预订工具；没有就给官方或预订深链，不声称已代订。即使有工具，也只在用户明确要求的范围内操作，不索取账号密码。

**不承诺实时库存**：余票、可订座位、实时房价、当日排队和路况给官方查询入口；查到天气或参考票价时标查询日期，不把查询结果写成保证。

天气、城际票价、高德地图钥匙的取法见 [references/live-data.md](references/live-data.md)。钥匙不要打印到聊天里，也不要把和风 key 写进 HTML。

签证、过境和入境要求按护照国籍、居留身份、行程路线、出行目的与日期查适用的官方页面，写明核查日期；缺关键身份信息时先问一项真正阻塞的信息，或只给官方核查入口，不下适用性结论。不要猜过签率，不要代填。

**事实**（价格、时间、是否必须预约）带来源；**建议**（放上午、换片区）是规划结论，不必每句都引用。

## 什么时候用

目的地研究、逐日行程、酒店短名单、餐厅、门票、打包、境内自驾或城际交通、周末去哪、N 天怎么玩，或一份可点击 HTML 攻略。

**不要用来**：登录订票、代填签证、替用户买票、退改签、纯机票比价、没有行程的城市百科、境外自驾路线。

## 工作流

用户需求 → 锁定约束 → 行程骨架 → 按复杂度选研究档位 → 列出会影响行程的关键事实 → 批量检索并核实最终声明 → 写作 → HTML 只转换已有事实 → 自检。

不要边搜边写完整攻略。先有骨架，再填已核实的事实。普通短途优先 Fast；多城市、复杂换乘、旺季或高风险入境信息按实际核实量升档。内部记住约束、锁定项、骨架、研究档位、检索缓存和校验结果即可，不要把状态机贴给用户。

收集问卷、缺省值、锁定项、改需求重算范围、减负顺序见 [references/planning.md](references/planning.md)；先定骨架再检索。

### 研究档位与检索投入

**研究档位、候选上限和检索预算以 [references/research-playbook.md](references/research-playbook.md) 为唯一出处。** 预算用于控制候选扩张，不代替最终事实的证据要求：无法核实的价格、开放时间、末班交通或入境要求，删去具体断言并给适用官方入口；不能用猜测补满攻略。可信来源已覆盖且没有冲突时不重复核同一事实。不需要的参考文件不要读。

## 只加载用得到的参考

| 情况 | 读 |
|---|---|
| 完整或精简攻略 | [references/planning.md](references/planning.md)、[references/research-playbook.md](references/research-playbook.md)、[references/output-template.md](references/output-template.md) 的对应档 |
| 只要大纲 | output-template 的大纲档 + planning 的负荷/抵达离开；纯结构可不检索，若包含实际目的地、交通或地点推荐，仍核查必要事实 |
| 中国大陆 / 港澳台 | [references/china.md](references/china.md) |
| 出境、签证、eSIM、时差 | [references/international.md](references/international.md) |
| 亲子、长辈、自驾、徒步、海岛、美食为主、摄影、旺季、冰雪、乐园、多城市、穷游/豪华、独自、商务顺游 | [references/modes.md](references/modes.md) 里对应小节 |
| 打包，或户外 / 雨季 / 高海拔 / 严寒 | [references/packing.md](references/packing.md) |
| 对话里的自驾（不要网页） | [references/maps.md](references/maps.md) 的「对话里的自驾」「每天路线卡片」「停靠点表」 |
| 用户要 HTML / 可预览 / 可点击 / 打印 | [references/html-guide.md](references/html-guide.md)、[references/maps.md](references/maps.md)、[references/media.md](references/media.md)、[assets/guide-shell.html](assets/guide-shell.html)、写完跑 [scripts/validate_html.py](scripts/validate_html.py) |
| 天气、飞机/高铁/火车票价、境内自驾真地图 | [references/live-data.md](references/live-data.md)；`TRAVEL_GUIDE_KEYS_FILE` 可指向包外配置，未设置时读取根目录 `local-keys.json`（格式见 `local-keys.example.json`）。先跑 `python scripts/live_data.py status` |
| 改完这个 skill 之后想抽查 | [references/eval.md](references/eval.md)（**不要**在做攻略时读） |

「画路线」只要求 HTML。对话里给文字路线 + 导航链接即可。

**同一条规则只在一个文件里是权威出处**：研究档位 / 预算 / 轮次 / 搜索与打开上限 / 来源 / 候选上限 → research-playbook；收集问卷 / 缺省值 / 锁定 / 改需求 / 负荷 → planning；地图 → maps；HTML 结构 → html-guide；输出章节 → output-template；天气与飞机/高铁/火车票价 → live-data。其他地方只引用，不重复解释，也不要把同一句话在多处改成不一样的数字。

## 输出要求

档位的完整定义（每档写哪些节、节奏要求）以 [references/output-template.md](references/output-template.md) 为唯一出处，这里只给「什么需求 → 什么档」的映射。

| 需求 | 档 |
|---|---|
| 「先给个大纲」 | 大纲 |
| 周末 / 1–2 天；只要吃 / 打包 / 交通 / 酒店 | 精简 |
| 3–5 天、一城 | 完整 |
| 多城市 / 7 天以上 | 默认精简偏长；用户明确要逐日细节时按要求展开 |
| HTML / 可点击 | 对话里给摘要，并给出 HTML 文件 |

默认完整档要有具名住宿、餐厅、景点和预订 / 导航入口。只有核心 / 收费 / 必订景点深核开放时间、票价和预约；非核心景点只给名称、建议停留和官方入口。扫一眼能看懂。一句背景就够。

用户要 HTML 时再写可双击打开的网页。未指定样式时用杂志版；用户要极简或打印优先时按其要求简化，同时保留清晰的逐日和来源信息。自驾 / 非自驾 / 混合交通用不同 `htmlMode`，见 html-guide.md / maps.md。

要不要地图看这次怎么走：自驾，或混合行程里真有自驾段，才保留路线图。飞机 / 高铁 / 火车、一城地铁步行删掉路线图，不要加载高德地图脚本，把票价列成表；混合行程若也含城际大交通，仍保留该段票价表。境外不排自驾路线；境外 HTML 给 Google 搜索链接，不接地图 JS，也不为非自驾行程强加路线图。加载与钥匙细则见 html-guide.md / live-data.md。

住、吃、景的数量上限以 [references/research-playbook.md](references/research-playbook.md) 的「候选上限」为准；表格样式见 [references/output-template.md](references/output-template.md)。不要为了填满表格硬凑；精简档仍要具名住/吃，除非用户只要其中一节。

## 质量线

- 每个推荐地点都有一句理由。
- 每天的负荷说得通：给吃饭、走路、排队留空档。发出前过 planning.md 的「发出前可行性校验」五条。
- 有数字上限时，推荐合计尽量低于上限；更好的放可升级。硬预算明显不够时直说，给最低可行方案或缩天数/换城市，不要造假穷游。
- 名字真实、没有错字。
- 不给违法、危险、易被骗的建议。点名常见坑。
- 季节不合适要直说，并给改期或 B 计划。
- 查不到的事实按 research-playbook 的降级话术写，不要堆「未确认」。
- 自驾先确认进城限行 / 尾号 / 预约通行；带娃或带老人时按馆核实优惠票依据（身高还是年龄），免票也要预约。
- 有目的地与日期、且天气会影响行程时，在对话和 HTML 给独立天气节；数字气温必须对应日期与来源。只问酒店、餐厅、打包，或日期未知时无需硬加天气。取法与降级见 [references/live-data.md](references/live-data.md)。
- **HTML 默认杂志版**：未指定样式时给封面、主线、日卡、住宿卡；用户要极简或打印版时按要求调整。
- 发出前过检索手册末尾自检；**交付 HTML 前必须跑 `scripts/validate_html.py`**，有 FAIL 先修结构、删无效字段或降级展示，不得因 FAIL 自动开启新一轮研究。WARN 要在对话里说明。HTML 只转换已有事实，不为配图或补店再搜。

## 交付之后

交付已完整时直接结束；仅在有决策缺口且用户回答会改变下一步时问一个问题。收集阶段问过的不要重复问。没有要求就不要整份重做（减负顺序见 planning.md）。

## 改这个 skill 之后

版本以 frontmatter 的 `metadata.version` 为准；修订时按语义版本升级，并在 CHANGELOG 新增条目。

1. 用 [references/eval.md](references/eval.md) 的回归案例抽查，按「必须出现 / 必须不存在」核对。
2. 跑 `python scripts/release.py`：它按顺序做钥匙状态 → skill 自查 → 钥匙门禁 → HTML、天气和密钥回归用例 → 壳子 JS 语法 → 重算 `MANIFEST.sha256`，任何一步失败就中止。
3. 要出普通压缩包就 `python scripts/release.py --zip`；用户明确要求把本机现有密钥随自用包带走时用 `python scripts/release.py --zip --private`。两者默认放桌面，`--out` 可指定目录；**正式包只通过 release.py 生成，禁止直接压整个工作目录**。脚本会核对成员、CRC、逐文件 SHA256、密钥位置，并解压实跑复验。
4. 以当前 `SKILL.md` 所在目录为工作目录，不假定安装盘符或用户目录。发布包由 `release.py` 的白名单生成，不把测试快照、单次行程脚本或备份塞进包。
5. 普通包不含私人钥匙；私用包只在包内 `local-keys.json` 放入当前配置，解压后 skill 可直接读取。聊天、文档及其他发布文件不要打印或复制 key。私人本地自驾 HTML 需要加载地图时会向打开该 HTML 的人暴露高德 JS 凭据，见 [references/live-data.md](references/live-data.md)。发布前跑 `scripts/security_check.py`。
