# Jaanch Training & Evaluation Data

This directory manages the datasets used for training and evaluating machine learning classifiers integrated with the Jaanch fraud detection system.

## Dataset Provenance & Attribution

- **Dataset Name:** Employment Scam Aegean Dataset (EMSCAD) / Real or Fake Job Posting Prediction
- **Source URL:** [Kaggle Dataset: Real or Fake Job Postings](https://www.kaggle.com/datasets/shivamb/real-or-fake-fake-jobposting-prediction)
- **Original Research:** University of the Aegean, Laboratory of Information & Communication Systems Security (ICCS)
- **License / Usage:** Open access research dataset (Creative Commons / Public Domain on Kaggle).
- **Format:** CSV (`fake_job_postings.csv`)
- **Total Records:** 17,880 historical job advertisements

## Expected File Placement

Original untouched CSV should be placed at:
```
data/raw/fake_job_postings.csv
```
*(A fallback check is also supported for `Data/fake_job_postings.csv` or any `.csv` under `data/raw/`)*

## Schema & Raw Attributes

The dataset contains 18 columns:
1. `job_id`: Unique identifier (Integer) — **excluded from features to prevent leakage**
2. `title`: Title of the job posting
3. `location`: Geographical location (Country, State, City)
4. `department`: Corporate department or team
5. `salary_range`: Indicative salary range
6. `company_profile`: Overview of the employer
7. `description`: Detailed description of the job
8. `requirements`: Candidate requirements and prerequisites
9. `benefits`: Perks and benefits offered
10. `telecommuting`: Whether remote work is offered (binary 0/1)
11. `has_company_logo`: Whether company logo is present (binary 0/1)
12. `has_questions`: Whether screening questions are included (binary 0/1)
13. `employment_type`: Full-time, Part-time, Contract, etc.
14. `required_experience`: Entry level, Mid-Senior, Executive, etc.
15. `required_education`: Degree requirements
16. `industry`: Industry sector
17. `function`: Professional job function
18. `fraudulent`: Target column (0 = legitimate, 1 = fraudulent/scam)

## Target Definition & Class Imbalance

- `0` -> Legitimate / Genuine job postings (~17,014 records, 95.16%)
- `1` -> Fraudulent / Scam postings (~866 records, 4.84%)
- The severe class imbalance (~20:1) requires stratified splitting and balanced weighting during training.

## Limitations & Known Gaps

1. **Geographic & Linguistic Scope:** EMSCAD consists predominantly of formal English-language online job board postings (primarily US/UK/global corporate postings from ~2012-2014).
2. **Modern Scams Difference:** Modern Indian student scams frequently occur over WhatsApp, Telegram, or SMS, often featuring Hinglish phrasing, UPI IDs, rapid interview-less shortlisting, or small registration fee demands (₹500 - ₹2,000) not represented in EMSCAD.
3. **Complementary Role:** The ML model serves as a textual job-posting classifier. It complements, but **does not replace**, Jaanch's live domain intelligence (RDAP, MX, lookalike domain matching) and pattern-based rule checks.

## Directory Structure

```
data/
├── README.md               # This documentation
├── raw/                    # Raw untouched original datasets (gitignored)
├── processed/              # Processed train/val/test splits (gitignored)
├── labels/                 # Target label mappings and metadata
└── reports/                # Dataset inspection and drift reports
```

## Preparation Workflow

Run the reproducible preparation script:
```bash
python scripts/prepare_dataset.py
```
This inspects `data/raw/`, cleans fields without injecting `"nan"`, builds a consolidated text feature, removes exact duplicates, creates stratified splits, and writes summary statistics to `data/reports/data_summary.json`.
