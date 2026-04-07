# MMWK_ROID

> This document is intended for product, solution, and technical collaboration contexts. Any references to vital signs, ECG-like waveforms, or blood pressure are for capability description or research discussion only and do not constitute clinical or diagnostic claims.

ROID is a mmWave radar firmware line focused on high-sample ROI observation and fine-grained micro-motion analysis. Instead of stopping at coarse presence status, it emphasizes preserving continuous data around the local target region so teams can carry the signal forward into vital-sign estimation and research-oriented algorithm validation.

For teams that want to go beyond "detecting something" and continue into heart rate, respiration, subtle periodic motion, or deeper human-signal research, the value of ROID is not just "giving a result." It provides a bridgeable signal path from ROI raw data to upper-layer analysis.

## Key Characteristics

- It does not stop at a coarse "presence / no presence" conclusion. The focus stays on ROI data that is more suitable for analyzing subtle human motion.
- It preserves layered outputs from raw ROI data to phase, then to breath-band and heart-band signals, which allows different algorithm stacks to take over progressively.
- It can support both real-time pipelines and host-side modeling, validation, and research workflows.
- It currently spans both the `6843` and `6432` chip families, which helps teams reuse the same ROI-oriented data path across different hardware forms and reduce migration cost.
- For teams trying to move from "it can detect" to "it can observe and analyze in more detail," ROID provides more headroom.

## Typical Users

- Customers who want to move product capability beyond coarse presence detection and into finer vital-sign observation.
- Sales, solution, and FAE teams that need to communicate differentiation around vital signs, research potential, and future expansion.
- Technical teammates who want to connect to the ROID data path quickly and build further validation, modeling, or algorithm work on top of it.

## Output Layers

The value of ROID is not only in a final answer. It also lets different teams enter the signal path at different layers:

- `INFO`: frame-level state such as ROI width, target presence, SNR, and motion intensity.
- `RAW ROI`: suitable for lower-level offline analysis, custom algorithms, and raw signal research.
- `PHASE`: suitable for observing continuous micro-motion and phase variation, and acts as a key intermediate layer for further analysis.
- `BREATH`: suitable for respiration-related observation, validation, and tuning.
- `HEART`: suitable for heart-related observation, validation, and research.

## Typical Use Cases

### Higher-Precision Heart / Respiration Observation
**Positioning: current capability**

When the goal is not just presence judgment but continuous observation of subtle periodic human motion, ROID is a better fit as the firmware base. It preserves more signal depth around the ROI so teams can keep optimizing heart-rate, respiration, and signal-quality logic instead of being locked into a single black-box result.

### ECG-like Waveform Research
**Positioning: research direction**

ROID is better understood as a data entry point for ECG-like waveform research, not as a finished ECG product. For teams that want to observe subtle heart-related periodic waveforms, run comparison experiments, or validate new algorithms, it provides an ROI phase path that is easier to keep exploring.

### Blood-Pressure Research and Algorithm Validation
**Positioning: research direction**

In the blood-pressure direction, ROID is better positioned as a research and modeling entry point. It can provide a finer data foundation for feature extraction, calibration experiments, offline evaluation, and algorithm validation, but it should not be interpreted as a finalized blood-pressure product capability. This direction still depends on reference-device comparison, calibration flows, and host-side modeling and validation.

## How To Integrate Through mmwk_sensor_bridge

If you want to connect ROID into an upper-layer system or validation workflow, [MMWK Bridge Mode](./bridge.md) is the most direct entry point. `mmwk_sensor_bridge` is better suited to act as a transparent bridge between the radar side and the host side so teams can first close the loop of firmware loading, data forwarding, and upper-layer processing before adding more product logic.

## Capability Boundaries

- Today, ROID is better used as a firmware base for higher-precision heart / respiration related capability than as a closed solution that only emits a single final result.
- ECG-like waveform and blood-pressure related topics should be understood as research and algorithm-validation directions, suitable for signal exploration, comparison experiments, and modeling iteration.
- This document does not describe ROID as a medical decision tool. Real-world performance still depends on installation, scene stability, target posture, and the upper-layer algorithm chain.

## Commercial Licensing

ROID firmware is provided under commercial license. For evaluation, procurement, or integration, contact `bp@wavvar.com`.

## Summary

ROID is currently best suited as a firmware base for higher-precision heart / respiration observation while also preserving an expandable data entry point for ECG-like waveform and blood-pressure research directions. For teams trying to move from "it can detect" to "it can observe, study, and validate in more detail," ROID offers a more extensible signal path than coarse presence-only sensing.
