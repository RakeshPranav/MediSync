# Medical Batch Inventory & Expiry Management System

A smart inventory management system designed to manage medical product batches, monitor expiry dates, maintain storage conditions, and ensure safe and efficient hospital dispatch.

---

## 1. Project Overview

The **Medical Batch Inventory & Expiry Management System** is a Python-based application designed to manage finished medical product batches such as medicines, IV fluids, and medical test kits.

In pharmaceutical warehouses, finished medical batches must undergo quality inspection before they can be released for distribution. Each batch has a specific expiry date and may have special storage requirements.

This system helps warehouse operators and quality teams manage these operations efficiently by ensuring that:

- Only quality-approved batches are available for dispatch.
- Products are dispatched based on their earliest expiry date.
- Hospital-specific minimum shelf-life requirements are respected.
- Expired and unsuitable batches are prevented from being dispatched.
- Temperature-sensitive products are monitored.
- Batches experiencing temperature excursions are automatically quarantined until quality review.

The application provides a centralized interface to monitor inventory, manage batch quality, track storage conditions, and process hospital orders.

## 2. Problem Statement

Medical warehouses often face challenges in managing finished product batches waiting for quality release.

Some important challenges include:

1. **Batch Quality Management:** Products cannot be distributed until they receive quality approval.
2. **Expiry Management:** Products with earlier expiry dates must be prioritized during dispatch.
3. **Customer Shelf-Life Requirements:** Hospitals may require products to have a minimum remaining shelf life, such as six months.
4. **Temperature Monitoring:** Certain medical products must be stored within a specific temperature range, such as 2–8°C.
5. **Quarantine Management:** Any batch experiencing an unacceptable temperature excursion must be isolated until reviewed by the quality team.
6. **Inventory Accuracy:** Stock quantities must be updated correctly after every successful dispatch.

This project addresses these challenges through automated validation, batch tracking, and inventory allocation.

## 3. Key Features

### 3.1 Inventory and Batch Management
- Add and manage medical product batches.
- Maintain batch IDs, product names, quantities, and expiry dates.
- Track batch quality status.
- View available inventory and batch details.

### 3.2 FEFO-Based Dispatch

The system implements the **FEFO (First Expired, First Out)** inventory allocation strategy.

This means the batch with the earliest eligible expiry date is dispatched first.

Example:

| Batch | Expiry Date | Quantity |
|---|---|---:|
| BATCH101 | June 2027 | 100 |
| BATCH102 | February 2027 | 50 |
| BATCH103 | October 2027 | 80 |

If a hospital requests 120 units, the system prioritizes BATCH102, followed by BATCH101.

Only batches satisfying all dispatch conditions are considered.

### 3.3 Minimum Shelf-Life Validation

Different hospitals may have different minimum shelf-life requirements.

For example:

| Hospital | Minimum Shelf Life |
|---|---:|
| Apollo Hospital | 6 Months |
| City Hospital | 8 Months |
| Green Valley Hospital | 12 Months |

Before dispatching a batch, the system checks whether its expiry date satisfies the hospital's required remaining shelf life.

A batch that expires before the required cutoff date is excluded from dispatch.

### 3.4 Temperature Monitoring

Certain medical products require controlled storage conditions.

This system supports temperature monitoring for products requiring storage between **2°C and 8°C**.

| Temperature | Condition | Action |
|---|---|---|
| 5°C | Normal | No action |
| 8°C | Normal | No action |
| 9°C | Temperature Excursion | Quarantine |
| 1°C | Temperature Excursion | Quarantine |

Temperature readings are recorded in the database for monitoring and traceability.

### 3.5 Quarantine and Quality Control

When a temperature excursion occurs:

1. The batch is automatically marked as Quarantined.
2. The batch becomes unavailable for dispatch.
3. Normal temperature readings do not automatically release it.
4. The quality team reviews the batch.
5. The quality team can approve or reject the batch.
6. The decision and reason are recorded for future reference.

### 3.6 Dispatch Management

- Select a hospital and product.
- Enter the required quantity.
- Automatically identify eligible batches.
- Allocate stock using FEFO.
- Validate minimum shelf-life requirements.
- Prevent dispatch of expired, rejected, or quarantined stock.
- Prevent partial dispatch when sufficient eligible stock is unavailable.
- Update inventory quantities after successful dispatch.
- Maintain dispatch history.

### 3.7 Dashboard and Reports

The dashboard is designed to display:

- Total number of batches.
- Total available inventory.
- Released batches.
- Quarantined batches.
- Rejected batches.
- Products approaching expiry.
- Temperature excursion alerts.
- Inventory and dispatch information.

