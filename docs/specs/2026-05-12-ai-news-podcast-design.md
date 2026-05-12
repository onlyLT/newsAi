# AI 投资晨读 — 自动化日更视频播客 设计文档

**Date**: 2026-05-12
**Status**: Draft, awaiting user review
**Owner**: louteng111@gmail.com

---

## 1. 目标

每天自动产出一期"AI 投资晨读"短视频（3–5 分钟）+ 一份当日 HTML 数字报告，全流程**无人值守**，帮助观众跟进 AI 板块的可投资信号。

对标参考：B站「小戴晨读」（财经晨读的栏目化结构、信息密度、有观点）。差异：垂直聚焦 AI 板块、视频更短、形态更轻（不上数字人）。

### 1.1 成功标准 (一期)

- 每天 07:00 自动跑完，产出 mp4 + HTML，无人工介入
- 选 10 条左右当日 AI 相关、对投资有信号的新闻
- 每条新闻都带"对哪些标的有什么影响"的解读，而非纯转述
- 单次端到端运行成本 ≤ 5 元（LLM + TTS）
- 任何阶段失败可单独重跑，不必从头再来

### 1.2 一期不做 (YAGNI)

- 数字人形象 / AI 主播
- 自动上传 B站 / YouTube（一期手动上传）
- 接 X/Twitter（API 贵，封号风险）
- 个性化推荐 / 用户互动
- 多语言版本

---

## 2. 内容定位

**AI 投资晨读** — 不是泛 AI 资讯，是 AI 板块（A股 / 美股 / 港股）的投资视角解读。

筛选标准（喂给 LLM 的硬性要求）：每条新闻需明确指向至少一个上市公司 / 板块 / 投资逻辑。例如：

- ✅ "NVIDIA 发布 Blackwell B200，性能提升 X" → 利好 NVDA、台积电、相关 HBM 供应商
- ✅ "OpenAI 估值传闻 5000 亿美元" → 影响 Microsoft、相关概念股情绪
- ✅ "国务院发文支持算力基础设施" → 利好国产算力链
- ❌ "某高校发表 LLM 论文" → 无明确投资信号

---

## 3. 子系统架构

```
┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│ 1. Ingest    │ → │ 2. Curate    │ → │ 3. Script    │ → │ 4. Render    │ → │ 5. (Manual)  │
│ 多源拉取去重 │   │ LLM 选10条+  │   │ LLM 口播稿   │   │ HTML+TTS+    │   │ 发布 B站     │
│              │   │ 投资解读     │   │ + 卡片数据   │   │ Video 拼装   │   │              │
└──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
        ↓                  ↓                  ↓                  ↓
   raw.json          curated.json        script.md          index.html
                                         cards.json         video.mp4
```

每个 pipeline 阶段：
- **独立可重跑**：输入产物在前一阶段的 `dist/YYYY-MM-DD/` 目录里，单独执行该阶段脚本即可
- **幂等**：重跑同一阶段会覆盖产物，不污染上下游
- **清晰边界**：每阶段输入 / 输出 schema 固定（见各节）

---

## 4. 子系统详细设计

### 4.1 Ingest — 多源采集

**输入**: `sources/sources.yaml`（新闻源清单）
**输出**: `dist/YYYY-MM-DD/raw.json`

```yaml
# sources/sources.yaml 示例
sources:
  - id: jiqizhixin
    name: 机器之心
    type: rss
    url: https://www.jiqizhixin.com/rss
    lang: zh
  - id: 36kr_ai
    name: 36氪 AI
    type: rss
    url: https://36kr.com/feed-newsflash
    filter_keywords: [AI, 大模型, 算力]
    lang: zh
  - id: techcrunch_ai
    type: rss
    url: https://techcrunch.com/category/artificial-intelligence/feed/
    lang: en
  # ... 见 §4.1.1 全清单
```

**职责**：
- 并发拉所有 RSS（`feedparser` + `asyncio`/`httpx`）
- 单源失败不影响其他源（记录到日志，继续）
- **时间过滤**：只保留 last 24h 的条目
- **去重**：基于 URL（normalize 后）+ 标题 fuzzy match (>= 85% similarity)
- **关键词过滤**：可选 `filter_keywords`，命中任一即保留（用于过滤泛财经源中的非 AI 新闻）

**输出 schema** (`raw.json`)：
```json
[
  {
    "id": "sha256(url)",
    "source_id": "techcrunch_ai",
    "title": "...",
    "url": "...",
    "published_at": "2026-05-12T03:21:00Z",
    "summary": "...",  // RSS 自带摘要，可能为空
    "content": "...",  // 如能拉到正文则填，否则空
    "lang": "en"
  }
]
```

#### 4.1.1 一期源清单

