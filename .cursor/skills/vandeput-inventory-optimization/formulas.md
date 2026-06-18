# Key formulas — Vandeput (2020)

Symbols: D annual demand, k order cost, h holding cost, L lead time, R review period, α cycle service level, β fill rate, b backorder cost.

## EOQ (Ch. 2)

```
Q* = sqrt(2 k D / h)
C* = sqrt(2 k D h)
```

## Safety stock — normal (Ch. 4)

```
Ss = z_α · σ_d · sqrt(τ)
Inventory = μ_x + Ss
```

τ = L for (s,Q); τ = R + L for (R,S).

## Stochastic lead time (Ch. 6)

```
μ_x = μ_d · (L + R)
σ_x = sqrt((L+R)σ_d² + μ_d² σ_L²)
```

## Fill rate (Ch. 7)

Expected units short under normal demand:

```
U_s(iota) = σ_x · L(z)   where z = (iota - μ_x) / σ_x
β = 1 - U_s / μ_x
```

Cycle service level α = Φ(z) — **not equal** to β.

## Optimal cycle SL (Ch. 8)

```
(R,S): α* = 1 - h·R / b
(s,Q): α* = 1 - h·Q / (b·D)
```

## Gamma demand (Ch. 9)

```
k = (μ - d_min)² / σ²
θ = σ² / (μ - d_min)
Skewness ≈ 2σ / (μ - d_min)
```

Use gamma if observed skewness > σ/μ.

```
iota = F_Gamma^{-1}(α)
```

## GSM serial (Ch. 10)

```
Ss_i = z · σ_d · sqrt(x_τ_i)
Cost = Σ Ss_i · h_i
```

Echelon order-up-to: cumulative sum from downstream upstream.

## Newsvendor (Ch. 11)

```
co = c - v          (overage)
cu = p - c + g      (underage, cost minimization)
cr = cu / (cu + co)
Q* = min Q : F(Q) >= cr
P(Q) = p·E[min(Q,D)] - c·Q + v·E[(Q-D)+]
```

## KDE bandwidth (Ch. 12)

Scott rule (90% factor):

```
bw = 0.9 · σ · n^(-1/5)
```

## Simulation optimization (Ch. 13)

1. Smart start: analytical (R,S) from Ch. 8
2. Grid search Ss ± radius
3. Optional: `scipy.optimize.minimize_scalar` on simulated cost
