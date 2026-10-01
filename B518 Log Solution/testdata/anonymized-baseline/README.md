# Anonymized baseline samples

This small replay set is derived from the supplied machine samples. Source files are read only; the preparation tool records selected source signatures before copying and verifies they remain unchanged. Serial-number values and path components are replaced with stable sample identifiers, and B482 configuration names are replaced with `ANONCONFIG`. The tool checks output paths and file contents for the selected original serials.

Coverage includes one Atlas DFU archive record, one Atlas FCT archive record, one complete four-slot B482 TestData run, four B482 CaseInfo files for 2026-08-21, and one four-slot RS-WMT final-result run. Optional RS-WMT companion logs are omitted because final-result replay does not require them.

To regenerate the set, pass the read-only source directory and a new or empty output directory:

```zsh
python3 tools/anonymize_baseline_samples.py "/path/to/ATE Test doc" "/path/to/new/anonymized-baseline"
python3 tools/replay_baseline_samples.py --caseinfo-date 2026-08-21 "/path/to/new/anonymized-baseline"
```

To replay the checked-in set from the application root (the directory containing `src/`, `tools/`, and `testdata/`):

```zsh
python3 tools/replay_baseline_samples.py --caseinfo-date 2026-08-21 testdata/anonymized-baseline
```
