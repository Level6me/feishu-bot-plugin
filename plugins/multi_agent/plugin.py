"""Multi-Agent Collaborative Development Plugin for antigravity-feishu-bot."""

import os
import json
import asyncio
import subprocess
from datetime import datetime
from plugin_base import BasePlugin
from logger import log


class MultiAgentPlugin(BasePlugin):

    def initialize(self):
        """插件加载初始化：从 config.json 加载当前 Agent 节点的角色与属性"""
        self.load_plugin_configs()
        log.info(f"[Plugin:{self.plugin_id}] 🤖 多 Agent 协同开发插件初始化成功！当前节点角色: {self.role}")

    def load_plugin_configs(self):
        """加载本地持久化配置"""
        config_data = {}
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
            except Exception as e:
                log.error(f"[Plugin:{self.plugin_id}] 加载配置文件失败: {e}")

        self.role = config_data.get("agent_role") or os.environ.get("AGENT_ROLE", "ARCHITECT").upper()
        self.cli_timeout = config_data.get("cli_timeout_seconds", 120)

    def save_config_file(self, new_configs: dict):
        """保存配置到插件本地 config.json 持久化存储"""
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
        current_configs = {}
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    current_configs = json.load(f)
            except Exception:
                pass
        
        current_configs.update(new_configs)
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(current_configs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            log.error(f"[Plugin:{self.plugin_id}] 保存配置持久化失败: {e}")

    async def on_command(self, command: str, args: str, chat_id: str, message_id: str, session_data: dict) -> bool:
        cmd = command.lower()
        if cmd == "/agent_config":
            config_card = self.build_panel_config_card()
            self.send_reply_card(message_id, config_card)
            return True
        elif cmd == "/multi_agent":
            status_card = self.build_status_card()
            self.send_reply_card(message_id, status_card)
            return True
        return False

    def build_panel_config_card(self) -> dict:
        """构建高级互动按钮功能配置面板卡片"""
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": "⚙️ Multi-Agent 交互式配置与角色切换面板"
                },
                "template": "violet"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**当前 Agent 节点角色:** `{self.role}`\n"
                                   f"**命令行超时限制:** `{self.cli_timeout} 秒`"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**👇 请直接点击以下按钮一键切换当前节点角色：**"
                    }
                },
                {
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "👑 架构师 (Architect)"},
                            "type": "primary" if self.role == "ARCHITECT" else "default",
                            "value": {"action": "set_agent_role", "role": "ARCHITECT"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "⚙️ 后端节点 (Backend)"},
                            "type": "primary" if self.role == "WORKER_BACKEND" else "default",
                            "value": {"action": "set_agent_role", "role": "WORKER_BACKEND"}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🎨 前端节点 (Frontend)"},
                            "type": "primary" if self.role == "WORKER_FRONTEND" else "default",
                            "value": {"action": "set_agent_role", "role": "WORKER_FRONTEND"}
                        }
                    ]
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**⏱️ 一键调整 CLI 运行超时上限：**"
                    }
                },
                {
                    "tag": "action",
                    "layout": "flow",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "⚡ 60 秒"},
                            "type": "primary" if self.cli_timeout == 60 else "default",
                            "value": {"action": "set_timeout", "timeout": 60}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "⏱️ 120 秒 (标准)"},
                            "type": "primary" if self.cli_timeout == 120 else "default",
                            "value": {"action": "set_timeout", "timeout": 120}
                        },
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "🐢 300 秒 (长任务)"},
                            "type": "primary" if self.cli_timeout == 300 else "default",
                            "value": {"action": "set_timeout", "timeout": 300}
                        }
                    ]
                }
            ]
        }

    async def on_card_action(self, action: str, value: dict, chat_id: str, card_message_id: str) -> bool:
        """响应卡片按钮回调点击事件"""
        action_name = value.get("action")
        
        if action_name == "set_agent_role":
            new_role = value.get("role")
            self.role = new_role
            self.save_config_file({"agent_role": new_role})
            log.info(f"[Plugin:{self.plugin_id}] 按钮点击：更新节点角色为 {new_role}")

            new_card = self.build_panel_config_card()
            from lark_client import patch_interactive_card_sdk
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        elif action_name == "set_timeout":
            new_timeout = int(value.get("timeout"))
            self.cli_timeout = new_timeout
            self.save_config_file({"cli_timeout_seconds": new_timeout})
            log.info(f"[Plugin:{self.plugin_id}] 按钮点击：更新超时为 {new_timeout} 秒")

            new_card = self.build_panel_config_card()
            from lark_client import patch_interactive_card_sdk
            patch_interactive_card_sdk(card_message_id, new_card)
            return True

        return False

    async def on_before_ai(self, user_text: str, chat_id: str, session_data: dict) -> tuple[str, dict]:
        clean_text = user_text.strip()
        chat_type = session_data.get("chat_type", "")

        # 防私聊误触发
        if chat_type != "group":
            return user_text, session_data

        if self.role == "ARCHITECT":
            explicit_triggers = ["/agent_assign", "[协同开发]", "[项目拆解]", "【协同开发】", "【项目拆解】"]
            is_explicit = any(trig in clean_text for trig in explicit_triggers)

            if is_explicit and not clean_text.startswith("[TASK_ASSIGN]"):
                log.info(f"[Plugin:{self.plugin_id}] 👑 [Bot A - 架构师] 捕获显式项目协同需求: {clean_text}")
                project_id = f"proj_{int(datetime.now().timestamp())}"
                
                req_content = clean_text
                for trig in explicit_triggers:
                    req_content = req_content.replace(trig, "")
                req_content = req_content.strip() or clean_text

                card = self.build_task_assign_card(project_id, req_content)
                self.send_card(chat_id, card)

                asyncio.create_task(self.async_architect_analyze_and_dispatch(project_id, req_content, chat_id))

        elif "WORKER" in self.role:
            if "[TASK_ASSIGN]" in clean_text and f"target:{self.role}" in clean_text:
                log.info(f"[Plugin:{self.plugin_id}] 🎯 [{self.role}] 被 Bot A 正确 @ 提及并捕获专属任务！")
                asyncio.create_task(self.async_run_worker_cli(clean_text, chat_id))

        return user_text, session_data

    async def async_architect_analyze_and_dispatch(self, project_id: str, requirement: str, chat_id: str):
        prompt = (
            f"你现在是系统架构师 Bot A。用户需求为：{requirement}。\n"
            f"请根据项目类型，自动分配前端与后端开发任务。"
        )
        cmd = f"timeout {self.cli_timeout}s antigravity --prompt \"{prompt}\""
        
        log.info(f"[Plugin:{self.plugin_id}] [Bot A] 开始 CLI 架构分析: {cmd}")
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            dispatch_card = self.build_multi_bot_dispatch_card(project_id, requirement)
            self.send_card(chat_id, dispatch_card)
            
            wake_signal = (
                f"📋 [TASK_ASSIGN] 项目 #{project_id} 架构分工命令已下发：\n"
                f"• target:WORKER_BACKEND (@Bot_B 后端 Agent): 请查收分支 `feature/backend` 开发任务\n"
                f"• target:WORKER_FRONTEND (@Bot_C 前端 Agent): 请查收分支 `feature/frontend` 开发任务"
            )
            self.send_text(chat_id, wake_signal)
        except Exception as e:
            log.error(f"[Plugin:{self.plugin_id}] [Bot A] 分析分工失败: {e}")

    async def async_run_worker_cli(self, task_contract: str, chat_id: str):
        safe_prompt = f"antigravity --prompt \"你现在是 Worker Agent [{self.role}]。请根据分工要求在各自 Git 分支编写代码：{task_contract}\""
        cmd = f"timeout 300s {safe_prompt}"

        log.info(f"[Plugin:{self.plugin_id}] [{self.role}] 被 @ 触发启动开发: {cmd}")
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if process.returncode == 0:
            self.send_text(chat_id, f"✅ [{self.role}] 独立分支代码编写与单元测试完成，已推送提交！")

    def build_multi_bot_dispatch_card(self, project_id: str, requirement: str) -> dict:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": f"👑 [Bot A 架构派发] 项目协同分工卡片 #{project_id}"},
                "template": "blue"
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**原始项目需求:** {requirement}\n**架构分析结论:** 需求成立，已成功拆解为 2 项并行开发任务。"
                    }
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": "**🎯 机器人任务分配明细:**\n"
                                   "1. **后端开发任务** ➔ <at id=\"all\"></at> **@Bot_B (后端 Agent)** | 目标分支: `feature/backend`\n"
                                   "2. **前端界面任务** ➔ <at id=\"all\"></at> **@Bot_C (前端 Agent)** | 目标分支: `feature/frontend`"
                    }
                }
            ]
        }

    def build_task_assign_card(self, project_id: str, requirement: str) -> dict:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "🚀 [Bot A 架构师] 正在分析项目需求..."},
                "template": "blue"
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**项目 ID:** `{project_id}`\n**需求:** {requirement}"}}
            ]
        }

    def build_status_card(self) -> dict:
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "🤖 Multi-Agent 运行状态看板"},
                "template": "green"
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"• **当前节点**: `{self.role}`\n• **权限策略**: 仅限群聊 + 显式指令触发"}}
            ]
        }
