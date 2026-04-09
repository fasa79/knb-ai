"""Ground truth evaluation dataset for RAGAS.

Each entry contains:
  - question: The user query
  - ground_truth: The expected correct answer (from the PDFs)
  - ground_truth_context: Key phrases that MUST appear in retrieved chunks for a correct retrieval
"""

EVAL_DATASET = [
    # ── Financial metrics ──────────────────────────────────────────
    {
        "question": "What was Khazanah's TWRR for 2025?",
        "ground_truth": "Khazanah's investments portfolio TWRR was 5.2% for 2025.",
        "ground_truth_context": ["5.2%", "TWRR"],
    },
    {
        "question": "What is Khazanah's Realisable Asset Value?",
        "ground_truth": "Khazanah's Realisable Asset Value (RAV) was RM156 billion in 2025, up from RM151 billion in 2024.",
        "ground_truth_context": ["RM156b", "RM151b", "RAV"],
    },
    {
        "question": "How much has Khazanah paid in cumulative dividends to the government?",
        "ground_truth": "Khazanah has paid RM21.1 billion in cumulative dividends to the Government of Malaysia.",
        "ground_truth_context": ["RM21.1b", "dividend"],
    },
    {
        "question": "What was the net assets value of Khazanah's portfolio?",
        "ground_truth": "Khazanah's overall portfolio net assets were RM105 billion.",
        "ground_truth_context": ["RM105b", "net assets"],
    },
    # ── Investment performance ─────────────────────────────────────
    {
        "question": "What was the 7-year rolling return for Khazanah?",
        "ground_truth": "Khazanah's 7-year rolling return (since 1 Jan 2019) was 6.1% annually.",
        "ground_truth_context": ["6.1%", "rolling"],
    },
    {
        "question": "What is Khazanah's portfolio allocation for Public Markets Malaysia?",
        "ground_truth": "Public Markets Malaysia represents approximately 50.7% of Khazanah's portfolio.",
        "ground_truth_context": ["Public Markets", "Malaysia", "50.7"],
    },
    # ── Strategic / ESG ────────────────────────────────────────────
    {
        "question": "What is the GEAR-uP programme?",
        "ground_truth": "GEAR-uP is Khazanah's programme that unlocks RM22 billion in investments.",
        "ground_truth_context": ["GEAR-uP", "RM22b"],
    },
    {
        "question": "How many startups has Khazanah's Future Malaysia Programme supported?",
        "ground_truth": "The Future Malaysia Programme has supported more than 60 startups.",
        "ground_truth_context": [">60 startups", "Future Malaysia"],
    },
    {
        "question": "What is the living wage policy deadline?",
        "ground_truth": "GLICs are required to implement the living wage policy by 30 June 2025.",
        "ground_truth_context": ["living wage", "30 Jun 2025"],
    },
    # ── Portfolio companies ────────────────────────────────────────
    {
        "question": "Did Khazanah increase its stake in EDOTCO?",
        "ground_truth": "Yes, Khazanah increased its stake in EDOTCO from 10.6% to 31.7%.",
        "ground_truth_context": ["EDOTCO", "10.6%", "31.7%"],
    },
    # ── People ─────────────────────────────────────────────────────
    {
        "question": "Who is the Managing Director of Khazanah?",
        "ground_truth": "Dato' Amirul Feisal Wan Zahir is the Managing Director of Khazanah Nasional Berhad.",
        "ground_truth_context": ["Amirul Feisal", "Managing Director"],
    },
    # ── Off-topic (should refuse) ──────────────────────────────────
    {
        "question": "What is the weather in Kuala Lumpur today?",
        "ground_truth": "This question is not related to Khazanah's Annual Review.",
        "ground_truth_context": [],
    },
    # ── Comparative ────────────────────────────────────────────────
    {
        "question": "How did Khazanah's total assets change from 2024 to 2025?",
        "ground_truth": "Khazanah's total assets (RAV) increased from RM151 billion in 2024 to RM156 billion in 2025.",
        "ground_truth_context": ["RM151b", "RM156b"],
    },
    # ── Semiconductor / Technology ─────────────────────────────────
    {
        "question": "What is Khazanah doing in the semiconductor sector?",
        "ground_truth": "Khazanah is supporting Malaysia's semiconductor ecosystem, having supported 3 Malaysian semiconductor companies through catalytic fund partnerships, aligned with the National Semiconductor Strategy.",
        "ground_truth_context": ["semiconductor", "3 Malaysian"],
    },
    # ── K-Youth ────────────────────────────────────────────────────
    {
        "question": "How many programme partners does K-Youth have?",
        "ground_truth": "K-Youth has 18 programme partners.",
        "ground_truth_context": ["K-Youth", "18"],
    },
]
