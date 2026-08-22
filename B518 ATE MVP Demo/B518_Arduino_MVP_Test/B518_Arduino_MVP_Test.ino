/*
  B518 Arduino MVP Test
  Target: Arduino UNO R4 Minima or UNO R4 WiFi + W5100 Ethernet module/shield

  USB CDC receives newline-terminated control commands.  Unknown lines are
  forwarded unchanged to the currently connected TCP client; TCP bytes are
  forwarded unchanged to USB CDC.
*/
#include <SPI.h>
#include <Ethernet.h>
#include <EEPROM.h>
#include <Keyboard.h>
#include <Mouse.h>
#include <HID.h>
#include "tusb.h"
#include "firmware_version.h"

// -------- Network configuration: change these values for the installation.
const byte DEFAULT_IP[] = {192, 168, 1, 100};
IPAddress ETHERNET_DNS(192, 168, 1, 1);
IPAddress ETHERNET_GATEWAY(192, 168, 1, 1);
IPAddress ETHERNET_SUBNET(255, 255, 255, 0);
const uint16_t TCP_LISTEN_PORT = 5000;
const uint8_t W5100_CS_PIN = 10;
const uint8_t SD_CS_PIN = 4;  // Prevent an Ethernet shield SD card from using SPI.

// -------- Protocol and HID configuration.
// A four-slot RESULT containing JOB ID, slot numbers and long SNs can exceed
// the legacy 256-byte buffer. 768 bytes covers the documented four × 128-char
// SN maximum while remaining small relative to the UNO R4's SRAM.
const size_t USB_FRAME_MAX = 768;
const int16_t MOUSE_RESET_DISTANCE = 3000;
const uint8_t MOUSE_STEP = 120;  // HID Mouse.move uses a signed 8-bit delta.
// Mojave/Catalina can require a longer interrupt-report interval than newer
// macOS releases. A neutral report wakes the endpoint before a relative move.
const uint8_t MOUSE_WAKE_DELAY_MS = 10;
const uint8_t MOUSE_REPORT_DELAY_MS = 8;
// The Renesas HID library waits forever for tud_hid_report_complete_cb().
// Older macOS hosts can leave that callback pending, which previously froze
// the whole firmware after it had already printed ACK.  Send reports directly
// through TinyUSB and bound the ready wait so USB CDC remains responsive.
const uint16_t HID_READY_TIMEOUT_MS = 180;
const uint8_t HID_MOUSE_REPORT_ID = 1;
const uint8_t HID_KEYBOARD_REPORT_ID = 2;
const uint8_t HID_ABSOLUTE_REPORT_ID = 3;
const int32_t HID_VALUE_MAX = 10000;
const uint16_t ABSOLUTE_HID_MAX = 32767;

// A second HID pointer report uses absolute, 16-bit X/Y values. macOS does
// not apply regular mouse acceleration to an absolute pointing report, which
// makes image-match coordinates repeatable. Report ID 1 remains the legacy
// relative Mouse library; Keyboard uses report ID 2; this uses report ID 3.
static const uint8_t absolutePointerDescriptor[] = {
  0x05, 0x01,                    // USAGE_PAGE (Generic Desktop)
  0x09, 0x02,                    // USAGE (Mouse)
  0xA1, 0x01,                    // COLLECTION (Application)
  0x09, 0x01,                    //   USAGE (Pointer)
  0xA1, 0x00,                    //   COLLECTION (Physical)
  0x85, 0x03,                    //     REPORT_ID (3)
  0x05, 0x09,                    //     USAGE_PAGE (Button)
  0x19, 0x01,                    //     USAGE_MINIMUM (Button 1)
  0x29, 0x03,                    //     USAGE_MAXIMUM (Button 3)
  0x15, 0x00,                    //     LOGICAL_MINIMUM (0)
  0x25, 0x01,                    //     LOGICAL_MAXIMUM (1)
  0x95, 0x03,                    //     REPORT_COUNT (3)
  0x75, 0x01,                    //     REPORT_SIZE (1)
  0x81, 0x02,                    //     INPUT (Data,Var,Abs)
  0x95, 0x01,                    //     REPORT_COUNT (1)
  0x75, 0x05,                    //     REPORT_SIZE (5)
  0x81, 0x03,                    //     INPUT (Cnst,Var,Abs)
  0x05, 0x01,                    //     USAGE_PAGE (Generic Desktop)
  0x09, 0x30,                    //     USAGE (X)
  0x09, 0x31,                    //     USAGE (Y)
  0x15, 0x00,                    //     LOGICAL_MINIMUM (0)
  0x26, 0xFF, 0x7F,              //     LOGICAL_MAXIMUM (32767)
  0x35, 0x00,                    //     PHYSICAL_MINIMUM (0)
  0x46, 0xFF, 0x7F,              //     PHYSICAL_MAXIMUM (32767)
  0x75, 0x10,                    //     REPORT_SIZE (16)
  0x95, 0x02,                    //     REPORT_COUNT (2)
  0x81, 0x02,                    //     INPUT (Data,Var,Abs)
  0xC0,                          //   END_COLLECTION
  0xC0                           // END_COLLECTION
};