---

## 4. Technology Stack

| Technology | Purpose |
|---|---|
| Python | Backend development and business logic |
| SQLite | Relational database management |
| Streamlit | Web-based user interface |
| Pandas | Data handling and tabular representation |
| Plotly | Interactive dashboard visualizations (optional) |

### Why These Technologies?

**Python:** Provides simple and efficient implementation of inventory allocation, validation, and business rules.

**SQLite:** A lightweight relational database that stores project data locally without requiring a separate database server.

**Streamlit:** Makes it possible to build an interactive web application using Python without developing a separate frontend.

**Pandas:** Helps process and display inventory data.

**Plotly:** Can be used to create interactive charts for inventory monitoring.

---

## 5. System Architecture

The application follows a simple three-layer architecture.

```text
             USER
               |
               v
     +--------------------+
     |   Streamlit UI     |
     |      app.py        |
     +--------------------+
               |
               v
     +--------------------+
     |   Business Logic   |
     |   inventory.py     |
     +--------------------+
               |
               v
     +--------------------+
     |  Database Layer    |
     |   database.py      |
     +--------------------+
               |
               v
     +--------------------+
     |   SQLite Database  |
     |   inventory.db     |
     +--------------------+
```

### Layer Responsibilities

**1. Presentation Layer – `app.py`**

Provides the user interface for managing batches, hospitals, temperature readings, quality control, and dispatch operations.

**2. Business Logic Layer – `inventory.py`**

Contains the core application logic, including FEFO allocation, shelf-life validation, temperature excursion detection, quarantine management, and dispatch processing.

**3. Database Layer – `database.py`**

Handles database connections, table creation, and database configuration.

**4. Storage Layer – SQLite**

Stores batches, hospitals, temperature logs, dispatch records, and quality decisions.

---

## 6. Database Design

The application uses SQLite with six primary tables.

| Table | Description |
|---|---|
| `batches` | Stores medical product batch information. |
| `hospitals` | Stores hospital details and shelf-life requirements. |
| `temperature_logs` | Maintains temperature readings for batches. |
| `dispatches` | Stores hospital dispatch transactions. |
| `dispatch_items` | Stores batch-wise quantities included in dispatches. |
| `quality_records` | Maintains quality inspection decisions and reasons. |

### Database Relationships

- One batch can have multiple temperature readings.
- One batch can have multiple quality records.
- One hospital can have multiple dispatch records.
- One dispatch can contain multiple batch items.
- Each dispatch item references the batch from which stock was allocated.

---

## 7. Important Business Rules

The system follows the following rules to maintain inventory accuracy and product safety.

| Rule | Description |
|---|---|
| Quality Release | Only Released batches can be dispatched. |
| FEFO | Earliest-expiring eligible stock is dispatched first. |
| Shelf-Life Validation | Batch expiry must satisfy the hospital's minimum shelf-life requirement. |
| Temperature Control | Readings outside 2–8°C trigger quarantine for temperature-controlled batches. |
| Quarantine | Quarantined batches cannot be dispatched. |
| Quality Approval | Only quality review can release quarantined batches. |
| Rejection | Rejected batches cannot be dispatched. |
| Expiry Validation | Expired batches cannot be dispatched. |
| Stock Validation | Dispatch quantity cannot exceed eligible stock. |
| Transaction Safety | Stock deduction and dispatch creation must succeed together or be rolled back. |

### Understanding FEFO

FEFO stands for **First Expired, First Out**.

Unlike FIFO (First In, First Out), which prioritizes the oldest received stock, FEFO prioritizes the stock that expires first.

This is especially important in pharmaceutical inventory management because it helps minimize product wastage due to expiry.

### Understanding Shelf-Life Validation

Suppose:

- Current date: January 2027.
- Hospital requirement: 6 months.
- Required expiry cutoff: July 2027.

A batch expiring in June 2027 is not eligible for that hospital, even if the batch is quality-approved and has sufficient stock.

---

## 8. Project Folder Structure

```text
medical_inventory/
│
├── app.py
│
├── database.py
│
├── inventory.py
│
├── test_backend.py
│
├── test_sqlite.py
│
├── check_db.py
│
├── database/
│   └── inventory.db
│
├── requirements.txt
│
└── README.md
```

### File Description

