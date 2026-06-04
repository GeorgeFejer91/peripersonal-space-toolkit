# Stimulus Designer

The stimulus designer is a Windows UI for drafting custom looming-stimulus configurations while preserving the Study 5 defaults as a reproducible baseline.

Launch it with:

```bat
windows\Launch_Stimulus_Designer.bat
```

Or from an installed environment:

```powershell
pps-design
```

## Design Controls

The designer currently covers:

- SOFA HRIR file selection and validation through the `sofar` package
- noise definitions for pink, blue, white, and brown noise
- per-noise azimuth, elevation, and gain
- snapping noise orientations to the nearest available SOFA source position
- looming trajectory radius, path direction, path length, propagation speed, start/end azimuth, elevation, and lead/tail padding
- protocol schedule controls for repetitions per condition, SOA values, spatial values, catch-trial percentage, respiratory phases, blocks, participants, and random seed
- auditory motion directions, tactile body sites, baseline-specific SOAs, and exact catch-trial counts for paradigms that report fixed trial counts
- preloadable published-study templates with verification status and citation metadata
- paired SOA/spatial values for distance-at-tactile designs, or full-factorial SOA x spatial designs for broader PPS variants
- a top-down trajectory preview
- JSON design save/load
- trajectory CSV export
- protocol CSV export

## Output Files

The default saved design path is:

```text
configs\stimulus_design.generated.json
```

Generated trajectory CSVs should be exported to `artifacts\`, which is ignored by Git.

Bundled literature templates live in:

```text
study_templates\
```

## Relationship To Study 5 Replication

`pps-generate` remains the locked Study 5 replication path. The designer adds a configurable layer for future variants and pilot work. Designs are explicit JSON artifacts so changes to azimuth, radius, direction, path length, or speed can be reviewed before they are used in a generated stimulus set.

The protocol CSV export materializes the requested trial family before audio generation: audio-tactile rows, optional tactile-only baselines, and catch trials computed from the target catch percentage.

Templates marked `partial` identify a published paradigm and preload its core structure, but should not be treated as exact replications until the original paper/protocol has been checked for every field.
