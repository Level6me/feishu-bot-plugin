#include "display_ui.h"

DisplayUI ui;

DisplayUI::DisplayUI() 
    : currentState(UI_STATE_BOOT),
      currentProject("antigravity-bot"),
      currentTimeStr("--:--:--"),
      currentStatus("CONNECTING"),
      subtitleText(""),
      alertTitle(""),
      alertContent(""),
      alertLevel("info"),
      dashboardPage(0),
      alertStartTime(0),
      lastAnimTime(0),
      lastActivityTime(0),
      currentBrightness(200),
      targetBrightness(200),
      animFrame(0) {}

void DisplayUI::init() {
    lcd.init();
    lcd.setRotation(0); // 竖屏 240x320
    lcd.setBrightness(200);
    lcd.fillScreen(0x101018); // 深空蓝黑底色
    lastActivityTime = millis();
    setState(UI_STATE_CONNECTING);
}

void DisplayUI::notifyActivity() {
    lastActivityTime = millis();
    targetBrightness = 200;
}

void DisplayUI::nextDashboardPage() {
    notifyActivity();
    dashboardPage = (dashboardPage + 1) % 3;
    if (currentState == UI_STATE_DASHBOARD) {
        renderDashboard();
    }
}

void DisplayUI::prevDashboardPage() {
    notifyActivity();
    dashboardPage = (dashboardPage + 2) % 3;
    if (currentState == UI_STATE_DASHBOARD) {
        renderDashboard();
    }
}

void DisplayUI::setState(UiState state) {
    notifyActivity();
    if (currentState == state && state != UI_STATE_DASHBOARD) return;
    currentState = state;
    lcd.fillScreen(0x101018);
    
    switch (currentState) {
        case UI_STATE_CONNECTING: renderConnecting(); break;
        case UI_STATE_DASHBOARD:  renderDashboard();  break;
        case UI_STATE_LISTENING:  renderListening();  break;
        case UI_STATE_THINKING:   renderThinking();   break;
        case UI_STATE_SPEAKING:   renderSpeaking();   break;
        case UI_STATE_ALERT:      renderAlert();      break;
        default: break;
    }
}

void DisplayUI::updateDashboard(const String& project, const String& time_str, int clients, const String& status) {
    currentProject = project;
    currentTimeStr = time_str;
    currentStatus = status;
    if (currentState == UI_STATE_DASHBOARD) {
        renderDashboard();
    }
}

void DisplayUI::setThinkingText(const String& text) {
    notifyActivity();
    subtitleText = text;
    if (currentState == UI_STATE_THINKING) {
        renderThinking();
    }
}

void DisplayUI::setSpeakingText(const String& text) {
    notifyActivity();
    subtitleText = text;
    if (currentState == UI_STATE_SPEAKING) {
        renderSpeaking();
    }
}

void DisplayUI::showAlert(const String& title, const String& content, const String& level) {
    notifyActivity();
    alertTitle = title;
    alertContent = content;
    alertLevel = level;
    alertStartTime = millis();
    setState(UI_STATE_ALERT);
}

