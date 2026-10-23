# Checkpoint notes for Martin (PM)

SendToAgent is not exposed to this executor (GetDynamicTools search for "SendToAgent" returned no match), so notes are kept here for relay.

## (a) LEAP-1A numbers + ETA — 2026-10-22 22:28 (Asia/Shanghai) — priority
Settled numbers (all from public sources, verified 22:30):
- Architecture: dual rotor; single-stage fan, 3-stage LPC (booster), 10-stage HPC, annular combustor, 2-stage HPT, 7-stage LPT — EASA TCDS E.110 Issue 14 (11 May 2026), section 2 (PDF fetched directly: https://www.easa.europa.eu/en/downloads/20086/en).
- Length 3,328 mm (fan case fwd flange to turbine rear frame aft flange); max envelope 2,543 W x 2,368 H mm — EASA TCDS E.110 section 4; same in Japan CAB TADS No.778.
- Fan diameter 78 in (1,981 mm) — CFM https://www.cfmaeroengines.com/leap and Safran LEAP-1A product page.
- 18 fan blades (3D-woven RTM composite), bypass ratio 11:1, 19 fuel nozzles, booster = 3 rotor + 4 stator rows, HPC = IGV + 4 variable + 5 fixed stator rows — Airbus A320neo CFM LEAP-1A technical training manual (ATA 70/72, public copies on pdfcoffee/slideshare); 18 blades + 11:1 also in AirInsight (citing CFM) and Wikipedia.
- Caveat: no CFM/Safran official page states 18 blades/BPR 11:1 in fetchable text; those two come from the Airbus training manual + secondary sources, which all agree.
- The 3,328 mm length excludes inlet cowl and exhaust plug, so the nacelle lip and plug are stylized extensions.
ETA: finals ~05:00 on 10-23, on track; no accuracy cuts needed.

## (b) Side-view proportion preview — 2026-10-22 22:33 (Asia/Shanghai)
- previews/side_01.png: orthographic half-section (1280x640). Thin red bars mark x=0 and x=3.328 m (EASA flange-to-flange length) and r=±0.991 m (78 in fan). Fan tip, LPC 3 rotors / 4 stators, HPC IGV + 10 rotors + 9 stators, annular combustor, HPT 2 stages, LPT 7 stages and the TRF all fall inside the 3.328 m station. Nacelle inlet lip (-0.80 m) and plug tip (4.0 m) are stylized extensions past the flanges.
- Build: 104 objects, 125k verts, 0.5 s; side render 16 s. On track for ~05:00.

## (c) Mid-quality cutaway + exterior — 2026-10-22 22:47 (Asia/Shanghai)
- previews/mid_03_cut.png and previews/mid_03_ext.png (1280x720, 64 samples, ~45 s and ~38 s each). Core crop: previews/crop_mid03_core.png.
- Cutaway wedge 110° (widened from 90°; at 90° the booster sat behind the fan ring), full ring of 18 fan blades kept. Dark studio, restrained metals, brick-coral cut caps; LP shaft caps blue, HP shaft caps copper.
- 10-part checklist (all identifiable in mid_03_cut): 1 Fan ✓ 2 LPC booster ✓ 3 HPC ✓ 4 Combustor (glow) ✓ 5 HPT (gold, small but visible) ✓ 6 LPT (blue) ✓ 7 Exhaust nozzle + plug ✓ 8 Bypass duct + OGVs ✓ 9 Nacelle ✓ 10 Dual-rotor shafts ✓
- Pylon stub (P2) is built but excluded from the exterior render (looked like a flat board; cleaner product shot without it). Finals expected well before 05:00.

## (d) Finals done, secret scan clean, ready to push (NOT pushed) — 2026-10-22 23:15 (Asia/Shanghai)
- renders/cutaway.png (1920x1080, 267 s) and renders/exterior.png (1920x1080, 368 s); engine.blend 2.2 MB (Cutaway + Exterior scenes, both verified to open and render: previews/blendcheck_v3.png); engine.py; README.md.
- Secret scan: gitleaks 8.21.2 on the tree and the full history found no leaks, and the manual grep was clean. See logs/secret-scan.txt.
- Git: local commits only, no remote. engine.blend and both final PNGs (2.0 and 1.7 MB) are committed; previews are ignored except previews/side_final.png.
- Delivered about 6 h ahead of the 05:00 target. Nothing from P0/P1 was cut; the P2 pylon is built but excluded from the exterior render.

## (e) Colour tweak, local only, NOT pushed (2026-10-23 08:19, Asia/Shanghai)
- Cut faces are now deep red instead of salmon: CutFace_DeepRed, specular 0.1, no emission, renders at about #8C2621 to #A10702. Fan blades are now dark charcoal composite instead of light grey: non-metallic, no coat, low specular, slight sheen.
- Previews: previews/tweak_cut.png and previews/tweak_ext.png (640x360, 32 samples), previews/mid_tweak5_cut.png (1280x720 check), and the iteration files prev_tweak1/2, mid_tweak3/4 with crops.
- Finals re-rendered at the same settings (1920x1080, 256 adaptive samples, threshold 0.015, 6 threads): cutaway 262.1 s, exterior 184.2 s. engine.blend regenerated; both scenes render their own camera (previews/blendcheck_tweak.png).
