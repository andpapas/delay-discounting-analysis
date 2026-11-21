# Quantitative analysis of delay-discounting questionnaire

Andreas Papasalouros

This repository contains the Python code used for the quantitative analysis of
a student questionnaire on **delay discounting**, **time-shifted monetary
choices**, and **school procrastination**.

The repository is designed so that the analysis is transparent to reviewers
without publishing participant-level data. A fully synthetic Excel workbook is
included and can be used to run the complete pipeline. The real Excel export is
kept only in a local/private folder that is excluded by `.gitignore`.

## 1. Repository structure

```text
delay_discounting_github_repo/
├── analysis.py
├── README.md
├── requirements.txt
├── .gitignore
├── data/
│   ├── stub_responses.xlsx           # synthetic; safe to publish
│   └── private/
│       ├── README.md
│       └── raw_responses_private.xlsx # local only; DO NOT publish
├── outputs/
│   └── .gitkeep
└── reference_results/
    └── summary_private_data.txt       # aggregate results only
```

## 2. Data and privacy

The real workbook contains row-level questionnaire responses. Even though the
file is anonymized, it should **not** be committed to a public repository.

The root `.gitignore` excludes everything under `data/private/` except its
README. The public GitHub version should therefore include only the synthetic
file `data/stub_responses.xlsx`.

> Important: `.gitignore` prevents ordinary `git add .` from adding the private
> file, but it does not protect against manually uploading the file through the
> GitHub web interface. Check the staged files before every commit.

A useful command is:

```bash
git status
```

The public stub has the **same 26-column structure** and the same response
formats as the real Google Forms export, but every row is generated
synthetically.

## 3. Questionnaire structure

The first column is the Google Forms timestamp. Questions 1–25 occupy the next
25 columns.

### Q4–Q12: immediate monetary-choice context

Each item asks the participant to choose between **€10 today** and a larger
amount after a delay. These 9 items are used to estimate the delay-discounting
parameter `k`.

The hyperbolic model is:

```text
V = A / (1 + kD)
```

where:

- `V` = subjective present value,
- `A` = delayed reward,
- `D` = delay in days,
- `k` = discount rate.

For an item comparing a smaller immediate reward `S` with a larger delayed
reward `L`, the indifference threshold is:

```text
k = (L/S - 1) / D
```

The nine thresholds are derived directly from the questionnaire amounts and
delays.

### Q13–Q21: future-shifted context

These are the corresponding monetary dilemmas shifted **one year into the
future**. They are deliberately treated as a **different context**.

They are **not pooled with Q4–Q12 to estimate a second standard k**. Instead,
they are used to examine whether the probability of choosing the
larger-later reward changes when both alternatives are moved away from the
present. The code also counts preference reversals:

- `SIR→LDR`: smaller/earlier in the immediate context, larger/later in the
  future-shifted context;
- `LDR→SIR`: the reverse direction;
- stable `SIR→SIR` and `LDR→LDR` choices.

### Q22–Q24: school procrastination choices

Participants choose between studying today and playing/relaxing today when a
test is:

1. tomorrow,
2. in 3 days,
3. in 1 week.

### Q25: self-reported procrastination

A five-point Likert item is coded from 1 (`Διαφωνώ απόλυτα`) to 5
(`Συμφωνώ απόλυτα`).

## 4. How `k` is estimated

This study uses a **Kirby-like maximum-consistency scoring procedure** for the
custom 9-item immediate monetary block. It is not the canonical 27-item MCQ.

For each participant:

1. The 9 Q4–Q12 items are sorted by their indifference threshold `k_i`.
2. Every possible switching region is considered.
3. For each region, the script calculates the fraction of the participant's
   answers that are consistent with a single stable `k`.
4. The region with the highest consistency is retained.
5. If several regions tie, the reported `k` is the geometric mean of their
   representative `k` values.
6. The analysis labels a `k` estimate as **reliable** when at least 7 monetary
   items are answered and maximum consistency is at least 75%.

With all 9 items answered, the 75% rule effectively means at least **7/9
consistent choices** (77.8%).

Because raw `k` is strongly right-skewed, group comparisons use `ln(k)`.

## 5. Statistical analyses

The script performs the following planned analyses.

### 5.1 Immediate vs future-shifted monetary choices

For each participant, the proportion of larger-later (`LDR`) choices is
calculated separately for Q4–Q12 and Q13–Q21. The two proportions are compared
with a **paired-samples t-test**, because both measurements come from the same
participants.

The script also reports:

- mean percentage-point change,
- 95% confidence interval,
- Cohen's `d_z`,
- preference-reversal counts.

### 5.2 Boys vs girls

Among participants with reliable `k`, `ln(k)` is compared between participants
who selected `Αγόρι` and `Κορίτσι` using a **Welch independent-samples t-test**.
Other/missing gender responses are not forced into either group.

A sensitivity check repeats the same comparison using all finite `k`
estimates, without the 75% consistency filter.

### 5.3 Gymnasium vs Lyceum

`ln(k)` is compared between `Γυμνάσιο` and `Λύκειο` using a **Welch t-test**.
A sensitivity analysis again repeats the test using all finite `k` estimates.

### 5.4 School procrastination choices

The three related binary choices in Q22–Q24 are compared using **Cochran's Q**.

### 5.5 Associations with procrastination

The script uses **Spearman rank correlations** for:

- `ln(k)` vs school procrastination choice score,
- `ln(k)` vs Q25 self-reported procrastination,
- school procrastination choice score vs Q25.

These are secondary/exploratory analyses.

## 6. Software

The analysis uses:

- Python 3.10+,
- NumPy,
- pandas,
- SciPy,
- Matplotlib,
- openpyxl (Excel reader used by pandas).

Install the dependencies with:

```bash
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows PowerShell
pip install -r requirements.txt
```

## 7. Run the analysis

### Public synthetic workbook

```bash
python analysis.py \
  --input data/stub_responses.xlsx \
  --output outputs/stub
```

### Real workbook, locally only

Place the real export at `data/private/raw_responses_private.xlsx`, then run:

```bash
python analysis.py \
  --input data/private/raw_responses_private.xlsx \
  --output outputs/private
```

## 8. Output files

Each run creates:

```text
participant_metrics.csv
item_summary.csv
preference_reversals.csv
summary.json
summary.txt
consistency.png
context_overall.png
context_by_item.png
school_choices.png
```

`participant_metrics.csv` contains only derived metrics for the input rows. Do
not publish it when it has been generated from the real participant data.

## 9. Aggregate results from the private dataset

For transparency, the repository includes
`reference_results/summary_private_data.txt`, which contains aggregate output
from the real dataset but no row-level responses.

For the analyzed dataset (`N = 192`), the main results were:

- reliable `k` (consistency >= 75%): **164/192 = 85.4%**;
- median `k` in the reliable subset: **0.061721**;
- larger-later choices: **44.99%** in the immediate context and **55.34%** in
  the future-shifted context;
- paired comparison: **t(191) = 4.95, p < 0.001**;
- preference reversals: **333 SIR→LDR** vs **162 LDR→SIR**;
- boys vs girls, reliable `k` subset: **Welch t = -0.83, p = 0.407**;
- Gymnasium vs Lyceum, reliable `k` subset: **Welch t = 0.87, p = 0.393**;
- school study-now rates: **86.4%**, **60.0%**, **34.6%** for tomorrow,
  3 days, and 1 week respectively; **Cochran's Q = 116.19, p < 0.001**;
- `ln(k)` was not significantly correlated with either school-choice
  procrastination or the Q25 self-report;
- school-choice procrastination and Q25 were positively associated
  (**Spearman rho = 0.352, p < 0.001**).

## 10. Interpretation cautions

- The `k` estimate measures **monetary delay discounting**, not a general
  personality trait or a universal "impulsivity score".
- The monetary block is a custom 9-item adaptation, not the full 27-item MCQ.
- Q13–Q21 are analyzed as a different time context, not as additional
  thresholds for the same immediate-context `k`.
- The Gymnasium/Lyceum sample sizes are unequal, so the school-level comparison
  has limited power for the smaller Lyceum group.
- Monetary rewards were hypothetical.
- Secondary analyses should be interpreted as exploratory.


## Acknowledgements

ChatGPT (OpenAI) was used to assist with the implementation and documentation
of the Python analysis code. All analyses and results were reviewed by the authors.

## 11. Reference

Kirby, K. N., Petry, N. M., & Bickel, W. K. (1999). *Heroin addicts have
higher discount rates for delayed rewards than non-drug-using controls*.
**Journal of Experimental Psychology: General, 128**(1), 78–87.

---

If this repository is used for review, the recommended public configuration is:

- publish `analysis.py`, `README.md`, `requirements.txt`, the synthetic stub,
  and aggregate reference results;
- do **not** publish `data/private/raw_responses_private.xlsx` or any derived
  participant-level CSV generated from it.