// 顶部全功能状态栏：包含飞书在线标志、时钟、Wi-Fi 信号格以及 CW2017 电池电量计
void DisplayUI::renderStatusBar() {
    lcd.fillRect(0, 0, 240, 26, 0x181825);
    
    // 1. 左侧：飞书在线绿点
    lcd.fillCircle(12, 13, 4, 0x00E676);
    lcd.setTextSize(1);
    lcd.setTextColor(0x9ECE6A, 0x181825);
    lcd.setTextDatum(ML_DATUM);
    lcd.drawString("LINK", 22, 13);

    // 2. 中间：时间字符串
    lcd.setTextColor(0xFFFFFF, 0x181825);
    lcd.setTextDatum(MC_DATUM);
    lcd.drawString(currentTimeStr, 110, 13);

    // 3. 右侧：Wi-Fi RSSI 信号格 (4 阶梯条)
    int rssi = WiFi.RSSI();
    bool wifiOk = (WiFi.status() == WL_CONNECTED);
    int bars = 0;
    if (wifiOk) {
        if (rssi >= -60) bars = 4;
        else if (rssi >= -72) bars = 3;
        else if (rssi >= -85) bars = 2;
        else bars = 1;
    }
    int wifiX = 160;
    for (int b = 1; b <= 4; b++) {
        int barH = b * 3;
        uint16_t c = (b <= bars) ? 0x00E5FF : 0x383C4A;
        lcd.fillRect(wifiX + (b * 4), 18 - barH, 3, barH, c);
    }

    // 4. 右侧：CW2017 电池电量图标与百分比
    uint8_t pct = battery.getPercent();
    bool charging = battery.isCharging();
    int batX = 188;
    int batY = 6;
    lcd.drawRoundRect(batX, batY, 26, 14, 2, 0x7AA2F7);
    lcd.fillRect(batX + 26, batY + 3, 2, 8, 0x7AA2F7); // 电池正极极柱
    
    int fillW = map(constrain(pct, 0, 100), 0, 100, 0, 22);
    uint16_t batColor = (pct > 40) ? 0x00E676 : ((pct > 15) ? 0xFFD600 : 0xFF5252);
    if (fillW > 0) {
        lcd.fillRect(batX + 2, batY + 2, fillW, 10, batColor);
    }
    
    // 电池内部或前方提示
    lcd.setTextDatum(MR_DATUM);
    lcd.setTextSize(1);
    if (charging) {
        lcd.setTextColor(0xFFD600, 0x181825);
        lcd.drawString("CHG", batX - 2, 13);
    } else {
        lcd.setTextColor(0xCAD3F5, 0x181825);
        lcd.drawString(String(pct) + "%", batX - 2, 13);
    }
}

// 灵动拟人化表情头像 (Avatar Face)
void DisplayUI::renderAvatarFace(int cx, int cy, const char* mood) {
    // 头部圆角卡片底衬
    lcd.fillRoundRect(cx - 50, cy - 35, 100, 70, 16, 0x1F2335);
    lcd.drawRoundRect(cx - 50, cy - 35, 100, 70, 16, 0x3B4261);

    bool blink = (animFrame % 60 >= 56);

    if (strcmp(mood, "idle") == 0) {
        // 呆萌大眼睛 (支持定时眨眼)
        if (blink) {
            lcd.fillRect(cx - 28, cy - 2, 18, 4, 0x00E5FF);
            lcd.fillRect(cx + 10, cy - 2, 18, 4, 0x00E5FF);
        } else {
            lcd.fillRoundRect(cx - 28, cy - 14, 18, 28, 8, 0x00E5FF);
            lcd.fillRoundRect(cx + 10, cy - 14, 18, 28, 8, 0x00E5FF);
            // 瞳孔反光点
            lcd.fillCircle(cx - 24, cy - 8, 3, 0xFFFFFF);
            lcd.fillCircle(cx + 14, cy - 8, 3, 0xFFFFFF);
        }
    } else if (strcmp(mood, "listening") == 0) {
        // 聆听状态：专注大眼 + 灵动发光
        lcd.fillRoundRect(cx - 30, cy - 16, 20, 32, 9, 0x00E5FF);
        lcd.fillRoundRect(cx + 10, cy - 16, 20, 32, 9, 0x00E5FF);
        lcd.fillCircle(cx - 20, cy - 2, 4, 0xFFFFFF);
        lcd.fillCircle(cx + 20, cy - 2, 4, 0xFFFFFF);
    } else if (strcmp(mood, "thinking") == 0) {
        // 思考状态：双环旋转或眯眼沉思
        float rot = (animFrame * 0.15f);
        int eyeOffX = (int)(cos(rot) * 4);
        int eyeOffY = (int)(sin(rot) * 4);
        lcd.fillRoundRect(cx - 28 + eyeOffX, cy - 10 + eyeOffY, 18, 20, 6, 0xBB9AF7);
        lcd.fillRoundRect(cx + 10 + eyeOffX, cy - 10 + eyeOffY, 18, 20, 6, 0xBB9AF7);
    } else if (strcmp(mood, "speaking") == 0) {
        // 说话状态：开心月牙眼 + 嘴巴声波开合
        lcd.fillRoundRect(cx - 28, cy - 14, 18, 22, 6, 0x00E676);
        lcd.fillRoundRect(cx + 10, cy - 14, 18, 22, 6, 0x00E676);
        int mouthH = 4 + (animFrame % 4) * 3;
        lcd.fillRoundRect(cx - 12, cy + 14, 24, mouthH, 3, 0x00E676);
    }
}

