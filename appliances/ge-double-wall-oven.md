# GE Double Wall Oven

- **Homebox Entity ID**: `585a83dc-dd0a-44b8-9aa8-4da40cd469e4`
- **Manufacturer**: GE Appliances
- **Model**: `JT5500SF5SS` (Series: `JT5500` - 30" Double Wall Oven)
- **Manual Part Number**: 49-80722 (Rev 03-14 GE)
- **Manual Attachment**: Stored in Homebox entity and locally at `images/processed/GE_Double_Wall_Oven_Manual.pdf`

---

## Specifications

| Spec | Value |
|---|---|
| **Type** | 30" Built-In Double Electric Wall Oven with Convection |
| **Total Capacity** | ~10.0 cu. ft. (5.0 cu. ft. Upper / 5.0 cu. ft. Lower) |
| **Cabinet Width** | 30" (76.2 cm) |
| **Cleaning Modes** | Self-Clean (Heavy/Normal) & Steam Clean |
| **Electrical Supply** | 240V / 208V AC, 60Hz, 40A dedicated circuit |

---

## Part & Accessory Numbers

- **Small Broiler Pan (8 ¾” × 1 ¼” × 13 ½”)**: `WB48X10055` (US) / `222D2097G001` (Canada)
- **Large Broiler Pan (12 ¾” × 1 ¼” × 16 ½”)**: `WB48X10056` (US) / `222D2097G002` (Canada)
- **XL Broiler Pan (17” × 1 ¼” × 19 ¼”)**: `WB48X10057` (US)
- **CitruShine Stainless Steel Wipes**: `WX10X10007`
- **CeramaBryte Stainless Cleaner**: `PM10X311`
- **Oven Light Bulb**: 40W appliance bulb (check socket type)
- **Full Parts List & Assembly Diagrams**: [JT5500SF1SS Bill of Materials](JT5500SF1SS/bill_of_materials.md)

---

## Error Codes & Diagnostics

| Code | Meaning | Action |
|---|---|---|
| `F20` / `F2` | Overheat or runaway temperature (>650°F bake, >915°F clean) | Turn off breaker immediately if overheating. Reset power 5 min. Test sensor WB21X10165 (~1100 Ω). If sensor OK, replace control board WB27X20240 / relay board WB27T11326. |
| `F— (Number/Letter)` | Function error code | Press **Cancel/Off**. Allow oven to cool for 1 hour. If repeating, disconnect power at circuit breaker for 30 seconds, then reconnect. If persists, service required. |
| `LOCK DOOR` (flashing) | Self-clean selected but door open | Close oven door securely. |
| `LOCKED` (solid) | Door locked due to high internal heat | Normal during self-clean or cool down; wait until temperature drops. |
| Display blank / unresponsive | Power interruption or tripped breaker | Check house breaker / fuse box. Reset clock once power returns. |
| Excessive smoking during clean | Heavy grease buildup or food on floor | Press **Cancel/Off**. Open windows to ventilate. Wait until `LOCKED` turns off before opening door to wipe residue. |

### Diagnostic Guide: F20 / F2 Error (Over-Temperature / Runaway Heat)

- **Condition**: Electronic control board detects oven cavity exceeds safety limits (>650°F in bake/normal mode, >915°F in self-clean).
- **Safety Precaution**: If heating elements remain energized/glowing red when oven is turned off or cavity temperature escalates uncontrollably, immediately shut off power at the dedicated circuit breaker panel.
- **Troubleshooting Steps**:
  1. **Hard Reset**: Shut off power at the circuit breaker for 5 minutes. If code returns upon power-up or heating, proceed with hardware checks.
  2. **Oven Sensor Probe Inspection**:
     - Remove power at circuit breaker.
     - Access and unscrew the temperature sensor probe inside the oven cavity (upper or lower cavity callout 253, part [`WB21X10165`](JT5500SF1SS/bill_of_materials.md); see schematics [`02_UPPER_OVEN.jpg`](JT5500SF1SS/diagrams/02_UPPER_OVEN.jpg) / [`04_LOWER_OVEN.jpg`](JT5500SF1SS/diagrams/04_LOWER_OVEN.jpg)).
     - Measure resistance across probe terminals with a multimeter at room temperature (~70°F / 21°C). Healthy sensor reads **~1,080 to 1,100 Ω**. Replace probe if reading is open (infinite resistance) or 0 Ω.
  3. **Wiring Harness Check**: Inspect harness wires between sensor probe and control board for crimps, shorts, or burns.
  4. **Control Board / Relay Replacement**: If sensor resistance is normal (~1,100 Ω) and harness intact, the heating element relay on the control board has fused/welded closed. Replace control board [`WB27X20240`](JT5500SF1SS/bill_of_materials.md) or relay daughter board [`WB27T11326`](JT5500SF1SS/bill_of_materials.md) (callouts 16 & 270 in [`01_CONTROL_PANEL.jpg`](JT5500SF1SS/diagrams/01_CONTROL_PANEL.jpg)).

---

## Maintenance & Care

- **Self-Clean Cycle**: Remove all oven racks (shiny flat racks will discolor/warp if left inside during high-heat self-clean). Wipe heavy spills before starting cycle.
- **Steam Clean**: Use 1 cup of water in oven bottom for light, everyday soils; takes ~30 minutes.
- **Stainless Steel Surfaces**: Clean with CeramaBryte (`PM10X311`) or CitruShine (`WX10X10007`); wipe in direction of grain; do not use steel wool or abrasive powders.
