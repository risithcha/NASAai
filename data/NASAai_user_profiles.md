# TerraScan / AeroField Team — Per-User AI Reference Document
> Auto-generated from NASA Dream With Us 2026 Engineering Notebook (TerraScan, AeroField Team)
> Purpose: Give the NASAai assistant fast, structured access to each team member's domain, sections, keywords, and expertise so per-user response filtering is accurate.

---

## Team Overview

| Field | Value |
|---|---|
| Project Name | TerraScan |
| Team Name | AeroField |
| Challenge | NASA Dream With Us High School Engineering Design Challenge |
| Submission Date | January 23, 2026 |
| Lead Institution | Glacier Peak High School |
| Participating Institution | Bothell High School |
| Coach / Advisor | Charitha Kankanamge (Amazon Software Development Manager) |
| Coach Email | uoccharitha@gmail.com |
| Coach Phone | (812) 360-1680 |

---
---

# USER: Risith Kankanamge — Technical Lead

## Identity
- **Full Name:** Risith Kankanamge
- **Role:** Technical Lead
- **Grade:** 11th Grade Junior
- **Age:** 16
- **School:** Bothell High School, 9130 NE 180th Street, Bothell, WA 98011
- **Email:** risithc@gmail.com

## Core Domain Expertise
Systems engineering, software architecture, control systems design, hardware/software interfaces, subsystem integration, design trade studies, center of gravity (CG) analysis, propulsion selection, command and control (C3) specification.

## Background That Earned This Role
- Previously served as **Software Lead** on Glacier Peak / Bothell High School Robotics Club software team (FRC).
- Plans to major in **Computer Science** (now also considering aerospace engineering and/or robotics engineering after this challenge).
- Strong background in programming enabled him to lead all technical and software-adjacent architecture decisions.

## Owned Sections (Lead Authority)
| Section | Title |
|---|---|
| 2.1 | Engineering Design Process |
| 2.3.1 | Air Vehicle (Airframe Subsystem) |
| 2.3.2 | Command, Control, and Communications (C3) |
| 3.3.1 | Detect and Avoid (DAA) |

## Cross-Functional Contributions
- Completed all **weight and power budgets** (Section 2.1) that constrained every other subsystem.
- Performed **center of gravity (CG) analysis** — finalized CG at 27.2% MAC (within 25–30% target).
- Selected all final components: T-Motor U3 outrunner (500 KV), Pixhawk 4 Mini FC, RFD900x 900 MHz radio, 6S 5000 mAh LiPo batteries, 11x7 composite propeller, ESC-40A.
- Designed the **semiautonomous C3 architecture** combining RC (2.4 GHz) for low-latency pilot input and 900 MHz telemetry for bidirectional data.
- Specified **DAA system**: ADS-B receiver (150 m cooperative detection range), three ultrasonic rangefinders (forward, left, right, ~5 m obstacle range), barometric altitude geofencing.
- Designed the avionics power architecture (5V/3A dedicated switching regulator to prevent brownouts; inline fuse on avionics bus).
- Receives mission requirements from Mission Lead; provides air vehicle performance data back to Mission Lead for analysis.

## Key Technical Decisions Owned
- **Airframe configuration selection:** Fixed-wing (over quadcopter and hybrid VTOL) — driven by 35-minute endurance vs. 18 min for quadcopter, and lower mechanical complexity.
- **Material selection:** Foam core with fiberglass/carbon fiber skins (saved ~300 g vs. aluminum).
- **Battery configuration change:** Shifted from one 6S 8000 mAh to **two 6S 5000 mAh batteries in series-parallel**, mounted on either side of fuselage to balance CG.
- **C3 architecture:** Semiautonomous (not fully manual, not fully autonomous) — onboard DAA decision logic, with two ground crew roles (Pilot + Mission Monitor).
- **Propulsion thermal management:** Passive ventilation holes in fuselage (avoided active cooling to save weight and power).

## Owned Keywords / Domain Terms
`airframe`, `fixed-wing`, `fuselage`, `wingspan`, `chord`, `MAC`, `CG`, `center of gravity`, `weight budget`, `power budget`, `C3`, `command and control`, `telemetry`, `RC`, `Pixhawk`, `RFD900x`, `ADS-B`, `DAA`, `detect and avoid`, `ESC`, `T-motor`, `KV`, `propeller`, `composite`, `foam core`, `carbon fiber`, `fiberglass`, `servo`, `subsystem architecture`, `avionics`, `IMU`, `GPS`, `flight controller`, `semiautonomous`, `waypoint`, `lost-link`, `RTH`, `return to home`, `stabilization loop`, `wing loading`, `cruise power`, `188W`, `27.2 MAC`, `6S 5000mAh`, `series-parallel battery`