| ID | 名称 | 类型 | 语言 |
|---|---|---|---|
| jiqizhixin | 机器之心 | RSS | zh |
| qbitai | 量子位 | RSS | zh |
| xinzhiyuan | 新智元 | RSS | zh |
| 36kr_ai | 36氪 AI 频道 | RSS | zh |
| techcrunch_ai | TechCrunch AI | RSS | en |
| theverge_ai | The Verge AI | RSS | en |
| hn_ai | Hacker News (filter: AI) | RSS | en |
| openai_blog | OpenAI Blog | RSS | en |
| anthropic_news | Anthropic News | RSS | en |
| google_ai_blog | Google AI Blog | RSS | en |
| nvidia_blog | NVIDIA Blog | RSS | en |

> 实施期可能发现部分源没有公开 RSS，会用 sitemap / HTML 抓取替代或换源。

### 4.2 Curate — 筛选 + 摘要 + 投资解读

**输入**: `raw.json`（当日全量，可能 50–200 条）
**输出**: `dist/YYYY-MM-DD/curated.json`（筛后 10 条）

**实现**：一次 LLM 调用（Claude 4.7），传入：
- System prompt（栏目定位 + 选稿标准 + 输出 schema）— **prompt caching**
- 最近 3 天 `curated.json`（避免重复选题）— **prompt caching**
- 当日 `raw.json` 全量

要求 LLM 输出**结构化 JSON**：

```json
[
  {
    "rank": 1,
    "title": "重写后的中文标题，<= 30 字",
    "tldr": "一句话核心信息，<= 80 字",
    "details": "2–3 句展开，<= 200 字",
    "impact": {
      "tickers": ["NVDA", "TSM"],         // 直接相关标的
      "sectors": ["算力", "HBM"],         // 概念板块
      "direction": "bullish|bearish|mixed",
      "reasoning": "为什么这条对这些标的有影响，<= 150 字"
    },
    "source_url": "...",
    "source_name": "..."
  }
]
```

**质量门**（curate 阶段自动校验，不达标重试一次）：
- 必须正好 10 条（允许 ±2）
- 每条 `impact.tickers` 或 `impact.sectors` 至少一项非空
- 标题 / tldr 字数限制满足

### 4.3 Script — 口播稿生成

**输入**: `curated.json`
**输出**:
- `dist/YYYY-MM-DD/script.md`（人类可读的完整稿）
- `dist/YYYY-MM-DD/segments.json`（按节拍切好的稿，TTS 用）

**栏目固定结构**（LLM 按模板填）：
1. **开场**（10s）："各位早，今天是 X 月 X 日，AI 投资晨读，今天有 10 条..."
2. **逐条播报**（每条 ~20–25s）：标题 → tldr → 投资影响一句话
3. **收尾**（10s）："以上是今日 AI 投资晨读，点赞关注..."

**segments.json schema**：
```json
[
  {"id": "intro", "text": "...", "duration_hint_s": 10},
  {"id": "item-1", "text": "...", "card_ref": "card-1", "duration_hint_s": 22},
  ...
  {"id": "outro", "text": "...", "duration_hint_s": 10}
]
```

`card_ref` 用于 Render 阶段对齐"当前讲到第几条 → 显示第几张卡片"。

### 4.4 Render — HTML 报告 + 视频拼装

#### 4.4.1 HTML 报告 (`index.html`)

单源 HTML 模板（Jinja2），渲染 `curated.json`，产出 `dist/YYYY-MM-DD/index.html`：

- 顶部：日期 + 期号 + 简介
- 10 张新闻卡片：rank + 标题 + tldr + 影响标签（tickers/sectors + 涨跌方向色块）+ 原文链接
- 视觉规范：暗色主题、等宽数字、信息密度高、单页可竖向滚动浏览（独立浏览用）

**复用为视频画面**：同一份 HTML，提供 `?mode=video&card=N` query 参数 → 只显示第 N 张卡片放大居中（视频画面布局）。

#### 4.4.2 视频拼装

```
1. Playwright 启动 headless Chromium
2. 对每个 segment：
   - intro/outro: 渲染对应的固定页（HTML 模板的 cover/end 视图）
   - item-N: 渲染 index.html?mode=video&card=N
   - 截图（1920×1080 PNG）
3. TTS（MiniMax）逐段生成 mp3，得到每段实际时长
4. ffmpeg / moviepy 拼装：
   - 每个截图作为一段视频底图，时长 = 对应 TTS 时长
   - 叠加自动生成的字幕（SRT，按 segment 文本切分）
   - 拼接 + 加 BGM（assets/bgm.mp3，混音 -20dB）
   - 输出 1080p H.264 mp4
```

**字幕**：基于 segment 文本 + TTS 段时长简单平分（不做 ASR 对齐，一期够用）。

### 4.5 调度