struct __attribute__((packed)) AbsolutePointerReport {
  uint8_t buttons;
  uint16_t x;
  uint16_t y;
};

void reportFirmwareError(const char *errorText, const char *faultCode);

bool waitForHidReady() {
  const uint32_t startedAt = millis();
  while (!tud_hid_ready()) {
    if ((uint32_t)(millis() - startedAt) >= HID_READY_TIMEOUT_MS) {
      reportFirmwareError("HID_NOT_READY", "HID_NOT_READY");
      return false;
    }
    delay(1);
  }
  return true;
}

bool sendHidReport(uint8_t reportId, const void *data, uint16_t length) {
  if (!waitForHidReady()) return false;
  if (!tud_hid_report(reportId, data, length)) {
    reportFirmwareError("HID_SEND_FAILED", "HID_SEND_FAILED");
    return false;
  }
  return true;
}

bool sendMouseReport(uint8_t buttons, int8_t x, int8_t y, int8_t wheel = 0) {
  // Keep the report layout used by the Arduino Mouse library: buttons, X, Y,
  // wheel and pan. The final pan byte is deliberately neutral.
  const uint8_t report[] = {buttons, (uint8_t)x, (uint8_t)y, (uint8_t)wheel, 0};
  return sendHidReport(HID_MOUSE_REPORT_ID, report, sizeof(report));
}

bool sendKeyboardReport(uint8_t modifiers, uint8_t keycode) {
  const uint8_t report[] = {modifiers, 0, keycode, 0, 0, 0, 0, 0};
  return sendHidReport(HID_KEYBOARD_REPORT_ID, report, sizeof(report));
}

class AbsolutePointer {
public:
  AbsolutePointer() : x(0), y(0), buttons(0) {
    static HIDSubDescriptor node(absolutePointerDescriptor, sizeof(absolutePointerDescriptor));
    HID().AppendDescriptor(&node);
  }

  bool move(uint16_t newX, uint16_t newY) {
    x = newX; y = newY; return send();
  }

  bool click(uint8_t button) {
    buttons = button;
    if (!send()) return false;
    delay(15);
    buttons = 0;
    return send();
  }

private:
  uint16_t x, y;
  uint8_t buttons;

  bool send() {
    AbsolutePointerReport report = {buttons, x, y};
    return sendHidReport(HID_ABSOLUTE_REPORT_ID, &report, sizeof(report));
  }
};

AbsolutePointer absolutePointer;

struct NetworkSettings {
  uint8_t magic0;
  uint8_t magic1;
  uint8_t version;
  uint8_t ip[4];
  uint8_t checksum;
};

const uint8_t NETWORK_MAGIC0 = 0xB5;
const uint8_t NETWORK_MAGIC1 = 0x18;
const uint8_t NETWORK_SETTINGS_VERSION = 1;
NetworkSettings networkSettings;
byte ethernetMac[6];
IPAddress ethernetIp;

EthernetServer tcpServer(TCP_LISTEN_PORT);
EthernetClient tcpClient;

char usbFrame[USB_FRAME_MAX];
size_t usbFrameLength = 0;
bool discardUsbFrame = false;
bool firmwareFault = false;
const char *lastFirmwareFault = "NONE";

bool looksLikeControlCommand(size_t commandLength);
bool typeAsciiCharacter(char value);
bool mouseReset();
bool moveMouseBy(int32_t x, int32_t y);
bool mouseClick(uint8_t button);
bool takeScreenshot();

