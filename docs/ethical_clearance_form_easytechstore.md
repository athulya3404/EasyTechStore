# MCA/BCA Student Dissertation / Capstone Ethical Clearance Form
**Department:** PG Dept. of Computer Applications &nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp; **Academic Year:** 2025-2026

---

### A. Student & Project Details

1. **Student Name :** Athulya
2. **Admission Number :** 25PMC______
3. **Programme of Study :** ☑ MCA &nbsp;&nbsp; ☐ BCA
4. **Institution Email :** athulya3404@gmail.com
5. **Contact Phone :** [Your Contact Phone Number]
6. **Project/Dissertation Title :** EasyTech – Full-Stack Electronic Gadgets E-Commerce System with AI-Powered Assistance & Secure Transaction Lifecycle
7. **Project Modality :** ☐ Dissertation &nbsp;&nbsp; ☐ Capstone &nbsp;&nbsp; ☐ Internship Project &nbsp;&nbsp; ☑ Other: Mini Project
8. **Supervisor (Faculty Guide) :** [Faculty Guide Name]
9. **DRAC/Departmental Research Advisory Member (if applicable) :** [Member Name, if applicable]
10. **Industry/External Mentor (if applicable) :** N/A
11. **Estimated Start Date :** 30 July 2025
12. **Estimated Completion Date :** 30 October 2025

---

### B. Project Overview

**13. Purpose & Rationale (aim, research problem, expected contribution; attach pages if needed):**  
The aim of this project, EasyTech (EasyTechStore), is to develop an enterprise-grade, full-stack e-commerce web platform engineered for purchasing electronic gadgets (smartphones, laptops, audio equipment, computer accessories) with intelligent AI assistance and robust transaction integrity. It addresses the real-world problems of high-concurrency race conditions during flash sales that lead to inventory overselling, security vulnerabilities in client-side payment processing, the difficulty customers face when comparing complex multi-dimensional hardware specifications (CPU, RAM, display, battery), and the lack of personalized, context-aware technical product advice. The proposed system provides a centralized platform where customers can browse catalog items with faceted filtering, perform side-by-side technical gadget comparisons, reserve stock with atomic database-level locks, execute secure simulated payments with cryptographic HMAC-SHA256 signature verification, track order lifecycles (Pending, Paid, Shipped, Delivered), and download GST-compliant PDF invoices. Store managers can oversee catalog CRUD operations, perform batch Excel/CSV imports, manage order state transitions, and monitor sales analytics. Additionally, the system incorporates a Retrieval-Augmented Generation (RAG) AI Chatbot powered by ChromaDB vector embeddings and Large Language Models (LLM) to assist shoppers with natural language gadget inquiries, budget filtering, and technical compatibility advice. The expected contribution of this project is to eliminate inventory leakage under concurrent traffic, ensure tamper-proof payment verification, streamline complex hardware evaluation for buyers, and demonstrate a secure, production-ready e-commerce architecture following clean software engineering standards.

**14. Methodology / Technical Approach (check all that apply and describe below):**  
☑ Software/System Development &nbsp;&nbsp; ☐ Data Analytics/Mining &nbsp;&nbsp; ☑ AI/ML/DL Model Development  
☐ HCI/Usability Testing &nbsp;&nbsp; ☐ Survey/Interviews &nbsp;&nbsp; ☐ Secondary Data Analysis  
☐ Network Measurement &nbsp;&nbsp; ☐ IoT/Robotics &nbsp;&nbsp; ☐ Web Scraping/Crawling  
☐ Security/Penetration Testing (with written authorization only)

**Brief description (design, datasets, tools, procedures, evaluation):**  
EasyTech (EasyTechStore) is a web-based e-commerce platform developed using Python (Django Framework), Django REST Framework, HTML5, CSS3, Bootstrap 5, JavaScript, Redis, and PostgreSQL for database management. The system automates electronic gadget discovery, inventory reservation, cryptographic payment validation, order fulfillment, and AI-driven customer support through a unified portal for customers and store managers. Customers can explore products with faceted filters (category, brand, price range), compare gadget specifications side by side, manage shopping carts with real-time stock verification, and track order lifecycles with automated ReportLab PDF invoice generation. Store managers can manage inventory, process batch catalog updates via Excel/CSV (OpenPyXL), and fulfill orders through a finite state machine. The system incorporates Artificial Intelligence and Retrieval-Augmented Generation (RAG) using ChromaDB vector database and LLMs (Groq / Ollama Llama 3.2 / Qwen) to deliver natural language product recommendations and technical assistance grounded on catalog data. It follows a modular Model–View–Template (MVT) architecture with decoupled domain applications (users, products, category, cart, orders, chatbot) to ensure high maintainability, testability, and scalability. Concurrency controls employ pessimistic row-level locking (`select_for_update`) and atomic SQL `F()` expressions to prevent race conditions during checkout, coupled with a 15-minute order reservation expiration worker (`cleanup_expired_orders`). Two-stage payment processing uses the Strategy/Adapter pattern with HMAC-SHA256 signature verification (`hmac.compare_digest`) for payment integrity. Evaluation focuses on automated unit and integration tests using Pytest, concurrency load testing verifying zero stock overselling, cryptographic tamper testing, and vector retrieval accuracy across a 1,000-question benchmark dataset.

