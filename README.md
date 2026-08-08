# 🧩 Antigravity Feishu Bot 插件开发规范与商店仓库

欢迎来到 **Antigravity Feishu Bot 官方插件仓库 (Plugin Store)**！

本项目为基于微内核架构的飞书机器人提供扩展插件的集中式维护、在线探索与一键下载/热更新支持。开发者可以通过本仓库提交新插件，实现零耦合的功能扩展。

---

## 📂 插件目录与文件规范

每个独立插件必须在仓库根目录下的 `plugins/` 目录中建立属于自己的**同名独立文件夹**（文件夹名即为 `plugin_id`），并至少包含以下三大核心文件：

```text
feishu-bot-plugin/
└── plugins/
    └── <plugin_id>/             # 插件目录（必须与 manifest.json 中的 id 完全一致）
        ├── manifest.json        # 【必须】插件元数据声明配置文件
        ├── plugin.py            # 【必须】插件主逻辑实现（必须继承 BasePlugin）
        ├── README.md            # 【必须】详细的插件功能使用与安装说明书
        └── requirements.txt     # 【可选】插件依赖的第三方 Pip 扩展包
```

---

## 📝 1. `manifest.json` 规范定义

`manifest.json` 是插件的身份识别清单，必须遵循以下标准 JSON 格式：

```json
{
  "id": "server_health",
  "name": "🖥️ 服务器巡检与健康报告",
  "version": "1.0.0",
  "author": "Antigravity",
  "description": "监控服务器 CPU 负载、内存率、磁盘余量，发送 /sysinfo 即可查看交互卡片",
  "commands": [
    "/sysinfo",
    "/health"
  ],
  "enabled": true
}
```

### 字段说明表：
| 字段 Key | 类型 | 是否必填 | 规范说明 |
| :--- | :--- | :--- | :--- |
| `id` | `String` | **是** | 插件唯一标识符，全小写字母+下划线，必须与目录名保持完全一致（如 `server_health`） |
| `name` | `String` | **是** | 插件在飞书卡片中展示的友好名称（建议附带 Emoji 图标） |
| `version` | `String` | **是** | 语义化版本号，如 `1.0.0`、`2.0.0` |
| `author` | `String` | **是** | 插件作者或团队名称 |
| `description` | `String` | **是** | 插件功能简短介绍，展示于插件商店列表中 |
| `commands` | `Array` | **是** | 插件注册的斜杠指令列表，系统会自动完成动态注册（如 `["/sysinfo", "/health"]`） |
| `enabled` | `Boolean` | **是** | 默认启用状态，设为 `true` |

---

## ⚙️ 2. `plugin.py` 逻辑开发接口规范

插件的核心类必须继承自 `BasePlugin`（系统自动注入基础上下文），并根据需要实现相应的异步生命周期 Hook 方法：

```python
import asyncio
from plugin_base import BasePlugin
from lark_client import send_reply_sdk
from logger import log

class MyCustomPlugin(BasePlugin):

    def initialize(self):
        """【可选】插件加载时触发的初始化 Hook"""
        log.info(f"[Plugin:{self.plugin_id}] 插件初始化成功！")

    async def on_command(self, command: str, args: str, chat_id: str, message_id: str, session_data: dict) -> bool:
        """【核心】响应插件注册的斜杠指令
        - Return True: 表示指令已成功处理，拦截后续默认 AI 响应
        - Return False: 放弃拦截，放行至下层流程
        """
        if command.lower() == "/mycmd":
            self.send_reply_text(message_id, "Hello from MyCustomPlugin!")
            return True
        return False

    async def on_before_ai(self, user_text: str, chat_id: str, session_data: dict) -> tuple[str, dict]:
        """【AI 管道前置 Hook】在用户消息发送给大模型前触发
        可修改 user_text 或给 session_data 注入额外上下文 Prompt
        """
        return user_text, session_data

    async def on_after_ai(self, ai_response_text: str, chat_id: str, session_data: dict) -> str:
        """【AI 管道后置 Hook】在大模型生成回复后、发送给飞书前触发
        可对 AI 返回文本进行后置替换或二次修饰
        """
        return ai_response_text

    async def on_card_action(self, action: str, value: dict, chat_id: str, card_message_id: str) -> bool:
        """【卡片按钮回调 Hook】处理飞书交互卡片中按钮的点击事件
        - Return True: 表示已响应该按钮动作
        """
        return False

    async def on_cron(self):
        """【定时巡检 Hook】由后台 Cron 定时触发"""
        pass
```

### 💡 内置工具方法 (BasePlugin 自带)：
- `self.send_text(chat_id, text)`：向指定会话发送文本消息
- `self.send_reply_text(message_id, text)`：引用回复某条消息
- `self.send_card(chat_id, card_dict)`：向指定会话发送飞书交互卡片
- `self.send_reply_card(message_id, card_dict)`：引用回复飞书交互卡片

---

## 🌟 官方精选插件索引

| 插件名称 | 插件 ID | 版本 | 注册指令 | README 详细文档 |
| :--- | :--- | :--- | :--- | :--- |
| **🖥️ 服务器巡检与健康报告** | `server_health` | `v1.0.0` | `/sysinfo`, `/health` | [查看说明文档](plugins/server_health/README.md) |
| **⏱️ 计划任务与定时调度** | `cron_scheduler` | `v2.0.0` | `/cron`, `/schedule` | [查看说明文档](plugins/cron_scheduler/README.md) |
| **🧠 AI 长期记忆管理** | `ai_memory` | `v2.0.0` | `/memory` | [查看说明文档](plugins/ai_memory/README.md) |
| **📝 备忘录与随手记** | `notes_manager` | `v2.0.0` | `/note`, `/notes` | [查看说明文档](plugins/notes_manager/README.md) |
| **🔄 系统在线热更新** | `system_updater` | `v2.0.0` | `/update` | [查看说明文档](plugins/system_updater/README.md) |

---

## 🚀 提交新插件的流程

1. Fork 本仓库并克隆到本地；
2. 在 `plugins/` 目录下新建您的插件文件夹 `plugins/<your_plugin_id>/`；
3. 按照规范编写 `manifest.json`、`plugin.py` 以及详细的 `README.md`；
4. 提交 Pull Request，通过审核后即可在飞书机器人的 `/plugin` 商店中在线一键扫码安装！
