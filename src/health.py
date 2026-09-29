"""Spec F-10 sensor health on a T3 neighbour-residual series, shared by the export step and the health diagnosis.

H = 100 * (1 - min(1, 0.5*|b|/tau + 0.3*f30 + 0.2*max(0, sigma_r/sigma_ref - 1)))
b = EWMA of the residual, f30 = share of observed steps with P(fault) >= 0.5 in the last 30 days,
sigma_r = residual std over the last 30 days, sigma_ref = healthy-period residual std.
"""
import numpy as np
import pandas as pd

TOL = {'temp_c': .5, 'rh_pct': 5., 'mslp_hpa': .5}
LAM = 1 - (1 - .02) ** 3  # spec lambda 0.02 is per hour; the same decay per 3-hourly step


def ewma(r):
    # carried across missing steps; NaN until the first observed residual
    return pd.Series(np.asarray(r, float)).ewm(alpha=LAM, adjust=False, ignore_na=True).mean().to_numpy()


def tau_eff(v, r_healthy):
    # deviation from the spec: tolerance widened to 3 x the healthy-period std of the EWMA bias
    b = ewma(r_healthy)
    return max(TOL[v], 3 * float(np.nanstd(b[~np.isnan(np.asarray(r_healthy, float))], ddof=1)))


def f10_series(r, alert, obs, times, sigma_ref, tau):
    """F-10 terms and H at every step; times is a tz-naive DatetimeIndex sorted ascending."""
    r = np.asarray(r, float)
    s = pd.DataFrame({'r': r, 'a': (np.asarray(alert) & np.asarray(obs)).astype(float), 'o': np.asarray(obs, float)}, index=times)
    b = ewma(r)
    n30 = s.o.rolling('30D').sum().to_numpy()
    f30 = np.where(n30 > 0, s.a.rolling('30D').sum().to_numpy() / np.maximum(n30, 1), 0.)
    sr = s.r.rolling('30D', min_periods=2).std().to_numpy()
    ratio = sr / sigma_ref if sigma_ref > 0 else np.full(len(r), np.nan)
    pb = .5 * np.abs(b) / tau
    pf = .3 * f30
    ps = .2 * np.clip(np.nan_to_num(ratio - 1, nan=0.), 0, None)
    H = 100 * (1 - np.minimum(1, pb + pf + ps))
    return pd.DataFrame({'b': b, 'f30': f30, 'sigma_r': sr, 'ratio': ratio, 'pb': pb, 'pf': pf, 'ps': ps, 'H': H, 'n30': n30}, index=times)


if __name__ == '__main__':
    t = pd.date_range('2024-01-01', periods=400, freq='3h')
    rng = np.random.default_rng(0)
    r = rng.normal(0, .2, 400)
    out = f10_series(r, np.zeros(400, bool), np.ones(400, bool), t, .2, .5)
    assert out.H.iloc[-1] > 80, out.iloc[-1]
    biased = f10_series(r + 2.0, np.zeros(400, bool), np.ones(400, bool), t, .2, .5)
    assert biased.H.iloc[-1] == 0, biased.iloc[-1]
    assert tau_eff('temp_c', r) == .5 and tau_eff('temp_c', r * 10) > .5
    print('health self-check ok')
