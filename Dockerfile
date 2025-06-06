FROM python:3.9-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    pandoc \
    libreoffice \
    texlive \
    texlive-latex-extra \
    texlive-xetex \
    texlive-plain-generic \      
    && rm -rf /var/lib/apt/lists/*


WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app/

EXPOSE 5000

CMD ["python", "app.py"]
