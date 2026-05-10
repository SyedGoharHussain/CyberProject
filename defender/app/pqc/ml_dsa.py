"""
ML-DSA — Module Lattice-based Digital Signature Algorithm
From-scratch implementation based on NIST FIPS 204 (CRYSTALS-Dilithium)
Security parameter set: ML-DSA-44 (Category 2, 128-bit post-quantum security)

Key operations:
  keygen()        → (public_key, private_key)
  sign(sk, msg)   → signature
  verify(pk, msg, signature) → True / False
"""

import os
import struct
import hashlib
from typing import Tuple, List

# ─────────────────────────────────────────────────────────────
# ML-DSA-44 Parameters  (FIPS 204 Table 1)
# ─────────────────────────────────────────────────────────────
Q       = 8380417       # Prime modulus: 2^23 − 2^13 + 1
N       = 256           # Polynomial ring degree (Z_q[X] / X^256 + 1)
K       = 4             # Rows in matrix A
L       = 4             # Columns in matrix A
ETA     = 2             # Bound for secret key coefficients  [-ETA, ETA]
TAU     = 39            # Number of ±1 coefficients in challenge polynomial
BETA    = TAU * ETA     # = 78  (signing bound)
GAMMA1  = 1 << 17       # = 131072, masking vector bound
GAMMA2  = (Q - 1) // 88  # = 95232, low-order rounding range
OMEGA   = 80            # Max number of 1s allowed in hint vector
D_BITS  = 13            # Bits dropped from public key t1

# ─────────────────────────────────────────────────────────────
# NTT Pre-computation
# ζ = 1753 is a primitive 512th root of unity mod Q
# We precompute zetas in bit-reversal order for the Cooley-Tukey butterfly
# ─────────────────────────────────────────────────────────────
ZETA = 1753

def _bitrev8(n: int) -> int:
    """Reverse the 8 bits of an integer."""
    r = 0
    for _ in range(8):
        r = (r << 1) | (n & 1)
        n >>= 1
    return r

# ZETAS[k] = ζ^bitrev8(k) mod Q — used in NTT butterfly stages
ZETAS: List[int] = [pow(ZETA, _bitrev8(i), Q) for i in range(256)]

# ─────────────────────────────────────────────────────────────
# Type Aliases
# ─────────────────────────────────────────────────────────────
Poly    = List[int]       # length-256 list of ints in [0, Q-1]
PolyVec = List[Poly]
PolyMat = List[PolyVec]


# ═══════════════════════════════════════════════════════════════
# SECTION 1 — Polynomial Arithmetic
# ═══════════════════════════════════════════════════════════════

def poly_add(a: Poly, b: Poly) -> Poly:
    return [(x + y) % Q for x, y in zip(a, b)]

def poly_sub(a: Poly, b: Poly) -> Poly:
    return [(x - y) % Q for x, y in zip(a, b)]

def poly_ntt(f: Poly) -> Poly:
    """
    Forward Number Theoretic Transform (NTT).
    Converts a polynomial into its NTT-domain representation.
    Uses Cooley-Tukey butterfly: log2(256) = 8 stages.
    """
    f = list(f)
    k = 0
    length = 128
    while length >= 1:
        start = 0
        while start < N:
            k += 1
            zeta = ZETAS[k]
            for j in range(start, start + length):
                t              = zeta * f[j + length] % Q
                f[j + length]  = (f[j] - t) % Q
                f[j]           = (f[j] + t) % Q
            start += 2 * length
        length >>= 1
    return f

def poly_inv_ntt(f: Poly) -> Poly:
    """
    Inverse NTT — reverses the forward NTT.
    Uses Gentleman-Sande butterfly (reversed order of stages).
    """
    f = list(f)
    k = 256
    length = 1
    while length <= 128:
        start = 0
        while start < N:
            k -= 1
            zeta = ZETAS[k]   # same twiddle as forward NTT, in reverse order
            for j in range(start, start + length):
                t              = f[j]
                f[j]           = (t + f[j + length]) % Q
                f[j + length]  = zeta * (f[j + length] - t) % Q
            start += 2 * length
        length <<= 1
    # Multiply by N^{-1} mod Q = 256^{-1} mod Q
    n_inv = pow(N, Q - 2, Q)
    return [x * n_inv % Q for x in f]

def poly_pointwise(a: Poly, b: Poly) -> Poly:
    """Pointwise multiplication in NTT domain (NOT polynomial mult)."""
    return [x * y % Q for x, y in zip(a, b)]

