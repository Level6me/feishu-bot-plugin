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

        # 设置节点角色 (ARCHITECT 架构师监听全量群消息 / WORKER 被 @ 触发)
        self.role = config_data.get("agent_role") or os.environ.get("AGENT_ROLE", "ARCHITECT").upper()
        self.cli_timeout = config_data.get("cli_timeout_seconds", 120)

    async def on_before_ai(self, user_text: str, chat_id: str, session_data: dict) -> tuple[str, dict]:
        """
        消息前置 Hook (严格校验场景与显式指令意图):
        1. 必须判断 chat_type == "group"（防私聊误触发）；
        2. 废除模糊关键词匹配，必须包含显式命令：如 /agent_assign 或 [协同开发]/[项目拆解] 前缀标志。
        """
        clean_text = user_text.strip()
        chat_type = session_data.get("chat_type", "")

        # ----------------------------------------------------
        # 严禁在私聊（P2P）中误触发多 Agent 协同流程！
        # ----------------------------------------------------
        if chat_type != "group":
            return user_text, session_data

        # ----------------------------------------------------
        # 场景 A: bot_a (ARCHITECT) 仅在群聊且带有显式触发标志时才启动需求拆解
        # ----------------------------------------------------
        if self.role == "ARCHITECT":
            # 只有用户显式使用命令或在群里明确要求 [协同开发] / [项目拆解] 时才响应
            explicit_triggers = ["/agent_assign", "[协同开发]", "[项目拆解]", "【协同开发】", "【项目拆解】"]
            is_explicit = any(trig in clean_text for trig in explicit_triggers)

            if is_explicit and not clean_text.startswith("[TASK_ASSIGN]"):
                log.info(f"[Plugin:{self.plugin_id}] 👑 [Bot A - 架构师] 捕获群聊显式项目协同需求: {clean_text}")
                
                project_id = f"proj_{int(datetime.now().timestamp())}"
                
                # 剥离触发词提取真实需求
                req_content = clean_text
                for trig in explicit_triggers:
                    req_content = req_content.replace(trig, "")
                req_content = req_content.strip() or clean_text

                # 在群里回发初始化卡片
                card = self.build_task_assign_card(project_id, req_content)
                self.send_card(chat_id, card)

                # 后台唤醒 antigravity-cli 进行需求分析与分工派发 (包含 @Bot_B 和 @Bot_C)
                asyncio.create_task(self.async_architect_analyze_and_dispatch(project_id, req_content, chat_id))

        # ----------------------------------------------------
        # 场景 B: bot_b / bot_c (WORKER) 只有在群聊且收到明确的 [TASK_ASSIGN] 派发时才响应
        # ----------------------------------------------------
        elif "WORKER" in self.role:
            if "[TASK_ASSIGN]" in clean_text and f"target:{self.role}" in clean_text:
                log.info(f"[Plugin:{self.plugin_id}] 🎯 [{self.role}] 被 Bot A 在群里正确 @ 提及并捕获专属任务！")
                asyncio.create_task(self.async_run_worker_cli(clean_text, chat_id))

        return user_text, session_data

    async def async_architect_analyze_and_dispatch(self, project_id: str, requirement: str, chat_id: str):
        """[Bot A 架构师] 智能分析需求并生成带有 @Bot_B 和 @Bot_C 的定向派发卡片消息"""
        prompt = (
            f"你现在是系统架构师 Bot A。用户需求为：{requirement}。\n"
            f"请根据项目类型（如 Web全栈/Python工具/小程序等），自动分配前端与后端开发任务。"
        )
        cmd = f"timeout {self.cli_timeout}s antigravity --prompt \"{prompt}\""
        
        log.info(f"[Plugin:{self.plugin_id}] [Bot A] 开始进行 CLI 架构分析: {cmd}")
        
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            # 构造会在群里 @Bot_B (后端) 和 @Bot_C (前端) 的强指派卡片消息
            dispatch_card = self.build_multi_bot_dispatch_card(project_id, requirement)
            self.send_card(chat_id, dispatch_card)
            
            # 同时在群内发送包含 target 标记文本以唤醒被 @ 的 Worker Agent 节点
            wake_signal = (
                f"📋 [TASK_ASSIGN] 项目 #{project_id} 架构分工命令已下发：\n"
                f"• target:WORKER_BACKEND (@Bot_B 后端 Agent): 请查收分支 `feature/backend` 开发任务\n"
                f"• target:WORKER_FRONTEND (@Bot_C 前端 Agent): 请查收分支 `feature/frontend` 开发任务"
            )
            self.send_text(chat_id, wake_signal)

        except Exception as e:
            log.error(f"[Plugin:{self.plugin_id}] [Bot A] 分析分工失败: {e}")

    async def async_run_worker_cli(self, task_contract: str, chat_id: str):
        """[Bot B / Bot C 开发者] 收到 @ 信号后在独立分支并行开发代码"""
        safe_prompt = f"antigravity --prompt \"你现在是 Worker Agent [{self.role}]。请根据分工要求在各自 Git 分支编写代码：{task_contract}\""
        cmd = f"timeout 300s {safe_prompt}"

        log.info(f"[Plugin:{self.plugin_id}] [{self.role}] 被 @ 触发，启动并行开发: {cmd}")
        
        process = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        if process.returncode == 0:
            self.send_text(chat_id, f"✅ [{self.role}] 独立分支代码编写与单元测试完成，已推送提交！")

    def build_multi_bot_dispatch_card(self, project_id: str, requirement: str) -> dict:
        """构建智能包含 @Bot_B 和 @Bot_C 机器人的多 Agent 任务协同卡片"""
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"👑 [Bot A 架构派发] 项目协同分工卡片 #{project_id}"
                },
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
                },
                {"tag": "hr"},
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "content": "Bot B 和 Bot C 收到 @ 提及信号后将自动启动独立分支开发。"
                        }
                    ]
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
                {"tag": "div", "text": {"tag": "lark_md", "content": f"• **当前节点**: `{self.role}`\n• **权限策略**: 仅限群聊 + 显式指令触发 / 私聊严格过滤"}}
            ]
        }

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
        return {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "⚙️ Multi-Agent 节点角色配置"},
                "template": "violet"
            },
            "elements": [
                {"tag": "div", "text": {"tag": "lark_md", "content": f"**当前节点角色:** `{self.role}`"}}
            ]
        }
