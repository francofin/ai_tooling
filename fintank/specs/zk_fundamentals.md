A prover can convince a verifier that the prover knows the solution without revealing the solution. A ZKP is a cryptographic method that allows one party (the prover) to convince another party (the verifier) that they know something without revealing that information itself.

### `ZK Proofs` must staisfy 3 conditions.

1. Completeness - If the statement is true an honest prover must be able to convince the verifier. 
2. Soundness - If the statement is false, no dishonest prover can convince an honest verifier. 
3. Zero Knowledge - The verifier must learn nothing except that the prover's statement is true. 

Use Cases -  A way to get privacy and privelages. 

Interactive vs Non Interactive ZK proofs.

Interactive - Back and forth between the two parties. Very time consuming and not practical for blockchain apps. 

Non-Interactive -  SIngle round of communication and single message between the prover and verifier. 

Key Terms

1. Claim/Statement - An assertion that something is true. It refers to the property being proven without revealing additional information. It is the claim the prover is making about the witness. 
2. Private and Public Inputs - A variable to the system. Inputs could be private. Values known only to the prover and not the verifier. Public input, known by both prover and verifier and used to check the proofs validity. Hash DIgest e.g.
3. Constraint - Mathematical condition which must be satisfied in order for the claim to be valid. Constraints define the rules the inputs must follow. 
4. Circuit - A system of constraints. A series of mathematical relations and operations. They define how the constraints work together. 
5. Witness -  Set of secret values that allow a prover to demonstrate their claim is true. Include the private inputs but can also include intermediate calculations. THe witness must satisfy the constraints of the circuit. 
6. Prover - The entity that generates the proof of computation to demonstrate knowledge of the witness while satisfying the circuit constraints. 
7. Verifier - Checks whether the proof is valid, runs a verification algorithm. DOne off chain or uses a verifier smart contract. 

Trusted Setup - A crucial system in ZK Proofs, used in SNARKS like GROTH16 and PLONK. 

A trusted setup ceremony is a procedure that is done once to generate some data that must be used every time some cryptographic protocol is run. 

Key COncepts

1. Toxic Watse - during the setup, random values are generated, if leaked an attacker can form invalid proofs, so random values must be destroyed. 
2. Common Reference String (CRS) - Set of public params, the prover and verifier use in the proof generation and verification process. 
3. Structured Reference String (SRS) - A type of CRS but contains structured data. e.g points on an elliptic curve. 
4. Multi-Party Computation (MPC) - A security enhancing process where multiple parties contribute to generating a final parameter. 

Powers of Tau (A trusted setup) - Used in SNARKS. Series of elliptic curve points generated using MPC. 

Polynomial Commitment - ryptographic method that allows you to commit to a specific polynomial. e.g. KZG commitment. 

SNARKS

Circuit Specific - Regenerated for every cicrcut - GROTH16
Universal - Reused for different circuits. - PLONK

GROTH 16
2 phase setup

1. Powers of Tau - Generates a general purpose SRS for circuits of a certain size. This step can be reused. SRS containing the encoded powers of tau as elliptic curve points is generated. These are gt, gt2, etc elements. 

2. Circuit specific phase - Params from first phase are combined with the circuit's constraints to produce an extended SRS. This generates a proving key and verification key. 

PLONK - Uses multiple circuits which can share the same setup as long as they fit within a size constraint. Powers of Tau generates the SRS which is then used for polynomial commitments. PLONK uses KZG commitment shceme where polynomials are commited using the Powers of Tau and evaluated at a specific challenge point. 

Proof of Knowledge vs Proof of Computation. Most times we prove computation was performed correctly so we know the secret inputs. 