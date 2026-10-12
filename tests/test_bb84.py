import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bb84_qkd import run_bb84  # noqa: E402


def mean_qber(eve, noise, trials=100, n=200, seed=0):
    rng = np.random.default_rng(seed)
    return np.mean([run_bb84(n, eve, noise, engine="numpy", rng=rng)["qber"]
                    for _ in range(trials)])


def test_no_eve_no_noise_is_clean():
    res = run_bb84(200, 0.0, 0.0, engine="numpy", rng=np.random.default_rng(1))
    assert res["qber"] == 0.0
    assert not res["detected"]
    assert np.array_equal(res["key_alice"], res["key_bob"])


def test_full_eve_gives_about_25_percent_qber():
    assert abs(mean_qber(1.0, 0.0) - 0.25) < 0.03


def test_noise_only_matches_noise_level():
    assert abs(mean_qber(0.0, 0.05) - 0.05) < 0.02


def test_eve_plus_noise_matches_theory():
    assert abs(mean_qber(1.0, 0.10) - (0.25 + 0.5 * 0.10)) < 0.03


def test_full_eve_is_detected():
    rng = np.random.default_rng(2)
    flags = [run_bb84(200, 1.0, 0.0, engine="numpy", rng=rng)["detected"] for _ in range(50)]
    assert np.mean(flags) > 0.95


def test_qiskit_engine_smoke():
    res = run_bb84(40, 0.0, 0.0, engine="qiskit", rng=np.random.default_rng(3))
    assert res["qber"] == 0.0
