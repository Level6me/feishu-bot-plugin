"""Clean Area-Status Dashboard Feishu Card Builder for Home Assistant.

Focuses entirely on glanceable, real-time area status monitoring:
1. Whole-home metrics overview (lights on/total, switches on/total, climate, indoor avg temp & humidity).
2. Jev System 1 semantic intent router switch & status diagnostics.
3. Multi-area structured grid (dual-column balanced layout with clean area cards).
4. Drill-down area detail view with pure status indicators (Zero control toggle buttons).
5. Fast interactive card-based refreshing and diagnostics.
"""

from typing import List, Dict, Any, Optional


def build_dashboard_card(
    areas: List[Dict[str, Any]],
    current_area_id: str,
    devices: List[Dict[str, Any]],
    summary_stats: Dict[str, Any],
    alert_text: Optional[str] = None,
    jev_status: Optional[Dict[str, Any]] = None
) -> dict:
    """Builds a glanceable, clean, pure status monitoring dashboard card without control buttons."""
    try:
        try:
            from ha_client import ha_client
        except ImportError:
            from .ha_client import ha_client
        all_status = ha_client.get_all_areas_status()
    except Exception:
        all_status = {"whole_home": {}, "areas": {}}

    wh = all_status.get("whole_home", {})
    area_map = all_status.get("areas", {})

    l_on = wh.get("lights_on", summary_stats.get("total_on", 0))
    l_tot = wh.get("lights_total", summary_stats.get("total", len(devices)))
    s_on = wh.get("switches_on", 0)
    s_tot = wh.get("switches_total", 0)
    c_act = wh.get("climates_active", 0)
    c_tot = wh.get("climates_total", 0)
    avg_t = wh.get("avg_temp")
    avg_h = wh.get("avg_humidity")

    elements = []

    # 1. Whole-Home Metric Indicators
    l_badge = f"<font color='green'>● 开启 {l_on} 盏</font> / 共 {l_tot} 盏" if l_on > 0 else f"<font color='grey'>○ 全部关闭 ({l_tot} 盏)</font>"
    s_badge = f"<font color='green'>● 通电 {s_on} 处</font> / 共 {s_tot} 处" if s_on > 0 else f"<font color='grey'>○ 全部断电 ({s_tot} 处)</font>"
    c_badge = f"<font color='blue'>● 运行 {c_act} 台</font> / 共 {c_tot} 台" if c_act > 0 else f"<font color='grey'>○ 全部待机 ({c_tot} 台)</font>"
    
    env_str = ""
    if avg_t is not None and avg_h is not None:
        env_str = f"  |  🌡️ 室内均温 **{avg_t}°C** (湿度 **{avg_h}%**)"
    elif avg_t is not None:
        env_str = f"  |  🌡️ 室内均温 **{avg_t}°C**"

    status_summary = (
        f"**📊 全屋实时状态总览**\n"
        f"• 💡 **照明系统**：{l_badge}\n"
        f"• 🔌 **电器插座**：{s_badge}\n"
        f"• ❄️ **暖通空调**：{c_badge}{env_str}"
    )
    if alert_text:
        status_summary += f"\n> 💡 {alert_text}"

    elements.append({
        "tag": "div",
        "text": {
            "tag": "lark_md",
            "content": status_summary
        }
    })

    # 2. Jev System 1 Routing Switch & Diagnostics
    if jev_status is None:
        try:
            try:
                from ha_client import ha_client
            except ImportError:
                from .ha_client import ha_client
            has_token, reason = ha_client.check_jev_token_status()
            is_on = ha_client.is_jev_enabled()
            jev_status = {
                "has_token": has_token,
                "enabled": is_on,
                "reason": reason
            }
        except Exception:
            jev_status = {"has_token": False, "enabled": False, "reason": "无法读取状态"}

    has_token = jev_status.get("has_token", False)
    is_jev_on = jev_status.get("enabled", False)

    if not has_token:
        # 未在 /s1 中配置 Token：灰色禁用
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "🤖 **Jev 秒级意图分发**：<font color='grey'>不可用</font>\n> ⚠️ **Jev 未配置正确**：检测到 `/s1` 未配置 TypeSafe API Token，秒级意图路由已停用。请先发送 `/s1` 完成配置。"
            },
            "extra": {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🚫 未配置Token"},
                "type": "default",
                "disabled": True,
                "value": {"action": "ha_toggle_jev_disabled", "area_id": current_area_id}
            }
        })
    elif is_jev_on:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "🤖 **Jev 秒级意图分发**：<font color='green'>● 已开启</font>（极速口语调度 ~200ms）\n> 💬 **语音调控**：本看板专用于状态查看；如需开关设备，直接发口语给机器人（如“开客厅灯”）即可秒级调度。"
            },
            "extra": {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🟢 关闭 Jev"},
                "type": "primary",
                "disabled": False,
                "value": {"action": "ha_toggle_jev", "target_state": False, "area_id": current_area_id}
            }
        })
    else:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "🤖 **Jev 秒级意图分发**：<font color='grey'>○ 已关闭</font>\n> 💤 **普通模式**：Jev 意图直通已关闭，所有口语指令将交由大模型规划。"
            },
            "extra": {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "⚪ 开启 Jev"},
                "type": "default",
                "disabled": False,
                "value": {"action": "ha_toggle_jev", "target_state": True, "area_id": current_area_id}
            }
        })

    elements.append({"tag": "hr"})

    # 3. Area Navigation Tabs
    area_buttons = []
    all_btn_type = "primary" if current_area_id == "all" else "default"
    area_buttons.append({
        "tag": "button",
        "text": {"tag": "plain_text", "content": "🏠 全屋"},
        "type": all_btn_type,
        "value": {"action": "ha_switch_area", "area_id": "all"}
    })

    # Prioritize active areas
    area_priority = ["ke_ting", "zhu_wo", "xuan_guan", "can_ting", "chu_fang", "yuan_zi", "wo_shi"]
    rendered_aids = set()
    for aid in area_priority:
        matching = [a for a in areas if a["id"] == aid]
        if matching:
            a = matching[0]
            rendered_aids.add(aid)
            btn_type = "primary" if current_area_id == aid else "default"
            area_buttons.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": a["name"]},
                "type": btn_type,
                "value": {"action": "ha_switch_area", "area_id": aid}
            })

    if current_area_id not in rendered_aids and current_area_id != "all":
        cur_obj = next((a for a in areas if a["id"] == current_area_id), None)
        if cur_obj:
            area_buttons.append({
                "tag": "button",
                "text": {"tag": "plain_text", "content": cur_obj["name"]},
                "type": "primary",
                "value": {"action": "ha_switch_area", "area_id": current_area_id}
            })

    elements.append({
        "tag": "action",
        "layout": "flow",
        "actions": area_buttons
    })
    elements.append({"tag": "hr"})

    # 4. Content Area
    if current_area_id == "all":
        # VIEW A: Whole-Home Area Matrix (Dual Column Grid)
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "**📍 各区域实时监控矩阵**"
            }
        })

        # Pre-format each area's status block
        area_blocks = []
        area_display_order = [
            ("ke_ting", "🛋️ 客厅"),
            ("zhu_wo", "🛏️ 主卧"),
            ("xuan_guan", "🚶 走廊"),
            ("can_ting", "🍽️ 餐厅"),
            ("chu_fang", "🍳 厨房"),
            ("wo_shi", "🛌 卧室"),
            ("ru_hu_xuan_guan", "🚪 入户玄关"),
            ("yuan_zi", "🌳 院子"),
            ("yang_tai", "🌿 阳台"),
            ("dian_nao", "🖥️ 电脑"),
            ("ci_wo", "👶 次卧")
        ]

        for aid, title in area_display_order:
            ad = area_map.get(aid)
            if not ad:
                continue
            
            # Format area status lines
            lines = [f"**{title}**"]
            
            # 1. Lighting
            ltot = ad["lights_total"]
            lon = ad["lights_on"]
            if ltot > 0:
                if lon > 0:
                    lines.append(f"• 💡 照明：<font color='green'>● 开启 {lon} 盏</font> / {ltot}")
                else:
                    lines.append(f"• 💡 照明：<font color='grey'>○ 全关</font> ({ltot} 盏)")

            # 2. Switches
            stot = ad["switches_total"]
            son = ad["switches_on"]
            if stot > 0:
                if son > 0:
                    lines.append(f"• 🔌 电器：<font color='green'>● 通电 {son} 处</font> / {stot}")
                else:
                    lines.append(f"• 🔌 电器：<font color='grey'>○ 断电</font> ({stot} 处)")

            # 3. Climate
            if ad["climates"]:
                c_desc = ad["climates"][0]
                c_color = "green" if "制" in c_desc or "heat" in c_desc or "cool" in c_desc else "blue"
                lines.append(f"• ❄️ 空调：<font color='{c_color}'>● {c_desc}</font>")

            # 4. Temperature / Humidity
            t_str = f"{ad['temps'][0]}°C" if ad["temps"] else ""
            h_str = f"{int(ad['humidity'][0])}%" if ad["humidity"] else ""
            if t_str and h_str:
                lines.append(f"• 🌡️ 环境：{t_str} | 💧 {h_str}")
            elif t_str:
                lines.append(f"• 🌡️ 气温：{t_str}")
            elif h_str:
                lines.append(f"• 💧 湿度：{h_str}")

            if len(lines) > 1:
                area_blocks.append("\n".join(lines))

        # Render area cards into pairs (2-column layout)
        for i in range(0, len(area_blocks), 2):
            left_content = area_blocks[i]
            right_content = area_blocks[i + 1] if i + 1 < len(area_blocks) else ""

            cols = [
                {
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": left_content
                        }
                    ]
                }
            ]
            if right_content:
                cols.append({
                    "tag": "column",
                    "width": "weighted",
                    "weight": 1,
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": right_content
                        }
                    ]
                })

            elements.append({
                "tag": "column_set",
                "flex_mode": "none",
                "background_style": "default",
                "columns": cols
            })

    else:
        # VIEW B: Single Area Detailed Status (Zero control buttons)
        cur_area_obj = next((a for a in areas if a["id"] == current_area_id), None)
        cur_area_name = cur_area_obj["name"] if cur_area_obj else current_area_id
        
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**📍 【{cur_area_name}】各设备与传感器当前状态明细**"
            }
        })

        if not devices:
            elements.append({
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": "✨ *该区域当前没有受管设备或传感器。*"
                }
            })
        else:
            # Render devices with pure status indicators (NO toggle button in extra!)
            rows = []
            for d in devices[:16]:
                eid = d.get("entity_id", "")
                dname = d.get("name", eid)
                domain = d.get("domain", "")
                state = str(d.get("state", "off")).lower()
                attrs = d.get("attributes", {})

                if domain == "light":
                    icon = "💡"
                    is_active = (state == "on")
                    status_str = "<font color='green'>● 开启</font>" if is_active else "<font color='grey'>○ 关闭</font>"
                elif domain == "switch":
                    icon = "🔌"
                    is_active = (state == "on")
                    status_str = "<font color='green'>● 通电运行</font>" if is_active else "<font color='grey'>○ 断电待机</font>"
                elif domain == "climate":
                    icon = "❄️"
                    temp = attrs.get("current_temperature") or attrs.get("temperature")
                    t_info = f" ({temp}°C)" if temp else ""
                    is_active = (state not in ["off", "unavailable", "idle"])
                    status_str = f"<font color='blue'>● {state}{t_info}</font>" if is_active else f"<font color='grey'>○ 待机{t_info}</font>"
                elif domain == "sensor":
                    icon = "🌡️"
                    unit = attrs.get("unit_of_measurement", "")
                    status_str = f"**{state} {unit}**".strip()
                elif domain == "binary_sensor":
                    icon = "🚨" if "motion" in eid or "door" in eid else "⚙️"
                    is_active = (state == "on")
                    status_str = "<font color='orange'>● 触发/检测到</font>" if is_active else "<font color='grey'>○ 正常/静止</font>"
                elif domain == "media_player":
                    icon = "📺"
                    is_active = (state in ["playing", "on"])
                    status_str = "<font color='green'>● 播放运行中</font>" if is_active else "<font color='grey'>○ 关机待机</font>"
                else:
                    icon = "⚙️"
                    status_str = state

                rows.append(f"{icon} **{dname}**：{status_str}")

            # Pair details into dual columns for clean readability
            for i in range(0, len(rows), 2):
                c_left = rows[i]
                c_right = rows[i + 1] if i + 1 < len(rows) else ""
                cols = [
                    {
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [{"tag": "markdown", "content": c_left}]
                    }
                ]
                if c_right:
                    cols.append({
                        "tag": "column",
                        "width": "weighted",
                        "weight": 1,
                        "elements": [{"tag": "markdown", "content": c_right}]
                    })
                elements.append({
                    "tag": "column_set",
                    "flex_mode": "none",
                    "background_style": "default",
                    "columns": cols
                })

    # 5. Bottom Controls (Zero device control buttons)
    elements.append({"tag": "hr"})
    elements.append({
        "tag": "action",
        "layout": "flow",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🔄 刷新实时状态"},
                "type": "primary",
                "value": {"action": "ha_refresh", "area_id": current_area_id}
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "⚙️ 连通与诊断"},
                "type": "default",
                "value": {"action": "ha_open_setup"}
            }
        ]
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "🏠 Home Assistant 全屋各区域状态监控"},
            "template": "turquoise"
        },
        "elements": elements
    }