## Exclude Keywords (Other Members' Domains)
`cost analysis`, `Gantt chart`, `business case`, `operating cost`, `logistics`, `PR`, `press release`, `mission performance calculations`, `energy budget`, `benchmark mission`, `sample gathering payload`, `pest detection algorithm`, `concept of operations`, `safety requirements (general)`, `public affairs`

## STEM Impact & Career
Risith learned that software must account for physical engineering constraints — hardware/software integration. Expanded career consideration from pure CS to include **aerospace engineering and robotics engineering**. Learned about electrical power systems, payload design, and aerospace engineering first-principles.

---
---

# USER: Santhosh Ilaiyaraja — Mission Lead

## Identity
- **Full Name:** Santhosh Ilaiyaraja
- **Role:** Mission Lead
- **Grade:** 11th Grade Junior
- **Age:** 16
- **School:** Bothell High School, 9130 NE 180th Street, Bothell, WA 98011
- **Email:** santhosh.ilaiyaraja21@gmail.com

## Core Domain Expertise
Mission analysis, computational modeling, sensor systems, energy budgeting, safety engineering, quantitative/mathematical analysis, payload design, benchmark mission performance calculations, contingency procedures.

## Background That Earned This Role
- Chosen for Mission Lead due to **strong computational skills and background in math**.
- Background primarily in theory, discrete math, and algorithmic runtime analysis (computer science oriented).
- This challenge showed Santhosh how math can derive real-world engineering reality; now wants to pursue careers that **bridge CS with real-world physical problem solving**.

## Owned Sections (Lead Authority)
| Section | Title |
|---|---|
| 2.3.3 | Payload — Pest Detection |
| 2.3.4 | Payload — Sample Gathering |
| 3.1 | Concept of Operations (CONOPS) |
| 3.2 | Benchmark Mission |
| 3.3 | Safety Requirements (full section) |

## Cross-Functional Contributions
- Drove **mission requirements** that informed the Technical Lead's air vehicle design decisions (e.g., payload weight constraints → wing area sizing; camera height ceiling → flight altitude planning).
- Provided **quantitative justification** for system specifications (e.g., camera resolution requirements, GSD calculations).
- Completed **mission analysis January 6–11, 2026** covering: pre-mission, in-mission (pest detection + sampling), and post-mission ground activities.
- Defined concept of operations for **two ground crew roles**: Pilot (RC, maintains VLOS) + Mission Monitor (telemetry, sample triggering, hazard comms).
- Analyzed the **benchmark mission**: 3 flights × 28 min per flight, 15-min transitions (battery/sample swap), 2h 40m total elapsed time, covering 100 acres.

## Payload — Pest Detection (Section 2.3.3)
- **Sensor:** Ultra-lightweight 1080p RGB camera (~500 g, 3.5 W power draw).
- **Mounting:** Beneath nose fuselage for maximum orchard canopy field-of-view overlap.
- **Ground Sampling Distance (GSD):** 5 cm at 60 m altitude — sufficient to identify codling moth entry holes and frass staining.
- **Computer vision pipeline (3 steps):** (1) Identify regions containing fruit, (2) Identify presence/location of damage, (3) Tag GPS coordinates to produce a pest pressure map.
- **Height restriction:** Camera resolution limits detection altitude to ≤200 ft (affects loiter radius and spiral descent planning in Section 3.2).
- **Power trade-off:** Lower power 1.5W USB camera was explored but rejected — image quality too low for pest detection algorithm. Accepted the 3.5W draw.

## Payload — Sample Gathering (Section 2.3.4)
- **Mechanism:** Motorized mechanical gripper on linear actuator.
- **Extension:** 30 cm below fuselage bottom.
- **Power:** ~2–4 W during 10-second activation cycles.
- **Operation:** Human (Mission Monitor) views camera feed, decides to sample, sends command — semi-manual triggering (fully automated sampling explored and rejected for reliability).
- **Storage:** 12-slot foam container inside aircraft fuselage (6 samples per flight × 3 flights = 18 samples max/day).
- **Post-mission:** Container can be cooled to preserve samples for lab identification.

