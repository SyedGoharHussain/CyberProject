# CyberProject — What It Does (Plain English)

## The big idea

Imagine a small **smart power grid** where solar panels, batteries, smart meters and EVs all talk to each other and trade electricity. Every "I sent you X kWh" message is a **transaction**. If a hacker tampers with those messages, somebody pays the wrong bill — or worse, the grid gets unstable.

This project is a **simulation** that shows how to keep those messages safe **even against a future quantum computer**.

## Two programs, run side by side

The project is split into two independent Python programs that you run in **two separate terminals**:

### 1. `defender/main.py` — the "good guys"

It pretends to be:
- **5 smart devices** (smart meter, solar panel, battery, EV, household meter)
- **3 fog nodes** (small edge servers that check transactions)
- **A blockchain** that records the approved transactions
- **A local database** that stores everything

What it does, step by step:
1. Each smart device **signs** an energy transaction using **ML-DSA-44** — a post-quantum signature algorithm standardised by NIST (FIPS 204, a.k.a. CRYSTALS-Dilithium).
2. The transactions are sent to the **attacker** first (to see if the attacker can mess with them).
3. The 3 fog nodes try to **verify** every signature. Anything tampered is rejected.
4. Verified transactions go into a **blockchain** using Proof-of-Authority consensus.
5. Charts are generated (signing time, verification time, throughput, etc.) into `defender/graphs/`.

### 2. `attacker/main.py` — the "bad guy"

It sits on `127.0.0.1:9999` and waits for the defender to send it traffic. When it gets a transaction it either:
- **flips bits in the signature** to corrupt it, then sends it back, or
- **lets it pass through** untouched

You choose how aggressive the attacker is (0%, 50%, or 100% tampering).

## Why post-quantum?

Today's standard signatures (RSA, ECDSA) will be **broken by Shor's algorithm** when large quantum computers exist. ML-DSA is based on **lattice math (M-LWE)** which has no known quantum shortcut, so transactions signed with it stay safe even in a post-quantum world.

## What you should see when you run it

- The defender prints a log of every transaction being signed, sent to the attacker, verified by the fog, and added to the blockchain.
- The attacker prints a log of every interception and whether it tampered.
- At the end, the fog summary should say **all tampered transactions were caught** ("tamper detected: 100%").
- Graphs are saved under `defender/graphs/` (signing time, verify time, block latency, throughput, classical-vs-PQC comparison, fog delay).

## How to run it

```bash
pip install -r requirements.txt

# Terminal 1
python attacker/main.py     # choose 1 for automatic mode

# Terminal 2
python defender/main.py     # choose 1 for automatic mode
```

The defender works fine even if the attacker isn't running — it just notes "attacker not available" and continues.

## Folder map

| Folder | What's inside |
|---|---|
| `attacker/` | The malicious node that intercepts traffic |
| `defender/app/devices/` | Simulated smart-grid devices |
| `defender/app/fog/` | Fog verification nodes |
| `defender/app/blockchain/` | The Proof-of-Authority blockchain |
| `defender/app/pqc/` | From-scratch ML-DSA-44 implementation |
| `defender/app/analytics/` | Metrics collection + graph plotting |
| `defender/app/database/` | Local JSON database |
| `graphs/` | Sample output charts from a previous run |
