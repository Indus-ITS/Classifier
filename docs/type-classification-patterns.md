# How the `type` column is classified from `title`

This is a plain-English summary of the patterns the classifier uses to fill
the **`type`** column (a 3-letter document-type code) from a document's
**`title`** alone. It is generated from the live rules — see
`src/classifier/config/type_keywords.py` and `type_overrides.py`.

## How a title becomes a type

1. **Normalise the title** — uppercase; strip punctuation (keeping `&` and `/`),
   parentheses, and revision/sheet noise (`REV 2`, `SHEET 3 OF 5`); fold
   regular plurals to singular. The title becomes a list of word tokens.
2. **Hard overrides first** — if the title contains an exact override phrase
   (below), that type is chosen immediately (longest phrase wins).
3. **Learned phrase scoring** — otherwise each type scores by the trigger
   phrases it matches in the title; higher-weight phrases count more.
4. **Negative suppression** — a type can be cancelled if a known false-signal
   phrase is present.
5. **Confidence gate** — the top type wins only if its score is high enough and
   clears the runner-up by a margin; otherwise `type` is left blank.
6. **Drawing/Sketch fallback** — if nothing else fired but the title literally
   says DRAWING or SKETCH, the type is set to `DWG`.

Matching is **exact phrase matching** — there is no fuzzy/spell-correction
matching, so each pattern below is a literal word or phrase.

There are **31 type codes** with rules. Each maps to a final
class (Drawing / Sheet / Document) shown in the table.

## Type codes and the title patterns that trigger them

