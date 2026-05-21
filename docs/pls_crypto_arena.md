# PLS Crypto Arena

> Status: external validation design draft
> Goal: test whether PLS helps Genesis accumulate, activate, and reuse useful concepts across externally verifiable tasks.

---

## 1. Why this test exists

PLS is hard to explain if it is only evaluated through Genesis/Yogg self-diagnosis. A useful validation task should be external, recognizable, objective, and difficult to reduce to a single impressive explanation.

This arena tests the claim that PLS is not another reasoning agent. PLS should improve the conceptual environment given to a fresh LLM run:

```text
past task experience
    ↓
point / line / surface topology
    ↓
current task activation
    ↓
LLM execution
    ↓
objective result and writeback
```

Success means later runs enter the right conceptual field faster, reuse earlier discoveries, avoid repeated mistakes, and solve new instances with less reconstruction.

---

## 2. Core hypothesis

PLS should show value on task families where later tasks depend on concepts discovered in earlier tasks.

The target effect is not:

```text
LLM knows the public answer from training data.
```

The target effect is:

```text
Genesis learns reusable attack concepts from private instances, then activates those concepts on later private instances.
```

A standard single-context LLM may solve some tasks, but it should not be able to accumulate private-instance lessons across isolated runs unless those lessons are supplied in context. PLS is the mechanism that decides which lessons enter the new context and in what epistemic form.

---

## 3. Why crypto challenges

Cryptopals / CTF-style cryptography tasks are a good first external validation target because they are:

- **Publicly recognizable**: security and cryptography exercises are widely understood benchmarks.
- **Objectively graded**: plaintext, key, flag, or oracle exploit either succeeds or fails.
- **Concept-chain heavy**: later attacks reuse earlier concepts.
- **Instance-randomizable**: private ciphertexts, keys, and oracle secrets avoid memorized public answers.
- **Tool-friendly**: success can be verified by local scripts, not by subjective judging.

This is better than a single formula puzzle because the main object of measurement is cross-task conceptual reuse, not one-shot cleverness.

---

## 4. Non-goals

This arena should not become another self-referential Yogg audit.

It should not measure:

- Whether Genesis can write a beautiful report about PLS.
- Whether the base model has memorized Cryptopals solutions.
- Whether one long prompt can include every previous solution.
- Whether an LLM can solve one isolated puzzle with enough time.

It should measure:

- Whether private solved instances create reusable points.
- Whether later tasks activate the right basis concepts.
- Whether activation stays small and useful rather than becoming a memory dump.
- Whether objective solve rate, latency, and repeated-error rate improve across the sequence.

---

## 5. Experimental controls

### 5.1 Private instances

Use Cryptopals-style task types, but generate private inputs locally:

- random keys
- random plaintexts
- random unknown suffixes
- random challenge IDs
- local judge scripts

The task type can be public. The concrete answer must not be public.

### 5.2 Isolated runs

Each challenge should be submitted as a separate Genesis request. Do not paste all previous solutions into the next request manually.

Allowed continuity:

- NodeVault / PLS
- knowledge cursor
- trace experience
- legitimate search/open of prior nodes

Disallowed continuity:

- manually appending the previous full transcript to the prompt
- giving explicit hints such as “reuse the Hamming distance method from task 2”
- changing the task after seeing failure, unless logged as a separate intervention

### 5.3 Baselines

Use at least three modes:

| Mode | Description |
|---|---|
| Base LLM | Same model, no Genesis PLS continuity, one task per fresh context. |
| Genesis without PLS surface | Tools available, but PLS activation disabled or ignored where practical. |
| Genesis with PLS | Normal Genesis PLS routing, surface, search, writeback. |

If disabling PLS cleanly is not yet practical, compare at minimum:

- first-pass Genesis with an empty relevant KB
- later-pass Genesis after prior private challenges
- same task family with prior nodes hidden from prompt/search, if feasible

---

