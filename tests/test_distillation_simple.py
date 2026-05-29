"""Tests de operaciones simples de destilación (flash / batch / steam)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import distillation_simple as ds


def test_flash_binary_split():
    """Flash B/T a 95°C: 0 < V_frac < 1 y el vapor está enriquecido en el
    componente liviano (y > x)."""
    f = ds.flash_binary('benzene', 'toluene', z_F=0.5, T_K=368.15, P_bar=1.013)
    assert f is not None
    assert 0.0 < f['V_frac'] < 1.0
    assert f['y_LK'] > f['x_LK']           # vapor más rico en LK
    assert f['x_LK'] < f['z_F'] < f['y_LK']


def test_flash_invalid():
    assert ds.flash_binary('benzene', 'toluene', z_F=1.0, T_K=368) is None
    assert ds.flash_binary('benzene', 'no_existe', z_F=0.5, T_K=368) is None


def test_rayleigh_mass_balance():
    """Rayleigh B/T 0.6→0.3: parte del calderín se destila y el destilado
    medio está enriquecido en el liviano; balance consistente."""
    r = ds.rayleigh_batch('benzene', 'toluene', x0=0.6, xf=0.3)
    assert r is not None
    assert 0.0 < r['W_over_W0'] < 1.0
    assert 0.0 < r['frac_distilled'] < 1.0
    assert r['x_D_avg'] > r['x0']          # destilado más rico que el inicial
    # cierre de balance: W0·x0 = W·xf + D·x_D
    lhs = r['x0']
    rhs = r['W_over_W0'] * r['xf'] + r['frac_distilled'] * r['x_D_avg']
    assert abs(lhs - rhs) < 1e-6


def test_rayleigh_invalid():
    assert ds.rayleigh_batch('benzene', 'toluene', x0=0.3, xf=0.6) is None   # xf>x0


def test_steam_distillation():
    """Arrastre con vapor: la mezcla hierve por DEBAJO de 100°C y por debajo
    del punto de ebullición del orgánico (toluene 110.6°C)."""
    s = ds.steam_distillation('toluene', P_total_bar=1.013)
    assert s is not None
    assert s['T_boil_C'] < 100.0
    assert s['T_boil_C'] < 110.0
    assert 0.0 < s['y_org'] < 1.0
    assert s['steam_ratio_mol'] > 0 and s['steam_ratio_mass'] > 0


if __name__ == '__main__':
    test_flash_binary_split()
    test_flash_invalid()
    test_rayleigh_mass_balance()
    test_rayleigh_invalid()
    test_steam_distillation()
    print("operaciones simples: OK")
