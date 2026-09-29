# 免费文本模型选型与 API 接入方案

## 1. 模型在本项目中的角色（先明确边界）

> 关键原则：**纠错不用 LLM，只用 LLM 做「语义判断」**。

- **用 LLM 做的事**：
  - 台词提取（识别哪些行是台词、区分中英文、处理不规则排版）；
  - 可选的跨语言兜底（若字幕与剧本不是同一种语言）。
- **不用 LLM 做的事**：
  - 字幕文本的纠错/替换。因为剧本是标准答案，用确定性算法（归一化 + 模糊匹配 + 逐字 diff）更准、零幻觉、零成本。

由于台词提取属于「轻量语义分类 + 少量生成」，对模型能力要求不高，小模型即可胜任，且推理量很小。

## 2. 候选方案对比（2026 现状）

### 2.1 本地 Ollama（推荐主方案）

| 维度 | 说明 |
| --- | --- |
| 成本 | 完全免费、离线、无次数限制 |
| 隐私 | 数据不出本机，剧本不外传（最符合本项目需求） |
| 模型 | `qwen2.5:7b`、`qwen3`、`llama3.1` 等，7B 级即可胜任台词提取 |
| 代价 | 需本机安装 Ollama 并下载模型（约 4~8GB），占用内存/显存 |

### 2.2 国内免费/低价 API（国内可直连）

| 平台 | 免费/额度 | 代表性模型 | 说明 |
| --- | --- | --- | --- |
| 硅基流动 SiliconFlow | 新用户赠金 + 多款免费模型 | Qwen 系列、DeepSeek、GLM | OpenAI 兼容，国内直连，响应快 |
| 智谱 AI | 新用户 2000 万 Tokens（永久） | GLM-4-flash（免费） | 国产，flash 档免费 |
| DeepSeek 官方 | 送免费额度 + 极低价 | DeepSeek-V3 | OpenAI 兼容，性价比高 |
| 阿里云百炼 | 每模型 100 万 Tokens（3 个月） | Qwen 系列 | 需开通阿里云 |

### 2.3 国际免费 API（需科学上网，不建议作主方案）

| 平台 | 免费额度 | 代表性模型 | 备注 |
| --- | --- | --- | --- |
| Google AI Studio | Flash 类免费（10~15 RPM） | Gemini Flash | 需科学上网，免费档可能用你的数据 |
| Groq | 30 RPM | Llama/Qwen/Whisper | 速度快，需科学上网 |
| OpenRouter | 50 req/天（免费档） | 多模型 | 聚合网关 |
| Cerebras | 约 100 万 Tokens/天 | Llama/Qwen | 模型列表易变动 |

## 3. 推荐方案

1. **首选：本地 Ollama**（`qwen2.5:7b` 或 `qwen3`）——离线、免费、隐私好，台词提取任务完全够用。
2. **备选/快速上手：硅基流动 或 智谱 GLM-4-flash**——无需装 Ollama，国内直连，OpenAI 兼容，几行代码即可调用。

> 建议：代码层面做「模型适配层」，运行时通过配置切换 Ollama / 硅基流动 / 智谱，三者对上层完全透明。

## 4. 免费 API 具体接入方案（OpenAI 兼容）

主流平台都兼容 OpenAI SDK，只需改 `base_url` 和 `api_key` 即可切换。

### 4.1 各平台接入参数

| 平台 | base_url | 示例模型 |
| --- | --- | --- |
| 硅基流动 | `https://api.siliconflow.cn/v1` | `Qwen/Qwen3-8B`、`deepseek-ai/DeepSeek-V3` |
| 智谱 AI | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-flash` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| Ollama（本地） | `http://localhost:11434/v1` | `qwen2.5:7b` |

### 4.2 统一调用示例

```python
from openai import OpenAI

# 切换 provider 只需改这两个值
client = OpenAI(
    base_url="https://api.siliconflow.cn/v1",   # 换成任意平台
    api_key="你的密钥",
)

resp = client.chat.completions.create(
    model="Qwen/Qwen3-8B",                       # 换成对应模型名
    messages=[
        {"role": "system", "content": "你负责判断剧本行是否为台词。"},
        {"role": "user", "content": "..."},
    ],
)
print(resp.choices[0].message.content)
```

### 4.3 适配层抽象（便于切换）

```python
# app/llm/base.py
class LLMProvider:
    def chat(self, messages: list[dict]) -> str:
        raise NotImplementedError

# app/llm/openai_provider.py
from openai import OpenAI

class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, base_url: str, api_key: str, model: str):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model

    def chat(self, messages: list[dict]) -> str:
        resp = self.client.chat.completions.create(
            model=self.model, messages=messages
        )
        return resp.choices[0].message.content

# app/llm/ollama_provider.py
class OllamaProvider(OpenAICompatibleProvider):
    def __init__(self, model: str = "qwen2.5:7b"):
        super().__init__(
            base_url="http://localhost:11434/v1",
            api_key="ollama",           # Ollama 本地无需真实密钥
            model=model,
        )
```

上层业务代码只依赖 `LLMProvider` 接口，通过配置文件决定使用哪个 provider。

### 4.4 免费 API 使用注意事项

1. **额度与限流**：免费档通常有 RPM/RPD/TPM 限制，批量处理时需做请求节流与重试（遇 429 退避）。
2. **模型下架风险**：免费模型可能随时下架（已有先例），不要硬编码模型名，放入配置。
3. **隐私**：免费 API 可能用你的数据训练，剧本版权敏感内容建议走本地 Ollama。
4. **密钥安全**：密钥放环境变量或本地配置，不提交到代码库。

## 5. 降级与兜底策略

- **台词提取**：规则（中英交替行配对）优先，规则能处理的情况不调用 LLM；LLM 仅在规则无法确定时兜底。
- **LLM 不可用**：若 Ollama 未启动、API 超限或断网，台词提取退化为纯规则模式（对严格「一行中文一行英文」的剧本仍可正常工作），并提示用户。
- **纠错永不依赖 LLM**：保证核心纠错功能在无模型时依然可用。