void DisplayUI::drawWaveform(int level) {
    if (currentState != UI_STATE_LISTENING) return;
    
    // 动态 8 频段跳动频谱条 (Equalizer Visualizer)
    int baseX = 24;
    int baseY = 240;
    int barW = 18;
    int gap = 6;
    
    for (int i = 0; i < 8; i++) {
        int phase = (animFrame * 2 + i * 3) % 10;
        int dynamicH = map(level, 0, 100, 6, 65) + ((i % 2 == 0) ? phase * 3 : -phase * 2);
        dynamicH = constrain(dynamicH, 6, 80);
        
        int x = baseX + i * (barW + gap);
        // 清除旧柱状区域
        lcd.fillRect(x, baseY - 80, barW, 80, 0x101018);
        
        // 绘制渐变色跳动条
        uint16_t col = (i < 4) ? 0x00E5FF : 0x7AA2F7;
        lcd.fillRoundRect(x, baseY - dynamicH, barW, dynamicH, 4, col);
    }
}

void DisplayUI::renderConnecting() {
    renderStatusBar();
    
    renderAvatarFace(120, 90, "thinking");

    lcd.setTextColor(0x00E5FF, 0x101018);
    lcd.setTextDatum(MC_DATUM);
    lcd.setTextSize(2);
    lcd.drawString("FoloToy AI", 120, 150);
    
    lcd.setTextSize(1);
    lcd.setTextColor(0xAAAAAA, 0x101018);
    lcd.drawString("Antigravity Passport", 120, 180);
    
    // 进度条
    lcd.fillRoundRect(30, 215, 180, 8, 4, 0x222233);
    int barLen = (animFrame * 12) % 180;
    lcd.fillRoundRect(30, 215, barLen, 8, 4, 0x00E5FF);
    
    lcd.drawString("Auto UDP Discovery: 8765", 120, 245);
    lcd.drawString("Connecting to Gateway...", 120, 265);
}

void DisplayUI::renderDashboard() {
    renderStatusBar();

    if (dashboardPage == 0) {
        renderDashboardPage0();
    } else if (dashboardPage == 1) {
        renderDashboardPage1();
    } else {
        renderDashboardPage2();
    }

    // 底部多功能按键与分页提示
    lcd.fillRect(0, 292, 240, 28, 0x181824);
    lcd.setTextColor(0x7DCFFF, 0x181824);
    lcd.setTextDatum(MC_DATUM);
    lcd.setTextSize(1);
    String pageIndicator = "[" + String(dashboardPage + 1) + "/3] ";
    lcd.drawString(pageIndicator + "[Hold OK: Talk] [Up/Down: Page]", 120, 306);
}

// 页面 0: 飞书双链工作区看板
void DisplayUI::renderDashboardPage0() {
    renderAvatarFace(120, 72, "idle");

    // 中部：当前工作项目卡片
    lcd.fillRoundRect(12, 115, 216, 75, 8, 0x1F2335);
    lcd.drawRoundRect(12, 115, 216, 75, 8, 0x3B4261);
    
    lcd.setTextColor(0x7AA2F7, 0x1F2335);
    lcd.setTextDatum(TL_DATUM);
    lcd.setTextSize(1);
    lcd.drawString("ACTIVE WORKSPACE", 24, 125);
    
    lcd.setTextColor(0xFFFFFF, 0x1F2335);
    lcd.setTextSize(2);
    lcd.drawString(currentProject, 24, 142);
    
    lcd.setTextColor(0x9ECE6A, 0x1F2335);
    lcd.setTextSize(1);
    lcd.drawString("Dual-Link Engine: READY", 24, 168);

    // 下部：控制状态指标卡片
    lcd.fillRoundRect(12, 198, 216, 85, 8, 0x1F2335);
    lcd.drawRoundRect(12, 198, 216, 85, 8, 0x3B4261);
    
    lcd.setTextColor(0xBB9AF7, 0x1F2335);
    lcd.drawString("FEISHU SMART DUAL-LINK", 24, 208);
    
    lcd.setTextColor(0xC0CAF5, 0x1F2335);
    lcd.drawString("• Voice ASR : Whisper Realtime", 24, 226);
    lcd.drawString("• TTS Output: Edge-TTS Native", 24, 244);
    lcd.drawString("• Bot Status: " + currentStatus, 24, 262);
}

