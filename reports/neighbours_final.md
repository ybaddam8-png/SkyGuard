# SkyGuard final neighbour list — 3-hour pipeline

Neighbour eligibility is evaluated within the same cluster.

- **Primary:** distance ≤ 200 km and elevation difference ≤ 500 m.
- **Sparse fallback:** if a station has fewer than 2 primary neighbours, widen to distance ≤ 300 km and elevation difference ≤ 800 m.
- Sparse links use a **0.7 T3 confidence multiplier**.
- If a station has no links after fallback, T3 abstains and fusion treats T3 as missing.

| Station | Cluster | Link type | Neighbours |
|---|---|---|---|
| 42181 New Delhi / Palam | a | sparse fallback | 42182 Safdarjung (8.3 km, 9 m); 42131 Hissar (150.3 km, 4 m) |
| 42182 New Delhi / Safdarjung | a | sparse fallback | 42181 Palam (8.3 km, 9 m); 42131 Hissar (156.9 km, 5 m) |
| 42348 Jaipur / Sanganer | a | sparse fallback | 42170 Churu (181.6 km, 95 m) |
| 42170 Churu | a | sparse fallback | 42348 Jaipur (181.6 km, 95 m); 42131 Hissar (129.4 km, 74 m) |
| 42103 Ambala | a | sparse fallback | 42131 Hissar (168.1 km, 55 m) |
| 42131 Hissar | a | primary | 42181 Palam (150.3 km, 4 m); 42182 Safdarjung (156.9 km, 5 m); 42170 Churu (129.4 km, 74 m); 42103 Ambala (168.1 km, 55 m) |
| 43003 Bombay / Santacruz | c | sparse fallback | none after fallback; T3 abstains |
| 43014 Aurangabad Chikalthan Aerodrome | c | sparse fallback | 42921 Nasik (169.8 km, 16 m) |
| 43063 Poona | c | sparse fallback | 43110 Ratnagiri (180.8 km, 480 m); 42921 Nasik (163.2 km, 43 m) |
| 43110 Ratnagiri | c | sparse fallback | 43063 Poona (180.8 km, 480 m) |
| 42921 Nasik | c | sparse fallback | 43014 Aurangabad (169.8 km, 16 m); 43063 Poona (163.2 km, 43 m) |
| 43117 Sholapur | c | sparse fallback | none after fallback; T3 abstains |
