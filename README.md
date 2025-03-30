# Any File to PDF Converter (Docker Edition)

This is a Flask application that lets you upload **any file** (up to 50MB) and attempts to convert it to PDF. It handles:

- **Microsoft Office / OpenDocument** files via **LibreOffice**.
- **Jupyter notebooks** (`.ipynb`) via **nbconvert**.
- **Text / Markup / Source Code** files via **Pandoc**.
- **Data files** (`.csv`, `.tsv`, `.parquet`, etc.) using **pandas** to generate a short preview in PDF.
- Any unrecognized file is still attempted via Pandoc (fallback).

## Requirements

- [Docker](https://docs.docker.com/get-docker/)

## Building the Docker Image


docker build -t any2pdf_app .
