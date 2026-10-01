# B518 BT / RS-WMT pilot

This pilot reads local result files. It does not control RS-WMT or the test equipment.
The Apple Silicon build targets macOS 15.0 and later, including the US station's
15.4.1. The build still needs to be produced on M4 and validated on the station;
source tests and sample replay do not prove packaged-app compatibility.

## Install and configure

1. Obtain the `macOS15.0-arm64.zip` candidate from the build owner. Extract it and
   open `B518 Log Solution.app`. No Python or Homebrew installation is required
   on the test station. Do not use the macOS 26-only package.
2. Open **設定** (Settings), choose **BT**, then **B518 RS-WMT** under **BT 格式 / Format**.
3. Set **RS-WMT output/SmtCal** to the actual fixed output directory, for example:
   `~/Documents/rswmt_conducted_1.0.0-b518+42/output/SmtCal`.
   Do not select only an old timestamp subfolder.
4. Leave **Live logs** blank initially. The monitor will also read `.log` files
   below the output directory. Only set another directory if its logs use the
   same per-DUT format as the supplied samples.
5. Selecting RS-WMT changes an unchanged 30-second start timeout to 240 seconds.
   This allows time for files that appear only after the test completes. Other
   custom timeout values remain unchanged. **儲存** saves; **取消** cancels.

## Run one test round

1. Press **開始監控** (Start monitoring), or **Command + Shift + M**.
2. Run **Run All** in RS-WMT.
3. Compare Slot1–4 against DUT1–4. CSV `tc=Slot...` values determine the mapping;
   filename order does not. Once a complete CSV is observed, its SN appears with
   COMPLETING. After five seconds without changes, PASS or FAIL is displayed and
   the dashboard comes to the front.
4. A Fail without a serial number remains FAIL. Missing files do not imply PASS
   or NOTEST. The event/session tab records rejected or conflicting data.
5. Start a new monitoring round before the next RS-WMT run. Existing files are
   ignored. Stop manually if a DUT never exports a result and other DUTs finish.

Testing and early SN display require logs that are available during the test.
Archived logs copied out only at completion cannot provide live progress. A
single item's PASS in the log never determines the final product result.
The test-time limit starts when the monitor first observes activity for that
Slot. A timed-out Slot keeps TIMEOUT even if its result arrives later.

## Return pilot feedback

Record the app version, macOS version and the configured paths. Verify:

- Startup and settings persistence after closing/reopening the app.
- All four DUT/Slot serial numbers and final statuses, including initialization
  failures without a serial number.
- Whether `.log` files grow while the test is running, and in which directory.
- The global start shortcut, final-result foreground behavior and per-Slot timeout.
- Multiple rounds without old or duplicate results entering a new round.

For a mismatch, preserve the complete run directory containing paired CSV/log
files, the application's Session directory (available from Settings), and an HMI
screenshot from that same run. The current supplied files cover four PASS results;
real FAIL and live-update samples are still needed for station acceptance.

## Build owner

On a native M4 builder (macOS 15 or later), install Python.org 3.12.10 universal2,
then run `./scripts/build_macos15_arm64_log_solution.sh` from the application source folder.
It uses a dedicated environment and checks every bundled arm64 binary against
macOS 15.0 before signing/creating the ZIP and SHA-256 file. Open the packaged app
on the builder, then test it on 15.4.1. Supporting the entire 15.x range also requires
runtime testing at the minimum supported version on compatible hardware.
