"""
FoloToy AI Passport 飞书机器人桥接插件 (PassportBridgePlugin)
"""

import os
import sys
import json
import asyncio
from typing import Optional

from plugin_base import BasePlugin
from logger import log
from lark_client import send_interactive_card_sdk, send_reply_sdk

_plugin_dir = os.path.dirname(os.path.abspath(__file__))
if _plugin_dir not in sys.path:
    sys.path.insert(0, _plugin_dir)

from ws_server import PassportServer


class PassportBridgePlugin(BasePlugin):

    def initialize(self):
        """插件初始化，加载配置并启动局域网异步服务端"""
        self.config_data = self.get_config() or {}
        self.enabled = self.config_data.get("enabled", True)
        if not self.enabled:
            log.info(f"[Plugin:{self.plugin_id}] 插件已在配置中禁用。")
            return

        host = self.config_data.get("server_host", "0.0.0.0")
        port = int(self.config_data.get("server_port", 8765))
        udp_port = int(self.config_data.get("udp_discovery_port", 8765))

        self.server = PassportServer(host=host, port=port, udp_port=udp_port, plugin=self)
        
        # 将服务端挂载到当前主 asyncio 事件循环中
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self.server.start())
            log.info(f"[Plugin:{self.plugin_id}] 局域网服务初始化成功，监听端口: {port}")
        except RuntimeError:
            log.warning(f"[Plugin:{self.plugin_id}] 当前未在异步主事件循环中，延后启动。")

    def get_config(self) -> dict:
        cfg_path = os.path.join(self.plugin_dir, "config.json")
        if os.path.exists(cfg_path):
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self, cfg: dict):
        cfg_path = os.path.join(self.plugin_dir, "config.json")
        try:
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=2, ensure_ascii=False)
            self.config_data = cfg
        except Exception as e:
            log.error(f"[Plugin:{self.plugin_id}] 保存配置失败: {e}")

    async def on_command(self, command: str, args: str, chat_id: str, message_id: str, session_data: dict) -> bool:
        """响应 /passport 与 /hardware 指令"""
        if command not in ["/passport", "/hardware"]:
            return False

        sub_cmd = args.strip().split()[0] if args.strip() else "status"
        sub_args = args.strip()[len(sub_cmd):].strip() if args.strip() else ""

        if sub_cmd in ["status", "info"]:
            await self._reply_status_card(message_id, chat_id)
            return True

        elif sub_cmd == "bind":
            # 绑定当前会话为语音消息主通道
            cfg = self.get_config()
            cfg["bound_chat_id"] = chat_id
            self.save_config(cfg)
            send_reply_sdk(message_id, f"✅ **成功绑定当前飞书会话！**\n\n后续 AI Passport 硬件端按键输入的语音和提问将实时推送到本会话中。")
            return True

        elif sub_cmd == "alert":
            # 向硬件推送测试弹窗
            alert_text = sub_args or "飞书端下发的测试通知！"
            if hasattr(self, "server") and self.server:
                await self.server.broadcast_alert("飞书通知", alert_text, level="warning", duration_sec=5)
                send_reply_sdk(message_id, f"🚨 **已向所有连接的 AI Passport 硬件推送弹窗告警**：\n> {alert_text}")
            else:
                send_reply_sdk(message_id, "⚠️ 硬件网关服务未启动，无法推送。")
            return True

        elif sub_cmd in ["help", "man"]:
            help_card = {
                "config": {"wide_screen_mode": True},
                "header": {
                    "template": "indigo",
                    "title": {"content": "📟 FoloToy AI Passport 硬件网关指令指南", "tag": "plain_text"}
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": (
                            "**支持的指令用法**：\n\n"
                            "• `/passport status`：查看硬件网关运行状态、已连接设备数与端口\n"
                            "• `/passport bind`：将硬件语音消息绑定推送到当前会话\n"
                            "• `/passport alert <文本>`：向硬件屏幕主动推送紧急告警/通知弹窗\n"
                            "• `/passport help`：显示本帮助说明\n\n"
                            "> 💡 *硬件开机连入同一 Wi-Fi 后会自动发现并接入本机。*"
                        )
                    }
                ]
            }
            send_interactive_card_sdk(message_id, help_card)
            return True

        return False

    async def _reply_status_card(self, message_id: str, chat_id: str):
        """生成并回复硬件网关运行状态卡片"""
        clients_count = len(self.server.active_websockets) if hasattr(self, "server") and self.server else 0
        cfg = self.get_config()
        port = cfg.get("server_port", 8765)
        bound = cfg.get("bound_chat_id", "")
        bound_status = "✅ 已绑定当前会话" if bound == chat_id else ("✅ 已绑定指定会话" if bound else "⚠️ 未绑定 (默认首个活跃会话)")

        status_card = {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue" if clients_count > 0 else "orange",
                "title": {"content": "📟 FoloToy AI Passport 硬件网关状态", "tag": "plain_text"}
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": (
                        f"**网关服务运行状态**：\n"
                        f"• 🌐 **内网监听端口**：`0.0.0.0:{port}` (WebSocket & UDP 发现)\n"
                        f"• 📡 **已连接硬件数**：**{clients_count}** 台在线设备\n"
                        f"• 💬 **飞书消息绑定**：{bound_status}\n"
                        f"• 🎙️ **语音 ASR 引擎**：本地 Whisper 极速语音识别\n"
                        f"• 🔊 **TTS 语音合成**：edge-tts (`{cfg.get('tts_voice', 'zh-CN-XiaoxiaoNeural')}`)\n\n"
                        f"> 💡 提示：在硬件端长按 **OK 键** 说话，飞书会话将实时同步语音卡片！"
                    )
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📌 绑定至当前会话"},
                            "type": "primary",
                            "value": {"action": "bind_passport", "chat_id": chat_id}
                        }
                    ]
                }
            ]
        }
        send_interactive_card_sdk(message_id, status_card)

    async def on_before_ai(self, user_text: str, chat_id: str, session_data: dict) -> tuple[str, dict]:
        """AI 思考前钩子：向硬件广播思考动画状态"""
        if hasattr(self, "server") and self.server and self.server.active_websockets:
            asyncio.create_task(self.server.broadcast_ai_state("thinking", "思考中..."))
        return user_text, session_data

    async def on_tool_call(self, tool_name: str, tool_args: dict):
        """工具调用钩子：向硬件广播当前正在执行的工具"""
        if hasattr(self, "server") and self.server and self.server.active_websockets:
            asyncio.create_task(self.server.broadcast_ai_state("tool_running", f"工具: {tool_name}"))

    async def on_after_ai(self, ai_response_text: str, chat_id: str, session_data: dict) -> str:
        """AI 答复后钩子：更新硬件状态"""
        if hasattr(self, "server") and self.server and self.server.active_websockets:
            asyncio.create_task(self.server.broadcast_ai_state("idle", "已完成"))
        return ai_response_text

    def on_service_restarting(self):
        """服务停止/重启时释放网络资源"""
        if hasattr(self, "server") and self.server:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.server.stop())
            except Exception:
                pass