void clearFirmwareFault() {
  firmwareFault = false;
  lastFirmwareFault = "NONE";
  digitalWrite(LED_BUILTIN, LOW);
}

void reportFirmwareError(const char *errorText, const char *faultCode) {
  firmwareFault = true;
  lastFirmwareFault = faultCode;
  digitalWrite(LED_BUILTIN, HIGH);
  Serial.print("ERR:");
  Serial.println(errorText);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  clearFirmwareFault();
  Serial.begin(115200);

  pinMode(SD_CS_PIN, OUTPUT);
  digitalWrite(SD_CS_PIN, HIGH);
  Ethernet.init(W5100_CS_PIN);
  loadNetworkSettings();
  initializeEthernet();

  Keyboard.begin();
  Mouse.begin();
  // Register the standard Arduino descriptors, but never use the library
  // send methods below: they can block indefinitely on older macOS HID hosts.
  // Do not send a neutral report during setup: on a cold USB enumeration the
  // host is not ready yet, and treating that as a HID fault would light the
  // diagnostic LED before the station has even opened the CDC port.
}

void loop() {
  acceptTcpClient();
  bridgeTcpToUsb();
  bridgeUsbToTcpOrHid();
}

void acceptTcpClient() {
  if (tcpClient && tcpClient.connected()) return;

  if (tcpClient) {
    tcpClient.stop();
  }

  EthernetClient candidate = tcpServer.available();
  if (candidate) {
    // MVP serves one upper-computer connection at a time.
    tcpClient = candidate;
  }
}

void bridgeTcpToUsb() {
  if (!tcpClient || !tcpClient.connected()) return;

  while (tcpClient.available() > 0) {
    int value = tcpClient.read();
    if (value < 0) break;
    // No DATA: prefix, ACK, or diagnostic text: this direction is transparent.
    Serial.write((uint8_t)value);
  }
}

void bridgeUsbToTcpOrHid() {
  while (Serial.available() > 0) {
    int value = Serial.read();
    if (value < 0) break;
    appendUsbByte((char)value);
  }
}

void appendUsbByte(char value) {
  if (discardUsbFrame) {
    if (value == '\n') discardUsbFrame = false;
    return;
  }

  // Some older macOS/virtual-USB paths can deliver the CR paired with a
  // previous LF as the first byte of the next CDC packet. Ignore only these
  // separator bytes while idle so the next control line starts cleanly.
  // A normal CRLF control line is still accepted because its CR arrives after
  // command data, before the terminating LF.
  if (usbFrameLength == 0 && (value == '\r' || value == '\n' || value == '\0')) {
    return;
  }

  if (usbFrameLength >= USB_FRAME_MAX) {
    usbFrameLength = 0;
    discardUsbFrame = true;
    reportFirmwareError("FRAME_TOO_LONG", "FRAME_TOO_LONG");
    return;
  }

  usbFrame[usbFrameLength++] = value;
  if (value == '\n') {
    processUsbFrame();
    usbFrameLength = 0;
  }
}

