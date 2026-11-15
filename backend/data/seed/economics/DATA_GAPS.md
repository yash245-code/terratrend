# TeraTrend Crop Economics: Coverage and Data Gap Report

**Generated:** 2026-11-14 09:19 UTC
**Official Sources:** Directorate of Economics and Statistics (DES), Commission for Agricultural Costs and Prices (CACP), National Horticulture Board (NHB), Agmarknet (data.gov.in).

## 1. State-Level Coverage Matrix (CACP Cost of Cultivation)

| Crop | National (IN) | Andhra Pradesh | Assam | Bihar | Gujarat | Haryana | Karnataka | Madhya Pradesh | Maharashtra | Odisha | Punjab | Rajasthan | Tamil Nadu | Telangana | Uttar Pradesh | West Bengal | Total States |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| barley | ✓ | - | - | - | - | - | - | - | - | - | - | ✓ | - | - | - | - | 1 |
| chickpea | ✓ | - | - | - | - | - | - | ✓ | ✓ | - | - | ✓ | - | - | - | - | 3 |
| cotton | ✓ | - | - | - | ✓ | - | - | - | ✓ | - | - | - | - | ✓ | - | - | 3 |
| finger_millet | ✓ | - | - | - | - | - | ✓ | - | - | - | - | - | - | - | - | - | 1 |
| groundnut | ✓ | ✓ | - | - | ✓ | - | - | - | - | - | - | - | - | - | - | - | 2 |
| lentil | ✓ | - | - | - | - | - | - | ✓ | - | - | - | - | - | - | ✓ | - | 2 |
| maize | ✓ | - | - | ✓ | - | - | ✓ | ✓ | - | - | - | - | - | - | - | - | 3 |
| mung_bean | ✓ | - | - | - | - | - | - | - | - | - | - | ✓ | - | - | - | - | 1 |
| mustard | ✓ | - | - | - | - | ✓ | - | ✓ | - | - | - | ✓ | - | - | - | - | 3 |
| onion | ✓ | - | - | - | - | - | - | - | ✓ | - | - | - | - | - | - | - | 1 |
| pearl_millet | ✓ | - | - | - | ✓ | - | - | - | - | - | - | ✓ | - | - | - | - | 2 |
| pigeon_pea | ✓ | - | - | - | - | - | ✓ | - | ✓ | - | - | - | - | - | - | - | 2 |
| potato | ✓ | - | - | - | - | - | - | - | - | - | - | - | - | - | ✓ | ✓ | 2 |
| rice | ✓ | ✓ | ✓ | ✓ | - | ✓ | - | - | - | ✓ | ✓ | - | ✓ | ✓ | ✓ | ✓ | 10 |
| sesame | ✓ | - | - | - | ✓ | - | - | - | - | - | - | - | - | - | - | - | 1 |
| sorghum | ✓ | - | - | - | - | - | ✓ | - | ✓ | - | - | - | - | - | - | - | 2 |
| soybean | ✓ | - | - | - | - | - | - | ✓ | ✓ | - | - | - | - | - | - | - | 2 |
| sugarcane | ✓ | - | - | - | - | - | - | - | ✓ | - | - | - | - | - | ✓ | - | 2 |
| tomato | ✓ | ✓ | - | - | - | - | - | - | - | - | - | - | - | - | - | - | 1 |
| wheat | ✓ | - | - | ✓ | - | ✓ | - | ✓ | - | - | ✓ | ✓ | - | - | ✓ | - | 6 |

## 2. Fallback Policy
- When a crop is assessed in a state without dedicated DES survey data (marked `-` above), TeraTrend falls back to the **National Weighted Average (IN)** with a transparent `benchmark_level: 'national'` and `cost_level: 'national'` flag.
- If a crop has no national benchmark, `economics.available = false` is returned with an explicit explanation.

## 3. Data Freshness & Verification Status
- Total Cost Records: 70 (All verified against CACP Price Policy / DES Schemes).
- Total Benchmark Yield Records: 70 (All verified against DES APY 3-year triennium averages).
- Unverified Records: 0 (Zero fabricated entries).
- Stale records (>24 months): 0.