## Safety Requirements (Section 3.3)
Santhosh led all safety planning. Key safety systems:
- **Lost-link:** Automatic RTH → auto-land at farm center on radio link loss.
- **Battery safety:** Voltage monitor triggers RTH at 3.0 V/cell (18 V total for 6S); LiPo balance charger; storage at 3.8 V/cell; pre-flight puff/damage inspection.
- **DAA:** ADS-B for cooperative aircraft (150 m), ultrasonic rangefinders for non-cooperative obstacles (50 m); satisfies FAA UTM integration minimums.
- **Parachute:** Backup passive parachute via electronic locking mechanism (manual trigger via pilot tether pull).
- **Weather:** Cancel if sustained wind > 10 m/s or thunderstorms within 30 km; in-flight RTH if conditions degrade.
- **Manual override:** 3-position RC switch (Stabilized / Manual / RTH).
- **Public safety:** Visual boundary flags/rope, dedicated safety observer, landowner coordination.

## Owned Keywords / Domain Terms
`mission analysis`, `benchmark mission`, `CONOPS`, `concept of operations`, `pest detection`, `computer vision`, `GSD`, `ground sampling distance`, `1080p camera`, `RGB camera`, `sample gathering`, `gripper`, `linear actuator`, `sample storage`, `12-slot`, `foam container`, `energy budget`, `power consumption`, `endurance analysis`, `safety requirements`, `lost-link`, `RTH`, `parachute`, `battery voltage`, `ADS-B`, `DAA cooperative`, `weather contingency`, `VLOS`, `pilot roles`, `mission monitor`, `100 acres`, `3 flights`, `28 min`, `quantitative analysis`, `payload mass 850g`, `camera mounting`, `frass detection`, `entry hole detection`, `GPS tagging`

## Exclude Keywords (Other Members' Domains)
`cost analysis`, `Gantt chart`, `business case`, `PR strategy`, `press release`, `logistics`, `airframe design`, `CG analysis`, `propulsion selection`, `C3 architecture`, `Pixhawk configuration`, `motor KV`, `wing loading`, `composite materials`

## STEM Impact & Career
Before this challenge, Santhosh's experience was primarily theoretical CS (discrete math, algorithm runtimes). The challenge showed him that **math can derive real-world engineering reality**. He now sees how CS can bridge into physical engineering fields and wants to pursue careers solving real-world problems using computational skills.

---
---

# USER: Ritvik Rajkumar — Operations & Business Lead

## Identity
- **Full Name:** Ritvik Rajkumar
- **Role:** Operations and Business Lead / Team Leader / Captain
- **Grade:** 11th Grade Junior
- **Age:** 16
- **School:** Glacier Peak High School, 7401 144th Place SE, Snohomish, WA 98296
- **Email:** rajkumarritvik1@gmail.com

## Core Domain Expertise
Project management, timeline coordination, task dependency mapping, Gantt chart development, cost analysis, financial modeling, business strategy, economic analysis, logistics planning, public affairs and communications.

## Background That Earned This Role
- Chosen due to **strong background in math** applied to cost calculations, economic analysis, and mathematical relations.
- Computer science background, but this role focused on **engineering economics and project integration** rather than technical design.
- After this challenge, wants to take more **business-side engineering courses** — sees engineering as integrating technical decisions with economics.

## Owned Sections (Lead Authority)
| Section | Title |
|---|---|
| 2.2 | Project Plan (Gantt chart, timeline, task dependencies) |
| 4 (entire) | Business Case |
| 4.1 | Cost Analysis (Operating + Fixed) |
| 4.2 | Logistics Details |
| 4.3 | Economic Impact |
| 5 (entire) | Public Affairs / Communications Plan |
| 5.1 | Public Relations Strategy |
| 5.2 | Products to Be Created |
| 5.3 | Distribution Plan |
| 6 | Conclusion |

## Cross-Functional Contributions
- Coordinated between Technical Lead and Mission Lead to ensure design decisions were captured in the **schedule and budget**.
- Although not responsible for system design, ensured the designed system met **schedule, cost, and logistical constraints**.
- Drafted Section 2.2 Project Plan describing timeline development and Gantt Chart (January 17–21, 2026).
- Led **peer review cycle** January 19–21 for technical accuracy, gaps, and consistent style.