void processUsbFrame() {
  // Commands are line based. The trailing LF and optional CR are not command data.
  size_t commandLength = usbFrameLength - 1;
  if (commandLength > 0 && usbFrame[commandLength - 1] == '\r') commandLength--;

  if (equalsCommand("GET_IP", commandLength)) {
    Serial.print("IP:");
    Serial.println(Ethernet.localIP());
    printFirmwareInfo();
  } else if (equalsCommand("GET_INFO", commandLength)) {
    printFirmwareInfo();
  } else if (equalsCommand("DIAG_CLEAR", commandLength)) {
    clearFirmwareFault();
    Serial.println("OK:DIAG_CLEAR");
  } else if (startsWith("NET_SET:", commandLength)) {
    handleNetworkSet(commandLength);
  } else if (equalsCommand("NET_RESET", commandLength)) {
    resetNetworkSettings();
  } else if (equalsCommand("M_RESET", commandLength)) {
    Serial.println("ACK:M_RESET");
    if (mouseReset()) Serial.println("OK:M_RESET");
  } else if (startsWith("M_MOVE:", commandLength)) {
    Serial.println("ACK:M_MOVE");
    handleMouseMove(commandLength);
  } else if (startsWith("M_DELTA:", commandLength)) {
    Serial.println("ACK:M_DELTA");
    handleMouseDelta(commandLength);
  } else if (startsWith("M_ABS:", commandLength)) {
    handleAbsoluteMove(commandLength);
  } else if (equalsCommand("M_ABS_CLICK:L", commandLength)) {
    if (absolutePointer.click(MOUSE_LEFT)) Serial.println("OK:M_ABS_CLICK:L");
  } else if (equalsCommand("M_CLICK:L", commandLength)) {
    if (mouseClick(MOUSE_LEFT)) Serial.println("OK:M_CLICK:L");
  } else if (equalsCommand("M_CLICK:R", commandLength)) {
    if (mouseClick(MOUSE_RIGHT)) Serial.println("OK:M_CLICK:R");
  } else if (startsWith("M_SCROLL:", commandLength)) {
    handleScroll(commandLength);
  } else if (startsWith("K_TYPE:", commandLength)) {
    handleType(commandLength);
  } else if (startsWith("K_WRITE:", commandLength)) {
    handleWrite(commandLength);
  } else if (equalsCommand("K_KEY:TAB", commandLength)) {
    if (typeAsciiCharacter('\t')) Serial.println("OK:K_KEY:TAB");
  } else if (equalsCommand("SCREENSHOT", commandLength) ||
             equalsCommand("K_SHORTCUT:SCREENSHOT", commandLength)) {
    // Emit a diagnostic before touching the HID endpoint.  The closed Mac
    // station can use the existing Agent log to distinguish a command/frame
    // problem from a HID action that never returns to this firmware.
    Serial.println("ACK:SCREENSHOT");
    if (takeScreenshot()) Serial.println("OK:SCREENSHOT");
  } else if (looksLikeControlCommand(commandLength)) {
    reportFirmwareError("UNKNOWN_CONTROL_COMMAND", "UNKNOWN_CONTROL_COMMAND");
  } else {
    // Non-control traffic remains byte-for-byte unchanged, including CR/LF.
    forwardUsbFrameToTcp();
  }
}

void printFirmwareInfo() {
  // Keep this command response on USB CDC only.  No boot banner is emitted,
  // so the TCP bridge remains byte-for-byte transparent for normal traffic.
  Serial.print("INFO:PRODUCT=");
  Serial.print(B518_FIRMWARE_PRODUCT);
  Serial.print(";FW=");
  Serial.print(B518_FIRMWARE_VERSION);
  Serial.print(";PROTO=");
  Serial.print(B518_PROTOCOL_VERSION);
  Serial.print(";BOARD=");
  Serial.print(B518_FIRMWARE_BOARD);
  Serial.print(";FAULT=");
  Serial.print(firmwareFault ? 1 : 0);
  Serial.print(";LAST=");
  Serial.println(lastFirmwareFault);
}

bool looksLikeControlCommand(size_t commandLength) {
  return startsWith("M_", commandLength) ||
         startsWith("K_", commandLength) ||
         startsWith("GET_", commandLength) ||
         startsWith("NET_", commandLength) ||
         startsWith("DIAG_", commandLength) ||
         startsWith("SCREENSHOT", commandLength);
}

uint8_t calculateNetworkChecksum(const NetworkSettings &settings) {
  uint8_t checksum = 0x5A;
  checksum ^= settings.magic0;
  checksum ^= settings.magic1;
  checksum ^= settings.version;
  for (uint8_t i = 0; i < 4; ++i) checksum ^= settings.ip[i];
  return checksum;
}

bool settingsAreValid(const NetworkSettings &settings) {
  return settings.magic0 == NETWORK_MAGIC0 &&
         settings.magic1 == NETWORK_MAGIC1 &&
         settings.version == NETWORK_SETTINGS_VERSION &&
         settings.checksum == calculateNetworkChecksum(settings) &&
         isUsableHostIp(settings.ip);
}

void setDefaultNetworkSettings() {
  networkSettings.magic0 = NETWORK_MAGIC0;
  networkSettings.magic1 = NETWORK_MAGIC1;
  networkSettings.version = NETWORK_SETTINGS_VERSION;
  for (uint8_t i = 0; i < 4; ++i) networkSettings.ip[i] = DEFAULT_IP[i];
  networkSettings.checksum = calculateNetworkChecksum(networkSettings);
}