def build_setup_card(
    config: Dict[str, Any],
    test_result: Optional[str] = None,
    alert_msg: Optional[str] = None
) -> dict:
    """Builds the interactive setup and diagnostics card for Home Assistant."""
    ha_url = config.get("ha_url", "http://10.0.0.2:8123")
    has_token = bool(config.get("ha_token"))
    wh = config.get("webhook_url", "")

    token_display = "已绑定 (********)" if has_token else "未绑定 (请配置)"
    wh_display = wh if wh else "未设置"

    elements = [
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**⚙️ Home Assistant 接入与状态诊断**\n\n"
                           f"• **服务地址 (URL)**：`{ha_url}`\n"
                           f"• **访问凭据 (Token)**：{token_display}\n"
                           f"• **局域网 Webhook**：`{wh_display}`"
            }
        }
    ]

    if alert_msg:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"> 🔔 **提示**：{alert_msg}"
            }
        })

    if test_result:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"> 🩺 **连通测试结果**：{test_result}"
            }
        })

    elements.append({"tag": "hr"})
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🩺 测试服务连通性"},
                "type": "primary",
                "value": {"action": "ha_test_conn"}
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "🔄 全量同步硬件状态"},
                "type": "default",
                "value": {"action": "ha_sync_devices"}
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "⬅️ 返回状态监控看板"},
                "type": "default",
                "value": {"action": "ha_back_dashboard"}
            }
        ]
    })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {"tag": "plain_text", "content": "⚙️ Home Assistant 服务诊断"},
            "template": "blue"
        },
        "elements": elements
    }