## Cost Analysis (Section 4.1) — Key Numbers
**Operating Cost Per Mission:**
| Item | Calculation | Cost |
|---|---|---|
| Energy | 3 flights × 88 Wh = 264 Wh × $0.30/Wh | $79 |
| Pilot labor | 2.25 hrs × $20/hr | $45 |
| Mission Monitor labor | 2.25 hrs × $20/hr | $45 |
| **Total per mission** | | **$169** |

**Fixed Costs (amortized over 5,000 missions / 5-year lifecycle):**
| Category | Total | Per Mission |
|---|---|---|
| Air Vehicle (fuselage, motor, servos, landing gear, ESC) | $435 | $0.09 |
| Batteries (2× 6S 5000 mAh) | $170 | $0.03 |
| Payload Detection (12 MP camera + mount) | $105 | $0.02 |
| Payload Sampling (gripper, actuator, container) | $100 | $0.02 |
| C3 System (Pixhawk, RFD900x, GPS, ADS-B, rangefinders, receiver) | $675 | $0.14 |
| GCS (laptop, RC transmitter, antenna) | $885 | $0.18 |
| Ground Support (transport case, charger, tools, pads, cooler) | $385 | $0.08 |
| **Total Fixed** | **$2,755** | **$0.55** |

**Total system cost: ~$6,200 | Per mission operating cost: ~$90–$169**

## Logistics Details (Section 4.2)
- **Personnel:** 2 people (Pilot + Mission Monitor), both present for full 2h 40m.
- **Pre-mission setup:** 30 min (aircraft prep, GCS checkout, preflight).
- **Three consecutive flights:** 28 min each + 15-min transitions (battery swap, sample swap).
- **Post-mission teardown:** 25 min (stowage, shutdown, sample preservation).
- **Setup time:** Under 30 min — enables same-day operations at multiple sites.
- **Transport:** All components fit in hard cases for field transport.

## Economic Impact (Section 4.3)
- Washington apple industry: **$2 billion annually** in fresh sales; **$9.5 billion total economic contribution**.
- Codling moth can destroy **80% of NW apple crops** if unmanaged.
- Potential WSU-estimated crop loss value: **$510–557 million** if infestations reach unmanageable levels.
- Traditional scouting cost: **$2,000–$2,250 per season** (saves user ~$1,500 vs. this UAS).
- ROI analysis at 25-farm scale (125 acres each): **$350,000–$460,000 annually with >750% ROI**.

## Public Affairs / Communications Plan (Section 5)
- **Campaign budget:** ~$3,400–$3,900 total.
- **Channels:** WSU Extension Network (free, 500 growers), Agricultural Trade Press ($200), Social Media (Facebook/Instagram/LinkedIn, $0–$500/mo), YouTube ($800 for pro demo video), Dealer Network ($1,500), Grower Cooperatives.
- **Posting schedule:** 2–3 posts/week during growing season (April–September); 1/week off-season.
- **Target metrics:** 50 grower inquiries in 6 months, 15 farms in pilot program, 2,000 social followers, 3 trade publication features, 2 dealer partnerships.

## Project Plan (Section 2.2) — Milestones
| Milestone | Date | Description |
|---|---|---|
| M1 | Nov 18, 2025 | Mentor Engagement (Charitha onboarded) |
| M2 | Dec 1, 2025 | Concept Review |
| M3 | Dec 10, 2025 | Preliminary Design Review |
| M4 | Dec 19, 2025 | Critical Design Review |
| M5 | Jan 11, 2026 | Safety Review |
| M6 | Jan 23, 2026 | NASA Submission |

## Owned Keywords / Domain Terms
`Gantt chart`, `timeline`, `task dependency`, `critical path`, `milestone`, `project plan`, `schedule`, `cost analysis`, `operating cost`, `fixed cost`, `per-mission cost`, `ROI`, `return on investment`, `economic impact`, `business case`, `logistics`, `personnel requirements`, `labor cost`, `budget`, `amortization`, `PR`, `press release`, `public affairs`, `distribution plan`, `social media`, `WSU extension`, `dealer network`, `grower cooperative`, `campaign budget`, `trade publication`, `5-year lifecycle`, `$6200`, `$169 per mission`, `$2755 fixed`, `2h 40m mission`, `30-min setup`

