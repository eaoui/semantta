# Development

This document describes how to set up Semantta from source and run it in a development environment.

## Prerequisites

* Python **3.10+** with `pip`
* Node.js **18+** with `npm`
* [Apache Jena Fuseki](https://jena.apache.org/documentation/fuseki2/) **5+** (requires Java **17+**)

## Getting Started

### 1. Get Semantta

Clone the repository:

```bash
git clone https://github.com/eaoui/semantta.git
cd semantta
```

For installing the packaged desktop application, see the [installation guide](../INSTALLATION.md).

### 2. Start a Fuseki Dataset

Start an existing (or create a new) Fuseki dataset by running the `fuseki-server` script with a TDB2 location:

```bash
# Linux/Mac
./fuseki-server --update --tdb2 --loc /path/to/database /dataset_name

# Windows
.\fuseki-server --update --tdb2 --loc path\to\database /dataset_name
```

The default port is `3030` and the default dataset name is `obmms`.

If you use a different port or name, set `FUSEKI_DATASET_URL` in a `backend/.env` file:

```bash
cd backend
cp .env.example .env  # Windows: copy .env.example .env
# then edit FUSEKI_DATASET_URL
```

### 3. Run the Backend

```bash
# 1. move to the /backend directory
cd backend

# 2. create a virtual environment named .venv
python -m venv .venv

# 3. activate the virtual environment
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 4. install Python dependencies
pip install -r requirements.txt

# 5. start the API server (default port number is 8000)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Next time you only need steps 1, 3, and 5.

### 4. Run the Frontend

```bash
# 1. move to the /frontend directory
cd frontend

# 2. install Node.js packages
npm install

# 3. start the development server
npm run dev
```

Next time you only need steps 1 and 3.

The app will be available at `http://localhost:3000`.
