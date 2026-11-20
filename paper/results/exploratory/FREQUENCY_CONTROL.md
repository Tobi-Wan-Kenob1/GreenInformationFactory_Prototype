# Exploratory C.1 — H3 and H4 controlling for input term frequency

**Exploratory, not registered.** Method fixed in PROTOCOL.md Appendix C.1 before it was run.
Partial Spearman correlation of class with uptake, controlling for each unit's document
frequency in the frozen input corpus; p one-sided, class permuted within frequency terciles.

| | A1 | A2 |
|---|---|---|
| **H3 bridge vs single** partial r [95 % CI] | **0.161** [-0.034, 0.338] | **0.193** [0.018, 0.355] |
| H3 bridge vs single: p (one-sided) | 0.041 | 0.046 |
| H3 bridge vs single: ρ(frequency, uptake) | 0.740 | 0.808 |
| H3 bridge vs single: P(class 1 > class 0) by frequency tercile (low, mid, high) | 0.914, 0.657, 0.566 | 0.874, 0.658, 0.498 |
| H3 bridge vs single: class 1 / class 0 counts per tercile | [4, 9, 14] / [38, 33, 28] | [3, 20, 18] / [45, 30, 29] |
| H3 bridge vs single: median input frequency, class 1 / class 0 | 56.000 / 24.000 | 82.000 / 29.500 |
| **H4 blind vs covered** partial r [95 % CI] | **-0.029** [-0.302, 0.246] | **0.071** [-0.349, 0.402] |
| H4 blind vs covered: p (one-sided) | 0.268 | 0.384 |
| H4 blind vs covered: ρ(frequency, uptake) | 0.689 | 0.794 |
| H4 blind vs covered: P(class 1 > class 0) by frequency tercile (low, mid, high) | —, —, 0.214 | —, 0.208, — |
| H4 blind vs covered: class 1 / class 0 counts per tercile | [19, 17, 3] / [0, 0, 14] | [14, 12, 0] / [0, 2, 14] |
| H4 blind vs covered: median input frequency, class 1 / class 0 | 1.000 / 25.000 | 0.000 / 59.000 |
