# Study 5 Protocol Notes

This toolkit packages the audio-tactile peripersonal-space task used for Study 5.

## Timing Contract

- spoken breathing instruction: exactly 4.000 s
- looming stimulus segment: exactly 4.000 s
- full trial: exactly 8.000 s
- tactile cue duration: 100 ms
- tactile SOAs: 0, 300, 800, 1500, 2200, 2700 ms
- looming approach: 110 cm to 10 cm over 3 s, embedded in a 4 s stimulus window

## Trial Families

- audio-tactile trials: looming noise plus tactile cue
- baseline trials: tactile cue without looming
- catch trials: looming noise without tactile cue

## Respiratory Phases

The public assets include separate 4-second inhale and exhale instruction WAVs. The generator combines these instructions with stimulus segments to create 8-second trials.

## Dashboard Preload

The HTML dashboard profile `study5_box_breathing_pps` is the unpublished local Study 5 preload. It is separate from published-study profiles such as Canzoneri et al. (2012) and preloads the bundled 4-second inhale/exhale instruction WAVs plus the default `Inhale instruction | Looming Stimulus` and `Exhale instruction | Looming Stimulus` filmstrip rows.

This profile is the default dashboard startup profile. Fresh launches and scratch-custom startup states initialize from Study 5 so the current lab workflow is ready without selecting a profile manually.

## Data Outputs

The runner stores loopback recordings and demographics locally. The decoder reconstructs trial timing from WAV recordings, then writes diagnostics, final CSVs, and summaries under the decoded artifact directory.
