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
- a top-down trajectory preview
- JSON design save/load
- trajectory CSV export

## Output Files

The default saved design path is:

```text
configs\stimulus_design.generated.json
```

Generated trajectory CSVs should be exported to `artifacts\`, which is ignored by Git.

## Relationship To Study 5 Replication

`pps-generate` remains the locked Study 5 replication path. The designer adds a configurable layer for future variants and pilot work. Designs are explicit JSON artifacts so changes to azimuth, radius, direction, path length, or speed can be reviewed before they are used in a generated stimulus set.