## 6. Initial challenge ladder

### Task 1: Single-byte XOR

Input:

```text
hex ciphertext
```

Expected output:

```text
key byte
plaintext
confidence / verification method
```

Reusable concepts that should emerge:

- brute-force byte key space
- English frequency scoring
- printable ASCII filtering
- candidate inspection instead of trusting a score blindly

Objective grade:

- exact key match
- exact plaintext match

### Task 2: Repeating-key XOR break

Input:

```text
base64 ciphertext encrypted with repeating-key XOR
```

Expected output:

```text
key
plaintext
method summary
```

Expected reuse from Task 1:

- single-byte XOR solving as a subroutine
- English scoring
- plaintext candidate validation

New concepts:

- normalized Hamming distance
- keysize estimation
- block transposition
- per-key-byte solving

Objective grade:

- exact key match, or plaintext match with equivalent key
- plaintext readability and checksum match

### Task 3: AES-ECB detection

Input:

```text
multiple ciphertexts, one encrypted in AES-ECB
```

Expected output:

```text
line/index containing ECB ciphertext
reason
```

Reusable concepts:

- block-level inspection
- repeated blocks as structural leakage
- distinction between stream/XOR attacks and block-mode attacks

Objective grade:

- exact line/index match

### Task 4: Byte-at-a-time ECB oracle

Input:

```text
local encryption oracle: encrypt(user_controlled_input || unknown_suffix)
```

Expected output:

```text
recovered unknown suffix
exploit script or transcript
```

Expected reuse from Task 3:

- ECB block repetition
- block size detection
- controlled plaintext alignment

New concepts:

- dictionary attack per byte
- prefix length control
- oracle behavior modeling

Objective grade:

- recovered suffix exact match

### Task 5: CBC padding oracle

Input:

```text
local decrypt oracle that returns padding-valid / padding-invalid
```

Expected output:

```text
recovered plaintext
exploit script or transcript
```

Expected reuse:

- block boundary thinking
- oracle behavior as an information channel
- candidate search with verification

New concepts:

- PKCS#7 padding semantics
- intermediate state recovery
- bytewise block attack from the end

Objective grade:

- recovered plaintext exact match

---

## 7. What PLS should write back

Good writeback should create compact, reusable concept points, not transcripts.

Examples of desirable points:

```text
When breaking repeating-key XOR, transpose ciphertext blocks by key-byte position so each column becomes a single-byte XOR problem.
```

```text
ECB mode leaks repeated plaintext structure because equal plaintext blocks encrypt to equal ciphertext blocks under the same key.
```

```text
A byte-at-a-time ECB oracle can be attacked by aligning the unknown byte at the end of a block and building a dictionary of candidate block outputs.
```

Examples of undesirable points:

```text
In round 2 I ran python script X and printed output Y.
```

```text
The ciphertext in this private instance starts with 8f3a...
```

```text
Cryptopals is about crypto.
```

Lines should record genuine dependency:

```text
byte-at-a-time ECB oracle attack
    based_on → ECB repeated block detection
    based_on → block size discovery
    based_on → controlled plaintext alignment
```

---

## 8. What PLS should activate

The prompt-facing activation should be small.

For Task 4, a healthy surface might expose:

```text
[基础] ECB leaks repeated blocks under identical plaintext blocks.
[基础] Block size can be inferred by increasing controlled input length until ciphertext length jumps.
[探索] Controlled plaintext can align an unknown byte at a block boundary.
[游离] Earlier XOR candidate scoring treated oracle outputs as verification signals.
```

It should not dump every previous ciphertext, every script, or every round report.

The key question is:

```text
Did the right concepts become visible in the right form before execution?
```

---

## 9. Metrics

### 9.1 Objective task metrics

For each task:

- **solve_success**: pass/fail
- **attempt_count**: number of submissions or major solution attempts
- **wall_time**: elapsed time
- **tool_calls**: total tool calls
- **tokens**: approximate input/output tokens if available
- **verification_strength**: local judge / self-check / no check