def poly_mul(a: Poly, b: Poly) -> Poly:
    """Full polynomial multiplication via NTT."""
    return poly_inv_ntt(poly_pointwise(poly_ntt(a), poly_ntt(b)))


# ═══════════════════════════════════════════════════════════════
# SECTION 2 — Vector / Matrix Operations
# ═══════════════════════════════════════════════════════════════

def vec_add(u: PolyVec, v: PolyVec) -> PolyVec:
    return [poly_add(a, b) for a, b in zip(u, v)]

def vec_sub(u: PolyVec, v: PolyVec) -> PolyVec:
    return [poly_sub(a, b) for a, b in zip(u, v)]

def mat_vec_mul(A_hat: PolyMat, v_hat: PolyVec) -> PolyVec:
    """
    Matrix-vector product: result = INTT( A_hat ⊙ v_hat )
    Both A_hat and v_hat must already be in NTT domain.
    Accumulation happens in NTT domain (pointwise), then one INTT per row.
    """
    result = []
    for row in A_hat:
        # Accumulate pointwise products of this row with vector
        acc = [0] * N
        for a_elem, v_elem in zip(row, v_hat):
            prod = poly_pointwise(a_elem, v_elem)
            acc  = [(acc[i] + prod[i]) % Q for i in range(N)]
        result.append(poly_inv_ntt(acc))
    return result

def polyvec_ntt(v: PolyVec) -> PolyVec:
    return [poly_ntt(p) for p in v]

def polyvec_inv_ntt(v: PolyVec) -> PolyVec:
    return [poly_inv_ntt(p) for p in v]

def poly_scale_ntt(c_hat: Poly, v_hat: PolyVec) -> PolyVec:
    """Multiply each polynomial in v_hat by scalar poly c_hat (NTT domain)."""
    return [poly_inv_ntt(poly_pointwise(c_hat, p)) for p in v_hat]


# ═══════════════════════════════════════════════════════════════
# SECTION 3 — Hash / XOF Utilities
# ═══════════════════════════════════════════════════════════════

def _shake128(data: bytes, length: int) -> bytes:
    """SHAKE-128 XOF — used for uniform matrix expansion."""
    return hashlib.shake_128(data).digest(length)

def _shake256(data: bytes, length: int) -> bytes:
    """SHAKE-256 XOF — used for secret sampling and hashing."""
    return hashlib.shake_256(data).digest(length)


# ═══════════════════════════════════════════════════════════════
# SECTION 4 — Sampling Functions
# ═══════════════════════════════════════════════════════════════

