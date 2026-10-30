============================================================================= 
---------------- MODULE SumerAvera ----------------
EXTENDS Integers, Sequences, FiniteSets, TLC

CONSTANTS 
    Payloads,
    ValidPayloads,
    ValidNonces,
    InvalidNonces

VARIABLES 
    ambient_surface,
    nonce_cache,
    kernel_mutex

vars == <<ambient_surface, nonce_cache, kernel_mutex>>

Init == 
    /\ ambient_surface = <<>>
    /\ nonce_cache = {}
    /\ kernel_mutex = "LOCKED_ZERO_TRUST"

ValidHandshake(payload, nonce) ==
    /\ nonce \notin nonce_cache
    /\ nonce_cache' = nonce_cache \cup {nonce}
    /\ ambient_surface' = Append(ambient_surface, payload)
    /\ kernel_mutex' = kernel_mutex

InvalidHandshake(nonce) ==
    /\ nonce \in nonce_cache
    /\ UNCHANGED vars

Next == 
    \/ \E p \in ValidPayloads, n \in ValidNonces: 
        ValidHandshake(p, n)
    \/ \E n \in InvalidNonces: 
        InvalidHandshake(n)

EdgeFirstInvariance == kernel_mutex = "LOCKED_ZERO_TRUST"

====================================================
