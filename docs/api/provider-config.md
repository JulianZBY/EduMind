# 声明式供应商配置（`providers.json`）

加一家 OpenAI 兼容服务商**不用改代码**：把服务地址与模型清单写进 `backend/providers.json`，
启动时就并进「供应商目录」——设置页「添加供应商」照常列出它、照常拉 `/v1/models`、照常按任务指派。

**Key 一律不写进这个文件**：用 `api_key_env` 指向环境变量（写 `.env`），
或者在设置页「添加供应商」里粘贴（Key 存在供应商实例行上，回读只有掩码）。

## 文件位置与开启方式

| | |
| --- | --- |
| 默认路径 | `backend/providers.json`（与后端进程的启动目录相对；不存在 = 没有扩展） |
| 覆盖路径 | 环境变量 `PROVIDERS_CONFIG=/abs/path/providers.json` |
| 明确关闭 | `PROVIDERS_CONFIG=`（空字符串）——测试与「只想用内置方言」时用 |
| 模板 | `backend/providers.example.json`（复制成 `providers.json` 再改） |

`backend/providers.json` 属于本机配置，已在 `.gitignore` 里（模板进仓库，实例不进）。

## 字段

顶层是数组，或 `{"providers": [...]}`。一条供应商：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | ✅ | 方言 id，小写字母/数字/`._-`；也是 `LLM_PROVIDER` 的取值。**与内置方言同名 = 覆盖内置**（日志会写一行） |
| `label` | ✅ | 面向教师的名称（设置页显示这个） |
| `base_url` | ✅ | 服务地址，必须 `http(s)` 完整地址 |
| `api_key_env` | | Key 从哪个环境变量读（写进 `.env` 更省事；不填就得在设置页粘） |
| `chat_models` | | 对话模型清单；**不填 = 放行任意模型 ID**（与服务商 `/v1/models` 拉取口径一致） |
| `vision_models` | | 其中支持视觉的（设置页据此判断多模态档） |
| `embed_models` | | 向量化模型；声明了就会出现在「能力实现 → 向量化」下拉里 |
| `chat_model` / `vision_model` / `embed_model` | | 默认档；缺省取对应清单的第一个 |
| `embed_dimensions` | | >0 时 embedding 请求携带 `dimensions` |
| `accepts_any_model` | | 缺省：没写 `chat_models` 时为 `true`，写了为 `false` |
| `note` | | 设置页里的一句话说明 |

```json
[
  {
    "id": "my-gateway",
    "label": "我的中转",
    "base_url": "https://api.example.com/v1",
    "api_key_env": "MY_GATEWAY_API_KEY",
    "chat_models": ["chat-pro", "chat-flash"],
    "vision_models": ["chat-pro"],
    "chat_model": "chat-flash",
    "vision_model": "chat-pro",
    "note": "公司中转：对话 + 视觉"
  }
]
```

对应的 `.env` 只加一行 `MY_GATEWAY_API_KEY=<你的 Key>`。

## 两条纪律

1. **坏配置不拖垮应用**：条目非法（缺 `id` / `label` / `base_url`、地址不是 `http(s)`、`id` 重复）
   只跳过并留一条告警；整个文件读不动也只是没有扩展。
   ——与「设置库里的存量值不该成为应用起不来的原因」同一条纪律。
2. **Key 不进配置文件**：文件可以放心进版本库之外的任何同步（Dropbox、笔记），
   因为它只有地址与模型名。

## 生效路径

| 场景 | 怎么用 |
| --- | --- |
| 设置页添加（推荐） | 「设置 → 添加供应商」里选到这家 → 粘 Key → 模型清单自动拉取进统一模型池 |
| 只写 `.env`（legacy） | `.env` 里 `LLM_PROVIDER=my-gateway` + `MY_GATEWAY_API_KEY=...`，不经过设置库 |
| 任务级指派 | 加了实例后，「设置 → 任务级模型」可以只把某档（如「生成」）指到这家 |

改完文件需要**重启后端**（合并发生在进程启动时，与 `.env` 的引导默认同一时机）；
改完设置页的设置不需要重启（写穿即时生效）。

## 模型级能力与手动标注

`GET /settings` 和供应商增改、刷新响应中的 `model_details` 返回模型名、
`capabilities`（`text` / `vision` / `embedding`）与 `source`（`catalog` / `manual` / `unknown`）。
原 `models` 字符串清单保留，现有读取方可以继续使用。视觉模型在目录中同时具备文本能力。

服务商 `/models` 仅返回 ID 时不猜测名称：没有目录声明或手动标注的模型返回空能力清单和 `unknown`。
这不是联通测试，也不代表服务商已经确认支持。手动配置未知模型仍可调用，错误由服务商返回。

通过已有 `PATCH /settings/providers/{instance_id}` 写入实例的手动能力标注：

```json
{
  "model_capabilities": {
    "my-vision-model": ["text", "vision"],
    "my-embed-model": ["embedding"]
  }
}
```

只更新传入的模型；模型对应 `null` 移除手动覆盖，空列表标为未知。非法能力值返回 422，整次更新不落库。
手动标注在实例上持久保存，刷新模型清单和重启后不会丢失。旧库启动时幂等补列，保留实例、Key 和模型记录。
设置页的能力徽标和编辑控件尚待接入；本轮只交付后端能力与生成的接口类型。

模型路由按能力检查：已知向量化模型不会发往对话接口，已知文本模型不会发往视觉接口；
选择了支持视觉的模型时，图片请求使用所选模型，显式 `llm_vision_model` 优先。
未显式选模型时仍沿用原先的默认视觉档。向量化依旧单独配置，不随对话实例切换，避免隐式更改资料索引。

`api_key_env` 与 `PROVIDERS_CONFIG` 同时支持进程环境变量和后端 `.env`；进程变量优先，
显式空字符串可关闭配置。配置文件的全部视觉与向量化模型、`accepts_any_model` 策略均保留；
覆盖内置供应商时不会偷偷拼回原先的模型名。
