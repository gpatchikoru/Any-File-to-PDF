import os
import uuid
import subprocess

from flask import Flask, request, render_template, send_from_directory, redirect, url_for
import pandas as pd
import img2pdf

app = Flask(__name__)

# Limit the maximum allowed payload to 50 MB
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024  # 50 MB

UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'GET':
        # Show the upload form
        return render_template('index.html')
    
    # Handle file upload
    if 'file' not in request.files:
        return "No 'file' field in form.", 400
    
    uploaded_file = request.files['file']
    if uploaded_file.filename == '':
        return "No file selected.", 400
    
    original_filename = uploaded_file.filename
    file_ext = os.path.splitext(original_filename)[1].lower()
    unique_id = str(uuid.uuid4())
    saved_filename = f"{unique_id}{file_ext}"
    saved_path = os.path.join(UPLOAD_FOLDER, saved_filename)
    
    # Save the uploaded file
    uploaded_file.save(saved_path)
    
    # Attempt to convert to PDF
    try:
        pdf_path = convert_to_pdf(saved_path, file_ext)
    except Exception as e:
        return f"Conversion error: {e}", 500
    
    if not pdf_path or not os.path.exists(pdf_path):
        return "Failed to produce a PDF.", 500
    
    # Redirect to a page that shows a "Download PDF" link
    pdf_filename = os.path.basename(pdf_path)
    return redirect(url_for('converted', filename=pdf_filename))

@app.route('/converted/<filename>')
def converted(filename):
    """
    Show a page indicating the PDF is ready, 
    with a link or button to download.
    """
    return render_template('converted.html', pdf_filename=filename)

@app.route('/download/<filename>')
def download_file(filename):
    """
    Downloads the specified PDF file from the uploads folder.
    """
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)


def convert_to_pdf(input_path, file_ext):
    """
    Main dispatcher: picks specialized methods or fallback.
    """
    # If it's an image, convert via img2pdf for speed
    if file_ext in ['.png', '.jpg', '.jpeg']:
        return convert_image_to_pdf(input_path)
    
    # If user uploaded a PDF, we won't re-convert
    if file_ext == '.pdf':
        return input_path
    
    # Office / ODF
    office_exts = ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp']
    if file_ext in office_exts:
        return convert_via_libreoffice(input_path)
    
    # Jupyter Notebooks
    if file_ext == '.ipynb':
        return convert_notebook_to_pdf(input_path)
    
    # CSV/TSV
    if file_ext in ['.csv', '.tsv']:
        return convert_csv_to_pdf(input_path, file_ext)
    
    # Data / binary
    data_exts = ['.parquet', '.feather', '.h5', '.hdf5', '.pickle', '.pkl', '.sav', '.dta', '.mat', '.db', '.sqlite']
    if file_ext in data_exts:
        return convert_datafile_to_pdf(input_path)
    
    # Fallback: Pandoc for text/markup/code
    return convert_via_pandoc(input_path)

def convert_image_to_pdf(image_path):
    """
    Fast image->PDF conversion using img2pdf.
    """
    pdf_path = replace_ext(image_path, ".pdf")
    with open(pdf_path, "wb") as f:
        f.write(img2pdf.convert(image_path))
    return pdf_path

def convert_via_libreoffice(input_path):
    """
    Use LibreOffice in headless mode for Office -> PDF.
    """
    out_dir = os.path.dirname(input_path)
    cmd = [
        "libreoffice",
        "--headless",
        "--convert-to", "pdf",
        "--outdir", out_dir,
        input_path
    ]
    run_subprocess(cmd, "LibreOffice conversion failed")
    
    base = os.path.splitext(os.path.basename(input_path))[0]
    pdf_path = os.path.join(out_dir, base + ".pdf")
    return pdf_path

