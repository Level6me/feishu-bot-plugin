#include <Arduino.h>
#include "config.h"
#include "display_ui.h"
#include "audio_driver.h"
#include "network_ws.h"

// 官方单一 ADC 引脚电阻分压按键定义
enum KeyType {
    KEY_NONE = 0,
    KEY_UP,
    KEY_DOWN,
    KEY_OK
};

struct AdcKeyTracker {
    KeyType currentKey;
    unsigned long pressStartTime;
    bool longPressTriggered;
    unsigned long lastDebounceTime;
    KeyType lastSampledKey;
};

AdcKeyTracker keyTracker = { KEY_NONE, 0, false, 0, KEY_NONE };
bool isRecording = false;
int16_t micPcmBuffer[AUDIO_DMA_BUF_LEN];

// 采样 GPIO0 ADC 分压读数并根据官方 bsp_pins.h 电压窗口判定按键
KeyType sampleAdcKey() {
    uint32_t mv = analogReadMilliVolts(BSP_BTN_ADC_PIN);
    
    // 上键: 0Ω (窗口: 0 ~ 150 mV)
    if (mv >= BSP_BTN_UP_MIN_MV && mv < BSP_BTN_UP_MAX_MV) {
        return KEY_UP;
    }
    // 下键: 1kΩ (窗口: 150 ~ 447 mV)
    if (mv >= BSP_BTN_DOWN_MIN_MV && mv < BSP_BTN_DOWN_MAX_MV) {
        return KEY_DOWN;
    }
    // 确定键: 2.2kΩ (窗口: 447 ~ 1900 mV)
    if (mv >= BSP_BTN_OK_MIN_MV && mv < BSP_BTN_OK_MAX_MV) {
        return KEY_OK;
    }
    // 松开态: 3300 mV
    return KEY_NONE;
}

void handleAdcButtons() {
    KeyType rawKey = sampleAdcKey();
    unsigned long now = millis();

    // 简易软件消抖
    if (rawKey != keyTracker.lastSampledKey) {
        keyTracker.lastDebounceTime = now;
        keyTracker.lastSampledKey = rawKey;
    }

    if ((now - keyTracker.lastDebounceTime) < DEBOUNCE_MS) {
        return;
    }

    // 按键状态转移机
    if (rawKey != KEY_NONE && keyTracker.currentKey == KEY_NONE) {
        // 新按下瞬间
        keyTracker.currentKey = rawKey;
        keyTracker.pressStartTime = now;
        keyTracker.longPressTriggered = false;
    }
    else if (rawKey != KEY_NONE && keyTracker.currentKey == rawKey) {
        // 持续按下中，检查是否达到长按判定阈值
        if (!keyTracker.longPressTriggered && (now - keyTracker.pressStartTime >= LONG_PRESS_MS)) {
            keyTracker.longPressTriggered = true;
            if (rawKey == KEY_OK) {
                // 确定键长按：启动语音对讲录音 (PTT)
                isRecording = true;
                net.sendVoiceStart();
                ui.setState(UI_STATE_LISTENING);
            } else if (rawKey == KEY_UP) {
                net.sendButtonEvent("up", "long_press");
            } else if (rawKey == KEY_DOWN) {
                // 下键长按：紧急物理安全熔断
                net.sendButtonEvent("down", "long_press");
            }
        }
    }
    else if (rawKey == KEY_NONE && keyTracker.currentKey != KEY_NONE) {
        // 松开瞬间
        KeyType releasedKey = keyTracker.currentKey;
        keyTracker.currentKey = KEY_NONE;

        if (releasedKey == KEY_OK && isRecording) {
            // 确定键松开：结束对讲录音，提交飞书 Agent
            isRecording = false;
            net.sendVoiceEnd();
            ui.setState(UI_STATE_THINKING);
            ui.setThinkingText("发送给飞书 Agent...");
        } else if (!keyTracker.longPressTriggered) {
            // 短按事件派发
            if (releasedKey == KEY_UP) {
                net.sendButtonEvent("up", "short_press");
            } else if (releasedKey == KEY_DOWN) {
                net.sendButtonEvent("down", "short_press");
            } else if (releasedKey == KEY_OK) {
                net.sendButtonEvent("ok", "short_press");
            }
        }
    }
}

void setup() {
    Serial.begin(115200);
    delay(200);
    log_i("==================================================");
    log_i("  FoloToy AI Passport - Antigravity Feishu Client ");
    log_i("  Hardware BSP: components/bsp/include/bsp_pins.h ");
    log_i("==================================================");

    // 1. 初始化官方 ADC 单引脚电阻分压按键 (GPIO0)
    analogSetAttenuation(ADC_11db);
    pinMode(BSP_BTN_ADC_PIN, INPUT); // 外部已板载 10k 上拉电阻，不使用内部上拉

    // 2. 初始化 240x320 ST7789P3 LCD 显示屏
    ui.init();

    // 3. 初始化 ES8311 音频编解码芯片与 I2S 总线
    if (!audio.init()) {
        log_e("Audio hardware initialization failed!");
    }

    // 4. 初始化局域网通信 (Wi-Fi + UDP 发现)
    net.init();
}

void loop() {
    // 1. 扫描与处理电阻分压按键事件
    handleAdcButtons();

    // 2. 录音对讲推流：按住确定键期间，流式读取 I2S PCM 并推送至 WebSocket
    if (isRecording) {
        size_t samples = audio.readRecordData(micPcmBuffer, 256);
        if (samples > 0) {
            int32_t sum = 0;
            for (size_t i = 0; i < samples; i++) {
                sum += abs(micPcmBuffer[i]);
            }
            int energy = sum / samples;
            int waveLevel = map(constrain(energy, 100, 3000), 100, 3000, 10, 100);
            ui.drawWaveform(waveLevel);

            // 发送 PCM 二进制帧 (16kHz 16bit mono)
            net.sendAudioChunk((const uint8_t*)micPcmBuffer, samples * sizeof(int16_t));
        }
    }

    // 3. 刷新 UI 状态动效与网络事件
    ui.loop();
    net.loop();
}