### 9.2 PLS-specific metrics

For each task after Task 1:

- **basis_activation_hit**: were the expected prior concepts visible?
- **basis_activation_precision**: how much irrelevant prior material was injected?
- **actual_reuse**: did the execution use the activated concept, not merely show it?
- **new_point_quality**: did writeback generalize beyond the private instance?
- **line_quality**: did new concepts link to real prerequisites?
- **repeated_error_rate**: did known mistakes recur?

### 9.3 Compounding metrics

Across the ladder:

- solve rate increases or stays high as tasks become harder
- time-to-first-correct-plan decreases for related tasks
- fewer repeated dead ends
- shorter but more relevant context activation
- later points become more abstract and reusable

---

## 10. Failure modes to watch

### Memorized public solution

Symptom:

```text
Genesis gives the known Cryptopals answer or stock solution without inspecting the private instance.
```

Mitigation:

- private random inputs
- local judge
- require produced plaintext/key/flag

### Memory dump instead of PLS

Symptom:

```text
Prompt includes large previous transcripts or every prior crypto note.
```

Mitigation:

- track activation size
- require one to three core concepts for hot-path activation
- distinguish expanded audit mode from normal solve mode

### Instance overfitting

Symptom:

```text
Writeback stores private ciphertext-specific facts rather than attack concepts.
```

Mitigation:

- reject points that cannot help a new random instance
- prefer method-level lessons

### Self-report illusion

Symptom:

```text
Genesis says it reused PLS, but the trace shows no prior node opened or used as basis.
```

Mitigation:

- inspect active nodes, opened nodes, and reasoning lines
- grade by objective solve result first

### Tool brute force masking concept failure

Symptom:

```text
A script brute-forces everything without any reusable concept being written or activated.
```

Mitigation:

- allow tools, but score conceptual activation separately
- inspect whether the generated script encodes the right reusable method

---

## 11. Minimal implementation plan

### Phase 0: Paper protocol

- Write this design.
- Select the first 3-5 challenge types.
- Define expected reusable concepts for each task.
- Define scoring sheet.

### Phase 1: Manual private instances

- Generate private task files locally.
- Run Genesis through one challenge at a time.
- Record solve results and PLS trace observations manually.

### Phase 2: Local judge harness

Create a small local harness that can:

- generate instances
- expose files or oracle scripts
- grade submitted answers
- write a JSON result per attempt

### Phase 3: PLS trace audit

After each task, inspect:

- activated prior nodes
- opened node contents
- reasoning lines created
- new points written
- objective judge result

### Phase 4: Baseline comparison

Run the same ladder against:

- base LLM fresh contexts
- Genesis cold start
- Genesis after accumulated PLS

Use private seeds that are comparable but not identical across modes.

---

## 12. Success criteria

The arena supports the PLS claim if:

1. Genesis with accumulated PLS solves later private tasks more reliably or faster than cold/fresh baselines.
2. The improvement is traceable to compact activated concepts, not manual hints or transcript stuffing.
3. Writeback produces reusable points and valid dependency lines.
4. Later tasks show fewer repeated conceptual mistakes.
5. The system can explain which prior concepts were activated, without treating PLS topology as proof of task correctness.

A strong demonstration would be:

```text
Genesis fails or struggles on a fresh oracle task.
Genesis solves earlier simpler private tasks.
PLS records compact XOR / block / oracle concepts.
Genesis later solves a harder private oracle task with those concepts activated.
The local judge confirms the recovered secret.
```

---

## 13. First recommended run

Start with three tasks only:

```text
1. Single-byte XOR
2. Repeating-key XOR
3. ECB detection
```

This is enough to test whether PLS can carry method-level concepts forward without requiring a large harness.

Only after those show clean writeback and activation should the arena move to byte-at-a-time ECB and padding oracle tasks.