def sample_uniform_poly(rho: bytes, i: int, j: int) -> Poly:
    """
    ExpandA: Sample a uniform polynomial in R_q from seed rho.
    Uses SHAKE-128 with domain separation (j, i).
    Rejection sampling: 3 bytes → 23-bit value → accept if < Q.
    """
    seed = rho + bytes([j & 0xFF, i & 0xFF])
    # Generate enough bytes; we need ~N * 3 bytes on average (rejection rate ~13%)
    buf  = bytearray(_shake128(seed, 1024))
    poly = []
    idx  = 0
    while len(poly) < N:
        if idx + 3 > len(buf):
            buf += bytearray(_shake128(seed + bytes([idx // 1024]), 512))
        b0, b1, b2 = buf[idx], buf[idx + 1], buf[idx + 2]
        idx += 3
        val = ((b2 & 0x7F) << 16) | (b1 << 8) | b0  # 23-bit value
        if val < Q:
            poly.append(val)
    return poly[:N]

def expand_A(rho: bytes) -> PolyMat:
    """Generate the K×L matrix A (already NTT-transformed) from seed rho."""
    A     = [[sample_uniform_poly(rho, i, j) for j in range(L)] for i in range(K)]
    A_hat = [[poly_ntt(p) for p in row] for row in A]
    return A_hat

def sample_eta_poly(seed: bytes, nonce: int) -> Poly:
    """
    Sample a polynomial with coefficients in [-ETA, ETA].
    For ETA=2: each coefficient uses 4 bits (nibble), reject if >= 15,
    then map via coef = (nibble mod 5) - 2.
    """
    domain = struct.pack('<H', nonce)
    buf    = bytearray(_shake256(seed + domain, 272))  # 272 bytes is enough
    poly   = []
    idx    = 0
    while len(poly) < N:
        if idx >= len(buf):
            buf += bytearray(_shake256(seed + domain + bytes([idx // 272]), 136))
        byte = buf[idx]
        idx += 1
        for nibble in [byte & 0x0F, (byte >> 4) & 0x0F]:
            if nibble < 15 and len(poly) < N:
                coef = nibble % (2 * ETA + 1)  # 0..4
                poly.append((coef - ETA) % Q)  # center to [-ETA, ETA] mod Q
    return poly

def expand_S(rho_prime: bytes, offset: int, count: int) -> PolyVec:
    """Sample a vector of `count` secret polynomials from rho_prime."""
    return [sample_eta_poly(rho_prime, offset + i) for i in range(count)]

def sample_gamma1_poly(rho_prime: bytes, base_nonce: int, col: int) -> Poly:
    """
    Sample a masking polynomial with coefficients in [-GAMMA1+1, GAMMA1].
    GAMMA1 = 2^17, so each coefficient needs 18 bits.
    """
    nonce  = base_nonce * L + col
    domain = struct.pack('<H', nonce)
    # Need 256 * 18 bits = 576 bytes minimum
    buf    = bytearray(_shake256(rho_prime + domain, 640))
    # Extract 18-bit chunks from the byte buffer
    poly   = []
    bit_buf = int.from_bytes(buf, 'little')
    for i in range(N):
        raw  = (bit_buf >> (i * 18)) & ((1 << 18) - 1)
        coef = (GAMMA1 - raw) % Q  # maps to [-GAMMA1+1, GAMMA1]
        poly.append(coef)
    return poly

def expand_mask(rho_prime: bytes, kappa: int) -> PolyVec:
    """Generate the masking vector y (L polynomials)."""
    return [sample_gamma1_poly(rho_prime, kappa, col) for col in range(L)]

def sample_challenge(c_tilde: bytes) -> Poly:
    """
    SampleInBall: Generate a sparse challenge polynomial.
    Exactly TAU coefficients are ±1; rest are 0.
    Uses Fisher-Yates shuffle on the last TAU positions.
    """
    buf   = bytearray(_shake256(c_tilde, 272))
    signs = int.from_bytes(buf[:8], 'little')  # 64 sign bits
    c     = [0] * N
    b_idx = 8
    for i in range(N - TAU, N):
        # Pick a random position in [0, i]
        while True:
            b = buf[b_idx % len(buf)]
            b_idx += 1
            if b <= i:
                break
        c[i] = c[b]
        # Sign bit for the ±1
        sign_bit = (signs >> (i - (N - TAU))) & 1
        c[b] = 1 - 2 * sign_bit  # +1 or -1
    return [x % Q for x in c]


# ═══════════════════════════════════════════════════════════════
# SECTION 5 — Rounding & Decomposition
# ═══════════════════════════════════════════════════════════════

def center(a: int, m: int) -> int:
    """Center a modulo m into the range (-m/2, m/2]."""
    a = a % m
    if a > m // 2:
        a -= m
    return a

def center_q(a: int) -> int:
    """Center a mod Q into (-Q/2, Q/2]."""
    return center(a, Q)

def power2round(a: int) -> Tuple[int, int]:
    """
    Split a into (a1, a0) such that a = a1 * 2^D + a0
    with a0 ∈ (-2^{D-1}, 2^{D-1}].
    """
    a  = a % Q
    a0 = center(a % (1 << D_BITS), 1 << D_BITS)
    a1 = (a - a0) >> D_BITS
    return a1, a0

def decompose(a: int) -> Tuple[int, int]:
    """
    Decompose a into (a1, a0) such that a = a1 * 2*GAMMA2 + a0
    with a0 ∈ (-GAMMA2, GAMMA2].
    Special case: if a1 hits max value, reset to avoid overflow.
    """
    a  = a % Q
    a0 = center(a % (2 * GAMMA2), 2 * GAMMA2)
    a1 = (a - a0) // (2 * GAMMA2)
    # Edge case: when a = q-1, formula gives a1 = (q-1)/(2γ2) which is out of range [0, m-1]
    # Fix: set a1 ← 0, a0 ← a0 - 1
    if a1 == (Q - 1) // (2 * GAMMA2):
        a1  = 0
        a0 -= 1
    return a1, a0

def high_bits(a: int) -> int:
    return decompose(a)[0]

def low_bits(a: int) -> int:
    return decompose(a)[1]

def make_hint(z: int, r: int) -> int:
    """
    MakeHint(z, r): returns 1 if rounding r and rounding (r+z) differ.
    Used to encode carry information into the hint vector.
    """
    return 0 if high_bits(r) == high_bits((r + z) % Q) else 1

def use_hint(h: int, r: int) -> int:
    """
    UseHint(h, r): use hint bit to recover the correct high-bits value.
    Corrects for a carry introduced by ct0 during signing.
    """
    m  = (Q - 1) // (2 * GAMMA2)
    r1, r0 = decompose(r)
    if h == 0:
        return r1
    if r0 > 0:
        return (r1 + 1) % m
    else:
        return (r1 - 1) % m


# ═══════════════════════════════════════════════════════════════
# SECTION 6 — Poly-Vector Rounding Wrappers
# ═══════════════════════════════════════════════════════════════

def polyvec_power2round(t: PolyVec) -> Tuple[PolyVec, PolyVec]:
    t1 = [[power2round(c)[0] for c in p] for p in t]
    t0 = [[power2round(c)[1] for c in p] for p in t]
    return t1, t0

def polyvec_highbits(w: PolyVec) -> PolyVec:
    return [[high_bits(c) for c in p] for p in w]

def polyvec_lowbits(w: PolyVec) -> PolyVec:
    return [[low_bits(c) for c in p] for p in w]

def polyvec_make_hint(z: PolyVec, r: PolyVec) -> PolyVec:
    return [[make_hint(zc, rc) for zc, rc in zip(zp, rp)]
            for zp, rp in zip(z, r)]

def polyvec_use_hint(h: PolyVec, r: PolyVec) -> PolyVec:
    return [[use_hint(hc, rc) for hc, rc in zip(hp, rp)]
            for hp, rp in zip(h, r)]

def polyvec_chknorm(v: PolyVec, bound: int) -> bool:
    """Return True if all coefficients are strictly within `bound` (inf-norm)."""
    for p in v:
        for c in p:
            if abs(center_q(c)) >= bound:
                return False
    return True

def count_hints(h: PolyVec) -> int:
    return sum(sum(p) for p in h)


# ═══════════════════════════════════════════════════════════════
# SECTION 7 — Serialization (simple 4-byte per coefficient)
# ═══════════════════════════════════════════════════════════════
# Note: The FIPS 204 spec uses bit-packing for compactness.
# For this implementation we use simple 4-byte integers for clarity.
# Sizes are larger than spec but mathematically identical.

def _pack_polyvec(v: PolyVec) -> bytes:
    out = bytearray()
    for p in v:
        for c in p:
            out += struct.pack('<I', c % Q)
    return bytes(out)

def _unpack_polyvec(data: bytes, count: int, offset: int = 0) -> Tuple[PolyVec, int]:
    v = []
    for _ in range(count):
        p = []
        for _ in range(N):
            c = struct.unpack('<I', data[offset:offset + 4])[0]
            p.append(c % Q)
            offset += 4
        v.append(p)
    return v, offset

def pack_pk(rho: bytes, t1: PolyVec) -> bytes:
    return rho + _pack_polyvec(t1)

def unpack_pk(pk: bytes) -> Tuple[bytes, PolyVec]:
    rho    = pk[:32]
    t1, _ = _unpack_polyvec(pk, K, 32)
    return rho, t1

def pack_sk(rho: bytes, K_seed: bytes, tr: bytes,
            s1: PolyVec, s2: PolyVec, t0: PolyVec) -> bytes:
    return (rho + K_seed + tr
            + _pack_polyvec(s1)
            + _pack_polyvec(s2)
            + _pack_polyvec(t0))

def unpack_sk(sk: bytes) -> Tuple[bytes, bytes, bytes, PolyVec, PolyVec, PolyVec]:
    rho    = sk[:32]
    K_seed = sk[32:64]
    tr     = sk[64:96]
    s1, off = _unpack_polyvec(sk, L,  96)
    s2, off = _unpack_polyvec(sk, K, off)
    t0, _   = _unpack_polyvec(sk, K, off)
    return rho, K_seed, tr, s1, s2, t0

def pack_sig(c_tilde: bytes, z: PolyVec, h: PolyVec) -> bytes:
    # h is a bit vector — pack as one byte per coefficient
    h_bytes = bytes(b & 1 for p in h for b in p)
    return c_tilde + _pack_polyvec(z) + h_bytes

def unpack_sig(sig: bytes) -> Tuple[bytes, PolyVec, PolyVec]:
    c_tilde  = sig[:32]
    z, off   = _unpack_polyvec(sig, L, 32)
    h = []
    for _ in range(K):
        p = [sig[off + i] & 1 for i in range(N)]
        off += N
        h.append(p)
    return c_tilde, z, h


# ═══════════════════════════════════════════════════════════════
# SECTION 8 — Key Generation
# ═══════════════════════════════════════════════════════════════

def keygen() -> Tuple[bytes, bytes]:
    """
    ML-DSA Key Generation (Algorithm 1 from FIPS 204):

    1. Sample random 32-byte seed.
    2. Derive (rho, rho_prime, K) from seed via SHAKE-256.
    3. Generate matrix A from rho (public randomness).
    4. Sample secret vectors s1, s2 from rho_prime.
    5. Compute t = A*s1 + s2.
    6. Power2Round(t) → (t1, t0) to hide low bits.
    7. Public key = (rho, t1); Private key = (rho, K, tr, s1, s2, t0).

    Returns: (public_key_bytes, private_key_bytes)
    """
    # Step 1 & 2: seed expansion
    seed      = os.urandom(32)
    expanded  = _shake256(seed, 128)
    rho       = expanded[:32]   # matrix seed (public)
    rho_prime = expanded[32:96] # secret vector seed
    K_seed    = expanded[96:]   # signing randomness seed

    # Step 3: Generate matrix A in NTT domain
    A_hat = expand_A(rho)

    # Step 4: Sample secret polynomials
    s1 = expand_S(rho_prime, 0, L)  # L polynomials
    s2 = expand_S(rho_prime, L, K)  # K polynomials

    # Step 5: Compute t = A*s1 + s2 (in standard domain)
    s1_hat = polyvec_ntt(s1)
    As1    = mat_vec_mul(A_hat, s1_hat)
    t      = vec_add(As1, s2)

    # Step 6: Split t into high and low bits
    t1, t0 = polyvec_power2round(t)

    # Step 7: Pack keys; compute tr = H(pk) for binding
    pk = pack_pk(rho, t1)
    tr = _shake256(pk, 32)
    sk = pack_sk(rho, K_seed, tr, s1, s2, t0)

    return pk, sk


# ═══════════════════════════════════════════════════════════════
# SECTION 9 — Signing
# ═══════════════════════════════════════════════════════════════

def sign(sk: bytes, message: bytes) -> bytes:
    """
    ML-DSA Signing (Algorithm 2 from FIPS 204):

    1. Unpack secret key.
    2. Compute mu = H(tr || message).
    3. Loop (rejection sampling):
       a. Sample masking vector y.
       b. Compute w = A*y; extract w1 = HighBits(w).
       c. Compute challenge c from H(mu || w1).
       d. Compute z = y + c*s1.
       e. Check bounds on z and r0 = LowBits(w - c*s2).
       f. Compute hints h = MakeHint(-c*t0, w - c*s2 + c*t0).
       g. If all checks pass, return (c_tilde, z, h).

    Returns: signature bytes
    """
    rho, K_seed, tr, s1, s2, t0 = unpack_sk(sk)

    # Recompute A
    A_hat = expand_A(rho)

    # Pre-NTT the secret vectors (done once, reused per loop iteration)
    s1_hat = polyvec_ntt(s1)
    s2_hat = polyvec_ntt(s2)
    t0_hat = polyvec_ntt(t0)

    # mu binds the message to the public key via tr
    mu        = _shake256(tr + message, 64)
    rho_prime = _shake256(K_seed + mu, 64)

    kappa = 0  # nonce / loop counter
    while True:
        # 3a. Sample masking vector y
        y     = expand_mask(rho_prime, kappa)
        y_hat = polyvec_ntt(y)

        # 3b. Compute w = A*y; extract high bits w1
        w  = mat_vec_mul(A_hat, y_hat)
        w1 = polyvec_highbits(w)

        # 3c. Challenge c_tilde = H(mu || w1)
        w1_bytes = bytes(c % 256 for p in w1 for c in p)
        c_tilde  = _shake256(mu + w1_bytes, 32)
        c        = sample_challenge(c_tilde)
        c_hat    = poly_ntt(c)

        # 3d. z = y + c*s1
        cs1 = poly_scale_ntt(c_hat, s1_hat)
        z   = vec_add(y, cs1)

        # Compute w - c*s2
        cs2    = poly_scale_ntt(c_hat, s2_hat)
        w_cs2  = vec_sub(w, cs2)

        # 3e. Check bounds
        if not polyvec_chknorm(z, GAMMA1 - BETA):
            kappa += 1
            continue
        r0 = polyvec_lowbits(w_cs2)
        if not polyvec_chknorm(r0, GAMMA2 - BETA):
            kappa += 1
            continue

        # 3f. Compute hints
        ct0      = poly_scale_ntt(c_hat, t0_hat)
        neg_ct0  = [[(Q - c) % Q for c in p] for p in ct0]

        # Check ct0 norm
        if not polyvec_chknorm(ct0, GAMMA2):
            kappa += 1
            continue

        # MakeHint(-ct0, w - cs2 + ct0)
        w_cs2_ct0 = vec_add(w_cs2, ct0)
        h = polyvec_make_hint(neg_ct0, w_cs2_ct0)

        # Check total hint count
        if count_hints(h) > OMEGA:
            kappa += 1
            continue

        # 3g. All checks passed — return signature
        return pack_sig(c_tilde, z, h)


# ═══════════════════════════════════════════════════════════════
# SECTION 10 — Verification
# ═══════════════════════════════════════════════════════════════

def verify(pk: bytes, message: bytes, sig: bytes) -> bool:
    """
    ML-DSA Verification (Algorithm 3 from FIPS 204):

    1. Unpack public key and signature.
    2. Check z and h bounds.
    3. Compute mu = H(H(pk) || message).
    4. Recover c from c_tilde.
    5. Compute w' = A*z - c*t1*2^D.
    6. Recover w1' = UseHint(h, w').
    7. Accept if c_tilde == H(mu || w1').

    Returns: True if signature is valid, False otherwise
    """
    try:
        rho, t1       = unpack_pk(pk)
        c_tilde, z, h = unpack_sig(sig)

        # Basic bound checks
        if not polyvec_chknorm(z, GAMMA1 - BETA):
            return False
        if count_hints(h) > OMEGA:
            return False

        # Recompute A
        A_hat = expand_A(rho)

        # Recompute mu
        tr = _shake256(pk, 32)
        mu = _shake256(tr + message, 64)

        # Recover challenge polynomial
        c     = sample_challenge(c_tilde)
        c_hat = poly_ntt(c)

        # Compute A*z
        z_hat = polyvec_ntt(z)
        Az    = mat_vec_mul(A_hat, z_hat)

        # Compute c * t1 * 2^D
        t1_scaled = [[(coef << D_BITS) % Q for coef in p] for p in t1]
        t1_hat    = polyvec_ntt(t1_scaled)
        ct1       = poly_scale_ntt(c_hat, t1_hat)

        # w' = A*z - c*t1*2^D   (verifier's view of the signer's w - cs2 + ct0)
        w_prime = vec_sub(Az, ct1)

        # Recover w1' using hints
        w1_prime = polyvec_use_hint(h, w_prime)

        # Recompute c_tilde' from recovered w1'
        w1_bytes    = bytes(c % 256 for p in w1_prime for c in p)
        c_tilde_exp = _shake256(mu + w1_bytes, 32)

        return c_tilde == c_tilde_exp

    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
# SECTION 11 — Public API Class
# ═══════════════════════════════════════════════════════════════

class MLDSA:
    """
    High-level interface to ML-DSA post-quantum signature scheme.

    Usage:
        pk, sk  = MLDSA.generate_keypair()
        sig     = MLDSA.sign(sk, b"my message")
        valid   = MLDSA.verify(pk, b"my message", sig)
    """

    SECURITY_LEVEL  = "ML-DSA-44 (Category 2 — 128-bit post-quantum)"
    KEY_ALG         = "Module Lattice (CRYSTALS-Dilithium)"

    @staticmethod
    def generate_keypair() -> Tuple[bytes, bytes]:
        """Generate a fresh (public_key, private_key) pair."""
        return keygen()

    @staticmethod
    def sign(private_key: bytes, message: bytes) -> bytes:
        """Sign `message` with `private_key`. Returns signature bytes."""
        if isinstance(message, str):
            message = message.encode('utf-8')
        return sign(private_key, message)

    @staticmethod
    def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
        """Verify `signature` on `message` using `public_key`."""
        if isinstance(message, str):
            message = message.encode('utf-8')
        return verify(public_key, message, signature)

    @staticmethod
    def pk_hex(pk: bytes) -> str:
        return pk.hex()

    @staticmethod
    def sk_hex(sk: bytes) -> str:
        return sk.hex()

    @staticmethod
    def sig_hex(sig: bytes) -> str:
        return sig.hex()

    @staticmethod
    def pk_size(pk: bytes) -> int:
        return len(pk)

    @staticmethod
    def sk_size(sk: bytes) -> int:
        return len(sk)

    @staticmethod
    def sig_size(sig: bytes) -> int:
        return len(sig)
