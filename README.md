
# Semantta — An Ontology‑based Linked Data Management System

A web‑based, RDF‑native platform for managing linked data based on OWL/RDF ontologies.
Semantta is domain‑independent and can host data from any domain.

## Architecture

Semantta is built around a three‑layer architecture:  
1. **Ontology Layer**: Provides capability to import semantics that represent knowledge about a domain, including concepts in the domian and relationships among them.  
2. **Application Profile (AP) Layer**: Provides capability to tailor the semantics from the *Ontology Layer* to the needs of a specific application.  
3. **Metadata Layer**: Provides capability to apply the tailored semantics from the *AP Layer* to real data.

## Features

- Import OWL/RDF ontologies and metadata in standard RDF formats (RDF/XML, Turtle, N‑Triples, JSON‑LD, …)
- Build a SHACL‑based, ontology‑aware Application Profile (AP)
- Create, import, edit, delete, and validate linked data against the AP and ontologies
- Generate an AP from existing metadata in one click
- Public dataset exploration with label‑first display and an interactive graph
- Plugin system and theme layers for extensibility and customisability
- Progressive Web App (PWA) with dark and light mode support

## Used Technologies

| Layer | Technology |
| --- | --- |
| Semantic Web | RDF, RDFS, OWL, SHACL, XSD, SPARQL |
| Backend | FastAPI, rdflib, owlrl, pyshacl, httpx |
| Triplestore | Apache Jena Fuseki |
| Frontend  | Nuxt 4 (Vue 3, TypeScript), Pinia, Tailwind CSS 4, SortableJS, vis‑network, Phosphor Icons, vue‑sonner |

## Prerequisites

- Python **3.10+** with `pip`
- Node.js **18+** with `npm`
- Apache Jena Fuseki – see the [installation guide](https://jena.apache.org/documentation/fuseki2/)

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/eaoui/semantta.git
cd semantta
```

### 2. Triplestore

Start (create/open) your Fuseki dataset. The simplest way is to run the fuseki-server script with a TDB2 location:

```bash
./fuseki-server --update --tdb2 --loc /path/to/database /dataset_name
```

The default port is 3030 and the default dataset name is obmms.
If you use a different port or name, set `FUSEKI_DATASET_URL` in a `backend/.env` file:

```bash
cd backend
cp .env.example .env	# then edit FUSEKI_DATASET_URL if necessary
```

### 3. Backend

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

Next time you only need stepts 1, 3, and 5.

### 4. Frontend

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

## Basic Workflow

1. **Import an ontology**: Upload an RDF/XML, Turtle, or other supported format via the admin interface. The system applies OWL‑RL reasoning and caches the result.
2. **Build the Application Profile**: Open the “Application Profile” page, activate the entities you need, and fine‑tune the SHACL constraints.
3. **Create or import metadata**: Create instances manually via the dynamic form, or upload RDF-based metadata files. Instances are validated against the AP.
4. **Explore publicly**: You can search or browser the existing dataset. The `/dataset` page indexes all instances. Click any instance to see its
description, syntax, and interactive graph.

## Project Structure

```
semantta/
├── backend/
│   ├── main.py              # FastAPI app, endpoints, core logic
│   ├── fuseki_store.py      # Async Fuseki client
│   ├── utils.py             # URI helpers
│   ├── vocab/               # OWL vocabulary for reasoning
│   ├── data/                # Runtime data (cache, uploads, settings)
│   └── plugins/             # User‑installed plugins
├── frontend/
│   └── app/
│       ├── components/      # Vue components
│       ├── composables/     # Reusable logic
│       ├── layouts/         # Admin and public layouts
│       ├── pages/           # Nuxt pages (admin & public)
│       ├── stores/          # Pinia store
│       ├── types/           # TypeScript interfaces
│       └── ...
```

## Contributing

Contributions are welcome! Please open an issue to discuss your idea before submitting a pull request.

## License

Semantta is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for more details.

See [LICENSE](LICENSE) for the full text.

## Applications

Have you built a public project on top of Semantta? Add it below!  

- [Example Application Name](https://example.app)
