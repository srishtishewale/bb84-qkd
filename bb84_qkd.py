"""
BB84 Quantum Key Distribution with an eavesdropper (Eve)
Supports both Qiskit and NumPy engines
========================================================
Install:  pip install qiskit qiskit-aer numpy matplotlib
"""

from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit
from qiskit_aer import AerSimulator
from qiskit_aer.noise import NoiseModel, ReadoutError

N_QUBITS = 200          # qubits Alice sends
SAMPLE_FRACTION = 0.5   # share of the sifted key revealed to estimate QBER
THRESHOLD = 0.11        # commonly used QBER abort threshold (~11%)


# ----------------------------------------------------------------------
# Quantum backend setup
# ----------------------------------------------------------------------
def make_backend(noise_prob=0.0):
    """Ideal simulator, or one with a simple channel/detector noise model."""
    if noise_prob > 0:
        p = noise_prob
        noise_model = NoiseModel()
        noise_model.add_all_qubit_readout_error(
            ReadoutError([[1 - p, p], [p, 1 - p]])
        )
        return AerSimulator(noise_model=noise_model)
    return AerSimulator()


def send_and_measure(bits, prep_bases, meas_bases, backend):
    """
    For each position: prepare |bit> in prep_basis, then measure in meas_basis.
    Returns the measured bits as a numpy array.
    """
    circuits = []
    for bit, prep_basis, meas_basis in zip(bits, prep_bases, meas_bases):
        qc = QuantumCircuit(1, 1)
        if bit == 1:
            qc.x(0)
        if prep_basis == 1:
            qc.h(0)
        if meas_basis == 1:
            qc.h(0)
        qc.measure(0, 0)
        circuits.append(qc)

    result = backend.run(circuits, shots=1).result()
    return np.array(
        [int(next(iter(result.get_counts(i)))) for i in range(len(circuits))]
    )


# ----------------------------------------------------------------------
# Dual-engine BB84
# ----------------------------------------------------------------------
def run_bb84(n=N_QUBITS, eve_fraction=0.0, noise_prob=0.0, engine="qiskit", rng=None):
    """
    eve_fraction : share of qubits Eve intercepts (0 = no Eve, 1 = all)
    noise_prob   : probability that Bob's measurement flips (channel noise)
    engine       : "qiskit" (simulate circuits) or "numpy" (fast probability model)
    rng          : random generator (optional)
    """
    if rng is None:
        rng = np.random.default_rng()

    if engine == "qiskit":
        return run_bb84_qiskit(n, eve_fraction, noise_prob, rng)
    elif engine == "numpy":
        return run_bb84_numpy(n, eve_fraction, noise_prob, rng)
    else:
        raise ValueError("Unknown engine: choose 'qiskit' or 'numpy'")


# ----------------------------------------------------------------------
# Qiskit engine (original implementation)
# ----------------------------------------------------------------------
def run_bb84_qiskit(n, eve_fraction=0.0, noise_prob=0.0, rng=None):
    backend = make_backend(noise_prob)

    alice_bits = rng.integers(0, 2, n)
    alice_bases = rng.integers(0, 2, n)
    bob_bases = rng.integers(0, 2, n)

    sent_bits, sent_bases = alice_bits, alice_bases
    if eve_fraction > 0:
        eve_bases = rng.integers(0, 2, n)
        eve_bits = send_and_measure(alice_bits, alice_bases, eve_bases, backend)
        intercepted = rng.random(n) < eve_fraction
        sent_bits = np.where(intercepted, eve_bits, alice_bits)
        sent_bases = np.where(intercepted, eve_bases, alice_bases)

    bob_bits = send_and_measure(sent_bits, sent_bases, bob_bases, backend)

    return sift_and_decide(alice_bits, alice_bases, bob_bits, bob_bases, rng)


# ----------------------------------------------------------------------
# NumPy engine (fast probability model)
# ----------------------------------------------------------------------
def run_bb84_numpy(n, eve_fraction=0.0, noise_prob=0.0, rng=None):
    alice_bits = rng.integers(0, 2, n)
    alice_bases = rng.integers(0, 2, n)
    bob_bases = rng.integers(0, 2, n)

    sent_bits, sent_bases = alice_bits.copy(), alice_bases.copy()
    if eve_fraction > 0:
        eve_bases = rng.integers(0, 2, n)
        eve_bits = np.array([
            bit if prep == eve else rng.integers(0, 2)
            for bit, prep, eve in zip(alice_bits, alice_bases, eve_bases)
        ])
        intercepted = rng.random(n) < eve_fraction
        sent_bits = np.where(intercepted, eve_bits, alice_bits)
        sent_bases = np.where(intercepted, eve_bases, alice_bases)

    bob_bits = []
    for sb, sbas, bbas in zip(sent_bits, sent_bases, bob_bases):
        if sbas == bbas:
            flip = rng.random() < noise_prob
            bob_bits.append(sb ^ flip)
        else:
            bob_bits.append(rng.integers(0, 2))
    bob_bits = np.array(bob_bits)

    return sift_and_decide(alice_bits, alice_bases, bob_bits, bob_bases, rng)


