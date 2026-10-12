"""
BB84 studies: "Can we tell Eve apart from noise?"
=================================================
Run AFTER bb84_qkd.py works. Keep both files in the same folder.

    python bb84_studies.py

Three experiments (each repeats BB84 hundreds of times, so it uses the fast
NumPy engine, which applies exactly the same rules as the Qiskit circuits):

  A. How many qubits does Alice need to send before Eve is caught reliably?
  B. How much does honest channel noise raise the error rate (QBER)?
     At what noise level do honest users get false alarms?
  C. "Eve's hiding zone": for every combination of noise level and share of
     qubits intercepted, how often is the attack detected?

A short Qiskit-vs-NumPy check at the start confirms the two engines agree.
Outputs (in results/): detection_vs_qubits.png, noise_sweep.png,
         hiding_zone.png, study_results.json
"""

import json
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from bb84_qkd import run_bb84, THRESHOLD, N_QUBITS

RUN_QISKIT_CHECK = True 
TRIALS = 500              # repeats per setting for experiments A and B
HEAT_TRIALS = 200         # repeats per cell for the heatmap

OUT = Path("results")
OUT.mkdir(exist_ok=True)

rng = np.random.default_rng(2026)   # separate generator -> reproducible studies


def monte_carlo(n, eve_fraction, noise, trials, engine="numpy"):
    """Repeat BB84 many times. Returns (mean QBER, detection rate)."""
    qbers, flags = [], []
    for _ in range(trials):
        res = run_bb84(n, eve_fraction, noise, engine=engine, rng=rng)
        qbers.append(res["qber"])
        flags.append(res["detected"])
    return float(np.mean(qbers)), float(np.mean(flags))


results = {}

# ----------------------------------------------------------------------
# 0. Check: Qiskit circuits vs NumPy twin
# ----------------------------------------------------------------------
if RUN_QISKIT_CHECK:
    print("Checking Qiskit engine against the NumPy engine (about a minute)...")
    check = []
    for f, p in [(0.0, 0.0), (1.0, 0.0), (1.0, 0.03)]:
        q_qiskit, _ = monte_carlo(N_QUBITS, f, p, 10, engine="qiskit")
        q_numpy, _ = monte_carlo(N_QUBITS, f, p, TRIALS, engine="numpy")
        print(f"  Eve share {f:.0%}, noise {p:.0%}: "
              f"Qiskit mean QBER {q_qiskit:.1%} | NumPy mean QBER {q_numpy:.1%}")
        check.append({"eve": f, "noise": p, "qiskit": q_qiskit, "numpy": q_numpy})
    results["engine_check"] = check

# ----------------------------------------------------------------------
# A. Detection probability vs number of qubits sent
# ----------------------------------------------------------------------
print("\nA. Detection probability vs qubits sent")
ns = [20, 40, 80, 160, 320]
eve_shares = [0.2, 0.5, 1.0]
detA = {}
for f in eve_shares:
    detA[f] = [monte_carlo(n, f, 0.0, TRIALS)[1] for n in ns]
    print(f"  Eve intercepts {f:.0%}: " + ", ".join(f"n={n}: {d:.0%}" for n, d in zip(ns, detA[f])))
results["A"] = {"ns": ns, "detection": {str(f): v for f, v in detA.items()}}

plt.figure(figsize=(7, 4.5))
for f, colr in zip(eve_shares, ["#00808A", "#5B6CFF", "#D9480F"]):
    plt.plot(ns, [d * 100 for d in detA[f]], "o-", color=colr, lw=2.5, label=f"Eve intercepts {f:.0%}")
plt.xlabel("Qubits sent by Alice")
plt.ylabel("Attack detected (% of runs)")
plt.title("More qubits make detection reliable")
plt.ylim(-3, 103)
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(OUT / "detection_vs_qubits.png", dpi=200)
plt.close()

