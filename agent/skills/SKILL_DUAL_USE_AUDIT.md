---
name: dual-use-audit
description: Formal Standard Operating Procedure for auditing dual-use electronics (Category 3 - 3A001) and information security items (Category 5 - 5A002) under EU Dual-Use Regulation (Annex I) and the Wassenaar Arrangement.
version: 1.0.0
author: Principal AI Systems Architect
license: Apache-2.0
tags:
  - trade-compliance
  - dual-use
  - export-control
  - wassenaar-arrangement
  - eu-annex-i
  - eccn-classification
---

# Dual-Use Technical Audit Standard Operating Procedure (SOP)

## 1. Overview & Regulatory Framework
This skill specification governs the autonomous compliance evaluation of dual-use hardware, software, and technology under:
- **EU Dual-Use Regulation (Regulation (EU) 2021/821 Annex I)**
- **Wassenaar Arrangement on Export Controls for Conventional Arms and Dual-Use Goods and Technologies**
- **U.S. Export Administration Regulations (EAR) Commerce Control List (CCL)**

All autonomous decisions must follow deterministic threshold evaluation, strict evidence logging, and human-in-the-loop escalation criteria.

---

## 2. Category 3: Telecommunications & High-Frequency Electronics (3A001)

### 2.1 Scope & Critical Items
Category 3 covers electronic components, integrated circuits, and microwave/RF assemblies.

### 2.2 Technical Threshold Matrix
| ECCN / Annex I Code | Item Subcategory | Technical Parameter Trigger | Control Reason |
| :--- | :--- | :--- | :--- |
| **3A001.a.1** | Radiation-hardened ICs | Total dose $\ge 5 \times 10^3\text{ Gy(Si)}$ or latch-up free | National Security (NS), Nuclear Proliferation (NP) |
| **3A001.a.2** | Microprocessor microcircuits | Clock frequency $> 50\text{ GHz}$ or arithmetic logic $> 32\text{-bit}$ military rated | National Security (NS) |
| **3A001.b.2** | Microwave MMIC power amplifiers | Operating frequency exceeding $31.8\text{ GHz}$ up to $37.5\text{ GHz}$ with peak saturated power $> 0.1\text{ W}$ | National Security (NS), Anti-Terrorism (AT) |
| **3A001.e.1** | High-energy storage devices | Energy density $> 0.5\text{ kJ/kg}$ or repetitive discharge rate | Non-proliferation |

### 2.3 Category 3 Audit Heuristic
```text
IF product contains ("semiconductor", "microprocessor", "RF amplifier", "oscillator", "transceiver"):
  EXTRACT operating_frequency
  IF operating_frequency >= 31.8 GHz:
    FLAG dual_use = TRUE
    ASSIGN ECCN = "3A001.b.2"
    SET licensing_required = TRUE
  ELSE IF radiation_hardened == TRUE:
    FLAG dual_use = TRUE
    ASSIGN ECCN = "3A001.a.1"
    SET licensing_required = TRUE
  ELSE:
    EVALUATE standard commercial EAR99 status
```

---

## 3. Category 5 - Part 2: Information Security & Cryptography (5A002)

### 3.1 Scope & Triggers
Category 5 Part 2 controls hardware, software, and systems employing cryptography designed or modified to use "cryptographic techniques" for data confidentiality.

### 3.2 Technical Threshold Matrix
| Parameter Category | Standard Commercial De-Minimis | Controlled Dual-Use Threshold (5A002.a.1) |
| :--- | :--- | :--- |
| **Symmetric Encryption** | Key length $\le 56\text{ bits}$ (e.g. legacy DES) | Key length $> 56\text{ bits}$ (e.g. AES-128, AES-256) |
| **Asymmetric / Public Key** | Key length $\le 512\text{ bits}$ | Factorization $> 512\text{ bits}$ (e.g. RSA-2048, RSA-4096), Elliptic Curve $> 112\text{ bits}$ |
| **Quantum-Resistant Crypto** | N/A | Lattice-based or post-quantum cryptographic primitives |

### 3.3 Exemptions & Mass-Market Demotions (5A992 / Note 3 Cryptography Note)
The agent must verify if any of the following carve-outs apply:
1. **Operations, Administration & Maintenance (OAM)**: Cryptography restricted solely to administrative access or copyright copy protection.
2. **Mass Market Note (Note 3)**: Generally available to the public sold from stock, where user cannot alter cryptographic functionality.
3. **Smart cards / Banking**: Fixed-purpose payment terminals and financial transaction tokens.

---

## 4. Hermes ReAct Execution Protocol

When executing compliance audits under this skill, the agent must adhere to the structured Hermes XML plan-and-act format:

```xml
<scratchpad>
Step 1: Identify all declared commodities and target recipients.
Step 2: Cross-examine entities against OFAC SDN & EU sanctions databases.
Step 3: Resolve tariff classification (HS Code) to establish baseline control category.
Step 4: Execute verify_dual_use on technical specifications (frequency, key length, etc.).
Step 5: Synthesize final compliance risk profile and audit verdict.
</scratchpad>
```

### Dynamic Error Recovery Heuristic:
- If `screen_entity` returns fuzzy confidence between 60% and 84%:
  - Do NOT reject immediately.
  - Formulate an alternate query plan: inspect corporate aliases, parent organizations, and jurisdiction codes.
- If `verify_dual_use` receives vague technical specifications:
  - Inspect product datasheet or prompt for frequency, bandwidth, and cipher key lengths.
  - Default to provisional conditional review `HUMAN_ESCALATION_REQUIRED`.

---

## 5. Self-Improving Reflection & Feedback
Following every resolved episode:
1. Compare agent decision with recorded historical precedents retrieved via episodic vector lookup.
2. Record any borderline ambiguity in the SQLite audit log for trade compliance officer review.
3. If new precedent is accepted by human officer, add the item parameter threshold to recurring vector memory.
