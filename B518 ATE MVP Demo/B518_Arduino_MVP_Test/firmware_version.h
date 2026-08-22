#pragma once

// This is the only firmware-version source.  Use bump_firmware_version.py
// before committing an executable firmware change.
#define B518_FIRMWARE_PRODUCT "B518_ARDUINO_MVP"
#define B518_FIRMWARE_VERSION "1.0.5"
#define B518_PROTOCOL_VERSION 1

#if defined(ARDUINO_UNOR4_MINIMA)
  #define B518_FIRMWARE_BOARD "UNO_R4_MINIMA"
#elif defined(ARDUINO_UNOR4_WIFI)
  #define B518_FIRMWARE_BOARD "UNO_R4_WIFI"
#else
  #define B518_FIRMWARE_BOARD "UNKNOWN"
#endif