void loadNetworkSettings() {
  NetworkSettings stored;
  EEPROM.get(0, stored);
  if (settingsAreValid(stored)) {
    networkSettings = stored;
  } else {
    setDefaultNetworkSettings();
  }
}

void saveNetworkSettings() {
  networkSettings.checksum = calculateNetworkChecksum(networkSettings);
  EEPROM.put(0, networkSettings);
}

void deriveMacAddress() {
  // Locally administered MAC. A unique assigned IPv4 address therefore gives
  // this MVP a unique W5100 MAC address as well.
  ethernetMac[0] = 0x02;
  ethernetMac[1] = 0xB5;
  ethernetMac[2] = networkSettings.ip[0];
  ethernetMac[3] = networkSettings.ip[1];
  ethernetMac[4] = networkSettings.ip[2];
  ethernetMac[5] = networkSettings.ip[3];
  ethernetIp = IPAddress(networkSettings.ip[0], networkSettings.ip[1],
                         networkSettings.ip[2], networkSettings.ip[3]);
}

void initializeEthernet() {
  deriveMacAddress();
  Ethernet.begin(ethernetMac, ethernetIp, ETHERNET_DNS,
                 ETHERNET_GATEWAY, ETHERNET_SUBNET);
  tcpServer.begin();
}

bool isUsableHostIp(const uint8_t ip[4]) {
  // This MVP accepts unicast IPv4 hosts but excludes clearly invalid/reserved
  // first octets and the usual /24 network/broadcast host addresses.
  return ip[0] != 0 && ip[0] != 127 && ip[0] < 224 &&
         ip[3] != 0 && ip[3] != 255;
}

bool parseIpv4(const char *text, size_t length, uint8_t destination[4]) {
  size_t start = 0;
  for (uint8_t octet = 0; octet < 4; ++octet) {
    size_t end = start;
    while (end < length && text[end] != '.') end++;
    int32_t value;
    if (!parseInteger(text + start, end - start, value) || value < 0 || value > 255) return false;
    destination[octet] = (uint8_t)value;
    if (octet == 3) {
      if (end != length) return false;
    } else {
      if (end == length) return false;
      start = end + 1;
    }
  }
  return isUsableHostIp(destination);
}

void printConfiguredIp(const char *prefix) {
  Serial.print(prefix);
  Serial.print(networkSettings.ip[0]);
  Serial.print('.');
  Serial.print(networkSettings.ip[1]);
  Serial.print('.');
  Serial.print(networkSettings.ip[2]);
  Serial.print('.');
  Serial.println(networkSettings.ip[3]);
}

void handleNetworkSet(size_t commandLength) {
  const size_t prefixLength = strlen("NET_SET:");
  uint8_t requestedIp[4];
  if (!parseIpv4(usbFrame + prefixLength, commandLength - prefixLength, requestedIp)) {
    reportFirmwareError("NET_SET_FORMAT", "NET_SET_FORMAT");
    return;
  }

  for (uint8_t i = 0; i < 4; ++i) networkSettings.ip[i] = requestedIp[i];
  saveNetworkSettings();
  if (tcpClient) tcpClient.stop();
  initializeEthernet();
  printConfiguredIp("OK:NET_SET:");
}

void resetNetworkSettings() {
  setDefaultNetworkSettings();
  saveNetworkSettings();
  if (tcpClient) tcpClient.stop();
  initializeEthernet();
  printConfiguredIp("OK:NET_RESET:");
}

bool equalsCommand(const char *text, size_t commandLength) {
  size_t length = strlen(text);
  return commandLength == length && memcmp(usbFrame, text, length) == 0;
}

bool startsWith(const char *prefix, size_t commandLength) {
  size_t length = strlen(prefix);
  return commandLength >= length && memcmp(usbFrame, prefix, length) == 0;
}

bool parseIntegerWithLimit(const char *text, size_t length, int32_t &result, int32_t maximum) {
  if (length == 0) return false;
  bool negative = false;
  size_t index = 0;
  if (text[index] == '+' || text[index] == '-') {
    negative = text[index] == '-';
    if (++index == length) return false;
  }

  int32_t value = 0;
  for (; index < length; ++index) {
    if (text[index] < '0' || text[index] > '9') return false;
    int32_t digit = text[index] - '0';
    if (value > (maximum - digit) / 10) return false;
    value = value * 10 + digit;
  }
  result = negative ? -value : value;
  return true;
}

