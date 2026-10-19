# Design and QA inventory

Subject: Meijiawu tea-garden inspection context. Job: explain which observation to verify next while preserving the weather's regional scope.

Palette: pine#123e3a, tea#197b64, porcelain#f5f9f7, amber#b77b29, lake#3c6c87, ink#243b38. Display: local Chinese Song face used only for the main thesis; body: Segoe UI/Microsoft YaHei; data: Consolas. Layout: compact header, left context sheet, right numerical reference and a large typed evidence graph, then inspection tasks. Signature: the actual draggable regional/context/evidence/task graph, not a decorative neural-network image. This is a scrollable workspace, not a fixed fullscreen shell.

Coverage required before signoff:

| Control/claim | Functional test | Visual state |
|---|---|---|
| Historical vs fixedAI weather | change modes and return; labels and numeric values update | both desktop states |
| Date | choose another allowed date and return | visible date and source label |
| Soil,shade,stage,cultivar | change context, update; same weather_hash | moist/dry/unknown and shade pairs |
| Advanced species/setting/treatment/endpoint | tea versus oilseed-rape and field versus chamber | scope checks readable |
| Scenario picker | N01—N10 loaded with explicitAI mode | N06/N07 scope refusal,N09 fallback |
| Graph | click a node, drag it, reset layout | selected node detail and moved node |
| Tasks | checkbox on/off produces new simulated version | no real-visit label |
| Version record | view an earlier record | earlier state visible |
| Evidence tab | all5 cards,source anchor and URL resolve | mismatch and partial cards |
| Data/replay tab |9grid coverage,0field labels,10cases/13variants/40checks | table readable |
| Export | preview and downloadMarkdown/JSON | assumptions and source markers retained |
| Fit | desktop1440×1000,mobile390×844 | no body horizontal overflow; graph may scroll within its labelled viewport |

Exploratory: stale controls before export; invalid date/unknown request; invalid old version after restart; repeated scenario and feedback. Also inspect the densest dry-soil task state and evidence panel. Actual screenshots and interaction receipts are written after implementation.

V0.3 additional required checks: request-in-flight locks context, case loading, record selection and export for feedback as well as analyze; independent analysis starts without a parent; a clean browser context retrieves persisted history from the server; completion panel distinguishes local implementation, frozen baseline, simulated field conditions and unverified submission; structured errors keep request IDs and never silently discard a missing parent. Graph, exports and five-card views must still pass after ES module extraction.