def convert_notebook_to_pdf(input_path):
    """
    Use nbconvert for .ipynb -> PDF.
    """
    pdf_path = replace_ext(input_path, ".pdf")
    cmd = [
        "jupyter", "nbconvert",
        "--to", "pdf",
        "--output", pdf_path,
        input_path
    ]
    run_subprocess(cmd, "Notebook conversion failed")
    
    # nbconvert might produce PDF under a slightly different name
    if not os.path.exists(pdf_path):
        alt_pdf = replace_ext(input_path, ".pdf", keep_path=False)
        alt_pdf_path = os.path.join(os.path.dirname(input_path), alt_pdf)
        if os.path.exists(alt_pdf_path):
            return alt_pdf_path
        else:
            raise FileNotFoundError("nbconvert did not produce the expected PDF.")
    return pdf_path

def convert_csv_to_pdf(input_path, file_ext):
    separator = '\t' if file_ext == '.tsv' else ','
    df = pd.read_csv(input_path, sep=separator, nrows=50)
    md_text = "# CSV/TSV Preview (first 50 rows)\n\n" + df.to_markdown(index=False)
    return text_to_pdf(md_text, input_path)

def convert_datafile_to_pdf(input_path):
    """
    Handle Parquet, Feather, HDF5, pickles, etc. 
    We'll produce a partial preview if possible.
    """
    import sqlite3
    extension = os.path.splitext(input_path)[1].lower()
    try:
        if extension in ['.parquet', '.feather']:
            df = pd.read_parquet(input_path)
            return df_to_pdf(df, input_path)
        elif extension in ['.h5', '.hdf5']:
            df = pd.read_hdf(input_path)
            return df_to_pdf(df, input_path)
        elif extension in ['.pickle', '.pkl']:
            obj = pd.read_pickle(input_path)
            if isinstance(obj, pd.DataFrame):
                return df_to_pdf(obj, input_path)
            else:
                return text_to_pdf(repr(obj), input_path)
        elif extension == '.sav':
            df = pd.read_spss(input_path)
            return df_to_pdf(df, input_path)
        elif extension == '.dta':
            df = pd.read_stata(input_path)
            return df_to_pdf(df, input_path)
        elif extension == '.mat':
            import scipy.io
            mat_data = scipy.io.loadmat(input_path)
            return text_to_pdf(str(mat_data), input_path)
        elif extension in ['.db', '.sqlite']:
            conn = sqlite3.connect(input_path)
            tables = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table'", conn)
            lines = ["# SQLite Database Preview"]
            for t in tables['name']:
                lines.append(f"## Table: {t}")
                preview = pd.read_sql_query(f"SELECT * FROM '{t}' LIMIT 5", conn)
                lines.append(preview.to_markdown(index=False))
            conn.close()
            return text_to_pdf("\n\n".join(lines), input_path)
        else:
            return text_to_pdf(f"No parsing strategy for {extension}.", input_path)
    except Exception as e:
        return text_to_pdf(f"Could not parse data file: {e}", input_path)

def df_to_pdf(df, input_path):
    preview = df.head(50)
    md_table = preview.to_markdown(index=False)
    md_text = (
        "# Data File Preview\n\n"
        f"Rows: {len(df)}; Columns: {len(df.columns)}\n\n{md_table}"
    )
    return text_to_pdf(md_text, input_path)

def text_to_pdf(text, input_path):
    """
    Writes text to a .md, then Pandoc -> PDF.
    """
    md_path = replace_ext(input_path, ".md")
    pdf_path = replace_ext(input_path, ".pdf")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(text)
    cmd = [
        "pandoc", md_path,
        "-o", pdf_path,
        "--pdf-engine=xelatex",
        "--highlight-style=tango"
    ]
    run_subprocess(cmd, "Text to PDF conversion failed")
    return pdf_path

def run_subprocess(command, error_msg):
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        stderr = result.stderr.decode('utf-8', errors='replace')
        raise RuntimeError(f"{error_msg}: {stderr}")

def replace_ext(file_path, new_ext, keep_path=True):
    dir_name, base_name = os.path.split(file_path)
    base, _ = os.path.splitext(base_name)
    if keep_path:
        return os.path.join(dir_name, base + new_ext)
    else:
        return base + new_ext

if __name__ == '__main__':
    # Make sure host='0.0.0.0' so Docker can map ports
    app.run(debug=True, host='0.0.0.0')
