
--------------------------- MODULE SumerAvera ---------------------------
EXTENDS Naturals, Sequences, FiniteSets

CONSTANTS
    Payloads,       \* Set of all incoming payloads
    ValidPayloads   \* Subset of payloads with valid cryptographic keys

VARIABLES
    ingressQueue,   \* Stream of incoming payloads
    stateLedger,    \* Core state engine ledger
    honeypotStorage \* Honeypot isolation buffer

vars == <<ingressQueue, stateLedger, honeypotStorage>>

Init ==
    
/\ ingressQueue \in (
     { << >> } \cup
     { <<p1>> : p1 \in Payloads } \cup
     { <<p1, p2>> : p1, p2 \in Payloads } \cup
     { <<p1, p2, p3>> : p1, p2, p3 \in Payloads }
   ) 

    /\ stateLedger = << >>
    /\ honeypotStorage = << >>

ProcessIngress ==
    /\ Len(ingressQueue) > 0
    /\ LET p == Head(ingressQueue)
       IN IF p \in ValidPayloads
          THEN /\ stateLedger' = Append(stateLedger, p)
               /\ honeypotStorage' = honeypotStorage
          ELSE /\ honeypotStorage' = Append(honeypotStorage, p)
               /\ stateLedger' = stateLedger
    /\ ingressQueue' = Tail(ingressQueue)

Next == ProcessIngress

NoStateContamination ==
    \A i \in 1..Len(stateLedger) : stateLedger[i] \in ValidPayloads

============================================================================= 