**15. Software/Hardware & Infrastructure**  
**Primary languages/frameworks:** Python, Django Framework, Cookiecutter Django (project scaffolding), Django REST Framework, HTML5, CSS3, Bootstrap 5, JavaScript, PostgreSQL, Redis  
**External libraries/models (names & licenses):** Django (BSD License), Bootstrap (MIT License), Django REST Framework (BSD License), ChromaDB (Apache-2.0 License), OpenAI Python SDK (Apache-2.0 License), ReportLab (BSD License), OpenPyXL (MIT License), Argon2-cffi (MIT License), Django-Allauth (MIT License), Psycopg (PostgreSQL/LGPL License), Redis-py (MIT License), and Gunicorn (MIT License). LLM Models: Llama 3.2 (Meta Community License) via Ollama, and Groq Cloud API (Commercial API terms for development).  
**Compute/Cloud services (provider, region, data location):** Local development environment using Docker and Docker Compose for PostgreSQL, Redis, and Traefik deployment. Amazon Web Services (AWS) – EC2 for application deployment with Traefik reverse proxy and Let's Encrypt SSL (https://easystore1.me). Amazon Web Services (AWS) – EC2, EU North (Stockholm) / US East, Data hosted in AWS Cloud.  
**On-prem resources/labs:** Personal computer with Python, Django, PostgreSQL, Docker Desktop, Visual Studio Code, Git, GitHub, and internet connectivity.

---

### C. Data, Participants, and Ethics

**16. Does the study involve human participants (e.g., usability tests, surveys, interviews, behavioral logging)?**  
☐ Yes &nbsp;&nbsp; ☑ No  
*(If Yes, answer Q17–Q24. If No, skip to Q25.)*

17. Participant Recruitment (source, criteria, messages, incentives/honoraria):
18. Anticipated Impact/Risks to Participants (time burden, privacy, discomfort, potential risks):
19. Confidentiality & Anonymity (minimization, pseudonymization, access controls):
20. Informed Consent Procedure (consent form/script, withdrawal, parental consent, accessibility):
21. Sensitive Contexts (tick if applicable):  
    ☐ Personal or sensitive topics &nbsp;&nbsp; ☐ Children or vulnerable adults  
    ☐ Possible psychological/social/physical harm or distress  
    ☐ Audio/video recording or screen capture &nbsp;&nbsp; ☐ Geo-location tracking or telemetry  
    If ticked, justify risk-mitigation measures and provide protocols:
22. Data Collection Details (Human Studies)  
    Instruments (surveys/interview guides/UX tasks):  
    Duration per participant: ______ minutes &nbsp;&nbsp;&nbsp;&nbsp; N (target): ______  
    Compensation (if any):
23. Debriefing & Support (post-study debrief, support contacts, complaint mechanism):
24. Privacy Notices (data use, storage, sharing, and participant rights):

#### If No Human Participants: Complete the Following

**25. Datasets and Digital Sources**  
**Primary datasets/sources (name, URL/DOI, owner):** Custom sample data (synthetic electronic gadgets catalog comprising smartphones, laptops, audio equipment, dummy prices, SKUs, and specifications), and a curated benchmark suite of 1,000 domain test queries for AI chatbot evaluation.  
**Licenses/Terms of Use (attach evidence of permissible use):** N/A  
**Provenance & Documentation (dataset cards/datasheets, model cards):** N/A  

**26. Web Scraping / Crawling (if applicable)**  
Target domains/URLs: N/A  
Respect for robots.txt and rate-limits: ☐ Yes &nbsp;&nbsp; ☑ N/A  
Terms of Service compliance & permission letters (attach): ☐ Attached &nbsp;&nbsp; ☑ N/A  
Data minimization & exclusion of personal data: ☑ Ensured  
Anti-disruption safeguards (throttling, off-peak scheduling): ☑ Implemented / N/A  