# ----------------------------------------------------------------------
# B. Noise sweep
# ----------------------------------------------------------------------
print("\nB. Noise sweep (200 qubits)")
noises = [0.0, 0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.14, 0.16]
q_honest, q_eve, alarm_honest, catch_eve = [], [], [], []
for p in noises:
    qh, ah = monte_carlo(N_QUBITS, 0.0, p, TRIALS)
    qe, ce = monte_carlo(N_QUBITS, 1.0, p, TRIALS)
    q_honest.append(qh); alarm_honest.append(ah)
    q_eve.append(qe); catch_eve.append(ce)
    print(f"  noise {p:.0%}: QBER no Eve {qh:.1%} (false alarms {ah:.0%}) | "
          f"QBER with Eve {qe:.1%} (caught {ce:.0%})")
results["B"] = {"noises": noises, "qber_honest": q_honest, "qber_eve": q_eve,
                "false_alarm": alarm_honest, "eve_caught": catch_eve}

p_arr = np.array(noises)
plt.figure(figsize=(7, 4.5))
plt.plot(noises, np.array(q_honest) * 100, "o-", color="#00808A", lw=2.5, label="No Eve (simulated)")
plt.plot(noises, np.array(q_eve) * 100, "o-", color="#D9480F", lw=2.5, label="Eve on every qubit (simulated)")
plt.plot(noises, p_arr * 100, ":", color="#00808A", label="Theory: noise only")
plt.plot(noises, (0.25 + 0.5 * p_arr) * 100, ":", color="#D9480F", label="Theory: Eve + noise")
plt.axhline(THRESHOLD * 100, color="black", ls="--", lw=1, label=f"Abort threshold ({THRESHOLD:.0%})")
plt.xlabel("Channel noise (probability a measurement flips)")
plt.ylabel("QBER (%)")
plt.title("Noise raises the error rate for everyone")
plt.legend(fontsize=8)
plt.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(OUT / "noise_sweep.png", dpi=200)
plt.close()

# ----------------------------------------------------------------------
# C. Eve's hiding zone: detection probability over noise x Eve share
# ----------------------------------------------------------------------
print("\nC. Hiding-zone heatmap")
heat_noise = [round(x, 2) for x in np.arange(0.0, 0.121, 0.01)]
heat_eve = [round(x, 1) for x in np.arange(0.0, 1.01, 0.1)]
grid = np.zeros((len(heat_eve), len(heat_noise)))
for i, f in enumerate(heat_eve):
    for j, p in enumerate(heat_noise):
        grid[i, j] = monte_carlo(N_QUBITS, f, p, HEAT_TRIALS)[1]
results["C"] = {"noise": heat_noise, "eve": heat_eve, "detection": grid.tolist()}

fig, ax = plt.subplots(figsize=(7.5, 4.8))
im = ax.imshow(grid * 100, origin="lower", aspect="auto", cmap="RdYlGn_r", vmin=0, vmax=100,
               extent=[heat_noise[0] * 100 - 0.5, heat_noise[-1] * 100 + 0.5,
                       heat_eve[0] * 100 - 5, heat_eve[-1] * 100 + 5])
ax.set_xlabel("Channel noise (%)")
ax.set_ylabel("Share of qubits Eve intercepts (%)")
ax.set_title("Eve's hiding zone (green = she goes unnoticed)")
cbar = fig.colorbar(im, ax=ax)
cbar.set_label("Attack detected (% of runs)")
fig.tight_layout()
fig.savefig(OUT / "hiding_zone.png", dpi=200)
plt.close(fig)

# Largest Eve share that is caught in under 50% of runs, for each noise level
hide = []
for j, p in enumerate(heat_noise):
    safe = [f for i, f in enumerate(heat_eve) if grid[i, j] < 0.5]
    hide.append(max(safe) if safe else 0.0)
results["C"]["max_hidden_share"] = hide
print("  Largest Eve share missed in more than half of the runs:")
print("  " + ", ".join(f"noise {p:.0%}: {h:.0%}" for p, h in zip(heat_noise, hide)))

with open(OUT / "study_results.json", "w") as fh:
    json.dump(results, fh, indent=2)
print("\nSaved figures and study_results.json to results/")
