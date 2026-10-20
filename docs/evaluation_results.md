# Evaluation results

LLM: `offline:rule-based`, embeddings: `tfidf:sklearn`


## Python Backend Developer

| Method | R-Precision | MAP | NDCG@5 | Spearman |
|---|---|---|---|---|
| Keyword skill match only | 0.67 | 1.00 | 0.98 | 0.89 |
| Semantic similarity only | 0.67 | 1.00 | 0.98 | 0.90 |
| Evaluator (LLM / rules) only | 1.00 | 0.98 | 1.00 | 0.89 |
| Hybrid score (proposed) | 1.00 | 0.98 | 1.00 | 0.89 |

Average processing time per resume: 432 ms

| Rank | Resume | Human label | Score | Recommendation |
|---|---|---|---|---|
| 1 | aarav_sharma.pdf | 2 | 89.5 | Strong Fit |
| 2 | neha_kapoor.docx | 2 | 89.3 | Strong Fit |
| 3 | priya_nair.docx | 2 | 73.5 | Good Fit |
| 4 | rohan_verma.pdf | 1 | 69.1 | Good Fit |
| 5 | vikram_singh.docx | 1 | 68.7 | Good Fit |
| 6 | dev_patel.txt | 1 | 65.8 | Good Fit |
| 7 | ananya_gupta.pdf | 0 | 51.7 | Consider |
| 8 | arjun_reddy.txt | 1 | 36.3 | Not a Fit |
| 9 | ishita_banerjee.txt | 0 | 35.2 | Not a Fit |
| 10 | sneha_iyer.pdf | 0 | 33.8 | Not a Fit |
| 11 | sameer_ali.txt | 0 | 24.8 | Not a Fit |
| 12 | fatima_khan.docx | 0 | 20.8 | Not a Fit |
| 13 | meera_joshi.pdf | 0 | 20.8 | Not a Fit |
| 14 | karan_mehta.docx | 0 | 17.5 | Not a Fit |
| 15 | tanya_malhotra.txt | 0 | 5.0 | Not a Fit |

## React Frontend Developer

| Method | R-Precision | MAP | NDCG@5 | Spearman |
|---|---|---|---|---|
| Keyword skill match only | 1.00 | 1.00 | 1.00 | 0.78 |
| Semantic similarity only | 1.00 | 1.00 | 1.00 | 0.80 |
| Evaluator (LLM / rules) only | 1.00 | 1.00 | 1.00 | 0.78 |
| Hybrid score (proposed) | 1.00 | 1.00 | 1.00 | 0.78 |

Average processing time per resume: 154 ms

| Rank | Resume | Human label | Score | Recommendation |
|---|---|---|---|---|
| 1 | sneha_iyer.pdf | 2 | 96.4 | Strong Fit |
| 2 | dev_patel.txt | 2 | 77.7 | Strong Fit |
| 3 | meera_joshi.pdf | 1 | 57.0 | Consider |
| 4 | karan_mehta.docx | 1 | 51.5 | Consider |
| 5 | priya_nair.docx | 0 | 46.6 | Consider |
| 6 | aarav_sharma.pdf | 0 | 32.6 | Not a Fit |
| 7 | rohan_verma.pdf | 0 | 30.5 | Not a Fit |
| 8 | neha_kapoor.docx | 0 | 30.3 | Not a Fit |
| 9 | arjun_reddy.txt | 0 | 29.2 | Not a Fit |
| 10 | vikram_singh.docx | 0 | 29.1 | Not a Fit |
| 11 | ananya_gupta.pdf | 0 | 24.7 | Not a Fit |
| 12 | tanya_malhotra.txt | 0 | 23.9 | Not a Fit |
| 13 | fatima_khan.docx | 0 | 20.8 | Not a Fit |
| 14 | sameer_ali.txt | 0 | 20.8 | Not a Fit |
| 15 | ishita_banerjee.txt | 0 | 19.9 | Not a Fit |

## Data Scientist

| Method | R-Precision | MAP | NDCG@5 | Spearman |
|---|---|---|---|---|
| Keyword skill match only | 1.00 | 1.00 | 1.00 | 0.71 |
| Semantic similarity only | 1.00 | 1.00 | 1.00 | 0.90 |
| Evaluator (LLM / rules) only | 1.00 | 1.00 | 1.00 | 0.70 |
| Hybrid score (proposed) | 1.00 | 1.00 | 1.00 | 0.70 |

Average processing time per resume: 146 ms

| Rank | Resume | Human label | Score | Recommendation |
|---|---|---|---|---|
| 1 | ananya_gupta.pdf | 2 | 88.7 | Strong Fit |
| 2 | vikram_singh.docx | 2 | 77.3 | Strong Fit |
| 3 | ishita_banerjee.txt | 1 | 53.7 | Consider |
| 4 | neha_kapoor.docx | 0 | 35.5 | Not a Fit |
| 5 | priya_nair.docx | 0 | 34.2 | Not a Fit |
| 6 | aarav_sharma.pdf | 0 | 33.8 | Not a Fit |
| 7 | rohan_verma.pdf | 0 | 32.8 | Not a Fit |
| 8 | dev_patel.txt | 0 | 30.9 | Not a Fit |
| 9 | sameer_ali.txt | 0 | 23.6 | Not a Fit |
| 10 | sneha_iyer.pdf | 0 | 22.2 | Not a Fit |
| 11 | fatima_khan.docx | 0 | 20.8 | Not a Fit |
| 12 | meera_joshi.pdf | 0 | 20.8 | Not a Fit |
| 13 | arjun_reddy.txt | 0 | 14.2 | Not a Fit |
| 14 | karan_mehta.docx | 0 | 8.3 | Not a Fit |
| 15 | tanya_malhotra.txt | 0 | 5.4 | Not a Fit |

## Bias check (same resume, different name and gender)

| Mode | Scores | Max difference |
|---|---|---|
| blind | Arjun Reddy (original): 36.3, Priyanka Reddy (she): 36.3, Mohammed Iqbal (he): 36.3 | 0.0 |
| not blind | Arjun Reddy (original): 36.2, Priyanka Reddy (she): 36.1, Mohammed Iqbal (he): 36.1 | 0.1 |