**27. Security/Penetration Testing or Network Experiments (if applicable)**  
Scope and assets under explicit written authorization (attach proof): ☐ Attached &nbsp;&nbsp; ☑ N/A  
Non-interference & logging plan; rollback procedures: Testing is restricted exclusively to local mock sandbox environments and Docker loopback interfaces; no external networks, payment gateways, or third-party production systems are targeted.  
Legal and institutional policy compliance statement: All security checks (CSRF verification, SQL injection protection via Django ORM, and HMAC signature tamper tests) strictly comply with institutional IT usage policies and academic ethics.

---

### D. Data Protection & Management (All Projects)

**28. Personal Data Handling (tick all applicable):**  
☑ No personal data processed &nbsp;&nbsp; ☐ Pseudonymized data only  
☐ Personal data (contact info, identifiers) &nbsp;&nbsp; ☐ Special categories/sensitive data  
*(All customer profiles, shipping addresses, phone numbers, and payment tokens in the system are synthetic dummy records generated purely for academic testing.)*

**29. Data Protection Compliance**  
**Applicable laws/policies (institutional policy, national data protection law, platform TOS):** Institutional policy, Information Technology (IT) Act (India), OWASP Top 10 Web Application Security guidelines  
**Legal basis/permission for processing (consent, license, contractual permission, legitimate use):** Legitimate educational use and academic software development

**30. Data Lifecycle Plan**  
**Storage location (drive/server/cloud & region):** Local File System, local PostgreSQL container, and AWS EC2 cloud instance (EU North / Stockholm).  
**Security (encryption, access control, keys/passwords):** Argon2 password hashing, role-based access control (RBAC), Django CSRF tokens, environment variable isolation (`.env` files) for `SECRET_KEY` and API keys, and constant-time HMAC-SHA256 signature verification (`hmac.compare_digest`).  
**Retention period:** 4 months &nbsp;&nbsp;&nbsp;&nbsp; **Destruction method & date:** Secure deletion after academic completion and degree evaluation, 15/11/2026  
**Sharing (who will access; will de-identified data/code be released?):** ☑ Yes &nbsp;&nbsp; ☐ No  
**If Yes, repository/license and de-identification approach:** https://github.com/athulya3404/EasyTechStore (Released under MIT License; all sensitive credentials, secret keys, and private `.env` configurations are excluded from the repository via `.gitignore`).

**31. Bias, Fairness, and Safety (for AI/ML/NLP/CV)**  
**Expected risks (bias, representational harms, unsafe outputs):** The RAG-based AI chatbot may produce hallucinations, out-of-catalog product recommendations, or inaccurate hardware compatibility advice when responding to complex user queries.  
**Mitigations (sampling, audits, human oversight, content filters, red-teaming):** Use Retrieval-Augmented Generation (RAG) strictly grounded on verified store inventory and technical spec sheets stored in the ChromaDB vector database. System prompts enforce explicit guardrails requiring the assistant to decline non-electronics queries and acknowledge when a product or feature is not in the store catalog. Evaluated across 1,000 diverse test questions to verify intent extraction and price-filtering accuracy.  
**Model reporting (model card/limitations/appropriate use):** Document the AI/RAG architecture, vector retrieval parameters, and evaluation benchmark in the project report. The chatbot is designed as an advisory shopping aid and customer support assistant, not an autonomous transactional decision-maker.

**32. Intellectual Property & Licensing**  
**Ownership of code/data/models:** Own  
**Open-source release plan and license (e.g., MIT, Apache-2.0, CC-BY):** MIT License  
**Third-party license compliance confirmed:** ☑ Yes

**33. Environmental & Cost Considerations (optional)**  
**Estimated compute (GPU hours/energy) and minimization steps:** N/A (Standard CPU workstation and lightweight cloud instance; local ChromaDB embeddings and cached queries minimize API calls and compute overhead).  
**Budget/credits and cost controls:** Free-tier API keys, open-source software stack, and low-cost/free-tier AWS EC2 cloud instance; minimal financial expenditure.

---

### E. Training, Conflicts, and Safety

**34. Research Ethics/Compliance Training Completed?**  
☑ Yes (course/date): 01/10/2026 &nbsp;&nbsp;&nbsp;&nbsp; ☐ No (commitment date: ________)

**35. Conflicts of Interest (financial, employment, personal, or role-based)**  
☑ None &nbsp;&nbsp;&nbsp;&nbsp; ☐ Disclosed below: _______________________________________________

**36. Health & Safety (labs/IoT/robotics/fieldwork): risk assessment; emergency procedures and supervision**  
☐ Yes (attach) &nbsp;&nbsp;&nbsp;&nbsp; ☑ Not applicable