## Exclude Keywords (Other Members' Domains)
`airframe design`, `CG analysis`, `C3 architecture`, `Pixhawk`, `DAA system`, `propulsion`, `motor`, `telemetry radio`, `payload design`, `camera specs`, `gripper mechanism`, `computer vision`, `GSD`, `benchmark mission performance`, `energy budget calculations`, `safety protocols (technical)`

## STEM Impact & Career
Ritvik learned that engineering is not just about solving math problems — it requires **integrating technical decisions with economics and project management**. Plans to take more business-side engineering courses. Views his role as mirroring real-world **program management in aerospace engineering teams**.

---
---

# Shared Project Knowledge (All Users)

## What All Three Members Know
- **Codling moth** (Cydia pomonella) biology, damage patterns, lifecycle, economic impact in Washington state.
- **TerraScan UAS system** at a high level: fixed-wing aircraft, 1.57 m wingspan, 35-min endurance, 100-acre mission coverage, 6S LiPo battery, RGB camera, gripper payload.
- **Design phases:** Conceptual (Nov 25–Dec 1), Preliminary (Dec 2–10), Detailed (Dec 11–19), Winter break, Mission/Safety (Jan 6–11), Business/PA (Jan 12–16), Submission (Jan 17–23).
- **Mentor:** Charitha Kankanamge (Amazon, distributed systems); contributed to C3 architecture, data logging pipeline, and systems-level thinking.
- **Competition requirements:** NASA DWU Challenge 2026, range/endurance/payload/safety/regulatory compliance requirements.
- **Decision-making model:** Distributed leadership — each lead has authority in their domain, decisions at domain boundaries are made collaboratively via trade-off discussion.

## Aircraft Specs (High-Level, Shared)
| Parameter | Value |
|---|---|
| Configuration | Fixed-wing, conventional tail |
| Wingspan | 1.57 m |
| Total system weight | 5,460 g (540 g under 6,000 g budget) |
| CG location | 27.2% MAC |
| Cruise power | 188 W |
| Endurance | ~30–35 minutes |
| Coverage | 100 acres in 3 missions |
| Battery | 2× 6S 5000 mAh LiPo (series-parallel) |
| Cruise speed | ~35 mph |
| Max flight radius | 5 km |
| Camera | 1080p RGB, 5 cm GSD at 60 m |
| Propulsion | T-Motor U3 500 KV, 11×7 prop, 40A ESC |
| Flight controller | Pixhawk 4 Mini |
| Telemetry | RFD900x 900 MHz (25 km range, 5 km required) |

---

# Quick Lookup: Section → Owner

| Section | Owner |
|---|---|
| 1.1 Local Agricultural Pest | All (shared research) |
| 1.2 Team Organization | All |
| 1.3 Acquiring Mentors | All |
| 1.4 Impact on STEM | All |
| 2.1 Engineering Design Process | **Risith** |
| 2.2 Project Plan / Gantt | **Ritvik** |
| 2.3.1 Air Vehicle | **Risith** |
| 2.3.2 C3 System | **Risith** |
| 2.3.3 Payload Pest Detection | **Santhosh** |
| 2.3.4 Payload Sample Gathering | **Santhosh** |
| 2.4 Lessons Learned | All |
| 2.5 Final Design Drawings | **Risith** (technical drawings) |
| 3.1 Concept of Operations | **Santhosh** |
| 3.2 Benchmark Mission | **Santhosh** |
| 3.3 Safety Requirements | **Santhosh** |
| 3.3.1 Detect and Avoid | **Risith** |
| 4 Business Case | **Ritvik** |
| 4.1 Cost Analysis | **Ritvik** |
| 4.2 Logistics | **Ritvik** |
| 4.3 Economic Impact | **Ritvik** |
| 5 Public Affairs | **Ritvik** |
| 6 Conclusion | **Ritvik** |

---

# Quick Lookup: Keyword → Owner

| Keyword / Topic | Owner |
|---|---|
| Airframe, wing, CG, propulsion, C3, Pixhawk, RFD900x, DAA hardware, avionics | **Risith** |
| Camera payload, computer vision, sample gripper, benchmark mission, CONOPS, safety protocols | **Santhosh** |
| Cost, budget, Gantt, schedule, milestones, logistics, PR, business case, ROI | **Ritvik** |
| Codling moth biology, pest damage, Washington agriculture, team structure | **All** |