| File | Responsibility |
|---|---|
| `app.py` | Streamlit application and user interface |
| `database.py` | Database connection and table creation |
| `inventory.py` | Inventory operations and business logic |
| `test_backend.py` | Backend business logic testing |
| `test_sqlite.py` | SQLite connection testing |
| `check_db.py` | Database verification |
| `inventory.db` | Local SQLite database |
| `requirements.txt` | Python dependency list |
| `README.md` | Project documentation |

---

## 9. Installation and Setup

Follow these steps to run the application on your local machine.

### Prerequisites

Make sure the following are installed:

- Python 3.10 or later.
- Visual Studio Code (recommended).
- Git (optional).
- DB Browser for SQLite (optional, for viewing database contents).

### Step 1: Clone the Repository

```bash
git clone <your-repository-url>
```

Navigate to the project folder:

```bash
cd medical_inventory
```

### Step 2: Create a Virtual Environment

```bash
python -m venv venv
```

### Step 3: Activate the Virtual Environment

For Windows:

```bash
venv\Scripts\activate
```

### Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

If the requirements file is not yet created, install the packages manually:

```bash
pip install streamlit pandas plotly
```

Note: SQLite is included with Python through the built-in `sqlite3` module. It does not require a separate Python package.

### Step 5: Initialize the Database

Run:

```bash
python database.py
```

This creates the required database tables.

### Step 6: Run the Application

```bash
streamlit run app.py
```

The application will open in your default web browser.

The default Streamlit address is:

```text
http://localhost:8501
```

---

## 10. Testing Scenarios

The following scenarios should be tested to verify the application's business logic.

| Test Case | Expected Result |
|---|---|
| Add a valid medical batch | Batch should be created. |
| Add a batch with negative quantity | Validation should reject it. |
| Record temperature of 5°C | Batch remains in normal condition. |
| Record temperature of 9°C | Temperature-controlled batch is quarantined. |
| Record normal temperature after excursion | Batch remains quarantined pending review. |
| Approve quarantined batch | Batch becomes Released if quality conditions are satisfied. |
| Reject quarantined batch | Batch becomes Rejected. |
| Dispatch an expired batch | Dispatch should be prevented. |
| Dispatch a quarantined batch | Dispatch should be prevented. |
| Dispatch a batch with insufficient shelf life | Batch should be excluded. |
| Dispatch multiple eligible batches | FEFO allocation should be followed. |
| Request more than available eligible stock | Dispatch should fail without deducting stock. |

---

## 11. Sample Demonstration Workflow

A typical demonstration of the application can follow this sequence:

1. Open the dashboard and view the current inventory.
2. Navigate to Batch Management and inspect the available batches.
3. View different hospitals and their shelf-life requirements.
4. Open Temperature Monitoring and record a temperature excursion.
5. Verify that the affected batch is automatically quarantined.
6. Navigate to Quality Control and review the quarantined batch.
7. Approve or reject the batch based on the quality review.
8. Navigate to Dispatch Management.
9. Select a hospital and request a specific quantity of medicine.
10. Observe how the system allocates stock using FEFO.
11. Verify that batches failing shelf-life or quality checks are excluded.
12. Open Dispatch History to inspect the completed transaction.

This workflow demonstrates the most important features of the system.

---

## 12. Future Enhancements

The following improvements can be considered in future versions:

- Integration with Supabase or PostgreSQL for centralized database access.
- Role-based access for warehouse operators and quality teams.
- Barcode or QR code scanning for batch identification.
- Real-time IoT temperature monitoring.
- Automated email and notification alerts.
- Exporting inventory and dispatch reports to Excel or PDF.
- Advanced inventory analytics and forecasting.
- Audit logs for all inventory and quality operations.
- Authentication and secure user management.

---

## 13. Project Objectives

The main objectives of this project are:

1. To develop a reliable medical batch inventory management application.
2. To implement FEFO-based inventory allocation.
3. To enforce hospital-specific minimum shelf-life requirements.
4. To monitor temperature-sensitive medical products.
5. To implement quarantine and quality release workflows.
6. To maintain accurate inventory quantities and dispatch records.
7. To demonstrate the practical use of Python, SQL, and database transactions in solving a real-world inventory management problem.

---

## 14. Conclusion

The Medical Batch Inventory & Expiry Management System provides a structured approach to managing pharmaceutical inventory and hospital dispatch operations.

By combining FEFO allocation, shelf-life validation, temperature monitoring, and quality control, the application helps prevent unsafe or unsuitable medical products from being dispatched.

The project demonstrates how software engineering concepts, database management, and business logic can be applied to solve practical challenges in healthcare supply chain management.

---

**Developed as a Final-Year Engineering Placement Project**

**Technology:** Python | SQLite | Streamlit | Pandas | Plotly