bool parseInteger(const char *text, size_t length, int32_t &result) {
  return parseIntegerWithLimit(text, length, result, HID_VALUE_MAX);
}

void handleMouseMove(size_t commandLength) {
  const size_t prefixLength = strlen("M_MOVE:");
  size_t comma = prefixLength;
  while (comma < commandLength && usbFrame[comma] != ',') comma++;

  int32_t x, y;
  if (comma == commandLength ||
      !parseInteger(usbFrame + prefixLength, comma - prefixLength, x) ||
      !parseInteger(usbFrame + comma + 1, commandLength - comma - 1, y) ||
      x < 0 || y < 0) {
    reportFirmwareError("M_MOVE_FORMAT", "M_MOVE_FORMAT");
    return;
  }

  if (mouseReset() && moveMouseBy(x, y)) Serial.println("OK:M_MOVE");
}

void handleMouseDelta(size_t commandLength) {
  const size_t prefixLength = strlen("M_DELTA:");
  size_t comma = prefixLength;
  while (comma < commandLength && usbFrame[comma] != ',') comma++;

  int32_t x, y;
  if (comma == commandLength ||
      !parseInteger(usbFrame + prefixLength, comma - prefixLength, x) ||
      !parseInteger(usbFrame + comma + 1, commandLength - comma - 1, y)) {
    reportFirmwareError("M_DELTA_FORMAT", "M_DELTA_FORMAT");
    return;
  }

  // Unlike M_MOVE, calibration deliberately does not reset to the origin.
  // This makes an arrow press a visible, repeatable relative HID movement.
  if (moveMouseBy(x, y)) Serial.println("OK:M_DELTA");
}

void handleAbsoluteMove(size_t commandLength) {
  const size_t prefixLength = strlen("M_ABS:");
  size_t comma = prefixLength;
  while (comma < commandLength && usbFrame[comma] != ',') comma++;

  int32_t x, y;
  if (comma == commandLength ||
      !parseIntegerWithLimit(usbFrame + prefixLength, comma - prefixLength, x, ABSOLUTE_HID_MAX) ||
      !parseIntegerWithLimit(usbFrame + comma + 1, commandLength - comma - 1, y, ABSOLUTE_HID_MAX) ||
      x < 0 || y < 0 || x > ABSOLUTE_HID_MAX || y > ABSOLUTE_HID_MAX) {
    reportFirmwareError("M_ABS_FORMAT", "M_ABS_FORMAT");
    return;
  }

  if (absolutePointer.move((uint16_t)x, (uint16_t)y)) Serial.println("OK:M_ABS");
}

void handleScroll(size_t commandLength) {
  const size_t prefixLength = strlen("M_SCROLL:");
  int32_t amount;
  if (!parseInteger(usbFrame + prefixLength, commandLength - prefixLength, amount)) {
    reportFirmwareError("M_SCROLL_FORMAT", "M_SCROLL_FORMAT");
    return;
  }
  bool sent = true;
  while (amount != 0 && sent) {
    int8_t step = amount > 127 ? 127 : (amount < -127 ? -127 : (int8_t)amount);
    sent = sendMouseReport(0, 0, 0, step);
    amount -= step;
  }
  if (sent) Serial.println("OK:M_SCROLL");
}

bool typeAsciiCharacter(char value) {
  uint8_t modifiers = 0;
  uint8_t keycode = 0;
  if (value >= 'a' && value <= 'z') {
    keycode = 0x04 + (value - 'a');
  } else if (value >= 'A' && value <= 'Z') {
    modifiers = 0x02;  // left shift
    keycode = 0x04 + (value - 'A');
  } else if (value >= '1' && value <= '9') {
    keycode = 0x1E + (value - '1');
  } else if (value == '0') {
    keycode = 0x27;
  } else {
    switch (value) {
      case '\n': case '\r': keycode = 0x28; break; // Enter
      case '\t': keycode = 0x2B; break;             // Tab
      case ' ': keycode = 0x2C; break;
      case '-': keycode = 0x2D; break;
      case '_': modifiers = 0x02; keycode = 0x2D; break;
      case '=': keycode = 0x2E; break;
      case '+': modifiers = 0x02; keycode = 0x2E; break;
      case '[': keycode = 0x2F; break;
      case ']': keycode = 0x30; break;
      case '\\': keycode = 0x31; break;
      case ';': keycode = 0x33; break;
      case ':': modifiers = 0x02; keycode = 0x33; break;
      case '\'': keycode = 0x34; break;
      case '"': modifiers = 0x02; keycode = 0x34; break;
      case ',': keycode = 0x36; break;
      case '<': modifiers = 0x02; keycode = 0x36; break;
      case '.': keycode = 0x37; break;
      case '>': modifiers = 0x02; keycode = 0x37; break;
      case '/': keycode = 0x38; break;
      case '?': modifiers = 0x02; keycode = 0x38; break;
      case '!': modifiers = 0x02; keycode = 0x1E; break;
      default:
        reportFirmwareError("K_TYPE_ASCII_MAP", "K_TYPE_ASCII_MAP");
        return false;
    }
  }
  if (!sendKeyboardReport(modifiers, keycode)) return false;
  delay(4);
  if (!sendKeyboardReport(0, 0)) return false;
  delay(4);
  return true;
}