`run_daily.py` 顺序执行 1→4，每阶段失败：
- 记录到 `dist/YYYY-MM-DD/run.log`
- 用 Windows 通知（`win10toast` 或 PowerShell `BurntToast`）弹一条本地提示
- 退出非 0（任务计划程序会标记失败）

Windows 任务计划程序触发：每日 07:00。

---

## 5. 项目结构

```
newsAi/
├── pipelines/
│   ├── ingest.py          # 4.1
│   ├── curate.py          # 4.2
│   ├── script.py          # 4.3
│   ├── render_html.py     # 4.4.1
│   └── render_video.py    # 4.4.2
├── sources/
│   └── sources.yaml
├── prompts/
│   ├── curate.system.md
│   └── script.system.md
├── templates/
│   ├── index.html.j2      # 双用途模板（独立浏览 + 视频画面）
│   └── styles.css
├── assets/
│   ├── bgm.mp3
│   ├── logo.png
│   └── intro_outro/       # 片头片尾素材
├── dist/
│   └── YYYY-MM-DD/        # 当日所有产物
│       ├── raw.json
│       ├── curated.json
│       ├── script.md
│       ├── segments.json
│       ├── audio/         # 每段 mp3
│       ├── frames/        # 每段 png
│       ├── index.html
│       ├── video.mp4
│       └── run.log
├── tests/
├── run_daily.py           # 编排入口
├── pyproject.toml
└── .env                   # ANTHROPIC_API_KEY, MINIMAX_API_KEY
```

---

## 6. 技术栈

| 模块 | 选型 | 理由 |
|---|---|---|
| 语言 | Python 3.11+ | 生态最全 |
| LLM | Claude 4.7 (`claude-opus-4-7`) | 长上下文 + prompt caching |
| LLM SDK | `anthropic` | 官方 SDK，支持 prompt caching |
| RSS | `feedparser` + `httpx` (async) | 标准方案 |
| HTML 模板 | `Jinja2` | 最熟知 |
| 截图 | `playwright` | 比 selenium 现代 |
| TTS | MiniMax (`mmx-cli` 或 SDK) | 用户已有经验 |
| 视频 | `ffmpeg-python` | 比 moviepy 更可控 |
| 配置 | `pydantic-settings` + YAML | 类型安全 |
| 日志 | `structlog` | 结构化日志便于排查 |
| 测试 | `pytest` | 标准 |

---

## 7. 错误处理与可观测性

- **每阶段独立日志**：`dist/YYYY-MM-DD/run.log`，包含每个 source 拉取耗时 / 条数、LLM token 用量、TTS 耗时、ffmpeg 命令
- **优雅降级**：
  - 单个 RSS 源失败：跳过，继续
  - LLM 返回不合规 JSON：重试 1 次，仍失败则保存原始响应到 `curated.error.json` 退出
  - 部分 TTS 段失败：跳过该段（视频会少一条，但能跑完）
- **本地通知**：成功 / 失败都弹通知，便于发现"没跑成"
- **历史回看**：保留过去 30 天的 `dist/` 目录，便于排查

---

## 8. 测试策略

- **Unit**：每个 pipeline 阶段的纯函数（去重、schema 校验、字幕切分）有单测
- **Integration**：每个阶段提供 `--input fixture.json` 入口，能用 fixture 跑完不依赖网络 / LLM
- **End-to-end smoke**：`run_daily.py --dry-run`：用 1 个源、3 条新闻、mock LLM、mock TTS，跑通到 mp4 输出
- **不 mock**：LLM 真实调用走真实 API（用小 fixture，token 消耗可控）

---

## 9. 成本估算（每日单次运行）

| 项 | 估算 | 备注 |
|---|---|---|
| LLM (curate) | ~50K input + 5K output ≈ ¥0.5 | prompt caching 后可降到 ¥0.2 |
| LLM (script) | ~5K input + 3K output ≈ ¥0.2 | |
| TTS | ~1500 字 × ¥0.001/字 ≈ ¥1.5 | MiniMax 标准价 |
| 其他 | 0 | 本机运行 |
| **合计** | **~¥2.2 / 天** | 远低于 ¥5 目标 |

---

## 10. 实施分期

**一期（本设计范围）**：
- 全部子系统 1–4，本地无人值守 + 手动上传
- 11 个新闻源
- 1 套 HTML 模板
- 验收：连续 7 天稳定跑通，产出可上传到 B站的视频

**二期（不在本 spec 范围）**：
- 自动上传 B站 / YouTube
- 接入 X/Twitter / 微博热搜
- 视觉升级：动态过渡 / 数字人
- 数据回看：每条新闻后续股价表现自动回填

---

## 11. 开放问题（实施时再定）

- MiniMax 音色选哪个（实施时试听几个再定）
- BGM 选哪首 / 是否需要授权（实施时找 royalty-free）
- 片头片尾的视觉具体设计（实施时做几个 mock 让用户选）

这些不影响架构，留到 plan 阶段处理。