// 页面 1: 硬件诊断与电量监控 (CW2017 + ESP32-C3)
void DisplayUI::renderDashboardPage1() {
    lcd.fillRoundRect(12, 36, 216, 248, 8, 0x1F2335);
    lcd.drawRoundRect(12, 36, 216, 248, 8, 0x3B4261);

    lcd.setTextColor(0x00E5FF, 0x1F2335);
    lcd.setTextDatum(TL_DATUM);
    lcd.setTextSize(1);
    lcd.drawString("HARDWARE DIAGNOSTICS", 24, 48);

    lcd.setTextColor(0xFFFFFF, 0x1F2335);
    int y = 72;
    int dy = 22;

    // CW2017 电池参数
    lcd.drawString("Battery Gauge: CW2017 (0x63)", 24, y); y += dy;
    lcd.drawString("Battery SOC  : " + String(battery.getPercent()) + "%", 24, y); y += dy;
    lcd.drawString("Cell Voltage : " + String(battery.getVoltageMv()) + " mV", 24, y); y += dy;
    lcd.drawString("Power State  : " + String(battery.isCharging() ? "Charging" : "Discharging"), 24, y); y += dy;

    // ESP32-C3 核心指标
    uint32_t freeHeap = esp_get_free_heap_size() / 1024;
    lcd.drawString("Free Heap    : " + String(freeHeap) + " KB", 24, y); y += dy;
    lcd.drawString("CPU Freq     : 160 MHz (RISC-V)", 24, y); y += dy;
    lcd.drawString("Wi-Fi IP     : " + WiFi.localIP().toString(), 24, y); y += dy;
    lcd.drawString("Wi-Fi RSSI   : " + String(WiFi.RSSI()) + " dBm", 24, y); y += dy;
    lcd.drawString("Uptime       : " + String(millis() / 1000) + "s", 24, y);
}

// 页面 2: 飞书待办与通知详情流
void DisplayUI::renderDashboardPage2() {
    lcd.fillRoundRect(12, 36, 216, 248, 8, 0x1F2335);
    lcd.drawRoundRect(12, 36, 216, 248, 8, 0x3B4261);

    lcd.setTextColor(0xBB9AF7, 0x1F2335);
    lcd.setTextDatum(TL_DATUM);
    lcd.setTextSize(1);
    lcd.drawString("FEISHU NOTIFICATIONS", 24, 48);

    lcd.setTextColor(0xFFFFFF, 0x1F2335);
    lcd.drawString("Recent Card Feed:", 24, 72);

    lcd.setTextColor(0xCAD3F5, 0x1F2335);
    lcd.drawString("• Interactive Cards Enabled", 24, 98);
    lcd.drawString("• Voice PTT: OK button hold", 24, 120);
    lcd.drawString("• Emergency Halt: Down hold", 24, 142);
    lcd.drawString("• Gateway Sync: Port 8765", 24, 164);

    lcd.fillRoundRect(24, 195, 192, 70, 6, 0x181825);
    lcd.setTextColor(0x7DCFFF, 0x181825);
    lcd.drawString("Voice Whisper Ready:", 32, 205);
    lcd.setTextColor(0x9ECE6A, 0x181825);
    lcd.drawString("Press & Hold [OK] to talk", 32, 225);
    lcd.drawString("Release to submit to Agent", 32, 243);
}

void DisplayUI::renderListening() {
    renderStatusBar();
    renderAvatarFace(120, 80, "listening");

    lcd.setTextColor(0x00E5FF, 0x101018);
    lcd.setTextDatum(MC_DATUM);
    lcd.setTextSize(2);
    lcd.drawString("LISTENING...", 120, 135);
    
    lcd.setTextSize(1);
    lcd.setTextColor(0xAAAAAA, 0x101018);
    lcd.drawString("Recording I2S Audio Stream", 120, 160);
    
    // 底部提示
    lcd.setTextColor(0xFF9800, 0x101018);
    lcd.drawString("Release [OK] to Send to Feishu", 120, 275);
}

