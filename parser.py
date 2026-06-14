import pandas as pd
import pdfplumber
from io import BytesIO
from pdf2image import convert_from_bytes
import pytesseract
from PIL import Image
import re
import spacy
import os
from app_logging import get_logger

logger = get_logger("parser")

def get_spacy_nlp(model_name='en_core_web_sm'):
    try:
        return spacy.load(model_name)
    except Exception:
        import subprocess
        subprocess.run(['python', '-m', 'spacy', 'download', model_name], check=True)
        return spacy.load(model_name)

nlp = None

def load_checklist_from_file(file_obj):
    fname = getattr(file_obj, 'name', '')
    if fname.endswith('.csv'):
        df = pd.read_csv(
            file_obj,
            engine='python',
            sep=',',
            quotechar='"',
            escapechar='\\',
        )
    elif fname.endswith('.xlsx') or fname.endswith('.xls'):
        df = pd.read_excel(file_obj)
    elif fname.endswith('.json'):
        df = pd.read_json(file_obj)
    else:
        df = pd.read_csv(
            file_obj,
            engine='python',
            sep=',',
            quotechar='"',
            escapechar='\\',
        )
    for col in ['id', 'item_text', 'category', 'weight', 'rule_type', 'rule_spec', 'confidence_threshold']:
        if col not in df.columns:
            df[col] = ''
    logger.info("Checklist loaded | file=%s | items=%s", fname or "upload", len(df))
    return df

def load_rules_from_file(file_obj):
    fname = getattr(file_obj, 'name', '')
    if fname.endswith('.csv'):
        df = pd.read_csv(file_obj)
    elif fname.endswith('.xlsx') or fname.endswith('.xls'):
        df = pd.read_excel(file_obj)
    elif fname.endswith('.json'):
        df = pd.read_json(file_obj)
    else:
        df = pd.read_csv(file_obj)
    for col in ['id', 'check_id', 'rule_type', 'rule_spec', 'confidence_threshold']:
        if col not in df.columns:
            df[col] = ''
    return df

def extract_text_from_pdf_bytes(file_bytes):
    text = ''
    try:
        with pdfplumber.open(BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text() or ''
                text += page_text + '\n'
    except Exception:
        text = ''
    if len(text.strip()) < 50:
        try:
            images = convert_from_bytes(file_bytes)
            ocr_text = ''
            for img in images:
                ocr_text += pytesseract.image_to_string(img) + '\n'
            if len(ocr_text.strip()) > len(text):
                logger.info("PDF OCR used | chars=%s", len(ocr_text.strip()))
                text = ocr_text
        except Exception as e:
            logger.warning("PDF OCR failed | error=%s", e)
    return text

def parse_supporting_file(file_obj):
    name = getattr(file_obj, 'name', 'uploaded_doc')
    content = file_obj.read()
    text = ''
    if name.lower().endswith('.pdf'):
        text = extract_text_from_pdf_bytes(content)
    else:
        try:
            text = content.decode('utf-8')
        except Exception:
            text = ''
    fields = {}
    for line in text.splitlines():
        if ':' in line and len(line.split(':', 1)[0].strip()) < 40:
            k, v = line.split(':', 1)
            fields[k.strip().lower().replace(' ', '_')] = v.strip()
    global nlp
    if nlp is None:
        try:
            nlp = get_spacy_nlp()
        except Exception:
            nlp = None
    if nlp is not None and text.strip():
        doc = nlp(text)
        names = [ent.text for ent in doc.ents if ent.label_ in ('PERSON',)]
        dates = [ent.text for ent in doc.ents if ent.label_ in ('DATE',)]
        orgs = [ent.text for ent in doc.ents if ent.label_ in ('ORG',)]
        if names:
            fields.setdefault('person_names', names)
        if dates:
            fields.setdefault('dates', dates)
        if orgs:
            fields.setdefault('orgs', orgs)
    normalized = {}
    for k, v in fields.items():
        nk = re.sub(r'[^a-z0-9_]', '', k.lower())
        normalized[nk] = v
    logger.info(
        "Document parsed | name=%s | chars=%s | fields=%s | field_keys=%s",
        name,
        len(text),
        len(normalized),
        list(normalized.keys())[:12],
    )
    return {'name': name, 'text': text, 'fields': normalized}
