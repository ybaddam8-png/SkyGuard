# SkyGuard final data-step report

## Status

Final station quality selection is complete. No fault injection or model training has run.

## Candidate scan

Scanned all **61** India Meteostat stations within 250 km of the Delhi and Pune reference points (32 and 29 respectively), including airport/ICAO and WMO/synoptic stations. Retrieval used `model=False` with no interpolation. Full ranking: `data/clean/candidate_synoptic_coverage.csv`.

## Final station quality at synoptic hours

The denominator is 8,768 exact timestamps per station (00, 03, ..., 21 UTC, 2023–2025).

|   station_id | name                            | cluster   | station_kind   |   distance_km | native_reporting_interval   |   temp_synoptic_coverage_pct |   mslp_synoptic_coverage_pct |   rh_synoptic_coverage_pct |   complete_triplet_synoptic_coverage_pct | low_coverage   |
|-------------:|:--------------------------------|:----------|:---------------|--------------:|:----------------------------|-----------------------------:|-----------------------------:|---------------------------:|-----------------------------------------:|:---------------|
|        42181 | New Delhi / Palam               | a         | airport/ICAO   |         10.3  | hourly                      |                      99.6578 |                      99.6008 |                    99.6578 |                                  99.6008 | False          |
|        42182 | New Delhi / Safdarjung          | a         | airport/ICAO   |          3.13 | 3-hourly                    |                      85.333  |                      85.3216 |                    85.276  |                                  85.2418 | False          |
|        42348 | Jaipur / Sanganer               | a         | airport/ICAO   |        242.95 | hourly                      |                      99.5324 |                      99.5096 |                    99.5096 |                                  99.4868 | False          |
|        42170 | Churu                           | a         | WMO            |        227.79 | 3-hourly                    |                      85.276  |                      85.1391 |                    85.2076 |                                  85.0707 | False          |
|        42103 | Ambala                          | a         | WMO            |        201.8  | 3-hourly                    |                      84.74   |                      84.5005 |                    84.6943 |                                  84.3978 | False          |
|        42131 | Hissar                          | a         | airport/ICAO   |        156.53 | 3-hourly                    |                      83.1889 |                      83.0178 |                    83.1318 |                                  82.8809 | False          |
|        43003 | Bombay / Santacruz              | c         | airport/ICAO   |        125.31 | hourly                      |                      99.9088 |                      99.8974 |                    99.9088 |                                  99.8974 | False          |
|        43014 | Aurangabad Chikalthan Aerodrome | c         | airport/ICAO   |        219.15 | mixed                       |                      97.4339 |                      97.3198 |                    97.4224 |                                  97.297  | False          |
|        43063 | Poona                           | c         | WMO            |          1.82 | 3-hourly                    |                      85.6182 |                      85.5839 |                    85.5497 |                                  85.3901 | False          |
|        43110 | Ratnagiri                       | c         | WMO            |        179.75 | 3-hourly                    |                      84.3978 |                      84.3864 |                    84.3864 |                                  84.3636 | False          |
|        42921 | Nasik                           | c         | WMO            |        164.77 | 3-hourly                    |                      84.0214 |                      83.9644 |                    83.9758 |                                  83.8846 | False          |
|        43117 | Sholapur                        | c         | airport/ICAO   |        235.57 | 3-hourly                    |                      82.516  |                      82.5502 |                    82.5046 |                                  82.4703 | False          |

## Neighbours (≤200 km, ≤500 m elevation)

| cluster   |   station_a |   station_b |   distance_km |   elevation_diff_m |
|:----------|------------:|------------:|--------------:|-------------------:|
| a         |       42181 |       42182 |          8.34 |                  9 |
| a         |       42170 |       42348 |        181.62 |                 95 |
| a         |       42103 |       42131 |        168.07 |                 55 |
| a         |       42131 |       42181 |        150.33 |                  4 |
| a         |       42131 |       42182 |        156.85 |                  5 |
| a         |       42131 |       42170 |        129.35 |                 74 |
| c         |       43063 |       43110 |        180.83 |                480 |
| c         |       42921 |       43014 |        169.83 |                 16 |
| c         |       42921 |       43063 |        163.24 |                 43 |

Stations with no eligible final neighbour use the sparse-neighbour fallback.

## Protected windows

| window     | cluster   |   station_id |   rows |   temp_real_pct |   mslp_real_pct |   rh_real_pct |   complete_triplet_real_pct |
|:-----------|:----------|-------------:|-------:|----------------:|----------------:|--------------:|----------------------------:|
| heatwave_a | a         |        42103 |    272 |          95.956 |          95.956 |        95.956 |                      95.956 |
| heatwave_a | a         |        42131 |    272 |          98.162 |          98.162 |        97.794 |                      97.794 |
| heatwave_a | a         |        42170 |    272 |          98.529 |          98.162 |        98.529 |                      98.162 |
| heatwave_a | a         |        42181 |    272 |         100     |         100     |       100     |                     100     |
| heatwave_a | a         |        42182 |    272 |          98.897 |          98.897 |        98.529 |                      98.529 |
| heatwave_a | a         |        42348 |    272 |         100     |         100     |       100     |                     100     |
| biparjoy_a | a         |        42103 |     35 |         100     |         100     |       100     |                     100     |
| biparjoy_a | a         |        42131 |     35 |          97.143 |          94.286 |        97.143 |                      94.286 |
| biparjoy_a | a         |        42170 |     35 |         100     |         100     |       100     |                     100     |
| biparjoy_a | a         |        42181 |     35 |         100     |         100     |       100     |                     100     |
| biparjoy_a | a         |        42182 |     35 |         100     |         100     |       100     |                     100     |
| biparjoy_a | a         |        42348 |     35 |         100     |         100     |       100     |                     100     |
| monsoon_c  | c         |        42921 |     57 |          98.246 |          96.491 |        98.246 |                      96.491 |
| monsoon_c  | c         |        43003 |     57 |         100     |         100     |       100     |                     100     |
| monsoon_c  | c         |        43014 |     57 |         100     |         100     |       100     |                     100     |
| monsoon_c  | c         |        43063 |     57 |         100     |         100     |       100     |                     100     |
| monsoon_c  | c         |        43110 |     57 |          98.246 |          98.246 |        98.246 |                      98.246 |
| monsoon_c  | c         |        43117 |     57 |          49.123 |          49.123 |        49.123 |                      49.123 |

Windows are cluster-specific. Native gaps are not F7 faults; injected dropouts will be labelled separately. Pressure is `mslp_hpa`, sea-level pressure; station pressure is unavailable from Meteostat.