void DisplayUI::renderThinking() {
    renderStatusBar();
    renderAvatarFace(120, 80, "thinking");

    lcd.setTextColor(0xBB9AF7, 0x101018);
    lcd.setTextDatum(MC_DATUM);
    lcd.setTextSize(2);
    lcd.drawString("THINKING...", 120, 135);
    
    lcd.setTextSize(1);
    lcd.setTextColor(0xC0CAF5, 0x101018);
    lcd.drawString("Antigravity Agent Processing", 120, 160);
    
    // 旋转粒子环动效
    int centerX = 120;
    int centerY = 205;
    for (int i = 0; i < 8; i++) {
        float angle = i * (PI / 4.0f) + (animFrame * 0.25f);
        int x = centerX + cos(angle) * 32;
        int y = centerY + sin(angle) * 32;
        uint16_t c = (i == 0) ? 0x00E5FF : ((i < 3) ? 0xBB9AF7 : 0x3B4261);
        lcd.fillCircle(x, y, 4, c);
    }
    
    if (subtitleText.length() > 0) {
        lcd.setTextColor(0x7DCFFF, 0x101018);
        lcd.drawString(subtitleText.substring(0, 20), 120, 260);
    }
}

void DisplayUI::renderSpeaking() {
    renderStatusBar();
    renderAvatarFace(120, 75, "speaking");

    lcd.setTextColor(0x00E676, 0x101018);
    lcd.setTextDatum(MC_DATUM);
    lcd.setTextSize(2);
    lcd.drawString("SPEAKING...", 120, 125);
    
    lcd.fillRoundRect(16, 145, 208, 125, 8, 0x1F2335);
    lcd.drawRoundRect(16, 145, 208, 125, 8, 0x00E676);
    
    lcd.setTextSize(1);
    lcd.setTextColor(0xFFFFFF, 0x1F2335);
    lcd.setTextDatum(TL_DATUM);
    
    // 多行字幕排版
    int y = 158;
    for (int i = 0; i < subtitleText.length(); i += 18) {
        if (y > 250) break;
        lcd.drawString(subtitleText.substring(i, min((int)subtitleText.length(), i + 18)), 26, y);
        y += 20;
    }
    
    lcd.setTextColor(0x7AA2F7, 0x101018);
    lcd.setTextDatum(MC_DATUM);
    lcd.drawString("Synced with Feishu TTS", 120, 285);
}

void DisplayUI::renderAlert() {
    uint16_t headerColor = (alertLevel == "danger") ? 0xFF5252 : 0xFFB300;
    
    lcd.fillRoundRect(10, 35, 220, 250, 10, 0x221515);
    lcd.drawRoundRect(10, 35, 220, 250, 10, headerColor);
    
    lcd.setTextColor(headerColor, 0x221515);
    lcd.setTextDatum(MC_DATUM);
    lcd.setTextSize(2);
    lcd.drawString(alertTitle, 120, 65);
    
    lcd.setTextSize(1);
    lcd.setTextColor(0xFFFFFF, 0x221515);
    lcd.setTextDatum(TL_DATUM);
    
    int y = 100;
    for (int i = 0; i < alertContent.length(); i += 16) {
        if (y > 235) break;
        lcd.drawString(alertContent.substring(i, min((int)alertContent.length(), i + 16)), 24, y);
        y += 20;
    }
    
    lcd.setTextColor(0xAAAAAA, 0x221515);
    lcd.setTextDatum(MC_DATUM);
    lcd.drawString("Auto-dismissing in 5s...", 120, 265);
}

// 智能背光管理：45秒无操作降亮，120秒熄屏休眠
void DisplayUI::updateBacklight() {
    unsigned long idle = millis() - lastActivityTime;
    if (idle > 120000) {
        targetBrightness = 0; // 熄屏休眠
    } else if (idle > 45000) {
        targetBrightness = 40; // 节能省电
    } else {
        targetBrightness = 200; // 全亮正常
    }

    if (currentBrightness != targetBrightness) {
        if (currentBrightness < targetBrightness) {
            currentBrightness = min((int)targetBrightness, (int)currentBrightness + 8);
        } else {
            currentBrightness = max((int)targetBrightness, (int)currentBrightness - 8);
        }
        lcd.setBrightness(currentBrightness);
    }
}

void DisplayUI::loop() {
    unsigned long now = millis();
    updateBacklight();

    if (now - lastAnimTime > 80) {
        lastAnimTime = now;
        animFrame++;
        
        if (currentState == UI_STATE_THINKING) {
            renderThinking();
        } else if (currentState == UI_STATE_DASHBOARD && (animFrame % 60 >= 56 || animFrame % 60 == 0)) {
            // 定时眨眼重绘
            if (dashboardPage == 0) {
                renderAvatarFace(120, 72, "idle");
            }
        }
    }
    
    if (currentState == UI_STATE_ALERT && (now - alertStartTime > 5000)) {
        setState(UI_STATE_DASHBOARD);
    }
}
