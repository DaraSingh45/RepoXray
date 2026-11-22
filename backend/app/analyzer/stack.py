"""Technology-stack detection from dependencies, files and content signatures."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

# name -> (category, matchers on dependency names)
DEP_SIGNATURES: dict[str, tuple[str, list[str]]] = {
    # Frontend frameworks
    "React": ("Frontend", ["react", "react-dom"]), "Next.js": ("Frontend", ["next"]),
    "Vue": ("Frontend", ["vue"]), "Nuxt": ("Frontend", ["nuxt"]), "Angular": ("Frontend", ["@angular/core"]),
    "Svelte": ("Frontend", ["svelte"]), "SvelteKit": ("Frontend", ["@sveltejs/kit"]),
    "Solid": ("Frontend", ["solid-js"]), "Astro": ("Frontend", ["astro"]), "Remix": ("Frontend", ["@remix-run/react"]),
    "Preact": ("Frontend", ["preact"]), "jQuery": ("Frontend", ["jquery"]), "Gatsby": ("Frontend", ["gatsby"]),
    "React Native": ("Mobile", ["react-native"]), "Expo": ("Mobile", ["expo"]), "Ionic": ("Mobile", ["@ionic/core", "@ionic/react"]),
    "Electron": ("Desktop", ["electron"]), "Tauri": ("Desktop", ["@tauri-apps/api", "tauri"]),
    # UI / styling
    "Tailwind CSS": ("Styling", ["tailwindcss"]), "Material UI": ("Styling", ["@mui/material", "@material-ui/core"]),
    "Chakra UI": ("Styling", ["@chakra-ui/react"]), "Bootstrap": ("Styling", ["bootstrap", "react-bootstrap"]),
    "styled-components": ("Styling", ["styled-components"]), "Sass": ("Styling", ["sass", "node-sass"]),
    "shadcn/Radix": ("Styling", ["@radix-ui/react-slot", "@radix-ui/react-dialog"]),
    "Ant Design": ("Styling", ["antd"]), "Framer Motion": ("Styling", ["framer-motion"]),
    # State / data fetching
    "Redux": ("State", ["redux", "@reduxjs/toolkit"]), "Zustand": ("State", ["zustand"]), "MobX": ("State", ["mobx"]),
    "TanStack Query": ("State", ["@tanstack/react-query", "react-query"]), "Apollo GraphQL": ("API", ["@apollo/client", "apollo-server", "@apollo/server"]),
    "tRPC": ("API", ["@trpc/server"]), "Axios": ("API", ["axios"]), "GraphQL": ("API", ["graphql", "graphene", "strawberry-graphql"]),
    # Backend (JS)
    "Express": ("Backend", ["express"]), "NestJS": ("Backend", ["@nestjs/core"]), "Fastify": ("Backend", ["fastify"]),
    "Koa": ("Backend", ["koa"]), "Hono": ("Backend", ["hono"]), "Socket.IO": ("Realtime", ["socket.io", "python-socketio"]),
    # Backend (Python)
    "Django": ("Backend", ["django"]), "Flask": ("Backend", ["flask"]), "FastAPI": ("Backend", ["fastapi"]),
    "Starlette": ("Backend", ["starlette"]), "Tornado": ("Backend", ["tornado"]), "aiohttp": ("Backend", ["aiohttp"]),
    "Django REST Framework": ("Backend", ["djangorestframework"]), "Celery": ("Queue", ["celery"]),
    "Streamlit": ("Frontend", ["streamlit"]), "Gradio": ("Frontend", ["gradio"]), "Pydantic": ("Backend", ["pydantic"]),
    "Uvicorn": ("Backend", ["uvicorn"]), "Gunicorn": ("Backend", ["gunicorn"]),
    # Backend (others)
    "Spring Boot": ("Backend", ["org.springframework.boot:spring-boot-starter-web", "org.springframework.boot:spring-boot-starter"]),
    "Gin": ("Backend", ["github.com/gin-gonic/gin"]), "Echo": ("Backend", ["github.com/labstack/echo/v4"]),
    "Fiber": ("Backend", ["github.com/gofiber/fiber/v2"]), "Chi": ("Backend", ["github.com/go-chi/chi/v5"]),
    "Actix Web": ("Backend", ["actix-web"]), "Axum": ("Backend", ["axum"]), "Rocket": ("Backend", ["rocket"]),
    "Tokio": ("Backend", ["tokio"]), "Rails": ("Backend", ["rails"]), "Laravel": ("Backend", ["laravel/framework"]),
    "Symfony": ("Backend", ["symfony/framework-bundle"]), "Flutter": ("Mobile", ["flutter"]),
    "ASP.NET Core": ("Backend", ["Microsoft.AspNetCore.App", "Swashbuckle.AspNetCore"]),
    # Data
    "PostgreSQL": ("Database", ["pg", "psycopg2", "psycopg2-binary", "psycopg", "asyncpg", "github.com/lib/pq", "github.com/jackc/pgx/v5", "org.postgresql:postgresql", "postgres"]),
    "MySQL": ("Database", ["mysql", "mysql2", "pymysql", "mysqlclient", "github.com/go-sql-driver/mysql"]),
    "MongoDB": ("Database", ["mongodb", "mongoose", "pymongo", "motor", "go.mongodb.org/mongo-driver"]),
    "Redis": ("Database", ["redis", "ioredis", "github.com/redis/go-redis/v9", "aioredis"]),
    "SQLite": ("Database", ["sqlite3", "better-sqlite3", "rusqlite"]), "Supabase": ("Database", ["@supabase/supabase-js", "supabase"]),
    "Firebase": ("Database", ["firebase", "firebase-admin"]), "Elasticsearch": ("Database", ["@elastic/elasticsearch", "elasticsearch"]),
    "Prisma": ("ORM", ["prisma", "@prisma/client"]), "Drizzle": ("ORM", ["drizzle-orm"]), "TypeORM": ("ORM", ["typeorm"]),
    "Sequelize": ("ORM", ["sequelize"]), "SQLAlchemy": ("ORM", ["sqlalchemy"]), "GORM": ("ORM", ["gorm.io/gorm"]),
    "Diesel": ("ORM", ["diesel"]), "SQLModel": ("ORM", ["sqlmodel"]), "Mongoose": ("ORM", ["mongoose"]), "Alembic": ("ORM", ["alembic"]), "Kafka": ("Queue", ["kafkajs", "kafka-python", "confluent-kafka"]),
    "RabbitMQ": ("Queue", ["amqplib", "pika"]),
    # AI / ML / data science
    "PyTorch": ("AI/ML", ["torch"]), "TensorFlow": ("AI/ML", ["tensorflow", "@tensorflow/tfjs"]), "Keras": ("AI/ML", ["keras"]),
    "scikit-learn": ("AI/ML", ["scikit-learn", "sklearn"]), "Hugging Face": ("AI/ML", ["transformers", "@huggingface/inference", "datasets"]),
    "LangChain": ("AI/ML", ["langchain", "langchain-core", "@langchain/core"]), "LlamaIndex": ("AI/ML", ["llama-index", "llama_index"]),
    "OpenAI SDK": ("AI/ML", ["openai"]), "Anthropic SDK": ("AI/ML", ["anthropic", "@anthropic-ai/sdk"]), "Ollama": ("AI/ML", ["ollama"]),
    "NumPy": ("Data", ["numpy"]), "Pandas": ("Data", ["pandas"]), "Matplotlib": ("Data", ["matplotlib"]),
    "Plotly": ("Data", ["plotly"]), "D3": ("Data", ["d3"]), "Chart.js": ("Data", ["chart.js"]), "Recharts": ("Data", ["recharts"]),
    "OpenCV": ("AI/ML", ["opencv-python", "opencv-python-headless"]), "ChromaDB": ("AI/ML", ["chromadb"]),
    # Tooling / testing
    "TypeScript": ("Language", ["typescript"]), "Vite": ("Build", ["vite"]), "Webpack": ("Build", ["webpack"]),
    "esbuild": ("Build", ["esbuild"]), "Rollup": ("Build", ["rollup"]), "Turborepo": ("Build", ["turbo"]),
    "Babel": ("Build", ["@babel/core"]), "ESLint": ("Quality", ["eslint"]), "Prettier": ("Quality", ["prettier"]),
    "Biome": ("Quality", ["@biomejs/biome"]), "Ruff": ("Quality", ["ruff"]), "Black": ("Quality", ["black"]),
    "mypy": ("Quality", ["mypy"]), "Jest": ("Testing", ["jest"]), "Vitest": ("Testing", ["vitest"]),
    "Mocha": ("Testing", ["mocha"]), "Cypress": ("Testing", ["cypress"]), "Playwright": ("Testing", ["@playwright/test", "playwright"]),
    "Testing Library": ("Testing", ["@testing-library/react"]), "pytest": ("Testing", ["pytest"]),
    "JUnit": ("Testing", ["org.junit.jupiter:junit-jupiter", "junit:junit"]), "Storybook": ("Testing", ["storybook", "@storybook/react"]),
    # Auth / payments / infra SDKs
    "NextAuth": ("Auth", ["next-auth"]), "Passport": ("Auth", ["passport"]), "JWT": ("Auth", ["jsonwebtoken", "pyjwt", "python-jose"]),
    "Clerk": ("Auth", ["@clerk/nextjs"]), "Stripe": ("Payments", ["stripe"]), "AWS SDK": ("Cloud", ["boto3", "aws-sdk", "@aws-sdk/client-s3"]),
    "Docker SDK": ("Cloud", ["docker"]), "Pulumi": ("Cloud", ["@pulumi/pulumi", "pulumi"]),
}

# file/path based detection
FILE_SIGNATURES: list[tuple[str, str, re.Pattern]] = [
    ("Docker", "DevOps", re.compile(r"(^|/)Dockerfile[^/]*$|(^|/)\.dockerignore$")),
    ("Docker Compose", "DevOps", re.compile(r"(^|/)(docker-)?compose[^/]*\.ya?ml$")),
    ("Kubernetes", "DevOps", re.compile(r"(^|/)(k8s|kubernetes|helm|charts)/|(^|/)Chart\.yaml$")),
    ("GitHub Actions", "CI/CD", re.compile(r"^\.github/workflows/.+\.ya?ml$")),
    ("GitLab CI", "CI/CD", re.compile(r"(^|/)\.gitlab-ci\.yml$")), ("CircleCI", "CI/CD", re.compile(r"^\.circleci/")),
    ("Jenkins", "CI/CD", re.compile(r"(^|/)Jenkinsfile$")), ("Travis CI", "CI/CD", re.compile(r"(^|/)\.travis\.yml$")),
    ("Terraform", "DevOps", re.compile(r"\.tf$")), ("Ansible", "DevOps", re.compile(r"(^|/)(ansible|playbooks?)/.*\.ya?ml$")),
    ("Vercel", "Hosting", re.compile(r"(^|/)vercel\.json$")), ("Netlify", "Hosting", re.compile(r"(^|/)netlify\.toml$")),
    ("Heroku", "Hosting", re.compile(r"(^|/)Procfile$")), ("Firebase Hosting", "Hosting", re.compile(r"(^|/)firebase\.json$")),
    ("Make", "Build", re.compile(r"(^|/)Makefile$")), ("CMake", "Build", re.compile(r"(^|/)CMakeLists\.txt$")),
    ("Gradle", "Build", re.compile(r"(^|/)build\.gradle(\.kts)?$")), ("Maven", "Build", re.compile(r"(^|/)pom\.xml$")),
    ("Poetry", "Build", re.compile(r"(^|/)poetry\.lock$")), ("uv", "Build", re.compile(r"(^|/)uv\.lock$")),
    ("pnpm", "Build", re.compile(r"(^|/)pnpm-(lock|workspace)\.yaml$")), ("Yarn", "Build", re.compile(r"(^|/)yarn\.lock$")),
    ("Bun", "Build", re.compile(r"(^|/)bun\.lockb?$")), ("Nx", "Build", re.compile(r"(^|/)nx\.json$")),
    ("Lerna", "Build", re.compile(r"(^|/)lerna\.json$")), ("pre-commit", "Quality", re.compile(r"(^|/)\.pre-commit-config\.yaml$")),
    ("EditorConfig", "Quality", re.compile(r"(^|/)\.editorconfig$")), ("Dependabot", "CI/CD", re.compile(r"^\.github/dependabot\.ya?ml$")),
    ("Jupyter", "Data", re.compile(r"\.ipynb$")), ("Protocol Buffers", "API", re.compile(r"\.proto$")),
    ("OpenAPI", "API", re.compile(r"(^|/)(openapi|swagger)\.(ya?ml|json)$")), ("Prisma", "ORM", re.compile(r"(^|/)schema\.prisma$")),
    ("Devcontainer", "DevOps", re.compile(r"^\.devcontainer/")), ("Nginx", "DevOps", re.compile(r"(^|/)nginx[^/]*\.conf$")),
]

CATEGORY_ORDER = ["Language", "Frontend", "Mobile", "Desktop", "Styling", "State", "Backend", "API", "Realtime",
                  "Database", "ORM", "Queue", "AI/ML", "Data", "Auth", "Payments", "Cloud", "Build", "Testing",
                  "Quality", "DevOps", "CI/CD", "Hosting"]

TECH_INFO = {
    "React": "Component-based UI library", "Next.js": "React meta-framework with SSR/routing",
    "FastAPI": "Async Python web API framework", "Django": "Batteries-included Python web framework",
    "Flask": "Lightweight Python web framework", "Express": "Minimal Node.js web server framework",
    "Docker": "Containerised builds & runtime", "GitHub Actions": "CI/CD workflows on GitHub",
    "PostgreSQL": "Relational database", "MongoDB": "Document database", "Redis": "In-memory cache / store",
    "Tailwind CSS": "Utility-first CSS framework", "Vite": "Fast dev server & bundler", "TypeScript": "Typed superset of JavaScript",
    "PyTorch": "Deep learning framework", "LangChain": "LLM application framework", "Spring Boot": "Java application framework",
}


def detect(files: list, deps: list[dict], languages: list[dict], contents: dict[str, str]) -> list[dict]:
    found: dict[str, dict] = {}

    def add(name: str, cat: str, evidence: str):
        if name not in found:
            found[name] = {"name": name, "category": cat, "evidence": [], "description": TECH_INFO.get(name, "")}
        if evidence not in found[name]["evidence"] and len(found[name]["evidence"]) < 4:
            found[name]["evidence"].append(evidence)

    for lang in languages[:8]:
        if lang.get("is_code") and lang["percent"] >= 2:
            add(lang["name"], "Language", f"{lang['percent']}% of code")

    dep_index: dict[str, dict] = {}
    for d in deps:
        dep_index.setdefault(d["name"].lower(), d)
    for d in deps:
        n = d["name"].lower()
        if n.startswith("org.springframework.boot:spring-boot-starter"):
            add("Spring Boot", "Backend", f"{d['name']} in {d['manifest']}")
            if "data-jpa" in n:
                add("Spring Data JPA", "ORM", d["name"])
            if "thymeleaf" in n:
                add("Thymeleaf", "Frontend", d["name"])
        elif n.startswith("org.springframework:"):
            add("Spring", "Backend", f"{d['name']} in {d['manifest']}")
        elif n in ("com.h2database:h2",):
            add("H2", "Database", d["name"])
        elif n in ("com.mysql:mysql-connector-j", "mysql:mysql-connector-java"):
            add("MySQL", "Database", d["name"])
    for tech, (cat, names) in DEP_SIGNATURES.items():
        for n in names:
            d = dep_index.get(n.lower())
            if d:
                add(tech, cat, f"{d['name']} in {d['manifest']}")
                break

    paths = [f.path for f in files]
    for tech, cat, rx in FILE_SIGNATURES:
        for p in paths:
            if rx.search(p):
                add(tech, cat, p)
                break

    # content signatures for languages without manifests (e.g. plain Flask script)
    imports_blob = "\n".join(t[:4000] for p, t in list(contents.items())[:800] if p.endswith((".py", ".js", ".ts", ".tsx", ".jsx")))
    for tech, cat, rx in [
        ("Flask", "Backend", r"from flask import|import flask"), ("FastAPI", "Backend", r"from fastapi import"),
        ("Django", "Backend", r"from django"), ("Express", "Backend", r"require\(['\"]express['\"]\)|from ['\"]express['\"]"),
        ("React", "Frontend", r"from ['\"]react['\"]"), ("Streamlit", "Frontend", r"import streamlit"),
        ("PyTorch", "AI/ML", r"import torch"), ("TensorFlow", "AI/ML", r"import tensorflow"),
        ("Pandas", "Data", r"import pandas"), ("NumPy", "Data", r"import numpy"), ("SQLite", "Database", r"import sqlite3"),
        ("OpenAI SDK", "AI/ML", r"from openai import|import openai"), ("Tkinter", "Desktop", r"import tkinter|from tkinter"),
        ("PyQt", "Desktop", r"from PyQt[56]|from PySide[26]"), ("Pygame", "Frontend", r"import pygame"),
    ]:
        if re.search(rx, imports_blob):
            add(tech, cat, "import statements")

    order = {c: i for i, c in enumerate(CATEGORY_ORDER)}
    return sorted(found.values(), key=lambda t: (order.get(t["category"], 99), t["name"]))


def project_type(stack: list[dict], files: list, projects: list[dict]) -> str:
    names = {t["name"] for t in stack}
    cats = {t["category"] for t in stack}
    has_frontend = bool(cats & {"Frontend"})
    has_backend = "Backend" in cats
    if names & {"React Native", "Flutter", "Expo", "Ionic"}:
        return "Mobile application"
    if names & {"Electron", "Tauri", "Tkinter", "PyQt"}:
        return "Desktop application"
    if has_frontend and has_backend:
        return "Full-stack web application"
    if names & {"Streamlit", "Gradio"}:
        return "Data / ML web app"
    if has_backend:
        return "Backend service / API"
    if has_frontend:
        return "Frontend web application"
    if "AI/ML" in cats:
        return "Machine-learning project"
    if "Jupyter" in names:
        return "Data-science notebooks"
    paths = [f.path for f in files]
    root_projects = [pr for pr in projects if "/" not in pr["path"]]
    if any(pr.get("bin") for pr in projects):
        return "CLI tool"
    if any(pr["ecosystem"] == "npm" and (pr.get("main") or pr.get("name")) for pr in root_projects) or \
            any(p in ("setup.py", "pyproject.toml", "Cargo.toml", "go.mod") for p in paths):
        return "Library / package"
    if any(p.endswith(("setup.py", "pyproject.toml", "Cargo.toml")) for p in paths):
        return "Library / CLI tool"
    if any(PurePosixPath(p).suffix in (".md", ".mdx") for p in paths) and len([f for f in files if f.is_code]) < 3:
        return "Documentation / resource collection"
    return "Software project"
