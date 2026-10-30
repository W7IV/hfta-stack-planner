# HFTA Stack Planner: Legal, Performance and Engineering Disclaimers

**Important: read before relying on calculations or building, modifying, or operating an antenna or tower system.** HFTA Stack Planner is free, community-contributed software for comparative amateur-radio station planning. **It is not a safety analysis, a structural design, a professional engineering opinion, or a guarantee of radio performance.** Numerical results, rankings, green indicators, and the absence of warnings **do not establish that any design is safe, feasible, compliant, or suitable for construction**.

This document explains material limitations and risks; it supplements the information in the project's [README](README.md) and the notices in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md). It does not change, replace, or add conditions to the [MIT License](LICENSE), or any third-party license.

## 1. Legal status; no professional relationship

- The software and all accompanying models, illustrations, reports, exports, examples, guidance, and documentation are supplied for **informational, experimental and educational purposes**. Neither the authors nor contributors are offering engineering, surveying, safety-inspection, legal, or other regulated professional services by publishing them.
- Providing the software, responding to issues, reviewing a user-submitted example, or discussing a possible configuration does **not** establish an engineer-client, consultant-client, fiduciary or other professional relationship.
- No author, contributor, or referenced third party approves or certifies a particular design or installation. Inclusion of a product name, reference model, safety margin, or threshold is **not** a manufacturer's approval, test certificate, or representation of fitness for use.
- Users and those responsible for a site must make their own judgments, consult qualified professionals where appropriate, and comply with applicable laws, building and electrical codes, permitting rules, land-use restrictions, manufacturer instructions, and other requirements. Requirements and professional licensure rules vary by location.

## 2. Structural, mechanical and life-safety limitations

**Do not use HFTA Stack Planner to determine whether a tower, guy system, foundation, rock anchor, antenna, mast, or installation is structurally safe.** Nothing displayed by the software is a rated load, allowable capacity, engineered clearance, or certification.

In particular:

- **Tower and foundation engineering are outside scope.** The program does not calculate tower member strength, buckling, fatigue, overturning, foundation or rock-anchor capacity, soil or bedrock behavior, base reactions, guy-anchor loads, corrosion, vibration, construction stages, or failure consequences.
- **Wind, ice and other environmental hazards are not comprehensively modeled.** Weather and combined-load cases, dynamic gusts, wind-induced antenna or guy deflection, galloping, seismic effects, material degradation, and long-term deterioration may govern a real installation. A hypothetical ice thickness in a clearance check is not a site-specific design load.
- **Guy-wire and antenna-turning calculations are simplified geometry checks only.** They use assumptions about sag, tension, turning radius, antenna droop and clearance. They do not verify tension under actual loads, insulators, hardware strength, attachment and anchor capacities, rotator behavior, transient movement or collision risk. A reported positive clearance, or no red/amber warning, **does not mean the physical arrangement will clear safely or is structurally adequate**.
- **Spacing and interaction warnings are not design limits.** The red and amber cutoffs are rough heuristics, not engineering safety factors or guarantees that antennas will not collide or interact. Antenna and boom geometry, mounting hardware, maintenance clearances, tolerances and motion may differ materially from entered values.
- Tower erection, climbing, rigging, operating near power lines and handling large antenna systems can cause serious injury, death or property damage. Use competent personnel, appropriate safety procedures, manufacturer documentation and qualified engineering review before constructing, altering, maintaining or operating installations.

Any actual structural design, anchor or foundation sizing, permitted installation, or determination of safe clearances must be performed and checked independently by appropriately qualified people using methods and standards applicable to that location and installation.

## 3. Radio-frequency model and predictive performance limits

