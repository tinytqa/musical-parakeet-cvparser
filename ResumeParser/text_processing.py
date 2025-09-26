import re



def fix_spacing(text: str) -> str:
    # xóa nhiều khoảng trắng, tab, newline dư thừa
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def clean_ocr_artifacts(text: str) -> str:
    # loại bỏ ký tự lạ thường xuất hiện trong OCR
    text = re.sub(r'[^\w\s,.!?-]', '', text)
    return text

def fix_punctuation_spacing(text: str) -> str:
    # xóa khoảng trắng trước dấu câu
    text = re.sub(r'\s+([,.!?;:])', r'\1', text)
    # thêm khoảng trắng sau dấu câu nếu thiếu
    text = re.sub(r'([,.!?;:])([^\s])', r'\1 \2', text)
    return text

def normalize_ocr_punctuation(text: str) -> str:
    replacements = {
        '“': '"',
        '”': '"',
        '‘': "'",
        '’': "'",
        '_': '-',
        '–': '-',
        '…': '...',
        '•': '-',
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text

def process_text_ocr(text: str) -> str:
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)             
    text = clean_ocr_artifacts(text)            
    text = normalize_ocr_punctuation(text)      
    text = fix_punctuation_spacing(text)       
    #text = correct_spelling(text)       
    return text

