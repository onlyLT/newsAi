# MiniMax 隐藏音色 + t2a_v2 接口速查

> 起源：你想用 `Podcast_girl`（心悦）合成口播，但官方 `get_voice` 接口返回的 303 个音色里查不到。
> 实测发现 —— MiniMax 的 t2a_v2 接口**同时认两套音色**：
> 1. 官方公开的（`get_voice` 返回的，platform docs 列的，332 个左右）
> 2. **海螺 AI（hailuo.ai）消费端衍生的"隐藏可用"音色**（API 接受但 `get_voice` 不返回，文档不列）
>
> 本文是后者的实测清单。`2026-05` 验证有效，API 没承诺稳定性，长期使用风险自担。

---

## 1. 接口规范

### 1.1 端点

| 区域 | URL |
|---|---|
| 国内 | `https://api.minimaxi.com/v1/t2a_v2` |
| 海外 | `https://api.minimax.io/v1/t2a_v2` |

**API key 区分大区**。`sk-api-` 开头的 key 通常是 CN 区，只能打 `api.minimaxi.com`。打错大区直接 `invalid api key`。

### 1.2 鉴权

HTTP Header：

```
Authorization: Bearer <YOUR_API_KEY>
Content-Type: application/json
```

key 在 [platform.minimaxi.com](https://platform.minimaxi.com) → API Keys 拿。

### 1.3 请求体

```json
{
  "model": "speech-2.8-hd",
  "text": "你要合成的文字。",
  "voice_setting": {
    "voice_id": "Podcast_girl",
    "speed": 1,
    "vol": 1,
    "pitch": 0
  },
  "audio_setting": {
    "sample_rate": 32000,
    "bitrate": 128000,
    "format": "mp3",
    "channel": 1
  }
}
```

| 字段 | 必填 | 说明 |
|---|---|---|
| `model` | ✓ | 推荐 `speech-2.8-hd`。备选 `speech-02-hd` / `speech-02-turbo` / `speech-01-hd`。隐藏音色实测仅 `speech-2.8-hd` 全支持 |
| `text` | ✓ | ≤ 10000 字符 |
| `voice_setting.voice_id` | ✓ | **大小写敏感**。`Podcast_girl` ≠ `podcast_girl` |
| `voice_setting.speed` | | 语速 0.5–2.0，默认 1 |
| `voice_setting.vol` | | 音量 0–10，默认 1 |
| `voice_setting.pitch` | | 音调 -12–12，默认 0 |
| `audio_setting.format` | | `mp3` / `wav` / `pcm` / `flac` |

### 1.4 响应体

```json
{
  "data": {
    "audio": "<hex-encoded audio bytes>",
    "status": 2,
    "ced": "..."
  },
  "trace_id": "...",
  "base_resp": {
    "status_code": 0,
    "status_msg": "success"
  }
}
```

落盘：`bytes.fromhex(d["data"]["audio"])` → 写文件。

### 1.5 常见错误码

| status_code | 含义 | 处理 |
|---|---|---|
| `0` | success | — |
| `1002` | rate limit exceeded (RPM) | 退避重试，throttle ≥ 3.5s/次（约 17 RPM）就稳了 |
| `2049` | invalid api key | 大区不对 / key 失效 |
| `2054` | voice id not exist | voice_id 拼写错（注意大小写） |
| `2043` | model does not support this voice_id | 换 model，`speech-2.8-hd` 兼容性最好 |

---

## 2. 隐藏可用音色清单（27 个）

> 探测方法：把 [LLM-Red-Team/minimax-free-api](https://github.com/LLM-Red-Team/minimax-free-api)
> repo README 列出的 32 个 Hailuo 音色逐个打 t2a_v2 接口，能返回 status 0 且不在
> `get_voice` 公开 303 个里的 = 隐藏可用。

### 2.1 播客 / 通用旁白（最适合长口播）

| voice_id | 中文名 | 风格 |
|---|---|---|
| **`Podcast_girl`** | 心悦 | 暖女声播客主持，**本项目当前在用** |
| `male-botong` | 思远 | 沉稳男声 |
| `boyan_new_hailuo` | 子轩 | 干净男声 |
| `Daniel_hailuo` | 潇然 | 中性男声 |
| `Bingjiao_zongcai_hailuo` | 沉韵 | 冷静低音 |
| `female-yaoyao-hd` | 瑶瑶 | 清亮女声（hd 模型专版） |

### 2.2 角色 / 戏剧化

| voice_id | 中文名 | 风格 |
|---|---|---|
| `Leishen2_hailuo` | 模仿雷电将军 | 原神角色 |
| `Zhongli_hailuo` | 模仿钟离 | 原神角色 |
| `Paimeng_hailuo` | 模仿派蒙 | 原神角色 |
| `keli_hailuo` | 模仿可莉 | 原神角色 |
| `Hutao_hailuo` | 模仿胡桃 | 原神角色 |
| `Xionger_hailuo` | 模仿熊二 | 熊出没 |
| `Haimian_hailuo` | 模仿海绵宝宝 | 卡通 |
| `Robot_hunter_hailuo` | 模仿变形金刚 | 机械 |
| `YaeMiko_hailuo` | 语嫣 | 御姐 |
| `xiaoyi_mix_hailuo` | 少泽 | 少年混合 |

### 2.3 名人 / 网红风

| voice_id | 中文名 | 风格 |
|---|---|---|
| `JayChou_hailuo` | JayJay | 模仿周杰伦 |
| `Linzhiling_hailuo` | 小玲玲 | 模仿林志玲 |
| `shenteng2_hailuo` | 夏洛特 | 模仿沈腾 |
| `Guodegang_hailuo` | 郭嘚嘚 | 模仿郭德纲 |
| `huafei_hailuo` | 拽妃 | 还珠格格华妃 |

### 2.4 方言 / 地方口音

| voice_id | 中文名 | 风格 |
|---|---|---|
| `lingfeng_hailuo` | 东北er | 东北女声 |
| `male_dongbei_hailuo` | 老铁 | 东北男声 |
| `Beijing_hailuo` | 北京er | 京味儿 |

### 2.5 英文

| voice_id | 中文名 | 风格 |
|---|---|---|
| `cove_test2_hailuo` | 浩翔（英文） | 英文男声 |
| `scarlett_hailuo` | 雅涵（英文） | 英文女声 |

### 2.6 其它

| voice_id | 中文名 | 风格 |
|---|---|---|
| `yueyue_hailuo` | 小月月 | 萌妹 |

---

## 3. 受限 / 不可用音色（4 个）

实测在 `speech-2.8-hd` / `speech-02-hd` / `speech-02-turbo` / `speech-01-hd` /
`speech-01-turbo` / `speech-01` 所有模型上都返回 `2043 model does not support
this voice_id`。可能是已废弃 / 需要特殊 SFT 微调模型权限：

| voice_id | 中文名 |
|---|---|
| ~~`xiaomo_sft`~~ | 芷溪 |
| ~~`murong_sft`~~ | 晨曦 |
| ~~`shangshen_sft`~~ | 沐珊 |
| ~~`kongchen_sft`~~ | 祁辰 |

---

## 4. 使用示例

### 4.1 curl 单段合成

```bash
KEY='sk-api-xxxxxxxx'
curl -X POST 'https://api.minimaxi.com/v1/t2a_v2' \
  -H "Authorization: Bearer $KEY" \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "speech-2.8-hd",
    "text": "你想象一下，每年到了预算评审季，财政局桌上堆着几百份申报表。",
    "voice_setting": {"voice_id": "Podcast_girl", "speed": 1, "vol": 1, "pitch": 0},
    "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1}
  }' | python -c "
import sys, json
d = json.load(sys.stdin)
print('status:', d['base_resp'])
open('out.mp3', 'wb').write(bytes.fromhex(d['data']['audio']))
"
```

### 4.2 Python（节流 + 重试）

参考本项目 `presentation/scripts/synthesize-audio-mmx.py`：

```python
import json, os, time, urllib.request

KEY = os.environ["MINIMAX_API_KEY"]
URL = "https://api.minimaxi.com/v1/t2a_v2"

def synth(text, voice_id, out_path, throttle=3.5):
    time.sleep(throttle)  # 留 RPM 余量
    payload = {
        "model": "speech-2.8-hd",
        "text": text,
        "voice_setting": {"voice_id": voice_id, "speed": 1, "vol": 1, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
    }
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        d = json.loads(r.read())
    assert d["base_resp"]["status_code"] == 0, d["base_resp"]
    open(out_path, "wb").write(bytes.fromhex(d["data"]["audio"]))
```

---

## 5. 注意事项

1. **voice_id 大小写敏感**。`Podcast_girl` ✓ / `podcast_girl` ✗。
2. **RPM 节流**。新账号实测 ~20 RPM，建议 throttle ≥ 3.5s/次。撞 1002 后指数退避（5s → 10s → 20s → 40s）。
3. **稳定性无保证**。隐藏音色不在官方文档，未来可能下架。生产环境建议把音频
   合成结果**预先落盘**，运行时不要在线调用。
4. **大区敏感**。CN key 打 `api.minimax.io` (global) 必 fail，反之亦然。
5. **计费按字符**。`speech-2.8-hd` 计费表见
   [platform 控制台](https://platform.minimaxi.com)。55 段 ~2500 字总耗 ¥1 内。
6. **`get_voice` 接口不返回隐藏音色**。要找新的隐藏音色只能从消费端
   （hailuo.ai 网页 UI）扒下来再来 t2a_v2 验证。

---

## 6. 自己再扒更多音色的方法

1. 打开 [hailuo.ai 的语音合成页面](https://hailuo.ai/audio)，浏览器 F12 → Network
2. 选一个新音色，触发合成 → 找请求体里的 `voice_id` 字段
3. 把这个 voice_id 喂给本项目 `scripts/probe-hidden-voices.py` 的 `HAILUO_CANDIDATES` 列表
4. 跑探测脚本：

   ```bash
   MINIMAX_API_KEY='sk-xxx' python scripts/probe-hidden-voices.py
   ```

5. 结果 dump 到 `scripts/hidden-voices.json`

---

## 7. 参考

- [LLM-Red-Team/minimax-free-api](https://github.com/LLM-Red-Team/minimax-free-api) — Hailuo 反向工程项目（已 archived 2025-11-27，但 README 的音色表仍是最完整的索引）
- [System Voice ID 官方列表](https://platform.minimax.io/docs/faq/system-voice-id) — 官方公开 332 个音色（不含本文清单）
- [t2a_v2 接口文档](https://platform.minimax.io/docs/api-reference/speech-t2a-http) — 请求 / 响应规范
- 本项目 `presentation/scripts/synthesize-audio-mmx.py` — 生产级合成脚本（节流 + 重试）
- 本项目 `presentation/scripts/hidden-voices.json` — 探测原始结果