| Type | Class | Trigger phrases (title contains…) | Hard-override phrases |
|------|-------|-----------------------------------|-----------------------|
| **BOD** | Document | `BASIS`, `DESIGN BASIS`, `PROJECT DESIGN`, `PROJECT DESIGN BASIS`, `PROCESS DESIGN`, `PROCESS DESIGN BASIS` | — |
| **CAL** | Document | `CALCULATION`, `CALCULATION NOTES`, `NOTES`, `CALCULATION NOTE`, `NOTE`, `STRUCTURAL CALCULATION`, `STRUCTURAL CALCULATION NOTE`, `CABLE SIZING` | — |
| **DAL** | Drawing | `LAYOUT AREA`, `LAYOUT`, `ARRANGEMENT LAYOUT`, `ARRANGEMENT LAYOUT AREA`, `CIVIL GENERAL`, `CIVIL GENERAL ARRANGEMENT`, `GENERAL ARRANGEMENT LAYOUT`, `CABLE ROUTING` | `ELECTRICAL EQUIPMENT LAYOUT`, `ELECTRICAL CABLE ROUTING` |
| **DAS** | Document | `DATA`, `DATA SHEET`, `SHEET`, `PROCESS DATA`, `PROCESS DATA SHEET`, `MECHANICAL DATA`, `MECHANICAL DATA SHEET`, `GAUGES` | `DATASHEET`, `DATA SHEET`, `MECHANICAL DATASHEET`, `INSTRUMENT DATASHEET`, `ELECTRICAL DATASHEET` |
| **DBD** | Drawing | `BLOCK`, `BLOCK DIAGRAM`, `BLOCK DIAGRAM DB`, `DIAGRAM DB`, `SYSTEM BLOCK`, `SYSTEM BLOCK DIAGRAM`, `LIGHTIING`, `LIGHTIING SYSTEM` | `BLOCK DIAGRAM`, `SCHEMATIC BLOCK DIAGRAM`, `ARCHITECTURE DIAGRAM` |
| **DCE** | Drawing | `CAUSE`, `EFFECT DIAGRAM`, `SYSTEM CAUSE` | `CAUSE & EFFECT`, `CAUSE & EFFET`, `CAUSE AND EFFECT` |
| **DDT** | Drawing | — | `DETAILS FOR`, `DETAIL FOR`, `FOUNDATION DETAILS`, `FOUNDATION DETAIL`, `STRUCTURAL DETAILS`, `STRUCTURAL DETAIL`, `MODIFICATION DETAILS`, `NOZZLES DETAILS`, `BRACKET DETAILS`, `CLEATS DETAILS`, `HANDRAIL DETAILS` |
| **DGA** | Drawing | `PIPING LAYOUT`, `PIPING LAYOUT DRAWING`, `LAYOUT DRAWING`, `PUMP AREA`, `RACK AREA`, `GA`, `GA DRAWING`, `NEW RACK` | `GENERAL ARRANGEMENT`, `GENERAL ARRANGMENT`, `GENERAL ARRANGEMENT DRAWING`, `PIPING GENERAL ARRANGEMENT` |
| **DPP** | Drawing | `PLOT`, `PLOT PLAN`, `PLAN AREA`, `PLOT PLAN AREA`, `OVERALL`, `OVERALL PLOT`, `OVERALL PLOT PLAN` | `PLOT PLAN` |
| **DSD** | Drawing | `INTERCONNECTION`, `INTERCONNECTION DIAGRAM`, `PM`, `DIAGRAM PM`, `INTERCONNECTION DIAGRAM PM`, `MOTOR STARTER`, `MOTOR STARTER SUBSTATION`, `STARTER` | — |
| **DSL** | Drawing | `LINE DIAGRAM`, `SINGLE`, `SINGLE LINE`, `SINGLE LINE DIAGRAM`, `SUBSTATION NO`, `LINE`, `NO`, `SUBSTATION` | — |
| **DWG** | Drawing | `TYPICAL`, `CONSTRUCTION DRAWING`, `DP`, `DP DT`, `DP DT DIAGRAM`, `DT`, `DT DIAGRAM`, `CONSTRUCTION` | `CONSTRUCTION DRAWING` |
| **IDX** | Sheet | `INDEX`, `INSTRUMENT INDEX`, `AREA/MODEL`, `AREA/MODEL INDEX`, `AREA/MODEL INDEX DRAWING`, `DESIGN AREA/MODEL`, `DESIGN AREA/MODEL INDEX`, `INDEX DRAWING` | — |
| **ISO** | Drawing | — | `ISOMETRIC`, `ISOMETRICS` |
| **LST** | Sheet | `LIST`, `I/O`, `I/O LIST`, `DCS`, `DCS I/O`, `DCS I/O LIST`, `EQUIPMENT LIST`, `EQUIPMENT LIST LOCATION` | — |
| **MSD** | Drawing | `MATERIAL SELECTION DIAGRAM`, `SELECTION DIAGRAM`, `MATERIAL SELECTION`, `SELECTION`, `SELECTION DIAGRAM LP`, `SELECTION DIAGRAM MANIFOLDS`, `UTILITY MATERIAL`, `UTILITY MATERIAL SELECTION` | `MATERIAL SELECTION DIAGRAM` |
| **MTO** | Sheet | `MTO`, `BULK MTO`, `PIPING MTO` | `MTO` |
| **PFD** | Drawing | `FLOW DIAGRAM`, `UTILITY FLOW`, `UTILITY FLOW DIAGRAM`, `PROCESS FLOW`, `PROCESS FLOW DIAGRAM`, `FLOW DIAGRAM LP`, `FLOW DIAGRAM MANIFOLDS` | `PROCESS FLOW DIAGRAM`, `UTILITY FLOW DIAGRAM`, `HEAT AND MATERIAL BALANCE`, `HEAT AND MATERIALS BALANCE` |
| **PHL** | Document | `PHILOSOPHY`, `CHANGE`, `CHANGE OVER`, `CHANGE OVER PHILOSOPHY`, `HSE PHILOSOPHY`, `OVER`, `OVER PHILOSOPHY`, `EXECUTION PHILOSOPHY` | `PHILOSOPHY` |
| **PID** | Drawing | `INSTRUMENT DIAGRAM`, `PIPING & INSTRUMENT`, `INSTRUMENT`, `DISTRIBUTION`, `AIR DISTRIBUTION`, `AIR`, `DIAGRAM INSTRUMENT`, `DIAGRAM NITROGEN` | `P&ID`, `PIPING & INSTRUMENT`, `PIPING AND INSTRUMENT`, `PIPING & INSTRUMENTATION`, `PIPING AND INSTRUMENTATION`, `PIPING & INSTRUMENTATION DIAGRAM`, `PIPING AND INSTRUMENT DIAGRAM` |
| **PLN** | Document | `HSE PLAN`, `EXECUTION PLAN`, `INSPECTION`, `INSPECTION PLAN`, `QUALITY INSPECTION`, `QUALITY INSPECTION PLAN`, `QUALITY` | `EXECUTION PLAN`, `QUALITY PLAN`, `HSE PLAN`, `INSPECTION PLAN`, `MANAGEMENT PLAN`, `PROJECT PLAN`, `CONTINGENCY PLAN`, `PROCUREMENT PLAN`, `MOBILIZATION PLAN`, `COMMISSIONING PLAN`, `EMERGENCY RESPONSE PLAN` |
| **PRO** | Document | `METHOD`, `METHOD STATEMENT`, `STATEMENT`, `ERECTION`, `CONCRETE`, `TEMPORARY`, `PROCEDURE`, `TESTING` | `PROCEDURE`, `METHOD STATEMENT`, `WORK INSTRUCTION` |
| **PSF** | Drawing | `SAFEGUARDING`, `SAFEGUARDING DIAGRAM`, `PROCESS SAFEGUARDING`, `PROCESS SAFEGUARDING DIAGRAM`, `SAFEGUARDING DIAGRAM MANIFOLD`, `UTILITY SAFEGUARDING`, `UTILITY SAFEGUARDING DIAGRAM`, `DIAGRAM MANIFOLD` | `SAFEGUARDING DIAGRAM`, `SAFEGUARDING MEMORANDUM` |
| **REG** | Sheet | `REGISTER`, `ACTION`, `ACTION TRACKING`, `ACTION TRACKING REGISTER`, `HSE ACTION`, `HSE ACTION TRACKING`, `TRACKING`, `TRACKING REGISTER` | `REGISTER` |
| **REP** | Document | `REPORT`, `ANALYSIS REPORT`, `CLOSE`, `CLOSE OUT`, `CLOSE OUT REPORT`, `OUT`, `OUT REPORT`, `STRESS ANALYSIS REPORT` | — |
| **REQ** | Document | `MATERIAL REQUISITION`, `REQUISITION`, `MATERIAL`, `CS`, `DUPLEX`, `DUPLEX STAINLESS`, `DUPLEX STAINLESS STEEL`, `FLOATING` | — |
| **SCH** | Sheet | `SCHEDULE`, `CABLE SCHEDULE`, `BOX`, `BOX SCHEDULE`, `HV LV`, `HV LV POWER`, `INSTRUMENT CABLE SCHEDULE`, `INSTRUMENT JUNCTION BOX` | `SCHEDULE` |
| **SOW** | Document | `SCOPE`, `WORK`, `MODIFICATION SCOPE`, `DESIGN & EXECUTION`, `DETAIL DESIGN`, `GRE VENDORS`, `VENDORS`, `ICSS` | — |
| **SPC** | Document | `SPECIFICATION`, `INSTRUMENT INSTALLATION`, `AREA EQUIPMENT`, `BOXES`, `HAZARDOUS AREA EQUIPMENT`, `INSTALLATION BULK`, `INSTALLATION BULK MATERIAL`, `INSTRUMENT INSTALLATION BULK` | — |
| **STD** | Document | `STANDARD`, `INSTALLATION STANDARD`, `STANDARD DRAWING`, `EARTHING INSTALLATION`, `EARTHING INSTALLATION STANDARD`, `LIGHTING INSTALLATION`, `LIGHTING INSTALLATION STANDARD`, `POWER INSTALLATION` | — |
| **TBE** | Document | — | `TBE`, `TECHNICAL BID EVALUATION`, `TECHNICAL BID EVALATION`, `TECHNICAL BID EVALATUION` |

## Negative (suppression) phrases

If one of these phrases appears, the listed type is suppressed (it stops it
from being chosen on a misleading keyword):

| Type | Suppressing phrases |
|------|---------------------|
| **IDX** | `DRAWING` |
| **PID** | `MTO`, `SCHEDULE`, `LAYOUT`, `LIST`, `BULK`, `LOCATION`, `INSTRUMENT LOOP`, `INSTRUMENT LOOP/SEGMENT`, `INSTRUMENT INSTALLATION`, `INSTRUMENT JB`, `INSTRUMENT INDEX`, `INSTRUMENT HOOK`, `LOOP DRAWING` |

## Notes

- The trigger phrases are **learned from labelled examples** in
  `input/classified_csv/`; re-running `learn-type-keywords` regenerates them.
- Only the strongest phrases per type are shown above (top 8); the full list
  lives in `src/classifier/config/type_keywords.py`.
- A title that matches no pattern strongly enough leaves `type` blank rather
  than guessing.
