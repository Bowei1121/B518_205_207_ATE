#include <SPI.h>
#include <Ethernet.h>

// MVP TCP-to-USB bridge for Arduino + W5500/Ethernet Shield.
// TCP client sends newline-terminated text. Arduino forwards each line to USB Serial as:
// DATA:<payload>

const unsigned long SERIAL_WAIT_MS = 3000;
const size_t MAX_LINE_LENGTH = 128;

byte mac[] = {0xDE, 0xAD, 0xBE, 0xEF, 0x51, 0x80};
IPAddress ip(192, 168, 1, 80);
IPAddress gateway(192, 168, 1, 1);
IPAddress subnet(255, 255, 255, 0);

const uint16_t TCP_PORT = 5000;
const uint8_t ETHERNET_CS_PIN = 10;
const uint8_t SD_CARD_CS_PIN = 4;

EthernetServer server(TCP_PORT);
EthernetClient activeClient;

char lineBuffer[MAX_LINE_LENGTH + 1];
size_t lineLength = 0;
char usbLineBuffer[MAX_LINE_LENGTH + 1];
size_t usbLineLength = 0;

void setup() {
  Serial.begin(115200);
  waitForSerialOrTimeout();

  pinMode(SD_CARD_CS_PIN, OUTPUT);
  digitalWrite(SD_CARD_CS_PIN, HIGH);

  Ethernet.init(ETHERNET_CS_PIN);
  Ethernet.begin(mac, ip, gateway, gateway, subnet);
  delay(1000);

  printEthernetDiagnostics();

  server.begin();

  Serial.print("EVT: TCP server ready at ");
  Serial.print(Ethernet.localIP());
  Serial.print(":");
  Serial.println(TCP_PORT);
}

void loop() {
  maintainClient();

  // Mac Agent -> USB CDC -> this bridge -> TCP upper computer.
  // HID-specific commands can be handled by the combined HID firmware before
  // forwarding; RESULT lines must always reach the active TCP client.
  while (Serial.available() > 0) {
    char incoming = Serial.read();
    handleSerialByte(incoming);
  }

  if (!activeClient || !activeClient.connected()) {
    return;
  }

  while (activeClient.available() > 0) {
    char incoming = activeClient.read();
    handleTcpByte(incoming);
  }
}

void handleSerialByte(char incoming) {
  if (incoming == '\r') return;
  if (incoming == '\n') {
    if (usbLineLength == 0) return;
    usbLineBuffer[usbLineLength] = '\0';

    if (strcmp(usbLineBuffer, "GET_IP") == 0) {
      Serial.print("EVT: IP=");
      Serial.println(Ethernet.localIP());
    } else if (strncmp(usbLineBuffer, "SET_IP:", 7) == 0) {
      IPAddress requested;
      if (requested.fromString(usbLineBuffer + 7)) {
        Ethernet.begin(mac, requested, gateway, gateway, subnet);
        Serial.print("EVT: IP=");
        Serial.println(Ethernet.localIP());
      } else {
        Serial.println("ERR: invalid IP");
      }
    } else if (activeClient && activeClient.connected()) {
      activeClient.println(usbLineBuffer);
      Serial.print("EVT: TCP TX ");
      Serial.println(usbLineBuffer);
    } else {
      Serial.println("ERR: no active TCP client for USB response");
    }
    usbLineLength = 0;
    return;
  }
  if (usbLineLength < MAX_LINE_LENGTH) usbLineBuffer[usbLineLength++] = incoming;
  else usbLineLength = 0;
}

void printEthernetDiagnostics() {
  Serial.print("EVT: Ethernet local IP=");
  Serial.println(Ethernet.localIP());

  if (Ethernet.hardwareStatus() == EthernetNoHardware) {
    Serial.println("ERR: Ethernet shield was not found");
  } else if (Ethernet.hardwareStatus() == EthernetW5100) {
    Serial.println("EVT: Ethernet hardware=W5100");
  } else if (Ethernet.hardwareStatus() == EthernetW5200) {
    Serial.println("EVT: Ethernet hardware=W5200");
  } else if (Ethernet.hardwareStatus() == EthernetW5500) {
    Serial.println("EVT: Ethernet hardware=W5500");
  } else {
    Serial.println("EVT: Ethernet hardware=unknown");
  }

  if (Ethernet.linkStatus() == LinkON) {
    Serial.println("EVT: Ethernet link=ON");
  } else if (Ethernet.linkStatus() == LinkOFF) {
    Serial.println("ERR: Ethernet link=OFF");
  } else {
    Serial.println("EVT: Ethernet link=unknown");
  }
}

void waitForSerialOrTimeout() {
  unsigned long startMs = millis();
  while (!Serial && millis() - startMs < SERIAL_WAIT_MS) {
    delay(10);
  }
}

void maintainClient() {
  if (activeClient && activeClient.connected()) {
    return;
  }

  if (activeClient) {
    activeClient.stop();
    Serial.println("EVT: TCP client disconnected");
  }

  EthernetClient newClient = server.available();
  if (newClient) {
    activeClient = newClient;
    lineLength = 0;
    activeClient.println("READY Arduino TCP-to-USB bridge");
    Serial.println("EVT: TCP client connected");
  }
}

void handleTcpByte(char incoming) {
  if (incoming == '\r') {
    return;
  }

  if (incoming == '\n') {
    flushLine();
    return;
  }

  if (lineLength >= MAX_LINE_LENGTH) {
    lineBuffer[lineLength] = '\0';
    Serial.print("ERR: TCP line too long, discarded prefix=");
    Serial.println(lineBuffer);
    activeClient.println("ERR line too long");
    lineLength = 0;
    return;
  }

  lineBuffer[lineLength] = incoming;
  lineLength++;
}

void flushLine() {
  if (lineLength == 0) {
    return;
  }

  lineBuffer[lineLength] = '\0';

  Serial.print("DATA:");
  Serial.println(lineBuffer);

  activeClient.print("ACK ");
  activeClient.println(lineBuffer);

  lineLength = 0;
}