- HFTA Stack Planner invokes **OpenHFTA**, an independent implementation of the HFTA terrain-assessment method, plus planner-specific comparison and optimization logic. Reproducing a number in HFTA demonstrates computational consistency for that case, **not independent verification of real-world RF performance**.
- Its antenna representations are generic approximations rather than models of particular products, boom configurations, element tapers, matching networks or installations. Mutual coupling between antennas and across bands, impedance changes, feedline and matching losses, phasing errors, power-divider imbalance, polarization effects, nearby structures and conductors, and many other real-world effects are omitted or simplified.
- Terrain inputs and assumed electrical ground characteristics may be incomplete, inaccurate, outdated, offset, differently resolved, or unrepresentative of local conditions. One path profile cannot represent every off-axis obstacle or nearby structure; vegetation and land cover may not be modeled reliably.
- Elevation-angle and propagation inputs, including ARRL .PRN files and VOACAP-derived tables, are statistical or modeled approximations, not forecasts of any particular operating period, contact, band opening or contest result. Solar, seasonal, geographic and propagation variability may substantially change actual outcomes.
- HFTA's modeled elevation-angle range is **1 through 35 degrees**; it cannot assess high-angle or NVIS performance reliably. Limitations also differ by frequency, terrain, profile length and quality. A numeric result outside the method's established range should not be treated as validated.
- Rankings and figures of merit depend on the input data, selected targets, weights, antennas, bands, constraints and objective function. Composite rankings can use averaging of decibel values as a **planning score**, which is not the same as the underlying HFTA figure of merit. The highest ranked design is not necessarily the best actual station.
- Some invalid calculation-core angles may be filled by interpolation under the documented policy and explicitly flagged; they are **not** exact original-HFTA results. Core validation against original HFTA covers a **limited reference set**, not every band, antenna type, site, combination or exported figure.

**No accuracy, sensitivity, coverage, contest-score, gain, signal-strength, communication-reliability or other performance outcome is promised.** Independently check inputs, model assumptions, calculations and conclusions, and consider on-air measurements or more detailed modeling where useful.

## 4. Data, exports, third-party services and redistribution

- Users are responsible for the accuracy, legality and rights associated with their terrain files, elevation-angle files, project data and any materials they upload, store, share or redistribute. In particular, ARRL .PRN datasets may be copyrighted; a private project archive is **not** automatically safe to publish. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
- Report files, screenshots, spreadsheets, CSVs, replay packs and project archives may be shared without their surrounding documentation. **Every such output remains subject to the modeling and safety limitations above**, regardless of whether the warning is displayed with the output. A report is not a sealed engineering drawing or professional opinion.
- Online terrain retrieval sends relevant geographic coordinates or other request information to external data services and may depend on availability, coverage, licensing and service rules; results may change without notice. Offline calculations do not imply that online retrieval is private or always available.
- Users who run a server, whether locally exposed or hosted on Railway or another platform, are responsible for access control, appropriate network exposure, credentials, backups, updates, resource limits and applicable privacy and data-protection obligations. Software security, availability and retention are **not guaranteed**. The authors do not operate or supervise independently deployed installations merely because the source is public.

## 5. Warranty, liability, maintenance and support

The project is licensed under the [MIT License](LICENSE), whose disclaimer expressly provides the software **"AS IS", WITHOUT WARRANTY OF ANY KIND**, and limits author and copyright-holder liability to the extent legally enforceable. That license is the governing copyright permission for the project's original code. Third-party components remain governed by their own terms.

There is no promise that the software is error-free, uninterrupted, secure, supported, maintained, updated, compatible with any particular operating system, or suitable for any purpose. Bugs, data loss, unintended results, and changed dependencies are possible. No issue response, suggested change, or past test result is a commitment to future support or a warranty.

**No disclaimer can guarantee immunity from legal claims or exclude liabilities that applicable law does not permit to be excluded.** This notice does not purport to waive anyone's non-waivable rights or shift responsibility for conduct where the law forbids doing so.

## Practical rule

**Use this planner to explore and compare possible radio configurations, not to certify an installation.** Before spending money, climbing, constructing, changing guy tension or antenna spacing, or making a decision that could affect safety or property, verify the underlying inputs, consult the relevant manufacturer and, where warranted, obtain independent review by a qualified engineer or other appropriate professional.
