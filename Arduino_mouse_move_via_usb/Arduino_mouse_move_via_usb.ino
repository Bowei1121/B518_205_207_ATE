#include <Mouse.h>

// 定義序列埠指令
const char CMD_START = 'S'; // 開始隨機移動
const char CMD_STOP  = 'P'; // 停止移動

// 定義系統參數
const unsigned long MOVE_INTERVAL = 200; // 每 200ms 移動一次

// 狀態變數
bool isMoving = false;
unsigned long lastMoveTime = 0;

void setup() {
  // 初始化 USB CDC 序列埠，波特率在原生 USB 上不影響速度，但習慣設定 115200
  Serial.begin(115200); 
  
  // 初始化 USB HID 滑鼠功能
  Mouse.begin();
  
  // 亂數種子初始化（讀取浮空類比腳位減少重複性）
  randomSeed(analogRead(A0));
}

void loop() {
  // 1. 處理 USB Data 指令接收 (CDC)
  checkSerialCommand();

  // 2. 處理滑鼠隨機移動邏輯 (HID) - 使用 millis() 非阻塞定時
  if (isMoving) {
    unsigned long currentTime = millis();
    if (currentTime - lastMoveTime >= MOVE_INTERVAL) {
      lastMoveTime = currentTime;
      moveMouseRandomly();
    }
  }
}

/**
 * 檢查序列埠指令
 */
void checkSerialCommand() {
  if (Serial.available() > 0) {
    char incomingChar = Serial.read();
    // 過濾掉換行符等雜訊
    if (incomingChar == '\r' || incomingChar == '\n') return;

    if (incomingChar == CMD_START) {
        isMoving = true;
        lastMoveTime = millis(); // 重設計時器，避免一開啟就暴走
        Serial.println("ACK: Mouse movement started.");
    } 
    else if (incomingChar == CMD_STOP) {
        isMoving = false;
        Serial.println("ACK: Mouse movement stopped.");
      }
    else {
      // 格式錯誤回報，方便上層除錯
      Serial.print("ERR: Unknown command '");
      Serial.print(incomingChar);
      Serial.println("'");
    }
  }
}

/**
 * 執行滑鼠隨機移動 (+/-5 pixel)
 */
void moveMouseRandomly() {
  // random(-10, 11) 會產生 -10 到 10 之間的整數 (包含 -5，不包含 6)
  int moveX = random(-10, 11);
  int moveY = random(-10, 11);

  // 透過 HID 送出相對移動量
  Mouse.move(moveX, moveY, 0);
}