void handleType(size_t commandLength) {
  const size_t prefixLength = strlen("K_TYPE:");
  for (size_t i = prefixLength; i < commandLength; ++i) {
    // Keyboard.print is deliberately restricted to printable ASCII for MVP.
    if ((uint8_t)usbFrame[i] < 0x20 || (uint8_t)usbFrame[i] > 0x7E) {
      reportFirmwareError("K_TYPE_ASCII_ONLY", "K_TYPE_ASCII_ONLY");
      return;
    }
  }
  for (size_t i = prefixLength; i < commandLength; ++i) {
    if (!typeAsciiCharacter(usbFrame[i])) return;
  }
  if (!typeAsciiCharacter('\n')) return;  // barcode input always completes with Enter.
  Serial.println("OK:K_TYPE");
}

void handleWrite(size_t commandLength) {
  const size_t prefixLength = strlen("K_WRITE:");
  for (size_t i = prefixLength; i < commandLength; ++i) {
    if ((uint8_t)usbFrame[i] < 0x20 || (uint8_t)usbFrame[i] > 0x7E) {
      reportFirmwareError("K_WRITE_ASCII_ONLY", "K_WRITE_ASCII_ONLY");
      return;
    }
  }
  for (size_t i = prefixLength; i < commandLength; ++i) {
    if (!typeAsciiCharacter(usbFrame[i])) return;
  }
  Serial.println("OK:K_WRITE");
}

bool mouseReset() {
  return moveMouseBy(-MOUSE_RESET_DISTANCE, -MOUSE_RESET_DISTANCE);
}

bool moveMouseBy(int32_t x, int32_t y) {
  // Do not rely on the first non-zero relative report being accepted by an
  // older Intel macOS HID stack. This report is intentionally neutral.
  if (!sendMouseReport(0, 0, 0)) return false;
  delay(MOUSE_WAKE_DELAY_MS);
  while (x != 0 || y != 0) {
    int8_t stepX = x > MOUSE_STEP ? MOUSE_STEP : (x < -MOUSE_STEP ? -MOUSE_STEP : (int8_t)x);
    int8_t stepY = y > MOUSE_STEP ? MOUSE_STEP : (y < -MOUSE_STEP ? -MOUSE_STEP : (int8_t)y);
    if (!sendMouseReport(0, stepX, stepY)) return false;
    x -= stepX;
    y -= stepY;
    delay(MOUSE_REPORT_DELAY_MS);  // lets older HID endpoints deliver each report
  }
  return true;
}

bool mouseClick(uint8_t button) {
  if (!sendMouseReport(button, 0, 0)) return false;
  delay(15);
  return sendMouseReport(0, 0, 0);
}

bool takeScreenshot() {
  // Command+Shift+3 as one boot-keyboard report; sending modifiers in
  // separate reports is less reliable on Mojave's older HID stack.
  const uint8_t modifier = 0x0A; // left GUI + left shift
  const uint8_t key3 = 0x20;
  if (!sendKeyboardReport(modifier, key3)) return false;
  delay(25);
  return sendKeyboardReport(0, 0);
}

void forwardUsbFrameToTcp() {
  if (tcpClient && tcpClient.connected()) {
    tcpClient.write((const uint8_t *)usbFrame, usbFrameLength);
  } else {
    Serial.println("ERR:TCP_NOT_CONNECTED");
  }
}