# ----------------------------------------------------------------------
# Common sifting + decision logic
# ----------------------------------------------------------------------
def sift_and_decide(alice_bits, alice_bases, bob_bits, bob_bases, rng):
    keep = alice_bases == bob_bases
    sifted_alice = alice_bits[keep]
    sifted_bob = bob_bits[keep]

    order = rng.permutation(len(sifted_alice))
    k = int(SAMPLE_FRACTION * len(order))
    sample, rest = order[:k], order[k:]
    qber = float(np.mean(sifted_alice[sample] != sifted_bob[sample])) if k else 0.0
    detected = qber > THRESHOLD

    return {
        "sent": len(alice_bits),
        "sifted": int(keep.sum()),
        "sample": k,
        "qber": qber,
        "detected": detected,
        "key_alice": sifted_alice[rest],
        "key_bob": sifted_bob[rest],
    }


# ----------------------------------------------------------------------
# Report helper
# ----------------------------------------------------------------------
def report(title, res):
    print(f"\n=== {title} ===")
    print(f"Qubits sent: {res['sent']} | sifted key: {res['sifted']} | "
          f"bits sampled: {res['sample']}")
    print(f"QBER = {res['qber']:.1%}  (threshold {THRESHOLD:.0%})")
    if res["detected"]:
        print("RESULT: eavesdropper / excess noise DETECTED -> key discarded")
    else:
        same = np.array_equal(res["key_alice"], res["key_bob"])
        print(f"RESULT: channel looks secure -> key of {len(res['key_alice'])} bits kept "
              f"(Alice and Bob keys identical: {same})")


# ----------------------------------------------------------------------
# Bit-flip illustration: what a random flip looks like
# ----------------------------------------------------------------------
def illustrate_bit_flips(n=20, noise_prob=0.10, seed=7):
    """
    Alice and Bob use the SAME basis for every qubit and there is no Eve,
    so Bob should read exactly Alice's bit. Any mismatch is a random flip
    caused by the noisy detector/channel (dark counts, fiber drift, ...).
    """
    rng = np.random.default_rng(seed)
    backend = make_backend(noise_prob)
    bits = rng.integers(0, 2, n)
    bases = rng.integers(0, 2, n)
    bob = send_and_measure(bits, bases, bases, backend)

    print(f"\n=== Random bit flips (no Eve, matching bases, noise {noise_prob:.0%}) ===")
    print("position : " + " ".join(f"{i:2d}" for i in range(n)))
    print("Alice    : " + " ".join(f"{b:2d}" for b in bits))
    print("Bob      : " + " ".join(f"{b:2d}" for b in bob))
    print("flipped  : " + " ".join(" ^" if a != b else "  " for a, b in zip(bits, bob)))
    print(f"{int((bits != bob).sum())} of {n} bits flipped by hardware noise alone "
          "(expected about " + f"{noise_prob * n:.1f})")


# ----------------------------------------------------------------------
# Sweep: QBER vs share of qubits Eve intercepts
# ----------------------------------------------------------------------
def sweep_eve_fraction(trials=50, n=N_QUBITS, out_dir="results"):
    """Mean QBER against Eve's interception share, with the 25% x share theory line."""
    rng = np.random.default_rng(11)
    fractions = np.round(np.arange(0.0, 1.01, 0.1), 1)
    means = []
    for f in fractions:
        qs = [run_bb84(n, f, 0.0, engine="numpy", rng=rng)["qber"] for _ in range(trials)]
        means.append(np.mean(qs))

    out = Path(out_dir)
    out.mkdir(exist_ok=True)
    plt.figure(figsize=(7, 4.5))
    plt.plot(fractions * 100, np.array(means) * 100, "o-", color="#D9480F", lw=2.5,
             label="Simulated QBER (mean)")
    plt.plot(fractions * 100, fractions * 25, ":", color="black", label="Theory: 25% x fraction")
    plt.axhline(THRESHOLD * 100, color="grey", ls="--", lw=1, label=f"Abort threshold ({THRESHOLD:.0%})")
    plt.xlabel("Share of qubits Eve intercepts (%)")
    plt.ylabel("QBER (%)")
    plt.title("Interception shows up as errors")
    plt.legend()
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(out / "qber_vs_eve.png", dpi=200)
    plt.close()
    print(f"\nSaved {out / 'qber_vs_eve.png'}")
    return fractions, means


# ----------------------------------------------------------------------
# Demo runs
# ----------------------------------------------------------------------
if __name__ == "__main__":
    report("No eavesdropper", run_bb84(eve_fraction=0.0, engine="qiskit"))
    report("Eve intercepts 100% of qubits", run_bb84(eve_fraction=1.0, engine="qiskit"))
    report("No Eve, 3% channel noise", run_bb84(eve_fraction=0.0, noise_prob=0.03, engine="qiskit"))
    illustrate_bit_flips()
    sweep_eve_fraction()
